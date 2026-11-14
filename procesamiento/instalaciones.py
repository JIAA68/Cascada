"""Instalaciones Seveso deducidas de las zonas del Catálogo de Riesgos Potenciales.

No hay una fuente abierta con la ubicación de los establecimientos Seveso. Las capas de
peligrosidad por accidente industrial (6_3 nube tóxica, 6_4 sobrepresión y 6_5 radiación
térmica) se trazan con los radios de las zonas de intervención (nivel 2) y alerta (nivel 1)
alrededor de cada instalación (memoria metodológica, 1.2.2): son círculos concéntricos, así
que el centro de cada zona de intervención es la instalación.

Para cada capa se separan las zonas de nivel 2 en componentes conexas (a 25 m) y se toma su
centro y su radio equivalente. El radio de alerta es el de la zona de nivel 1 que contiene ese
centro si la instalación está sola en ella. Cuando las zonas de alerta de varias instalaciones se
tocan y forman una sola mancha, su área no dice nada del radio de cada una: se estima como el radio
de intervención más la diferencia mediana entre alerta e intervención de las instalaciones aisladas
de la misma capa. Las instalaciones de distintas capas a menos de 300 m
son la misma.

El resultado (datos/procesados/instalaciones_seveso.csv) no se publica: se regenera en local.

Uso: python -m procesamiento.instalaciones
"""
import math

import numpy as np
import pandas as pd
import rasterio
from scipy import ndimage

from .capas import SIN_DATO, tif
from .fuentes import PROCESADOS

CAPAS_SEVESO = {"6_3": "nube tóxica", "6_4": "sobrepresión por explosión", "6_5": "radiación térmica"}
FACTOR = 5           # de 5 m a 25 m
FUSION_M = 300
SALIDA = PROCESADOS / "instalaciones_seveso.csv"


def _leer_25m(codigo):
    with rasterio.open(tif(codigo)) as s:
        b, tr = s.read(1), s.transform * s.transform.scale(FACTOR, FACTOR)
    h, w = (b.shape[0] // FACTOR) * FACTOR, (b.shape[1] // FACTOR) * FACTOR
    b = np.where(b[:h, :w] == SIN_DATO, 0, b[:h, :w])
    return b.reshape(h // FACTOR, FACTOR, w // FACTOR, FACTOR).max(axis=(1, 3)), tr


def zonas(codigo) -> pd.DataFrame:
    """Una fila por zona de intervención: centro, radio de intervención y radio de alerta."""
    a, tr = _leer_25m(codigo)
    celda = tr.a
    lab_i, n = ndimage.label(a >= 2)
    lab_a, _ = ndimage.label(a >= 1)
    idx = np.arange(1, n + 1)
    area_i = ndimage.sum(np.ones_like(lab_i), lab_i, idx) * celda ** 2
    area_a = np.bincount(lab_a.ravel()) * celda ** 2
    filas = []
    for k, (f, c) in enumerate(ndimage.center_of_mass(np.ones_like(lab_i), lab_i, idx)):
        x, y = tr * (c + 0.5, f + 0.5)
        comp = lab_a[int(round(f)), int(round(c))]
        filas.append({"capa": codigo, "amenaza": CAPAS_SEVESO[codigo], "x": x, "y": y, "mancha": int(comp),
                      "radio_intervencion_m": math.sqrt(area_i[k] / math.pi),
                      "radio_alerta_m": math.sqrt(area_a[comp] / math.pi) if comp else None})
    z = pd.DataFrame(filas)
    if z.empty:
        return z
    # Manchas de alerta compartidas por varias instalaciones: radio de intervención + diferencia típica de la capa
    compartida = z.mancha.map(z.mancha.value_counts()) > 1
    aisladas = z[~compartida & z.radio_alerta_m.notna()]
    diferencia = float((aisladas.radio_alerta_m - aisladas.radio_intervencion_m).median()) if len(aisladas) else 0.0
    z["alerta_estimada"] = compartida | z.radio_alerta_m.isna()
    z.loc[z.alerta_estimada, "radio_alerta_m"] = z.radio_intervencion_m[z.alerta_estimada] + diferencia
    return z.drop(columns="mancha")


def construir() -> pd.DataFrame:
    z = pd.concat([zonas(c) for c in CAPAS_SEVESO], ignore_index=True)
    grupo = -np.ones(len(z), dtype=int)
    for i in range(len(z)):
        if grupo[i] < 0:
            grupo[(np.hypot(z.x - z.x[i], z.y - z.y[i]) < FUSION_M) & (grupo < 0)] = i
    z["id"] = pd.Series(pd.factorize(grupo)[0] + 1).map(lambda i: f"SEV-{i:02d}")
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    z.to_csv(SALIDA, index=False, encoding="utf-8")
    return z


def cargar() -> pd.DataFrame:
    return pd.read_csv(SALIDA) if SALIDA.exists() else construir()


if __name__ == "__main__":
    z = construir()
    print(f"Zonas de intervención: {len(z)} | instalaciones distintas: {z['id'].nunique()}")
    print(z.groupby("capa").size().to_string())
