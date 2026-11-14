"""Núcleos de población de la Comunidad de Madrid y los que alcanza un incendio simulado.

El mapa de crisis anuncia las poblaciones a las que va a llegar el fuego. Nombres y posición: Nomenclátor
Geográfico Básico de España del IGN (servicio WFS INSPIRE de nombres geográficos), con los tipos «Capital de
municipio», «Núcleos de población» y «Entidad menor de población». Forma: las manchas urbanas del mapa base del IGN
que ya prepara la cadena (procesamiento/nucleos.py).

Una población está alcanzada cuando el fuego llega a menos de 250 m de su casco urbano: de alguna celda de su
mancha. Si varios núcleos comparten mancha, cada celda de la mancha es del núcleo más cercano. Un núcleo sin mancha
se toma como un punto. El aviso se coloca en la celda por la que llega el fuego.

Salida: datos/procesados/poblaciones.csv (nombre, tipo y posición en EPSG:25830).
Uso: python -m procesamiento.poblaciones [--forzar]
"""
import argparse
import gzip
import json
import math
import re
from functools import lru_cache

import numpy as np
import pandas as pd
import shapely
from rasterio import features

from .fuentes import BRUTOS, PROCESADOS, descargar
from .incendio.entradas import A_GEO, A_UTM, Ventana
from .nucleos import SALIDA as MANCHAS, contorno_comunidad

WFS = "https://www.ign.es/wfs-inspire/ngbe"
TIPOS = ("Capital de municipio", "Núcleos de población", "Entidad menor de población")
POR_PETICION = 5000
RECUADRO_GRADOS = 0.2
LIMITES = (39.86, -4.62, 41.18, -3.03)   # lat y lon mínimas y máximas (EPSG:4258, en ese orden)
SALIDA = PROCESADOS / "poblaciones.csv"
MISMO_NUCLEO_M = 300.0     # capital de municipio y núcleo con el mismo nombre a menos de 300 m: uno solo
EN_LA_MANCHA_M = 300.0     # un núcleo pertenece a la mancha urbana que lo contiene o está a menos de 300 m


def url(lat0: float, lon0: float, lat1: float, lon1: float) -> str:
    """Todos los lugares de un recuadro. Se filtran los tipos aquí: con filtro por tipo, el IGN no responde a tiempo."""
    return (f"{WFS}?service=WFS&version=2.0.0&request=GetFeature&typeNames=gn:NamedPlace&count={POR_PETICION}"
            f"&bbox={lat0},{lon0},{lat1},{lon1},urn:ogc:def:crs:EPSG::4258")


def recuadros() -> list[tuple[float, float, float, float]]:
    """Recuadros de RECUADRO_GRADOS que tocan la Comunidad."""
    contorno = contorno_comunidad()
    lat0, lon0, lat1, lon1 = LIMITES
    salida = []
    for i in range(math.ceil((lat1 - lat0) / RECUADRO_GRADOS)):
        for j in range(math.ceil((lon1 - lon0) / RECUADRO_GRADOS)):
            a, b = round(lat0 + i * RECUADRO_GRADOS, 3), round(lon0 + j * RECUADRO_GRADOS, 3)
            r = (a, b, round(a + RECUADRO_GRADOS, 3), round(b + RECUADRO_GRADOS, 3))
            if contorno.intersects(shapely.box(r[1], r[0], r[3], r[2])):
                salida.append(r)
    return salida


def descargar_recuadro(r) -> str:
    """Texto de la respuesta de un recuadro; si viene llena, se parte en cuatro."""
    nombre = "_".join(f"{c:.3f}" for c in r)
    ruta = descargar(url(*r), BRUTOS / "ign_ngbe" / f"{nombre}.xml.gz",
                     "IGN, Nomenclátor Geográfico Básico de España (WFS INSPIRE), lugares del recuadro", cabeceras={"Accept-Encoding": "gzip"})
    datos = ruta.read_bytes()
    texto = (gzip.decompress(datos) if datos[:2] == bytes([0x1F, 0x8B]) else datos).decode("utf-8")
    cabecera = dict(re.findall(r'(numberMatched|numberReturned)="(\d+)"', texto[:3000]))
    if not cabecera:
        raise RuntimeError(f"Respuesta inesperada del IGN en {nombre}: {texto[:300]}")
    if cabecera["numberMatched"] == cabecera["numberReturned"]:
        return texto
    a, b, c, d = r
    ma, mb = round((a + c) / 2, 4), round((b + d) / 2, 4)
    return "".join(descargar_recuadro(q) for q in ((a, b, ma, mb), (a, mb, ma, d), (ma, b, c, mb), (ma, mb, c, d)))


def leer(texto: str) -> pd.DataFrame:
    """Nombre, tipo y posición (lon, lat) de cada lugar de la respuesta del WFS."""
    filas = []
    for m in texto.split("<wfs:member>")[1:]:
        tipo = re.search(r"<gn:localType>.*?>([^<]+)</gmd:LocalisedCharacterString>", m, re.S)
        nombre = re.search(r"<gn:text>([^<]+)</gn:text>", m)
        pos = re.search(r"<gml:pos>([-\d.]+) ([-\d.]+)</gml:pos>", m)
        if tipo and nombre and pos:
            filas.append({"nombre": nombre.group(1).strip(), "tipo": tipo.group(1).strip(),
                          "lat": float(pos.group(1)), "lon": float(pos.group(2))})
    return pd.DataFrame(filas, columns=["nombre", "tipo", "lat", "lon"])


