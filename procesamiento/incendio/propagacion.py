"""Propagación del incendio por tiempo mínimo de recorrido sobre una rejilla.

Cada celda tiene un modelo de combustible, una pendiente y una orientación. En cada
dirección, la velocidad de avance sale de la elipse de Rothermel (velocidad máxima,
dirección y excentricidad) con la ignición en el foco. El tiempo de llegada a cada celda es
el del camino más rápido desde la ignición: camino mínimo (Dijkstra) sobre un grafo de 32
vecinos (hasta tres celdas), como en el método de tiempo mínimo de recorrido de FlamMap (Finney,
2002); con 32 vecinos la velocidad apenas depende del rumbo del viento respecto de la rejilla. Las
aristas que cruzan una celda sin combustible no existen: una franja sin combustible es barrera.

El viento y la humedad pueden cambiar cada hora. Mientras no cambian se hace un solo cálculo; al
cambiar, el grafo se reconstruye y lo quemado sigue ardiendo desde el instante del cambio: cada
arista que el fuego había empezado a recorrer conserva la fracción ya recorrida, de modo que las
condiciones nuevas solo actúan hacia delante. El resultado es el
mapa completo de tiempos de llegada, que el visor reproduce minuto a minuto sin recalcular.

Salto de franjas sin combustible (pavesas): con viento de al menos
SALTO_VIENTO_KMH, una celda que arde junto a una celda sin combustible puede encender celdas con
combustible a menos de SALTO_M metros viento abajo (en un cono de ±SALTO_CONO grados), si entre
ambas hay alguna celda sin combustible: carreteras, avenidas y cortafuegos estrechos. El salto se
recorre a la velocidad del fuego de la celda de origen en esa dirección.
"""
import math
from dataclasses import dataclass

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

from .combustibles import FACTOR_VIENTO, MODELOS, Humedades
from .rothermel import elipse, lecho, velocidad_en

# Del viento a 10 m (AEMET) al viento a 6,1 m (20 ft) de Rothermel
VIENTO_10M_A_20FT = 1 / 1.15
# 32 vecinos (fila, columna): los desplazamientos de hasta tres celdas con componentes primos entre sí;
# el norte es fila decreciente
VECINOS = [(df, dc) for df in range(-3, 4) for dc in range(-3, 4)
           if (df or dc) and math.gcd(df, dc) == 1]
RUMBOS = [math.degrees(math.atan2(dc, -df)) % 360 for df, dc in VECINOS]


def _intermedias(df: int, dc: int) -> list[tuple[int, int]]:
    """Celdas que cruza el segmento entre los centros de dos celdas, sin contar sus extremos."""
    pasos = 8 * max(abs(df), abs(dc))
    celdas = {(math.floor(0.5 + df * k / pasos), math.floor(0.5 + dc * k / pasos)) for k in range(1, pasos)}
    return sorted(celdas - {(0, 0), (df, dc)})


INTERMEDIAS = [_intermedias(df, dc) for df, dc in VECINOS]
INDICE_VECINO = {v: i for i, v in enumerate(VECINOS)}
MARGEN_CELDAS = 4   # celdas de margen del recorte de cada tramo
SALTO_M = 300.0             # anchura máxima de franja sin combustible que cruza el fuego
SALTO_VIENTO_KMH = 30.0     # viento a 10 m a partir del cual hay salto
SALTO_CONO = 45.0           # grados a cada lado de la dirección hacia la que sopla el viento


@dataclass(frozen=True)
class Viento:
    """Viento a 10 m durante una hora: velocidad (km/h) y dirección de donde viene (grados)."""
    velocidad_kmh: float
    desde: float


def campos(combustible, pendiente, subida, viento: Viento, humedades: Humedades):
    """Velocidad máxima (m/min), dirección (grados) y excentricidad de la elipse, por celda."""
    vel = np.zeros(combustible.shape)
    dire = np.zeros(combustible.shape)
    exc = np.zeros(combustible.shape)
    hacia = (viento.desde + 180) % 360
    for numero in np.unique(combustible):
        if int(numero) not in MODELOS:
            continue  # 0: sin combustible
        m = combustible == numero
        k = lecho(MODELOS[int(numero)], humedades)
        if k.r0 <= 0:
            continue
        u = viento.velocidad_kmh * VIENTO_10M_A_20FT * FACTOR_VIENTO[int(numero)]
        vel[m], dire[m], exc[m] = elipse(k, u, hacia, pendiente[m], subida[m])
    return vel, dire, exc


def lentitudes(vel, dire, exc) -> np.ndarray:
    """Inversa de la velocidad (min/m) en cada dirección de VECINOS: (direcciones, filas, columnas)."""
    s = np.full((len(VECINOS),) + vel.shape, np.inf, dtype=np.float32)
    q = vel > 0
    for d, rumbo in enumerate(RUMBOS):
        s[d][q] = 1 / velocidad_en(vel[q], dire[q], exc[q], rumbo)
    return s


