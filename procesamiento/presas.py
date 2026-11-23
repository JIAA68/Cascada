"""Presas de la Comunidad de Madrid deducidas de la capa de rotura de presas del catálogo (2_3).

No hay una fuente abierta con la zona de inundación de cada presa: la capa del catálogo da, en una sola rejilla de
5 m, el nivel 2 (lo que inunda la onda en los primeros 30 minutos tras la rotura) y el nivel 1 (el resto de la llanura
de inundación), sin decir de qué presa es cada zona. Como con las instalaciones Seveso, se deduce del propio catálogo:

- La capa se lleva a una rejilla de 50 m de toda la Comunidad (nivel máximo de cada celda), con la altitud media del
  MDT de 25 m del IGN.
- Cada zona de nivel 2 de al menos 0,2 km² es una presa. Se sitúa, de las celdas más altas de la zona, en aquella
  desde la que el agua llega, bajando, a más parte de la zona (la más alta a secas puede ser una ladera).
- Su longitud de 30 minutos es la mayor distancia que recorre el agua, solo aguas abajo, desde la presa por su zona
  de nivel 2 (procesamiento/presa/modelo.py).
- El nombre es el de la presa del Nomenclátor Geográfico Básico del IGN más cercana (a menos de 1,5 km) o, si no hay,
  el del embalse más cercano (a menos de 4 km); si tampoco, el del municipio, numerado si se repite.

Salida: datos/procesados/presas.csv (identificador, nombre, posición, longitud de 30 minutos) y
datos/procesados/presas_rejilla.npz (nivel de la capa y altitud en la rejilla de 50 m, con su origen).

Uso: python -m procesamiento.presas
"""
import gzip
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from rasterio.warp import Resampling
from scipy import ndimage

from .capas import tif
from .fuentes import BRUTOS, PROCESADOS

SALIDA = PROCESADOS / "presas.csv"
REJILLA = PROCESADOS / "presas_rejilla.npz"
CELDA_M = 50.0
AREA_MIN_KM2 = 0.2
NOMBRE_MAX_M = 4000
PRESA_MAX_M = 1500    # una «Presa de…» del Nomenclátor así de cerca gana al embalse
CANDIDATAS = 40      # celdas más altas de cada zona entre las que se busca la presa


def construir_rejilla():
    """Nivel (máximo) de la capa 2_3 y altitud (media) del MDT en una rejilla de 50 m que cubre la capa."""
    from .sin_conexion import preparar_mdt
    with rasterio.open(tif("2_3")) as src:
        b = src.bounds
        x0, y0 = np.floor(b.left / CELDA_M) * CELDA_M, np.ceil(b.top / CELDA_M) * CELDA_M
        columnas = int(np.ceil((b.right - x0) / CELDA_M)); filas = int(np.ceil((y0 - b.bottom) / CELDA_M))
        transform = from_origin(x0, y0, CELDA_M, CELDA_M)
        with WarpedVRT(src, crs=src.crs, transform=transform, width=columnas, height=filas,
                       resampling=Resampling.max, src_nodata=255, nodata=255) as vrt:
            nivel = vrt.read(1)
    nivel[nivel == 255] = 0
    with rasterio.open(preparar_mdt()) as mdt, \
            WarpedVRT(mdt, crs=mdt.crs, transform=transform, width=columnas, height=filas,
                      resampling=Resampling.average, nodata=-32768) as vrt:
        altitud = vrt.read(1).astype("float32")
    altitud[altitud <= -32768] = np.nan
    return nivel, altitud, (float(x0), float(y0))


def nombres_ign() -> pd.DataFrame:
    """Embalses y presas del Nomenclátor del IGN descargado por recuadros (procesamiento/poblaciones.py)."""
    from .poblaciones import leer
    from .incendio.entradas import A_UTM
    partes = []
    for f in sorted((BRUTOS / "ign_ngbe").glob("*.xml.gz")):
        datos = f.read_bytes()
        partes.append(leer((gzip.decompress(datos) if datos[:2] == b"\x1f\x8b" else datos).decode("utf-8")))
    if not partes:
        return pd.DataFrame(columns=["nombre", "x", "y"])
    d = pd.concat(partes, ignore_index=True).drop_duplicates()
    d = d[(d.tipo == "Embalse") | d.nombre.str.startswith("Presa")].copy()
    d["x"], d["y"] = A_UTM.transform(d.lon.values, d.lat.values)
    return d


