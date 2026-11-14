"""Teselas PMTiles de las capas de peligrosidad para el visor.

Cada capa se reproyecta a Web Mercator tesela a tesela. Cómo se agregan los píxeles de
origen que caen en cada píxel de la tesela depende del tipo de capa:

- Capas de superficie (incendios, subsidencias, avión): el nivel más frecuente.
  Con el máximo, al alejarse casi toda la Comunidad aparecía en el nivel más alto.
- Resto de capas (lineales, derrumbes, que va por edificio, y elementos pequeños): el
  nivel máximo, para que vías, carreteras, conducciones, edificios e instalaciones no
  desaparezcan al alejarse.

Las capas lineales se engrosan a 3 píxeles en todos los zooms. Las de elementos pequeños
(sobrepresión, centrales, actividades extractivas) se engrosan más cuanto más lejos, para
que sigan viéndose a escala de la Comunidad. Cada zona lleva un borde más oscuro de su
color, salvo en las capas lineales y en las muy fragmentadas (incendios, derrumbes), donde
el borde se convierte en un punteado oscuro. Cada capa va a un fichero
datos/visor/capas/peligrosid_<código>.pmtiles.

Para los zooms bajos se usa una pirámide reducida en memoria (máximo o nivel más frecuente
por bloque), de modo que GDAL no tenga que leer la capa completa de 5 m para cada tesela.

Las capas llegan al zoom 15 (3,6 m por píxel en Madrid: la resolución de los 5 m del catálogo; decisión del
08-11-2026). A esos zooms la mayoría de las teselas están vacías en las capas de ríos, vías o instalaciones: una
máscara de ocupación por bloques de 32 × 32 píxeles permite saltarlas sin reproyectar. Las 13 capas
meteorológicas de la prealerta se teselan igual (nivel más frecuente), pero solo hasta el zoom 11, porque son
zonas suaves.

Uso: python -m procesamiento.teselas [--zoom-max 15] [--capas 3_1 6_15 ...]
"""
import argparse
import warnings
from pathlib import Path

import numpy as np
import rasterio
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer
from pyproj import Transformer
from rasterio.errors import NotGeoreferencedWarning
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
from rasterio.vrt import WarpedVRT
from rasterio.warp import Resampling, transform_bounds
from scipy.ndimage import maximum_filter, minimum_filter

from .capas import (CAPAS, CAPAS_METEO, COMBINADAS, CON_FONDO, LINEALES, PEQUENAS, SIN_BORDE, SIN_DATO, SUPERFICIE,
                    nombre_capa, tif)
from .fuentes import VISOR

LADO = 256
MUNDO = 20037508.342789244
ZOOM_MIN = 7
# Paleta cálida por nivel (RGBA), con los niveles bajos saturados para que las capas que no
# pasan de nivel 2 o 3 se lean sobre el mapa base; el nivel 1 de fondo, casi transparente
PALETA = {1: (250, 210, 60, 205), 2: (245, 160, 20, 215), 3: (235, 105, 15, 220),
          4: (210, 40, 25, 220), 5: (125, 0, 30, 230)}
# Borde de cada zona: el mismo color oscurecido y opaco
BORDE = {n: (int(r * 0.6), int(g * 0.6), int(b * 0.6), 255) for n, (r, g, b, _) in PALETA.items()}
FONDO = (255, 241, 168, 35)
FACTORES = (2, 4, 8, 16, 32)


def limites(z, x, y):
    paso = 2 * MUNDO / 2 ** z
    return (-MUNDO + x * paso, MUNDO - (y + 1) * paso, -MUNDO + (x + 1) * paso, MUNDO - y * paso)


