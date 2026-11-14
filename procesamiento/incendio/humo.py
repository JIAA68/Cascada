"""Ruta del humo de un incendio simulado (modelo geométrico, parámetros provisionales).

El humo sale del área quemada hasta ese momento y se desplaza viento abajo con el viento de
esa hora, abriéndose en un cono:
- alcance = velocidad del viento × tiempo transcurrido, hasta 2 h de permanencia, con un máximo
  de 25 km más allá del área quemada;
- apertura = semiángulo fijo a cada lado del eje del viento.
La zona de humo es la envolvente convexa del área quemada y de esa misma área desplazada viento
abajo y ensanchada a cada lado. Sin viento, el humo se queda en 500 m alrededor del fuego.

Una sola geometría: la zona se calcula aquí cada PASO_MIN minutos; el
visor dibuja esas mismas zonas y cada centro, carretera, vía o estación queda bajo el humo en el
primer paso en que su punto cae dentro. Así lo que se ve y lo que se marca coinciden siempre.

No es un modelo de dispersión: no tiene en cuenta la altura de la columna, la estabilidad
atmosférica, el relieve ni la concentración. Señala qué activos pueden quedar a sotavento.
"""
import math

import numpy as np
import pandas as pd
import shapely

SEMIANGULO_GRADOS = 20
PERMANENCIA_H = 2.0
ALCANCE_MAX_KM = 25.0
RADIO_CALMA_M = 500
PASO_MIN = 5


def puntos_quemados(llegada: np.ndarray, ventana, minutos: float) -> np.ndarray | None:
    """Esquinas (EPSG:25830) de la primera y la última celda quemada de cada fila: bastan para la envolvente."""
    quemado = llegada <= minutos
    filas = np.nonzero(quemado.any(axis=1))[0]
    if not len(filas):
        return None
    sub = quemado[filas]
    c0 = sub.argmax(axis=1)
    c1 = sub.shape[1] - 1 - sub[:, ::-1].argmax(axis=1)
    x0, x1 = ventana.x0 + c0 * ventana.celda, ventana.x0 + (c1 + 1) * ventana.celda
    y0, y1 = ventana.y0 - filas * ventana.celda, ventana.y0 - (filas + 1) * ventana.celda
    return np.concatenate([np.c_[x0, y0], np.c_[x0, y1], np.c_[x1, y0], np.c_[x1, y1]])


def zona_humo(quemado, velocidad_kmh: float, desde: float, horas_desde_ignicion: float):
    """Zona de humo (EPSG:25830) a partir del área quemada (geometría o puntos) y del viento de esa hora; None si aún no hay."""
    puntos = np.asarray(shapely.get_coordinates(quemado) if isinstance(quemado, shapely.Geometry) else quemado)
    envolvente = shapely.convex_hull(shapely.multipoints(puntos))
    if velocidad_kmh <= 0:
        return envolvente.buffer(RADIO_CALMA_M)
    alcance = min(velocidad_kmh * min(horas_desde_ignicion, PERMANENCIA_H), ALCANCE_MAX_KM) * 1000
    if alcance <= 0:
        return None
    hacia = math.radians((desde + 180) % 360)
    dx, dy = alcance * math.sin(hacia), alcance * math.cos(hacia)
    ancho = alcance * math.tan(math.radians(SEMIANGULO_GRADOS))
    nx, ny = math.cos(hacia), -math.sin(hacia)
    base = np.asarray(shapely.get_coordinates(envolvente))
    lejos = np.concatenate([base + [dx + nx * ancho, dy + ny * ancho], base + [dx - nx * ancho, dy - ny * ancho]])
    return shapely.convex_hull(shapely.multipoints(np.concatenate([base, lejos])))


def zonas_de_humo(llegada: np.ndarray, ventana, vientos, horizonte_min: float = 24 * 60,
                  paso_min: float = PASO_MIN) -> list[tuple[float, shapely.Geometry]]:
    """(minutos, zona de humo en EPSG:25830) cada paso_min minutos desde el primer paso con humo."""
    salida = []
    for m in np.arange(paso_min, horizonte_min + 1e-9, paso_min):
        puntos = puntos_quemados(llegada, ventana, m)
        if puntos is None:
            continue
        w = vientos[min(int(m // 60), len(vientos) - 1)]
        zona = zona_humo(puntos, w.velocidad_kmh, w.desde, m / 60)
        if zona is not None:
            salida.append((float(m), zona))
    return salida


def primer_minuto_bajo_humo(zonas, x, y) -> np.ndarray:
    """Primer minuto en que cada punto queda dentro de alguna zona de humo; inf si nunca."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    minuto = np.full(len(x), np.inf)
    for m, z in zonas:
        pendientes = np.isinf(minuto)
        if not pendientes.any():
            break
        dentro = shapely.contains_xy(z, x[pendientes], y[pendientes])
        minuto[np.nonzero(pendientes)[0][dentro]] = m
    return minuto


def activos_bajo_humo(zonas, activos: pd.DataFrame) -> pd.DataFrame:
    """Activos dentro de alguna zona de humo, con humo_min: el primer minuto en que quedan bajo él."""
    primero = primer_minuto_bajo_humo(zonas, activos.x.values, activos.y.values)
    a = activos[np.isfinite(primero)].copy()
    a["humo_min"] = primero[np.isfinite(primero)]
    return a