def grafo(s: np.ndarray, celda_m: float, arde: np.ndarray | None = None):
    """Aristas dirigidas (origen, destino, minutos, dirección) entre vecinos: media de las lentitudes × distancia.

    Con `arde` (celdas con combustible), una arista larga solo existe si todas las celdas que cruza arden.
    """
    _, alto, ancho = s.shape
    idx = np.arange(alto * ancho, dtype=np.int32).reshape(alto, ancho)
    origenes, destinos, pesos, direcciones = [], [], [], []
    for d, (df, dc) in enumerate(VECINOS):
        f0, f1 = max(0, -df), alto - max(0, df)
        c0, c1 = max(0, -dc), ancho - max(0, dc)
        a = idx[f0:f1, c0:c1]
        b = idx[f0 + df:f1 + df, c0 + dc:c1 + dc]
        w = celda_m * math.hypot(df, dc) / 2 * (s[d][f0:f1, c0:c1] + s[d][f0 + df:f1 + df, c0 + dc:c1 + dc])
        ok = np.isfinite(w)
        if arde is not None:
            for mf, mc in INTERMEDIAS[d]:
                ok &= arde[f0 + mf:f1 + mf, c0 + mc:c1 + mc]
        origenes.append(a[ok]), destinos.append(b[ok]), pesos.append(w[ok].astype(np.float32))
        direcciones.append(np.full(int(ok.sum()), d, dtype=np.int8))
    return (np.concatenate(origenes), np.concatenate(destinos), np.concatenate(pesos), np.concatenate(direcciones))


def _desplazar(a: np.ndarray, df: int, dc: int) -> np.ndarray:
    """a desplazada (df, dc) celdas: el resultado en (f, c) es a[f + df, c + dc] (False fuera)."""
    alto, ancho = a.shape
    r = np.zeros_like(a)
    r[max(0, -df):alto - max(0, df), max(0, -dc):ancho - max(0, dc)] = \
        a[max(0, df):alto - max(0, -df), max(0, dc):ancho - max(0, -dc)]
    return r