def teselas_que_cubren(limites_3857, z):
    paso = 2 * MUNDO / 2 ** z
    xmin, ymin, xmax, ymax = limites_3857
    for x in range(int((xmin + MUNDO) // paso), int((xmax + MUNDO) // paso) + 1):
        for y in range(int((MUNDO - ymax) // paso), int((MUNDO - ymin) // paso) + 1):
            yield x, y


def niveles_tesela(fuente, z, x, y, src_nodata, moda=False) -> np.ndarray:
    """Niveles 0 a 5 de una tesela, con el máximo (o el nivel más frecuente) de los píxeles de origen.

    El "sin dato" de destino es 255: con 0, GDAL convertiría los ceros válidos en 1.
    """
    with WarpedVRT(fuente, crs="EPSG:3857", resampling=Resampling.mode if moda else Resampling.max, src_nodata=src_nodata, nodata=SIN_DATO,
                   transform=from_bounds(*limites(z, x, y), LADO, LADO), width=LADO, height=LADO) as vrt:
        niveles = vrt.read(1)
    niveles[niveles == SIN_DATO] = 0
    return niveles


def engrosado(codigo: str, z: int) -> int:
    """Lado (píxeles) del engrosado de una capa en un zoom; 1 = sin engrosar."""
    if codigo in LINEALES:
        return 3
    if codigo in PEQUENAS:
        return 7 if z <= 9 else 5 if z <= 11 else 3 if z == 12 else 1
    return 1


def colorear(niveles: np.ndarray, con_fondo: bool, engrosar: int = 1, bordes: bool = True) -> np.ndarray:
    if engrosar > 1:
        niveles = maximum_filter(niveles, size=engrosar)
    rgba = np.zeros(niveles.shape + (4,), np.uint8)
    for n, color in PALETA.items():
        rgba[niveles == n] = FONDO if (con_fondo and n == 1) else color
    if bordes:
        # Píxeles de una zona que tocan otra de nivel menor; el fondo de incendios y avión no lleva borde
        borde = (niveles > minimum_filter(niveles, size=3, mode="nearest")) & ~(con_fondo & (niveles == 1))
        for n, color in BORDE.items():
            rgba[borde & (niveles == n)] = color
    return rgba


def png(rgba: np.ndarray) -> bytes:
    with MemoryFile() as mem, warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)  # un PNG no lleva georreferencia
        with mem.open(driver="PNG", width=LADO, height=LADO, count=4, dtype="uint8") as d:
            d.write(np.moveaxis(rgba, -1, 0))
        return mem.read()


def moda_2x2(a: np.ndarray) -> np.ndarray:
    """Nivel más frecuente de cada bloque de 2 × 2; en caso de empate, el mayor."""
    h, w = (a.shape[0] // 2) * 2, (a.shape[1] // 2) * 2
    b = a[:h, :w].reshape(h // 2, 2, w // 2, 2)
    mejor = np.zeros((h // 2, w // 2), np.uint8)
    cuenta = np.zeros((h // 2, w // 2), np.uint8)
    for n in range(6):
        c = (b == n).sum(axis=(1, 3), dtype=np.uint8)
        gana = c >= cuenta
        mejor[gana], cuenta[gana] = n, c[gana]
    return mejor


def piramide(src, moda=False):
    """Versiones reducidas de la capa (máximo o nivel más frecuente por bloque), por factor, en memoria,
    y la máscara de ocupación (bloques de 32 × 32 píxeles con algún dato) para saltar las teselas vacías.

    El nivel más frecuente se calcula por etapas de 2 × 2 sobre la versión anterior.
    """
    datos = src.read(1)
    datos[datos == SIN_DATO] = 0
    k = FACTORES[-1]
    h, w = (datos.shape[0] // k) * k, (datos.shape[1] // k) * k
    ocupada = datos[:h, :w].reshape(h // k, k, w // k, k).max(axis=(1, 3)) > 0
    salida = {1: src}
    anterior, k_anterior = datos, 1
    for k in FACTORES:
        if moda:
            while k_anterior < k:
                anterior, k_anterior = moda_2x2(anterior), k_anterior * 2
            reducida = anterior
        else:
            h, w = (datos.shape[0] // k) * k, (datos.shape[1] // k) * k
            reducida = datos[:h, :w].reshape(h // k, k, w // k, k).max(axis=(1, 3))
        mem = MemoryFile()
        with mem.open(driver="GTiff", width=reducida.shape[1], height=reducida.shape[0], count=1,
                      dtype="uint8", crs=src.crs, transform=src.transform * src.transform.scale(k, k)) as d:
            d.write(reducida, 1)
        salida[k] = mem.open()  # reabierta en solo lectura: es lo que WarpedVRT espera
    return salida, ocupada


def tiene_datos(z, x, y, ocupada, transform_ocupada, crs) -> bool:
    """Si algún bloque con datos toca la tesela: filtro rápido para no reproyectar las teselas vacías,
    que a zooms altos son la mayoría en las capas de ríos, vías o instalaciones."""
    xmin, ymin, xmax, ymax = transform_bounds("EPSG:3857", crs, *limites(z, x, y))
    inversa = ~transform_ocupada
    c0, r0 = inversa * (xmin, ymax)
    c1, r1 = inversa * (xmax, ymin)
    r0, c0 = max(int(r0) - 1, 0), max(int(c0) - 1, 0)
    r1, c1 = min(int(r1) + 2, ocupada.shape[0]), min(int(c1) + 2, ocupada.shape[1])
    return r1 > r0 and c1 > c0 and bool(ocupada[r0:r1, c0:c1].any())


def factor_para(z, celda=5.0):
    """Mayor reducción que deja al menos dos píxeles de origen por píxel de tesela."""
    tam_pixel = 2 * MUNDO / 2 ** z / LADO
    k = 1
    while k * 4 * celda <= tam_pixel and k < FACTORES[-1]:
        k *= 2
    return k


def fichero(codigo: str) -> Path:
    """PMTiles de una capa del catálogo o de una capa combinada por grupo."""
    prefijo = "combinada" if codigo in COMBINADAS else "peligrosid"
    return VISOR / "capas" / f"{prefijo}_{codigo}.pmtiles"


def generar(codigo: str, zoom_max: int = 15) -> int:
    destino = fichero(codigo)
    destino.parent.mkdir(parents=True, exist_ok=True)
    escritas = 0
    with rasterio.open(tif(codigo)) as src:
        a3857 = Transformer.from_crs(src.crs, "EPSG:3857", always_xy=True).transform_bounds(*src.bounds)
        lonlat = Transformer.from_crs(src.crs, "EPSG:4326", always_xy=True).transform_bounds(*src.bounds)
        lista = sorted((zxy_to_tileid(z, x, y), z, x, y)
                       for z in range(ZOOM_MIN, zoom_max + 1) for x, y in teselas_que_cubren(a3857, z))
        # Nivel más frecuente al alejarse en las capas de superficie, en las meteorológicas (zonas suaves) y en las
        # combinadas (vistas de conjunto en las que el máximo pintaría casi toda la Comunidad del nivel más alto)
        moda = codigo in SUPERFICIE or codigo in CAPAS_METEO or codigo in COMBINADAS
        niveles, ocupada = piramide(src, moda)
        transform_ocupada = src.transform * src.transform.scale(FACTORES[-1], FACTORES[-1])
        with open(destino, "wb") as f:
            w = Writer(f)
            for tid, z, x, y in lista:
                k = factor_para(z)
                if k < FACTORES[-1] and not tiene_datos(z, x, y, ocupada, transform_ocupada, src.crs):
                    continue
                n = niveles_tesela(niveles[k], z, x, y, src_nodata=SIN_DATO if k == 1 else None, moda=moda)
                if not n.any():
                    continue
                w.write_tile(tid, png(colorear(n, codigo in CON_FONDO, engrosado(codigo, z),
                                               bordes=codigo not in LINEALES | SIN_BORDE | set(COMBINADAS))))
                escritas += 1
            w.finalize(
                {"tile_type": TileType.PNG, "tile_compression": Compression.NONE,
                 "min_zoom": ZOOM_MIN, "max_zoom": zoom_max,
                 "min_lon_e7": int(lonlat[0] * 1e7), "min_lat_e7": int(lonlat[1] * 1e7),
                 "max_lon_e7": int(lonlat[2] * 1e7), "max_lat_e7": int(lonlat[3] * 1e7),
                 "center_zoom": 9, "center_lon_e7": int(-3.7e7), "center_lat_e7": int(40.45e7)},
                {"name": nombre_capa(codigo) if codigo in COMBINADAS else f"Peligrosidad: {nombre_capa(codigo)}",
                 "attribution": "Catálogo de Riesgos Potenciales, Comunidad de Madrid (CC BY 4.0)"})
        for k, d in niveles.items():
            if k != 1:
                d.close()
    return escritas


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--zoom-max", type=int, default=15)
    p.add_argument("--capas", nargs="*", default=list(CAPAS))
    a = p.parse_args(argv)
    for c in a.capas:
        n = generar(c, a.zoom_max)
        mb = fichero(c).stat().st_size / 1e6
        print(f"  {c:12s} {nombre_capa(c):38s} {n:5d} teselas {mb:6.1f} MB", flush=True)


if __name__ == "__main__":
    main()
