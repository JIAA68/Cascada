"""Trenes y tráfico en tiempo real frente a un incendio simulado.

Cruza la situación actual (posición de los trenes de viajeros, incidencias de la DGT y puntos de
medida del tráfico de la ciudad) con la evolución estimada de una simulación guardada:

- llamas: minuto en que el fuego llega a menos de 250 m del elemento (la misma distancia de
  "alcanzado" que los activos);
- humo: primer minuto (en pasos de 5 min, humo.PASO_MIN) en que el elemento queda bajo la zona de humo.

Es una foto del momento de la consulta: un tren se mueve y no se proyecta su recorrido. Sirve
para ver qué trenes circulan ahora por la zona que se verá afectada y qué carreteras de la zona
tienen ya obras, cortes o retenciones.
"""
import json

import numpy as np
import pandas as pd
import rasterio

from .. import tiempo_real
from .consecuencias import DISTANCIA_ALCANZADO_M, llegada_en_radio
from .entradas import A_UTM, Ventana
from .humo import activos_bajo_humo, zonas_de_humo
from .propagacion import Viento
from .simulacion import ID_VALIDO
from . import simulacion

FUENTES = {
    "trenes": (tiempo_real.trenes, "trenes"),
    "incidencias": (tiempo_real.incidencias, "incidencias"),
    "ciudad": (tiempo_real.ciudad, "puntos"),
}


def cargar(id_simulacion: str):
    """Mapa de llegada (minutos, inf si no llega), ventana y vientos de una simulación guardada."""
    carpeta = simulacion.CARPETA / id_simulacion
    if not ID_VALIDO.fullmatch(id_simulacion) or not (carpeta / "llegada.tif").is_file():
        raise FileNotFoundError(id_simulacion)
    with rasterio.open(carpeta / "llegada.tif") as src:
        t, tr = src.read(1), src.transform
    v = Ventana(tr.c, tr.f, tr.a, t.shape[0], t.shape[1])
    respuesta = json.loads((carpeta / "respuesta.json").read_text(encoding="utf-8"))
    vientos = [Viento(w["velocidad_kmh"], w["desde"]) for w in respuesta["vientos_por_hora"]]
    return np.where(t < 0, np.inf, t), v, vientos


def evaluar(elementos: list[dict], llegada_250: np.ndarray, v: Ventana, zonas_humo) -> list[dict]:
    """Elementos alcanzados por las llamas o el humo, con sus minutos, ordenados por el primero.

    Una incidencia de la DGT que ocupa un tramo cuenta por el primero de sus dos extremos."""
    puntos = [(i, e["lon"], e["lat"]) for i, e in enumerate(elementos)]
    puntos += [(i, *e["fin"]) for i, e in enumerate(elementos) if e.get("fin")]
    if not puntos:
        return []
    indice = np.array([p[0] for p in puntos])
    x, y = A_UTM.transform(np.array([p[1] for p in puntos]), np.array([p[2] for p in puntos]))
    dentro = v.contiene(x, y)
    llamas = np.full(len(puntos), np.inf)
    f, c = ((v.y0 - y[dentro]) // v.celda).astype(int), ((x[dentro] - v.x0) // v.celda).astype(int)
    llamas[dentro] = llegada_250[f, c]
    tabla = pd.DataFrame({"x": x, "y": y})
    bajo_humo = activos_bajo_humo(zonas_humo, tabla)
    humo = np.full(len(puntos), np.inf)
    humo[bajo_humo.index.values] = bajo_humo.humo_min.values
    salida = []
    for i, e in enumerate(elementos):
        m_llamas, m_humo = llamas[indice == i].min(), humo[indice == i].min()
        if np.isfinite(m_llamas) or np.isfinite(m_humo):
            salida.append({**e, "minutos_llamas": round(float(m_llamas), 1) if np.isfinite(m_llamas) else None,
                           "minutos_humo": round(float(m_humo), 1) if np.isfinite(m_humo) else None,
                           "minutos": round(float(min(m_llamas, m_humo)), 1)})
    return sorted(salida, key=lambda e: e["minutos"])


def cruce(id_simulacion: str, fuentes: dict | None = None) -> dict:
    """Trenes, incidencias y tráfico de la ciudad actuales dentro de la zona afectada de una simulación."""
    llegada, v, vientos = cargar(id_simulacion)
    llegada_250 = llegada_en_radio(llegada, v.celda, DISTANCIA_ALCANZADO_M)
    zonas_humo = zonas_de_humo(llegada, v, vientos)
    salida = {"id": id_simulacion, "distancia_alcanzado_m": DISTANCIA_ALCANZADO_M}
    for clave, (obtener, campo) in (fuentes or FUENTES).items():
        datos = tiempo_real.con_error(clave, obtener)
        if "error" in datos:
            salida[clave] = datos
            continue
        salida[clave] = {k: datos[k] for k in ("fuente", "consultado", "marca") if k in datos}
        salida[clave]["total"] = len(datos[campo])
        salida[clave]["afectados"] = evaluar(datos[campo], llegada_250, v, zonas_humo)
    return salida
