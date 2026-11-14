"""Eje de las conducciones de hidrocarburos para el mapa de crisis (decisión del 11-11-2026).

La Comunidad publica los tramos de conducciones de la BTA sin geometría, y el catálogo solo da la franja de
peligrosidad de la capa 6_12, trazada alrededor de gasoductos y oleoductos: la conducción va hacia el centro de su
núcleo (nivel 3, moderado). Aquí se calcula ese eje una vez para toda la Comunidad:

1. núcleo a 25 m (nivel máximo de la capa de 5 m dentro de cada celda);
2. adelgazamiento de Zhang y Suen (1984) hasta una línea de una celda de ancho;
3. vectorización: cada celda se une con sus vecinas ortogonales, y con las diagonales donde no hay camino
   ortogonal, y los tramos se empalman;
4. poda de las ramitas sueltas de menos de 300 m, que salen de los bordes irregulares de la banda;
5. simplificación a 25 m.

Es una aproximación: el catálogo no publica la línea exacta de la tubería.

El visor la pinta siempre, en los tres modos, y la simulación coloca sobre ella el punto en que el fuego alcanza
la conducción (sobre_el_eje).

Salida: datos/visor/conducciones.geojson (EPSG:4326).
Uso: python -m procesamiento.conducciones [--forzar]
"""
import argparse
import functools
import json
import math

import numpy as np
import rasterio
import shapely
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

from .capas import SIN_DATO, tif
from .fuentes import VISOR
from .incendio.entradas import A_GEO, A_UTM

CAPA = "6_12"
CELDA_M = 25.0
RAMITA_MIN_M = 300.0
SIMPLIFICAR_M = 25.0
SALIDA = VISOR / "conducciones.geojson"


def nucleo_25m() -> tuple[np.ndarray, rasterio.Affine]:
    """Núcleo de la capa 6_12 (nivel 3) en celdas de 25 m: máscara y transformación (EPSG:25830)."""
    with rasterio.open(tif(CAPA)) as src:
        b = src.bounds
        transform = from_origin(b.left, b.top, CELDA_M, CELDA_M)
        destino = np.full((math.ceil((b.top - b.bottom) / CELDA_M), math.ceil((b.right - b.left) / CELDA_M)),
                          SIN_DATO, dtype=np.uint8)
        # Sin dato de destino 255, no 0: GDAL convertiría los ceros válidos en 1
        reproject(rasterio.band(src, 1), destino, dst_transform=transform, dst_crs=src.crs, src_nodata=SIN_DATO,
                  dst_nodata=SIN_DATO, resampling=Resampling.max)
    return (destino >= 3) & (destino != SIN_DATO), transform


def adelgazar(mascara: np.ndarray) -> np.ndarray:
    """Adelgazamiento de Zhang y Suen: deja una línea de una celda por el centro de cada banda."""
    m = np.pad(mascara, 1).astype(np.uint8)
    while True:
        cambio = False
        for paso in (0, 1):
            centro = m[1:-1, 1:-1]
            p2, p3, p4, p5 = m[:-2, 1:-1], m[:-2, 2:], m[1:-1, 2:], m[2:, 2:]
            p6, p7, p8, p9 = m[2:, 1:-1], m[2:, :-2], m[1:-1, :-2], m[:-2, :-2]
            vecinos = [p2, p3, p4, p5, p6, p7, p8, p9]
            b = sum(v.astype(np.int16) for v in vecinos)
            a = sum(((x == 0) & (y == 1)).astype(np.int16) for x, y in zip(vecinos, vecinos[1:] + vecinos[:1]))
            if paso == 0:
                c = (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
            else:
                c = (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)
            borrar = (centro == 1) & (b >= 2) & (b <= 6) & (a == 1) & c
            if borrar.any():
                centro[borrar] = 0
                cambio = True
        if not cambio:
            return m[1:-1, 1:-1].astype(bool)


def vectorizar(eje: np.ndarray, transform) -> list:
    """Líneas (EPSG:25830) que unen las celdas del eje: ortogonales siempre, diagonales si no hay paso ortogonal."""
    e = np.pad(eje, 1)
    pares = []
    for df, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        vecina = np.roll(np.roll(e, -df, axis=0), -dc, axis=1)
        une = e & vecina
        if df and dc:   # diagonal: solo si las dos celdas ortogonales intermedias están vacías
            une &= ~np.roll(e, -dc, axis=1) & ~np.roll(e, -df, axis=0)
        f, c = np.nonzero(une)
        pares.append(np.stack([np.c_[f, c], np.c_[f + df, c + dc]], axis=1))
    pares = np.concatenate(pares) - 1          # sin el relleno
    x = transform.c + (pares[..., 1] + 0.5) * transform.a
    y = transform.f + (pares[..., 0] + 0.5) * transform.e
    lineas = shapely.line_merge(shapely.multilinestrings(shapely.linestrings(np.stack([x, y], axis=-1))))
    return list(lineas.geoms) if lineas.geom_type == "MultiLineString" else [lineas]


def podar(lineas: list, minimo_m: float = RAMITA_MIN_M, rondas: int = 3) -> list:
    """Quita las ramitas cortas con un extremo suelto (y los trozos sueltos cortos) y vuelve a empalmar."""
    for _ in range(rondas):
        extremos = {}
        for l in lineas:
            for p in (l.coords[0], l.coords[-1]):
                extremos[p] = extremos.get(p, 0) + 1
        quedan = [l for l in lineas if l.length >= minimo_m
                  or min(extremos[l.coords[0]], extremos[l.coords[-1]]) > 1]
        if len(quedan) == len(lineas):
            break
        unidas = shapely.line_merge(shapely.multilinestrings(quedan))
        lineas = list(unidas.geoms) if unidas.geom_type == "MultiLineString" else [unidas]
    return lineas


@functools.lru_cache(maxsize=1)
def _ejes() -> shapely.MultiLineString | None:
    if not SALIDA.exists():
        return None
    rasgos = json.loads(SALIDA.read_text(encoding="utf-8"))["features"]
    return shapely.multilinestrings([shapely.LineString(np.column_stack(A_UTM.transform(*np.asarray(r["geometry"]["coordinates"]).T)))
                                     for r in rasgos])


def sobre_el_eje(x: float, y: float, max_m: float = 600.0) -> tuple[float, float]:
    """Punto del eje más cercano a (x, y) (EPSG:25830), si está a menos de max_m; si no, el propio punto."""
    ejes = _ejes()
    if ejes is None:
        return x, y
    p = shapely.Point(x, y)
    q = ejes.interpolate(ejes.project(p))
    return (q.x, q.y) if p.distance(q) <= max_m else (x, y)


def construir(forzar: bool = False):
    if SALIDA.exists() and not forzar:
        return SALIDA
    nucleo, transform = nucleo_25m()
    lineas = podar(vectorizar(adelgazar(nucleo), transform))
    rasgos = []
    for l in lineas:
        l = shapely.simplify(l, SIMPLIFICAR_M)
        lon, lat = A_GEO.transform(*np.asarray(l.coords).T)
        rasgos.append({"type": "Feature", "properties": {"km": round(l.length / 1000, 2)},
                       "geometry": {"type": "LineString", "coordinates": np.round(np.c_[lon, lat], 5).tolist()}})
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps({"type": "FeatureCollection", "features": rasgos}, ensure_ascii=False), encoding="utf-8")
    print(f"  {len(rasgos)} tramos, {sum(r['properties']['km'] for r in rasgos):.0f} km")
    return SALIDA


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--forzar", action="store_true", help="recalcular aunque ya exista")
    construir(p.parse_args().forzar)
