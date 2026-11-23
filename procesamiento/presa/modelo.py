"""Llegada de la onda de rotura de una presa (modelo propio, calibrado con el catálogo).

El catálogo de la Comunidad da la zona que inunda la onda en los primeros 30 minutos (nivel 2 de la capa 2_3) y el
resto de la llanura de inundación (nivel 1), pero no cuándo llega el agua más allá. Modelo:

- **Recorrido:** el agua avanza desde la presa por las celdas de 50 m de la zona inundable (niveles 1 y 2), aguas
  abajo: no pasa a una celda más de 10 m por encima de la más baja por la que ya ha pasado (según el MDT de 25 m del
  IGN). Así salva los artefactos del relieve (puentes, taludes, cañones estrechos que la media de 50 m eleva) pero no
  remonta los afluentes. La distancia de cada celda a la presa es la del camino más corto así (Dijkstra, 8 vecinos).
- **Onda frenada:** la velocidad cae con la distancia, v(s) = v₀·L / (L + s), con L la longitud de la zona de 30
  minutos de la presa (la mayor distancia que recorre el agua por su zona de nivel 2): a la salida de esa zona la
  onda va a la mitad de velocidad y al triple de distancia, a un cuarto. Integrando, t(s) = (s + s²/2L) / v₀.
- **Calibración con el catálogo:** v₀ = 1,5·L / 30 min, para que la onda tarde exactamente 30 minutos en recorrer la
  zona de nivel 2 de cada presa.
- **Velocidad mínima** de 2 km/h: desde donde la onda frenada iría más despacio, avanza a esa velocidad.

No modela calados, caudales ni la forma de la onda: solo cuándo llega el agua a cada punto de la zona del catálogo.
"""
import heapq

import numpy as np
from scipy import ndimage

SUBIDA_MAX_M = 10.0
VELOCIDAD_MIN_KMH = 2.0
LONGITUD_MIN_M = 200.0
VECINOS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def distancias_aguas_abajo(mascara: np.ndarray, altitud: np.ndarray, origen: tuple[int, int], celda: float) -> np.ndarray:
    """Distancia en metros desde `origen` por las celdas de la máscara (inf donde no se llega).

    El agua no pasa a una celda más de SUBIDA_MAX_M por encima de la más baja por la que ya ha pasado en su camino:
    salva los artefactos del relieve de 50 m (puentes, taludes, cañones estrechos) pero no remonta los afluentes.
    Dijkstra con esa restricción, que depende del camino: cada celda guarda la altitud mínima del camino por el que se
    alcanzó antes. Solo se usa la parte de la máscara conectada con el origen.
    """
    etiquetas, _ = ndimage.label(mascara, structure=np.ones((3, 3)))
    comp = etiquetas == etiquetas[origen]
    filas, columnas = np.nonzero(comp)
    f0, f1, c0, c1 = filas.min(), filas.max() + 1, columnas.min(), columnas.max() + 1
    sub = comp[f0:f1, c0:c1]
    alt = np.where(np.isfinite(altitud[f0:f1, c0:c1]), altitud[f0:f1, c0:c1], np.inf)   # sin altitud: se mira abajo
    h, w = sub.shape
    dist = np.full((h, w), np.inf)
    minimo = np.full((h, w), np.inf)
    fo, co = origen[0] - f0, origen[1] - c0
    dist[fo, co] = 0.0
    minimo[fo, co] = alt[fo, co] if np.isfinite(alt[fo, co]) else 0.0
    pasos = [(df, dc, celda * (2 ** 0.5 if df and dc else 1.0)) for df, dc in VECINOS]
    cola = [(0.0, fo, co)]
    hecho = np.zeros((h, w), dtype=bool)
    while cola:
        d, f, c = heapq.heappop(cola)
        if hecho[f, c]:
            continue
        hecho[f, c] = True
        tope = minimo[f, c] + SUBIDA_MAX_M
        for df, dc, paso in pasos:
            g, k = f + df, c + dc
            if 0 <= g < h and 0 <= k < w and sub[g, k] and not hecho[g, k]:
                z = alt[g, k]
                if z > tope and np.isfinite(z):
                    continue
                nd = d + paso
                if nd < dist[g, k]:
                    dist[g, k] = nd
                    minimo[g, k] = min(minimo[f, c], z) if np.isfinite(z) else minimo[f, c]
                    heapq.heappush(cola, (nd, g, k))
    salida = np.full(mascara.shape, np.inf)
    salida[f0:f1, c0:c1] = np.where(sub, dist, np.inf)
    return salida


def longitud_30_min(zona_30: np.ndarray, altitud: np.ndarray, presa: tuple[int, int], celda: float) -> float:
    """Mayor distancia que recorre el agua, solo aguas abajo, desde la presa por su zona de nivel 2."""
    d = distancias_aguas_abajo(zona_30, altitud, presa, celda)
    return float(max(d[np.isfinite(d)].max(), LONGITUD_MIN_M))


def minutos_de_llegada(distancia_m: np.ndarray, longitud_30_m: float) -> np.ndarray:
    """Minutos de llegada de la onda frenada a cada distancia de la presa (inf donde no se llega)."""
    L = max(longitud_30_m, LONGITUD_MIN_M)
    v0 = 1.5 * L / 30.0                           # m/min: t(L) = 30 min
    vmin = VELOCIDAD_MIN_KMH * 1000 / 60          # m/min
    s = np.asarray(distancia_m, dtype=float)
    frenada = (s + s ** 2 / (2 * L)) / v0
    if v0 <= vmin:
        return s / vmin
    s_lim = L * (v0 / vmin - 1)                    # desde aquí, la onda frenada iría por debajo de la mínima
    t_lim = (s_lim + s_lim ** 2 / (2 * L)) / v0
    return np.where(s <= s_lim, frenada, t_lim + (s - s_lim) / vmin)
