"""Núcleos de población alcanzados por el fuego (decisión del 12-11-2026)."""
import numpy as np
import pandas as pd
import shapely

from procesamiento import poblaciones
from procesamiento.incendio.entradas import Ventana

V = Ventana(400_000.0, 4_500_000.0, 50.0, 100, 100)     # 5 × 5 km, celdas de 50 m


def _xy(fila, col):
    return V.x0 + (col + 0.5) * V.celda, V.y0 - (fila + 0.5) * V.celda


def test_dos_nucleos_en_una_mancha_y_uno_suelto():
    # El fuego avanza de oeste a este: llega a la columna c en el minuto c
    llegada = np.tile(np.arange(100, dtype=float), (100, 1))
    llegada[:, 90:] = np.inf
    # Una mancha urbana de las columnas 20 a 59 (filas 40 a 59), con un núcleo hacia cada extremo
    mancha = shapely.box(V.x0 + 20 * V.celda, V.y0 - 60 * V.celda, V.x0 + 60 * V.celda, V.y0 - 40 * V.celda)
    n = pd.DataFrame([{"nombre": "Oeste", "tipo": "Núcleos de población", "x": _xy(50, 22)[0], "y": _xy(50, 22)[1]},
                      {"nombre": "Este", "tipo": "Núcleos de población", "x": _xy(50, 57)[0], "y": _xy(50, 57)[1]},
                      {"nombre": "Suelto", "tipo": "Entidad menor de población", "x": _xy(10, 80)[0], "y": _xy(10, 80)[1]},
                      {"nombre": "Lejos", "tipo": "Núcleos de población", "x": _xy(10, 95)[0], "y": _xy(10, 95)[1]}])
    d = {p["nombre"]: p for p in poblaciones.alcanzadas(llegada, V, manchas=[mancha], nucleos=n)}
    assert set(d) == {"Oeste", "Este", "Suelto"}          # a «Lejos» no llega el fuego
    assert d["Oeste"]["minutos"] == 20.0                   # por el borde oeste de la mancha
    assert d["Este"]["minutos"] == 40.0                    # las celdas más cerca de él empiezan en la columna 40
    assert d["Suelto"]["minutos"] == 80.0                  # sin mancha, su propio punto
