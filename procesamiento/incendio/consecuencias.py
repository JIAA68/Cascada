"""Consecuencias de un incendio simulado: activos alcanzados, efecto cascada y municipios.

- Activos alcanzados: la hora (minutos desde la ignición) a la que el fuego llega a menos de
  250 m de cada activo de la ventana. Casi todos los centros están
  en suelo urbano, sin combustible: la amenaza les llega desde el borde.
- Efecto cascada: cuando el fuego llega a una instalación peligrosa del catálogo, su zona de
  efectos se activa como amenaza derivada, con los activos que contiene.
  - Seveso (6_3, 6_4, 6_5): la instalación es el centro de su zona circular. Se activan la
    zona de intervención (nivel 2) y la de alerta (nivel 1).
  - Conducciones (6_12): el núcleo de la franja (nivel 3) es el trazado. Cuando el fuego entra
    en él se activa la franja (nivel 2 o más) en 750 m alrededor del tramo alcanzado.
- Municipios: primer minuto en que el fuego entra en cada municipio.
- Ruta del fuego hasta un activo: el camino por el que llega el fuego,
  reconstruido hacia atrás sobre el mapa de tiempos de llegada. El visor la usa para la flecha de
  los avisos anticipados.
"""
import math

import numpy as np
import pandas as pd
import rasterio
import shapely
from rasterio.warp import Resampling, reproject
from rasterio.features import shapes
from scipy.ndimage import minimum_filter
from scipy.spatial import cKDTree

from ..capas import SIN_DATO, tif
from ..fuentes import PROCESADOS
from ..rejilla import celda_de_utm, id_celda
from ..instalaciones import CAPAS_SEVESO
from .entradas import A_GEO, CRS, Ventana
from .propagacion import SALTO_M

DISTANCIA_ALCANZADO_M = 250
ALCANCE_CONDUCCION_M = 750   # mayor distancia de efectos de la memoria (charco de gasolinas, 738 m)


def capa_en_ventana(codigo: str, v: Ventana) -> np.ndarray:
    """Nivel máximo de una capa de peligrosidad (5 m) dentro de cada celda de la ventana."""
    destino = np.zeros((v.filas, v.columnas), dtype=np.uint8)
    with rasterio.open(tif(codigo)) as src:
        reproject(rasterio.band(src, 1), destino, dst_transform=v.transform, dst_crs=CRS, src_nodata=SIN_DATO,
                  dst_nodata=0, resampling=Resampling.max)
    return destino


def nivel_en_puntos(codigo: str, x, y) -> np.ndarray:
    """Nivel de una capa en puntos (EPSG:25830); 0 fuera de la Comunidad."""
    with rasterio.open(tif(codigo)) as src:
        v = np.array([s[0] for s in src.sample(zip(x, y))]) if len(x) else np.zeros(0)
    return np.where(v == SIN_DATO, 0, v)