def aristas_salto(vel, dire, exc, viento: Viento, celda_m: float):
    """Aristas (origen, destino, minutos) de salto de franjas sin combustible; None si no hay."""
    if viento.velocidad_kmh < SALTO_VIENTO_KMH:
        return None
    arde, sin = vel > 0, vel <= 0
    alto, ancho = vel.shape
    origen = arde & np.logical_or.reduce([_desplazar(sin, df, dc) for df in (-1, 0, 1) for dc in (-1, 0, 1) if df or dc])
    if not origen.any():
        return None
    hacia = (viento.desde + 180) % 360
    idx = np.arange(alto * ancho).reshape(alto, ancho)
    r = int(SALTO_M // celda_m)
    partes = []
    for df in range(-r, r + 1):
        for dc in range(-r, r + 1):
            dist = math.hypot(df, dc) * celda_m
            rumbo = math.degrees(math.atan2(dc, -df)) % 360
            if dist < 2 * celda_m or dist > SALTO_M or abs((rumbo - hacia + 180) % 360 - 180) > SALTO_CONO:
                continue
            f0, f1, c0, c1 = max(0, -df), alto - max(0, df), max(0, -dc), ancho - max(0, dc)
            pasos = max(abs(df), abs(dc))
            cruza = np.logical_or.reduce([sin[f0 + round(df * k / pasos):f1 + round(df * k / pasos),
                                              c0 + round(dc * k / pasos):c1 + round(dc * k / pasos)] for k in range(1, pasos)])
            ok = origen[f0:f1, c0:c1] & arde[f0 + df:f1 + df, c0 + dc:c1 + dc] & cruza
            d = INDICE_VECINO.get((df, dc))
            if d is not None:   # si existe la arista normal (todo lo que cruza arde), el salto sobra
                normal = np.ones_like(ok)
                for mf, mc in INTERMEDIAS[d]:
                    normal &= arde[f0 + mf:f1 + mf, c0 + mc:c1 + mc]
                ok &= ~normal
            if ok.any():
                v = velocidad_en(vel[f0:f1, c0:c1][ok], dire[f0:f1, c0:c1][ok], exc[f0:f1, c0:c1][ok], rumbo)
                partes.append((idx[f0:f1, c0:c1][ok], idx[f0 + df:f1 + df, c0 + dc:c1 + dc][ok], dist / v))
    if not partes:
        return None
    return tuple(np.concatenate([p[i] for p in partes]).astype(np.float64 if i == 2 else np.int64) for i in range(3))


def tiempos_llegada(combustible, pendiente, subida, celda_m: float, ignicion, vientos: list[Viento],
                    humedades: Humedades | list[Humedades], horizonte_min: float = 24 * 60) -> np.ndarray:
    """Tiempo de llegada del fuego a cada celda, en minutos (inf si no llega en el horizonte).

    combustible: modelos NFFL por celda (0 = sin combustible). pendiente: tangente.
    subida: dirección de máxima subida (grados). ignicion: (fila, columna).
    vientos: uno por hora desde la ignición; si faltan, se repite el último.
    humedades: una para todo el horizonte o una por hora (si faltan, se repite la última).
    """
    alto, ancho = combustible.shape
    n = alto * ancho
    f0, c0 = ignicion
    if int(combustible[f0, c0]) not in MODELOS:
        raise ValueError("La ignición cae en una celda sin combustible")
    llegada = np.full(n, np.inf)
    llegada[f0 * ancho + c0] = 0.0
    humedades = humedades if isinstance(humedades, list) else [humedades]
    # Tramos de condiciones constantes: un solo cálculo mientras el viento y la humedad no cambian
    tramos = []
    for h in range(math.ceil(horizonte_min / 60)):
        t0, t1 = h * 60, min((h + 1) * 60, horizonte_min)
        cond = (vientos[min(h, len(vientos) - 1)], humedades[min(h, len(humedades) - 1)])
        if tramos and tramos[-1][2] == cond:
            tramos[-1][1] = t1
        else:
            tramos.append([t0, t1, cond])
    progreso = np.zeros((len(VECINOS), n), dtype=np.float32)   # fracción recorrida de cada arista (dirección, origen)
    rejilla = np.arange(n, dtype=np.int64).reshape(alto, ancho)
    for t0, t1, (viento, humedad) in tramos:
        vel, dire, exc = campos(combustible, pendiente, subida, viento, humedad)
        quemada = llegada <= t0
        # Recorte: en este tramo el fuego no puede ir más lejos de la velocidad máxima por su duración (el salto
        # también se recorre a la velocidad del origen); solo se construye el grafo de ese recuadro alrededor de lo quemado
        fq, cq = np.divmod(np.flatnonzero(quemada), ancho)
        r = int(math.ceil((float(vel.max()) * (t1 - t0) + SALTO_M) / celda_m)) + MARGEN_CELDAS
        a0, a1 = max(int(fq.min()) - r, 0), min(int(fq.max()) + r + 1, alto)
        b0, b1 = max(int(cq.min()) - r, 0), min(int(cq.max()) + r + 1, ancho)
        sub = (slice(a0, a1), slice(b0, b1))
        global_ = rejilla[sub].ravel()                     # índice global de cada celda del recorte
        m = len(global_)
        o, d, w, dirs = grafo(lentitudes(vel[sub], dire[sub], exc[sub]), celda_m, vel[sub] > 0)
        go = global_[o]
        quemada_sub = quemada[global_]
        w_ef = w.astype(np.float64)
        # Lo quemado sigue desde el cambio: solo queda por recorrer lo que faltaba de cada arista
        empezada = quemada_sub[o]
        w_ef[empezada] *= 1 - progreso[dirs[empezada], go[empezada]]
        salto = aristas_salto(vel[sub], dire[sub], exc[sub], viento, celda_m)
        quemadas = np.flatnonzero(quemada_sub)
        partes_o, partes_d, partes_w = [o, np.full(len(quemadas), m, dtype=np.int32)], [d, quemadas.astype(np.int32)], \
            [w_ef, np.full(len(quemadas), float(t0))]
        if salto is not None:
            partes_o.append(salto[0].astype(np.int32)), partes_d.append(salto[1].astype(np.int32)), partes_w.append(salto[2])
        g = csr_matrix((np.maximum(np.concatenate(partes_w), 1e-9),   # csgraph trata el 0 como ausencia de arista
                        (np.concatenate(partes_o), np.concatenate(partes_d))), shape=(m + 1, m + 1))
        nuevo = dijkstra(g, directed=True, indices=m, limit=t1)[:m]
        llegada[global_] = np.where(quemada_sub, llegada[global_], nuevo)
        # Fracción recorrida de cada arista al final del tramo (las de salto no la conservan)
        lo = llegada[go]
        arde_fin = lo <= t1
        ganado = np.zeros(len(o), dtype=np.float32)
        ganado[arde_fin] = (t1 - np.maximum(lo[arde_fin], t0)) / w[arde_fin]
        previo = np.where(empezada, progreso[dirs, go], 0.0)
        progreso[dirs, go] = np.minimum(previo + ganado, 1.0)
    return llegada.reshape(alto, ancho)
