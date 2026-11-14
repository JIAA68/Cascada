"""Red de carreteras, pistas y vías de tren de la Comunidad de Madrid (decisión del 11-11-2026).

Fuente: Base Topográfica Armonizada 2017 (1:10.000) del geoportal IDEM de la Comunidad, servicio WFS
geoidem/BTA/wfs, en EPSG:25830:
- Red viaria (IDEM_BTA_REDVIARIA_LIN_17): carreteras de calzada doble y de calzada única, con su código
  (A-6, M-607…), y pistas. Las vías urbanas, caminos y sendas no entran.
- Red ferroviaria (IDEM_BTA_REDFERRO_LIN_17): ferrocarril, metro y tranvía en uso, en superficie o elevados.
  Los tramos soterrados no entran: el fuego no los alcanza.

El WFS no ofrece descarga en bloque: se piden páginas de 5.000 tramos ordenadas por su identificador,
comprimidas, y cada página queda en datos/brutos/bta_transporte/ con su registro. El resultado,
datos/procesados/red_transporte.npz, guarda para cada trozo de unos 200 m su tipo, su geometría para dibujarla y
puntos cada 25 m para cruzarla con el mapa de tiempos de llegada de una simulación; los códigos y
nombres van en red_transporte.csv.

Uso: python -m procesamiento.red_transporte   (unos minutos la primera vez)
"""
import gzip
import json
import math
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

import numpy as np
import pandas as pd
import shapely

from .fuentes import BRUTOS, PROCESADOS, descargar

WFS = "https://idem.comunidad.madrid/geoidem/BTA/wfs?service=WFS&version=2.0.0&request=GetFeature"
POR_PAGINA = 5000
CARPETA = BRUTOS / "bta_transporte"
SALIDA = PROCESADOS / "red_transporte.npz"
NOMBRES = PROCESADOS / "red_transporte.csv"
PASO_M = 25.0   # puntos de muestreo a lo largo de cada tramo (la mitad de la celda del modelo de incendio)
SIMPLIFICAR_M = 5.0   # tolerancia de la geometría que se dibuja
TROZO_M = 200.0       # largo de cada trozo de vía (el último de un tramo, hasta el doble): lo que se pinta de una vez

# tipo de Cascada: (capa del WFS, valores de id_fenomeno, campo identificador)
CAPAS = {
    "viaria": ("BTA:IDEM_BTA_REDVIARIA_LIN_17", ("Carretera de calzada doble", "Carretera de calzada única", "Pista"),
               "id_redviaria_lin", "id_fenomeno,situacion_des,codigoc,nombre,geom"),
    "ferroviaria": ("BTA:IDEM_BTA_REDFERRO_LIN_17", ("Ferrocarril", "Metro", "Tranvía"),
                    "id_redferro_lin", "id_fenomeno,situacion_des,estado_des,geom"),
}
TIPOS = ["carretera", "pista", "ferrocarril", "metro", "tranvia"]
TIPO_DE = {"Carretera de calzada doble": "carretera", "Carretera de calzada única": "carretera", "Pista": "pista",
           "Ferrocarril": "ferrocarril", "Metro": "metro", "Tranvía": "tranvia"}
NOTA = "Comunidad de Madrid (IDEM), Base Topográfica Armonizada 2017, WFS"


def _filtro(valores) -> str:
    return "id_fenomeno IN (" + ",".join("'" + v + "'" for v in valores) + ")"


def total(capa: str) -> int:
    nombre, valores, _, _ = CAPAS[capa]
    url = f"{WFS}&typeNames={nombre}&resultType=hits&cql_filter={urllib.parse.quote(_filtro(valores))}"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Cascada/1.0"}), timeout=120) as r:
        return int(r.read().decode("utf-8", "replace").split('numberMatched="')[1].split('"')[0])


def url_pagina(capa: str, inicio: int) -> str:
    nombre, valores, orden, campos = CAPAS[capa]
    return (f"{WFS}&typeNames={nombre}&propertyName={campos}&cql_filter={urllib.parse.quote(_filtro(valores))}"
            f"&sortBy={orden}&startIndex={inicio}&count={POR_PAGINA}&outputFormat=application/json")


def descargar_paginas(hilos: int = 3) -> list:
    """Descarga (si faltan) las páginas comprimidas de las dos capas y devuelve sus rutas en orden."""
    trabajos = []
    for capa in CAPAS:
        n = total(capa)
        trabajos += [(capa, inicio, n) for inicio in range(0, n, POR_PAGINA)]

    def una(trabajo):
        capa, inicio, n = trabajo
        destino = CARPETA / f"{capa}_{inicio // POR_PAGINA:03d}.json.gz"
        if destino.exists():
            return destino
        ruta = descargar(url_pagina(capa, inicio), destino, f"{NOTA} {CAPAS[capa][0]}, tramos {inicio} a {min(inicio + POR_PAGINA, n) - 1}",
                         cabeceras={"Accept-Encoding": "gzip"})
        print(f"  {capa}: página {inicio // POR_PAGINA + 1} de {math.ceil(n / POR_PAGINA)}", flush=True)
        return ruta

    with ThreadPoolExecutor(hilos) as ex:
        return list(ex.map(una, trabajos))