def llegada_en_radio(llegada: np.ndarray, celda: float, radio_m: float) -> np.ndarray:
    """Para cada celda, el tiempo mínimo de llegada en las celdas cuyo centro está a radio_m o menos (un círculo)."""
    r = int(radio_m // celda)
    if not r:
        return llegada
    df, dc = np.ogrid[-r:r + 1, -r:r + 1]
    circulo = (df ** 2 + dc ** 2) * celda ** 2 <= radio_m ** 2
    return minimum_filter(llegada, footprint=circulo, mode="constant", cval=np.inf)


def _celdas(v: Ventana, x, y):
    return ((v.y0 - y) // v.celda).astype(int), ((x - v.x0) // v.celda).astype(int)


def activos_alcanzados(llegada: np.ndarray, v: Ventana, activos: pd.DataFrame) -> pd.DataFrame:
    """Activos de la ventana con llegada_min: minuto en que el fuego llega a menos de 250 m (NaN si no)."""
    a = activos[v.contiene(activos.x.values, activos.y.values)].copy()
    f, c = _celdas(v, a.x.values, a.y.values)
    t = llegada_en_radio(llegada, v.celda, DISTANCIA_ALCANZADO_M)[f, c]
    a["llegada_min"] = np.where(np.isfinite(t), t, np.nan)
    return a


def _minimo_cercano(llegada: np.ndarray, fila: int, col: int, k: int):
    """Celda con la llegada más temprana en el cuadrado de ±k celdas, o None si ninguna arde."""
    f0, f1 = max(fila - k, 0), min(fila + k + 1, llegada.shape[0])
    c0, c1 = max(col - k, 0), min(col + k + 1, llegada.shape[1])
    sub = llegada[f0:f1, c0:c1]
    if not np.isfinite(sub).any():
        return None
    i = int(np.argmin(np.where(np.isfinite(sub), sub, np.inf)))
    return f0 + i // sub.shape[1], c0 + i % sub.shape[1]


def ruta_del_fuego(llegada: np.ndarray, v: Ventana, x: float, y: float, radio_m: float = DISTANCIA_ALCANZADO_M,
                   paso_m: float = 100.0) -> list[list[float]]:
    """Camino por el que el fuego llega a un punto: [[lon, lat, minuto], ...] desde la ignición hasta el punto.

    Empieza en la celda que arde antes a menos de radio_m del punto (la que marca su llegada) y baja por el mapa de
    tiempos de llegada hasta la ignición: en cada paso, la celda que arde antes a ±2 celdas; si ninguna arde antes,
    a la distancia del salto de franjas sin combustible. Es una aproximación del camino de tiempo mínimo, no el
    camino exacto del cálculo de propagación. Se deja un punto cada
    paso_m metros. Vacía si el fuego no llega.
    """
    fila, col = v.fila_columna(x, y)
    actual = _minimo_cercano(llegada, fila, col, int(round(radio_m / v.celda)))
    if actual is None:
        return []
    llegada_punto = float(llegada[actual])
    celdas, salto = [actual], int(math.ceil(SALTO_M / v.celda)) + 1
    while llegada[actual] > 0:
        siguiente = None
        for k in (2, salto):
            c = _minimo_cercano(llegada, *actual, k)
            if c is not None and llegada[c] < llegada[actual]:
                siguiente = c
                break
        if siguiente is None:
            break
        celdas.append(siguiente)
        actual = siguiente
    puntos = [(v.x0 + (c + 0.5) * v.celda, v.y0 - (f + 0.5) * v.celda, float(llegada[f, c])) for f, c in reversed(celdas)]
    puntos.append((x, y, llegada_punto))
    ruta = [puntos[0]]
    for p in puntos[1:-1]:
        if math.hypot(p[0] - ruta[-1][0], p[1] - ruta[-1][1]) >= paso_m:
            ruta.append(p)
    ruta.append(puntos[-1])
    return [[round(lon, 5), round(lat, 5), round(m, 1)] for (px, py, m) in ruta for lon, lat in [A_GEO.transform(px, py)]]


def cascada_seveso(llegada: np.ndarray, v: Ventana, instalaciones: pd.DataFrame, activos: pd.DataFrame):
    """Zonas Seveso alcanzadas (con activacion_min) y activos en sus zonas de intervención y alerta."""
    ins = instalaciones[v.contiene(instalaciones.x.values, instalaciones.y.values)].copy()
    if ins.empty:
        return ins, pd.DataFrame()
    f, c = _celdas(v, ins.x.values, ins.y.values)
    ins["activacion_min"] = llegada_en_radio(llegada, v.celda, DISTANCIA_ALCANZADO_M)[f, c]
    ins = ins[np.isfinite(ins.activacion_min)]
    derivados = []
    for z in ins.itertuples():
        distancia = np.hypot(activos.x - z.x, activos.y - z.y)
        dentro = activos[distancia <= z.radio_alerta_m].copy()
        if dentro.empty:
            continue
        dentro["distancia_m"] = distancia[distancia <= z.radio_alerta_m]
        nivel = nivel_en_puntos(z.capa, dentro.x.values, dentro.y.values)  # el activo debe estar en la zona del catálogo
        dentro = dentro[nivel >= 1].assign(nivel_catalogo=nivel[nivel >= 1])
        # Intervención solo dentro del radio de intervención propio de la instalación: el
        # nivel 2 del catálogo en el punto puede ser de la zona de otra instalación cercana
        dentro["zona"] = np.where(dentro.distancia_m <= z.radio_intervencion_m, "intervención", "alerta")
        dentro = dentro.drop(columns="distancia_m")
        dentro["origen"], dentro["capa"], dentro["amenaza_derivada"] = z.id, z.capa, CAPAS_SEVESO[z.capa]
        dentro["activacion_min"] = z.activacion_min
        derivados.append(dentro)
    return ins, (pd.concat(derivados, ignore_index=True) if derivados else pd.DataFrame())


def cascada_conducciones(llegada: np.ndarray, v: Ventana, activos: pd.DataFrame):
    """Resumen del tramo de conducción alcanzado (o None) y activos en la franja cercana."""
    nivel = capa_en_ventana("6_12", v)
    nucleo = (nivel >= 3) & np.isfinite(llegada)
    if not nucleo.any():
        return None, pd.DataFrame()
    filas, cols = np.nonzero(nucleo)
    t = llegada[filas, cols]
    arbol = cKDTree(np.c_[v.x0 + (cols + 0.5) * v.celda, v.y0 - (filas + 0.5) * v.celda])
    a = activos.copy()
    vecinos = arbol.query_ball_point(np.c_[a.x, a.y], ALCANCE_CONDUCCION_M)
    a["activacion_min"] = [t[i].min() if i else np.nan for i in vecinos]
    a = a[a.activacion_min.notna()]
    if not a.empty:
        n = nivel_en_puntos("6_12", a.x.values, a.y.values)
        a = a[n >= 2].assign(nivel_catalogo=n[n >= 2])
        a["zona"] = np.where(a.nivel_catalogo >= 3, "franja moderada", "franja baja")
        a["origen"], a["capa"], a["amenaza_derivada"] = "conducción", "6_12", "incendio o explosión de la conducción"
    tramo = np.c_[v.x0 + (cols[t == t.min()][0] + 0.5) * v.celda, v.y0 - (filas[t == t.min()][0] + 0.5) * v.celda][0]
    x, y = v.x0 + (cols + 0.5) * v.celda, v.y0 - (filas + 0.5) * v.celda
    return {"primera_llegada_min": float(t.min()), "celdas_nucleo_alcanzadas": int(nucleo.sum()),
            "x": float(tramo[0]), "y": float(tramo[1]), "franja": franja_por_hora(x, y, t),
            "tramos": tramos_alcanzados(x, y, t)}, a


def tramos_alcanzados(x, y, t, separacion_m: float = 2 * ALCANCE_CONDUCCION_M) -> list[dict]:
    """Cada vez que el fuego alcanza un tramo nuevo de la conducción: [{"minutos", "x", "y"}].

    Un tramo es nuevo si el fuego llega a una celda del núcleo sin ninguna celda del núcleo alcanzada antes a menos de
    separacion_m (dos veces el alcance de la franja: su franja no se solapa con la ya activada). El primero es la
    primera llegada. Si el fuego avanza a lo largo de la conducción, no hay tramos nuevos.
    """
    orden = np.argsort(t, kind="stable")
    x, y, t = x[orden], y[orden], t[orden]
    vecinos = cKDTree(np.c_[x, y]).query_ball_point(np.c_[x, y], separacion_m)
    tramos = []
    for i, cerca in enumerate(vecinos):
        if min(cerca) < i:   # hay una celda del núcleo alcanzada antes (o a la vez, ya contada) a menos de separacion_m
            continue
        tramos.append({"minutos": round(float(t[i]), 1), "x": float(x[i]), "y": float(y[i])})
    return tramos


def franja_por_hora(x, y, t, alcance_m: float = ALCANCE_CONDUCCION_M, simplificar_m: float = 25.0) -> list[dict]:
    """Franja activada de la conducción a medida que el fuego alcanza su núcleo, para dibujarla.

    Para cada hora en que el fuego alcanza celdas nuevas del núcleo, la franja de alcance_m alrededor de todas las
    alcanzadas hasta entonces, en lon/lat: [{"minutos": primera llegada de esa hora, "hasta": la siguiente o None,
    "coords": polígonos [[[lon, lat], ...], ...] (anillo exterior de cada uno)}]. Es la zona de efectos aproximada
    para el mapa; los activos afectados se eligen con la capa 6_12 del catálogo (cascada_conducciones).
    """
    horas = np.floor(t / 60).astype(int)
    salida, acumulada = [], None
    for h in np.unique(horas):
        # Unión incremental: solo las celdas alcanzadas en esta hora se unen a la franja de las horas anteriores
        de_la_hora = horas == h
        nueva = shapely.union_all(shapely.buffer(shapely.points(x[de_la_hora], y[de_la_hora]), alcance_m, quad_segs=4))
        acumulada = nueva if acumulada is None else shapely.union(acumulada, nueva)
        zona = shapely.simplify(acumulada, simplificar_m)
        partes = list(zona.geoms) if zona.geom_type == "MultiPolygon" else [zona]
        salida.append({"minutos": round(float(t[horas == h].min()), 1),
                       "coords": [np.round(np.column_stack(A_GEO.transform(*np.asarray(p.exterior.coords).T)), 5).tolist()
                                  for p in partes]})
    for a, b in zip(salida, salida[1:]):
        a["hasta"] = b["minutos"]
    salida[-1]["hasta"] = None
    return salida


HUECO_MIN_M2 = 50_000      # huecos sin quemar de menos de 5 ha no se dibujan en las isocronas
ISLA_MIN_M2 = 10_000       # ni las manchas de menos de 1 ha


def isocronas(llegada: np.ndarray, v: Ventana, minuto_primera: float, cada_min: float = 60.0,
              horizonte_min: float = 24 * 60, simplificar_m: float = 50.0) -> list[dict]:
    """Contorno del área quemada a cada hora del reloj.

    minuto_primera: minutos desde la ignición hasta la primera hora en punto. Para cada hora, los anillos (exterior
    y huecos grandes) del área con llegada hasta entonces, simplificados y en lon/lat:
    [{"minutos": ..., "coords": [[[lon, lat], ...], ...]}]. El visor dibuja las de las próximas horas.
    """
    salida = []
    t = minuto_primera
    while t <= horizonte_min:
        quemado = np.isfinite(llegada) & (llegada <= t)
        if quemado.any():
            poligonos = [shapely.geometry.shape(g) for g, _ in shapes(quemado.astype(np.uint8), mask=quemado, transform=v.transform)]
            zona = shapely.simplify(shapely.union_all(poligonos), simplificar_m)
            anillos = []
            for p in (zona.geoms if zona.geom_type == "MultiPolygon" else [zona]):
                if p.area < ISLA_MIN_M2:
                    continue
                anillos.append(p.exterior)
                anillos += [h for h in p.interiors if shapely.Polygon(h).area >= HUECO_MIN_M2]
            if anillos:
                salida.append({"minutos": round(float(t), 1), "coords": [
                    np.round(np.column_stack(A_GEO.transform(*np.asarray(a.coords).T)), 5).tolist() for a in anillos]})
        t += cada_min
    return salida


def municipios_alcanzados(llegada: np.ndarray, indice: np.ndarray, lista, v: Ventana | None = None) -> list[dict]:
    """Municipios en los que entra el fuego, con el primer minuto, ordenados por ese minuto.

    Con la ventana, también el punto por el que entra (centro de la primera celda que arde en el municipio), que el
    visor usa para llevar la cámara a ese suceso de la cronología.
    """
    salida = []
    for i, (codigo, nombre) in enumerate(lista):
        dentro = indice == i + 1
        t = np.where(dentro, llegada, np.inf)
        if not np.isfinite(t).any():
            continue
        fila, col = np.unravel_index(int(np.argmin(t)), t.shape)
        m = {"codigo_ine": codigo, "nombre": nombre, "minutos": round(float(t[fila, col]), 1)}
        if v is not None:
            lon, lat = A_GEO.transform(v.x0 + (col + 0.5) * v.celda, v.y0 - (fila + 0.5) * v.celda)
            m["lon"], m["lat"] = round(lon, 5), round(lat, 5)
        salida.append(m)
    return sorted(salida, key=lambda d: d["minutos"])


def poblacion_por_celda(llegada: np.ndarray, v: Ventana) -> list[dict]:
    """Población del Censo 2021 de cada celda de 1 km a la que llega el fuego, con el primer minuto de llegada.

    Es la población de las celdas que toca el fuego: una cota alta, porque cuenta entera una
    celda en cuanto arde una parte de ella, aunque el casco urbano no arda. El visor suma las celdas con llegada hasta
    cada minuto. Solo se devuelven celdas con población.
    """
    filas, cols = np.nonzero(np.isfinite(llegada))
    if not len(filas):
        return []
    e, n = celda_de_utm(v.x0 + (cols + 0.5) * v.celda, v.y0 - (filas + 0.5) * v.celda)
    tabla = pd.DataFrame({"e": e, "n": n, "t": llegada[filas, cols]}).groupby(["e", "n"]).t.min()
    rejilla = pd.read_csv(PROCESADOS / "rejilla_1km.csv", usecols=["grd_id", "poblacion", "menores_16", "mayores_64"])         .set_index("grd_id")
    salida = []
    for (ek, nk), minuto in tabla.items():
        gid = id_celda(int(ek), int(nk))
        if gid not in rejilla.index or not rejilla.at[gid, "poblacion"]:
            continue
        f = rejilla.loc[gid]
        salida.append({"minutos": round(float(minuto), 1), "poblacion": int(f.poblacion),
                       "menores_16": int(f.menores_16), "mayores_64": int(f.mayores_64)})
    return sorted(salida, key=lambda d: d["minutos"])