def construir(forzar: bool = False):
    if SALIDA.exists() and not forzar:
        return SALIDA
    lista = recuadros()
    partes = []
    for i, r in enumerate(lista):
        partes.append(leer(descargar_recuadro(r)))
        if (i + 1) % 10 == 0:
            print(f"  recuadros del nomenclátor: {i + 1}/{len(lista)}", flush=True)
    d = pd.concat(partes, ignore_index=True)
    d = d[d.tipo.isin(TIPOS)].drop_duplicates()
    d = d[shapely.contains_xy(contorno_comunidad(), d.lon.values, d.lat.values)].copy()
    d["x"], d["y"] = A_UTM.transform(d.lon.values, d.lat.values)
    # La capital de un municipio suele estar también como núcleo: se queda una entrada por nombre y lugar
    d["orden"] = d.tipo.map({"Capital de municipio": 0}).fillna(1)
    quedan = []
    for _, g in d.sort_values("orden").groupby("nombre", sort=False):
        elegidos = []
        for r in g.itertuples():
            if all(np.hypot(r.x - e.x, r.y - e.y) > MISMO_NUCLEO_M for e in elegidos):
                elegidos.append(r)
        quedan += elegidos
    salida = pd.DataFrame([{"nombre": r.nombre, "tipo": r.tipo, "x": round(r.x, 1), "y": round(r.y, 1)} for r in quedan])
    salida.sort_values(["nombre", "x"]).to_csv(SALIDA, index=False, encoding="utf-8")
    print(f"  {len(salida)} núcleos de población ({len(d)} lugares del nomenclátor)")
    return SALIDA


@lru_cache(maxsize=1)
def cargar() -> pd.DataFrame:
    return pd.read_csv(SALIDA, encoding="utf-8")


@lru_cache(maxsize=1)
def _manchas_utm() -> list:
    rasgos = json.loads(MANCHAS.read_text(encoding="utf-8"))["features"]
    return [shapely.transform(shapely.geometry.shape(r["geometry"]), lambda xy: np.column_stack(A_UTM.transform(xy[:, 0], xy[:, 1])))
            for r in rasgos]


def alcanzadas(llegada_250: np.ndarray, v: Ventana, manchas=None, nucleos: pd.DataFrame | None = None) -> list[dict]:
    """Poblaciones a las que llega el fuego (a menos de 250 m de su casco), con el minuto y el punto de llegada.

    llegada_250: para cada celda, el minuto en que el fuego llega a menos de 250 m (consecuencias.llegada_en_radio).
    """
    if nucleos is None:
        if not SALIDA.exists() or not MANCHAS.exists():
            return []
        nucleos = cargar()
    n = nucleos[v.contiene(nucleos.x.values, nucleos.y.values)].reset_index(drop=True)
    if n.empty:
        return []
    caja = shapely.box(*v.limites)
    manchas = [m for m in (_manchas_utm() if manchas is None else manchas) if m.intersects(caja)]
    # Índice de mancha por celda (0 = fuera de toda mancha) y mancha de cada núcleo (0 = ninguna)
    indice = features.rasterize([(m, i + 1) for i, m in enumerate(manchas)], out_shape=(v.filas, v.columnas),
                                transform=v.transform, fill=0, dtype="int32") if manchas else np.zeros((v.filas, v.columnas), "int32")
    puntos = shapely.points(n.x.values, n.y.values)
    de_mancha = np.zeros(len(n), dtype=int)
    if manchas:
        arbol = shapely.STRtree(manchas)
        cerca, distancia = arbol.query_nearest(puntos, max_distance=EN_LA_MANCHA_M, return_distance=True)
        for p, m in zip(*cerca):
            if not de_mancha[p]:
                de_mancha[p] = m + 1
    fila_n = ((v.y0 - n.y.values) // v.celda).astype(int)
    col_n = ((n.x.values - v.x0) // v.celda).astype(int)
    salida = []
    for k in range(len(n)):
        m = de_mancha[k]
        if m:
            filas, cols = np.nonzero(indice == m)
            # Celdas de la mancha más cercanas a este núcleo que a los demás núcleos de la misma mancha
            otros = np.nonzero(de_mancha == m)[0]
            if len(otros) > 1:
                cx, cy = v.x0 + (cols + 0.5) * v.celda, v.y0 - (filas + 0.5) * v.celda
                d2 = (cx[:, None] - n.x.values[otros][None, :]) ** 2 + (cy[:, None] - n.y.values[otros][None, :]) ** 2
                mias = otros[np.argmin(d2, axis=1)] == k
                filas, cols = filas[mias], cols[mias]
            if not len(filas):
                filas, cols = fila_n[k:k + 1], col_n[k:k + 1]
        else:
            filas, cols = fila_n[k:k + 1], col_n[k:k + 1]
        t = llegada_250[filas, cols]
        if not np.isfinite(t).any():
            continue
        i = int(np.argmin(t))
        lon, lat = A_GEO.transform(v.x0 + (cols[i] + 0.5) * v.celda, v.y0 - (filas[i] + 0.5) * v.celda)
        salida.append({"nombre": n.nombre[k], "tipo": n.tipo[k], "minutos": round(float(t[i]), 1),
                       "lon": round(lon, 5), "lat": round(lat, 5)})
    return sorted(salida, key=lambda p: p["minutos"])


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--forzar", action="store_true", help="volver a leer el nomenclátor descargado")
    construir(p.parse_args().forzar)