def leer_pagina(ruta) -> list[dict]:
    """Tramos de una página: tipo, código, nombre y geometría; sin los soterrados ni los que no están en uso."""
    datos = ruta.read_bytes()
    if datos[:2] == b"\x1f\x8b":
        datos = gzip.decompress(datos)
    d = json.loads(datos)
    if d.get("type") != "FeatureCollection":
        raise RuntimeError(f"Respuesta inesperada del WFS en {ruta.name}")
    tramos = []
    for f in d["features"]:
        p, g = f["properties"], f["geometry"]
        if not g or p.get("situacion_des") == "soterrado o subterráneo" or p.get("estado_des") not in (None, "en uso"):
            continue
        partes = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"] if g["type"] == "MultiLineString" else []
        # la BTA rellena con 9000 o 9500 cuando no hay nombre ni código
        nombre, codigo = ("" if re.fullmatch(r"\d*", v) else v for v in ((p.get("nombre") or "").strip(), (p.get("codigoc") or "").strip()))
        for c in partes:
            if len(c) >= 2:
                tramos.append({"tipo": TIPO_DE[p["id_fenomeno"]], "codigo": codigo,
                               "nombre": nombre, "coords": np.asarray(c, dtype=float)[:, :2]})
    return tramos


def trocear(tramos: list[dict], largo_m: float = TROZO_M, paso_m: float = PASO_M) -> list[dict]:
    """Corta cada tramo en trozos de unos largo_m (el último, hasta el doble), con un punto cada paso_m como máximo.

    La BTA tiene tramos de varios kilómetros: sin cortarlos, el fuego a 250 m de un extremo pintaría la carretera
    entera. Los trozos consecutivos comparten el punto de corte, para que la línea dibujada no tenga huecos.
    """
    salida = []
    for t in tramos:
        c = shapely.get_coordinates(shapely.segmentize(shapely.linestrings(t["coords"]), paso_m))
        acumulado = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(c, axis=0).T))])
        trozo = np.minimum((acumulado // largo_m).astype(int), max(int(acumulado[-1] // largo_m) - 1, 0))
        for k in np.unique(trozo):
            i = np.nonzero(trozo == k)[0]
            fin = min(i[-1] + 1, len(c) - 1)             # el primer punto del trozo siguiente cierra este
            salida.append({**t, "coords": c[i[0]:fin + 1]})
    return salida


def construir(forzar: bool = False):
    """Descarga la red y escribe el fichero de tramos con sus puntos de muestreo. Devuelve su ruta."""
    if SALIDA.exists() and NOMBRES.exists() and not forzar:
        return SALIDA
    tramos = trocear([t for ruta in descargar_paginas() for t in leer_pagina(ruta)])
    lineas = shapely.linestrings(np.concatenate([t["coords"] for t in tramos]),
                                 indices=np.repeat(np.arange(len(tramos)), [len(t["coords"]) for t in tramos]))
    simplificadas = shapely.simplify(lineas, SIMPLIFICAR_M)   # para dibujar basta con 5 m
    dibujo = shapely.get_coordinates(simplificadas)
    partes_dibujo = shapely.get_num_coordinates(simplificadas)
    np.savez_compressed(
        SALIDA, tipo=np.array([TIPOS.index(t["tipo"]) for t in tramos], dtype=np.uint8),
        largo=shapely.length(lineas).astype(np.float32),
        dibujo=dibujo, inicio_dibujo=np.concatenate([[0], np.cumsum(partes_dibujo)]).astype(np.int64),
        puntos=np.concatenate([t["coords"] for t in tramos]),
        tramo_punto=np.repeat(np.arange(len(tramos), dtype=np.int32), [len(t["coords"]) for t in tramos]))
    pd.DataFrame({"codigo": [t["codigo"] for t in tramos], "nombre": [t["nombre"] for t in tramos]}).to_csv(
        NOMBRES, index=False, encoding="utf-8")
    return SALIDA


@lru_cache(maxsize=1)
def cargar() -> dict:
    """La red preparada: arrays del npz y códigos y nombres de cada tramo."""
    with np.load(SALIDA) as z:
        red = {k: z[k] for k in z.files}
    nombres = pd.read_csv(NOMBRES, dtype=str, keep_default_na=False)
    red["codigo"], red["nombre"] = nombres.codigo.to_numpy(), nombres.nombre.to_numpy()
    return red


if __name__ == "__main__":
    ruta = construir()
    red = cargar()
    print(f"{ruta.name}: {len(red['tipo'])} tramos, {len(red['puntos'])} puntos de muestreo; "
          + ", ".join(f"{t} {int((red['tipo'] == i).sum())}" for i, t in enumerate(TIPOS)))