def construir(forzar: bool = False) -> Path:
    if SALIDA.exists() and REJILLA.exists() and not forzar:
        return SALIDA
    from .incendio.entradas import A_GEO, municipio_de
    from .presa.modelo import distancias_aguas_abajo, longitud_30_min
    nivel, altitud, (x0, y0) = construir_rejilla()
    etiquetas, n = ndimage.label(nivel == 2, structure=np.ones((3, 3)))
    area = ndimage.sum(np.ones_like(etiquetas), etiquetas, range(1, n + 1)) * CELDA_M ** 2 / 1e6
    lugares = nombres_ign()
    filas = []
    for k in np.argsort(-area):
        if area[k] < AREA_MIN_KM2:
            break
        zona = etiquetas == k + 1
        ff, cc = np.nonzero(zona)
        alt = np.where(np.isfinite(altitud[ff, cc]), altitud[ff, cc], -np.inf)
        # La presa: de las celdas más altas de la zona, aquella desde la que el agua llega, bajando, a más parte de la
        # zona (la más alta a secas puede ser una ladera por encima de la presa)
        mejor = None
        for i in np.argsort(-alt)[:CANDIDATAS]:
            d = distancias_aguas_abajo(zona, altitud, (int(ff[i]), int(cc[i])), CELDA_M)
            alcance = int(np.isfinite(d).sum())
            if mejor is None or alcance > mejor[0]:
                mejor = (alcance, int(ff[i]), int(cc[i]))
        f, c = mejor[1], mejor[2]
        x, y = x0 + (c + 0.5) * CELDA_M, y0 - (f + 0.5) * CELDA_M
        d30 = longitud_30_min(zona, altitud, (f, c), CELDA_M)
        nombre = None
        if len(lugares):
            dist = np.hypot(lugares.x.values - x, lugares.y.values - y)
            presa = lugares.nombre.str.startswith("Presa").values & (dist <= PRESA_MAX_M)
            j = int(np.argmin(np.where(presa, dist, np.inf))) if presa.any() else int(np.argmin(dist))
            if dist[j] <= NOMBRE_MAX_M:
                nombre = lugares.nombre.values[j]
        try:
            municipio = municipio_de(x, y)[1]
        except ValueError:
            municipio = ""
        lon, lat = A_GEO.transform(x, y)
        filas.append({"nombre": nombre or f"Presa de {municipio}", "municipio": municipio, "x": round(x), "y": round(y),
                      "lon": round(lon, 5), "lat": round(lat, 5), "fila": f, "columna": c,
                      "area_30_min_km2": round(float(area[k]), 2), "longitud_30_min_m": round(d30)})
    presas = pd.DataFrame(filas).sort_values(["nombre", "area_30_min_km2"], ascending=[True, False]).reset_index(drop=True)
    # Nombres repetidos (dos presas sin nombre propio en el mismo municipio): se numeran
    orden = presas.groupby("nombre").cumcount()
    presas.loc[orden > 0, "nombre"] = presas.nombre[orden > 0] + " (" + (orden[orden > 0] + 1).astype(str) + ")"
    presas.insert(0, "id", [f"PRE-{i + 1:02d}" for i in range(len(presas))])
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    presas.to_csv(SALIDA, index=False)
    np.savez_compressed(REJILLA, nivel=nivel, altitud=altitud, origen=np.array([x0, y0]), celda=np.array(CELDA_M))
    print(f"  {SALIDA.name}: {len(presas)} presas")
    return SALIDA


def cargar() -> pd.DataFrame:
    if not SALIDA.exists():
        construir()
    return pd.read_csv(SALIDA)


if __name__ == "__main__":
    construir(forzar=True)
