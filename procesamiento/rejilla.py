"""Rejilla europea de 1 km (INSPIRE/Eurostat, EPSG:3035) y población del Censo 2021.

Una celda se identifica como el INE: CRS3035RES1000mN<norte>E<este>, con las coordenadas
de su esquina suroeste en metros. Las funciones trabajan con las coordenadas de celda en
kilómetros (e_km, n_km).
"""
import numpy as np
import pandas as pd
from pyproj import Transformer

from .fuentes import fuente

A3035 = Transformer.from_crs("EPSG:25830", "EPSG:3035", always_xy=True)
A4326 = Transformer.from_crs("EPSG:3035", "EPSG:4326", always_xy=True)
DE4326 = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)


def id_celda(e_km: int, n_km: int) -> str:
    return f"CRS3035RES1000mN{n_km * 1000}E{e_km * 1000}"


def celda_de_utm(x, y) -> tuple[np.ndarray, np.ndarray]:
    """Celda (e_km, n_km) de puntos en EPSG:25830 (acepta vectores)."""
    e, n = A3035.transform(np.asarray(x, dtype=float), np.asarray(y, dtype=float))
    return np.floor(e / 1000).astype(np.int64), np.floor(n / 1000).astype(np.int64)


def celda_de_lonlat(lon: float, lat: float) -> tuple[int, int]:
    e, n = DE4326.transform(lon, lat)
    return int(np.floor(e / 1000)), int(np.floor(n / 1000))


def contorno(e_km: int, n_km: int) -> list[list[float]]:
    """Polígono de la celda en lon/lat (cerrado), para dibujarla en el mapa."""
    esquinas = [(e_km, n_km), (e_km + 1, n_km), (e_km + 1, n_km + 1), (e_km, n_km + 1), (e_km, n_km)]
    return [[round(v, 6) for v in A4326.transform(e * 1000, n * 1000)] for e, n in esquinas]


def poblacion() -> pd.DataFrame:
    """Población total, menores de 16 y mayores de 64 por celda (INE, Censo 2021)."""
    # El fichero lleva una fila de cabecera de grupo antes de los nombres de columna, está
    # en latin-1 y usa el punto como separador de miles.
    p = pd.read_csv(fuente("poblacion_rejilla"), sep=";", skiprows=1, encoding="latin-1", dtype=str)
    salida = pd.DataFrame({"grd_id": p["GRD_ID"]})
    for columna, nombre in (("TOTAL", "poblacion"), ("<16", "menores_16"), (">64", "mayores_64")):
        salida[nombre] = (pd.to_numeric(p[columna].str.replace(".", "", regex=False), errors="coerce")
                          .fillna(0).astype(int))
    return salida
