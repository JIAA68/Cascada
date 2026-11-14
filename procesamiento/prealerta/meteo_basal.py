"""Nivel de las capas meteorológicas del catálogo, y de torrencialidad en cauces, en el punto de cada activo.

Las 13 capas de peligrosidad por fenómenos meteorológicos adversos (1_1 a 1_13) y la de torrencialidad (2_2) no
forman parte del análisis basal: se muestrean aquí para la prealerta. Los píxeles de 5 m de los activos se agrupan
por bloque del GeoTIFF para leer cada bloque una sola vez.

Salida: datos/procesados/meteo_activos.csv (id y una columna n_<código> por capa). No se publica.

Uso: python -m procesamiento.prealerta.meteo_basal
"""
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window

from ..activos import escribir as escribir_activos
from ..capas import CAPAS_ACTIVACION_EXTRA, CAPAS_METEO, SIN_DATO, tif
from ..fuentes import PROCESADOS

CODIGOS = list(CAPAS_METEO) + list(CAPAS_ACTIVACION_EXTRA)
SALIDA = PROCESADOS / "meteo_activos.csv"


def muestrear(ruta, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Valor del ráster en cada punto (0 fuera de la Comunidad o sin dato), leyendo cada bloque una vez."""
    salida = np.zeros(len(x), np.uint8)
    with rasterio.open(ruta) as src:
        t = src.transform
        filas = np.floor((y - t.f) / t.e).astype(np.int64)
        cols = np.floor((x - t.c) / t.a).astype(np.int64)
        dentro = (filas >= 0) & (filas < src.height) & (cols >= 0) & (cols < src.width)
        alto_b, ancho_b = src.block_shapes[0]
        bloques = pd.DataFrame({"i": np.flatnonzero(dentro), "bf": filas[dentro] // alto_b, "bc": cols[dentro] // ancho_b})
        for (bf, bc), grupo in bloques.groupby(["bf", "bc"]):
            f0, c0 = int(bf) * alto_b, int(bc) * ancho_b
            ventana = Window(c0, f0, min(ancho_b, src.width - c0), min(alto_b, src.height - f0))
            datos = src.read(1, window=ventana)
            idx = grupo["i"].to_numpy()
            salida[idx] = datos[filas[idx] - f0, cols[idx] - c0]
    salida[salida == SIN_DATO] = 0
    return salida


def construir() -> pd.DataFrame:
    ruta_activos = PROCESADOS / "activos.csv"
    activos = pd.read_csv(ruta_activos) if ruta_activos.exists() else escribir_activos()
    activos = activos.dropna(subset=["x", "y"]).reset_index(drop=True)
    x, y = activos["x"].to_numpy(float), activos["y"].to_numpy(float)
    salida = pd.DataFrame({"id": activos["id"]})
    for codigo in CODIGOS:
        salida[f"n_{codigo}"] = muestrear(tif(codigo), x, y)
        print(f"  {codigo}: niveles {dict(zip(*np.unique(salida[f'n_{codigo}'], return_counts=True)))}", flush=True)
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    salida.to_csv(SALIDA, index=False, encoding="utf-8")
    return salida


if __name__ == "__main__":
    construir()
