"""Mapa de combustibles forestales de la Comunidad de Madrid, rasterizado a 25 m.

Fuente: geoportal IDEM de la Comunidad, «Mapa de Modelos de Combustibles» (servicio WFS
ZonasRiesgo:BOPC_MODELOS_COMBUSTIBLES): 433.681 polígonos en EPSG:25830 elaborados a partir de LiDAR,
con el modelo NFFL en el campo NM_BEHAVE (0 sin combustible, 1 a 9). Sustituye dentro de la Comunidad
al mapa europeo de EFFIS (250 m, vegetación de hacia el año 2000), que trata los pastos y cultivos
como «sin combustible»; fuera de la Comunidad se sigue usando EFFIS.

El WFS no ofrece descarga en bloque: se piden páginas de 5.000 polígonos ordenadas por su
identificador, comprimidas (gzip), y cada página queda en datos/brutos/combustibles_cm/ con su
registro. Después se rasterizan en una rejilla de 25 m que cubre la Comunidad (un píxel toma el
modelo del polígono que contiene su centro) y el resultado queda en
datos/procesados/combustible_cm_25m.tif, con 255 donde no hay dato (fuera de la Comunidad).

Uso: python -m procesamiento.incendio.combustible_cm   (unos 25 minutos la primera vez)
"""
import gzip
import json
import math
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import rasterio
import shapely
from rasterio.features import rasterize
from rasterio.transform import from_origin

from ..fuentes import BRUTOS, PROCESADOS, descargar

WFS = "https://idem.comunidad.madrid/geoidem/ZonasRiesgo/wfs?service=WFS&version=2.0.0&request=GetFeature" \
      "&typeNames=ZonasRiesgo:BOPC_MODELOS_COMBUSTIBLES"
POR_PAGINA = 5000
CARPETA = BRUTOS / "combustibles_cm"
RASTER = PROCESADOS / "combustible_cm_25m.tif"
CELDA = 25.0
# Extensión de la Comunidad en EPSG:25830 (límites municipales de 2020), con margen y alineada a 25 m
X0, Y0, X1, Y1 = 365000.0, 4415000.0, 496000.0, 4558000.0
SIN_DATO = 255
NOTA = "Comunidad de Madrid (IDEM), mapa de modelos de combustibles, WFS BOPC_MODELOS_COMBUSTIBLES"


def total() -> int:
    """Número de polígonos del mapa, según el propio servicio."""
    with urllib.request.urlopen(WFS + "&resultType=hits", timeout=120) as r:
        texto = r.read().decode("utf-8", "replace")
    return int(texto.split('numberMatched="')[1].split('"')[0])


def url_pagina(inicio: int) -> str:
    return (f"{WFS}&propertyName=NM_BEHAVE,GEOMETRY1&sortBy=CDID&startIndex={inicio}&count={POR_PAGINA}"
            "&outputFormat=application/json")


def descargar_paginas(hilos: int = 3) -> list:
    """Descarga (si faltan) todas las páginas comprimidas del WFS y devuelve sus rutas en orden."""
    n = total()
    inicios = range(0, n, POR_PAGINA)

    def una(inicio):
        destino = CARPETA / f"pagina_{inicio // POR_PAGINA:03d}.json.gz"
        if destino.exists():
            return destino
        ruta = descargar(url_pagina(inicio), destino, f"{NOTA}, polígonos {inicio} a {min(inicio + POR_PAGINA, n) - 1}",
                         cabeceras={"Accept-Encoding": "gzip"})
        print(f"  página {inicio // POR_PAGINA + 1} de {math.ceil(n / POR_PAGINA)}", flush=True)
        return ruta

    with ThreadPoolExecutor(hilos) as ex:
        return list(ex.map(una, inicios))


def leer_pagina(ruta) -> list[tuple[shapely.Geometry, int]]:
    """Polígonos y modelo NFFL de una página (comprimida o no)."""
    datos = ruta.read_bytes()
    if datos[:2] == b"\x1f\x8b":
        datos = gzip.decompress(datos)
    d = json.loads(datos)
    if d.get("type") != "FeatureCollection":
        raise RuntimeError(f"Respuesta inesperada del WFS en {ruta.name}")
    return [(shapely.geometry.shape(f["geometry"]), int(f["properties"].get("NM_BEHAVE") or 0))
            for f in d["features"] if f.get("geometry")]


def rasterizar(paginas, extension=(X0, Y0, X1, Y1), celda: float = CELDA):
    """Modelo NFFL por píxel (SIN_DATO donde no hay polígono) y su transformación."""
    x0, y0, x1, y1 = extension
    transform = from_origin(x0, y1, celda, celda)
    modelo = np.full((int(round((y1 - y0) / celda)), int(round((x1 - x0) / celda))), SIN_DATO, dtype=np.uint8)
    for i, ruta in enumerate(paginas, 1):
        poligonos = leer_pagina(ruta)
        if poligonos:
            rasterize(poligonos, out=modelo, transform=transform)
        if i % 10 == 0:
            print(f"  rasterizadas {i} de {len(paginas)} páginas", flush=True)
    return modelo, transform


def construir(forzar: bool = False):
    """Descarga el mapa y escribe el ráster de 25 m. Devuelve su ruta."""
    if RASTER.exists() and not forzar:
        return RASTER
    modelo, transform = rasterizar(descargar_paginas())
    filas, columnas = modelo.shape
    RASTER.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(RASTER, "w", driver="GTiff", height=filas, width=columnas, count=1, dtype="uint8",
                       crs="EPSG:25830", transform=transform, nodata=SIN_DATO, compress="deflate", tiled=True) as dst:
        dst.write(modelo, 1)
    return RASTER


def main():
    ruta = construir()
    with rasterio.open(ruta) as src:
        m = src.read(1)
    valores, cuentas = np.unique(m[m != SIN_DATO], return_counts=True)
    print(f"{ruta.name}: {m.shape[1]} × {m.shape[0]} píxeles de 25 m")
    for v, c in zip(valores, cuentas):
        print(f"  modelo {v}: {c * CELDA * CELDA / 1e6:,.0f} km²")


if __name__ == "__main__":
    main()
