"""Carreteras y vías de tren afectadas por un incendio simulado, y trenes programados (decisión del 11-11-2026).

Las pistas forestales de la red no entran: en el mapa despistaban más que ayudaban (decisión del 12-11-2026).

- Un tramo está afectado **por el fuego** desde el minuto en que el fuego llega a menos de 250 m de alguno de sus
  puntos (la misma distancia que los activos): probable corte. Y **por el humo** desde el primer horizonte en que
  alguno de sus puntos queda bajo el humo: visibilidad reducida. Los puntos se toman cada 25 m (red_transporte).
- Trenes programados de Cercanías: con el horario de Renfe, los trenes que pasan por una estación cuando ya está
  afectada por el fuego o por el humo, dentro de las 24 horas simuladas. Se agrupan por línea y estación, con el
  primero y el número de trenes. No se estima cuántas personas llevan.
"""
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .. import cercanias, red_transporte
from .entradas import A_GEO, MADRID, Ventana
from .humo import primer_minuto_bajo_humo

HORIZONTE_MIN = 24 * 60
SIN_PISTAS = red_transporte.TIPOS.index("pista")
ETIQUETA_GRUPO = {"ferrocarril": "Vías de ferrocarril", "metro": "Vías de metro en superficie",
                  "tranvia": "Vías de tranvía"}


def _celdas(v: Ventana, x, y):
    return ((v.y0 - y) // v.celda).astype(int), ((x - v.x0) // v.celda).astype(int)


def _minuto(valor: float):
    return round(float(valor), 1) if np.isfinite(valor) else None


def vias_afectadas(llegada_250: np.ndarray, v: Ventana, zonas_humo) -> dict:
    """Tramos afectados (para dibujarlos) y su resumen por carretera o tipo de vía (para listas y cronología).

    llegada_250: para cada celda, el minuto en que el fuego llega a menos de 250 m (consecuencias.llegada_en_radio).
    """
    red = red_transporte.cargar()
    pts = red["puntos"]
    idx = np.nonzero(v.contiene(pts[:, 0], pts[:, 1]) & (red["tipo"][red["tramo_punto"]] != SIN_PISTAS))[0]
    if not len(idx):
        return {"tramos": [], "resumen": []}
    x, y, tramo = pts[idx, 0], pts[idx, 1], red["tramo_punto"][idx]
    f, c = _celdas(v, x, y)
    t_llamas, t_humo = llegada_250[f, c], primer_minuto_bajo_humo(zonas_humo, x, y)
    n = len(red["tipo"])
    llamas, humo = np.full(n, np.inf), np.full(n, np.inf)
    np.minimum.at(llamas, tramo, t_llamas)
    np.minimum.at(humo, tramo, t_humo)
    afectados = np.nonzero(np.isfinite(llamas) | np.isfinite(humo))[0]
    if not len(afectados):
        return {"tramos": [], "resumen": []}

    inicio = red["inicio_dibujo"]
    trozos = [red["dibujo"][inicio[i]:inicio[i + 1]] for i in afectados]
    todos = np.concatenate(trozos)
    lon, lat = A_GEO.transform(todos[:, 0], todos[:, 1])
    lonlat = np.round(np.column_stack([lon, lat]), 5)
    cortes = np.cumsum([len(t) for t in trozos])[:-1]
    tramos = [{"tipo": red_transporte.TIPOS[red["tipo"][i]], "codigo": red["codigo"][i] or None,
               "llamas": _minuto(llamas[i]), "humo": _minuto(humo[i]), "coords": coords.tolist()}
              for i, coords in zip(afectados, np.split(lonlat, cortes))]

    # Resumen: cada carretera por su código (o nombre), y las vías de tren agrupadas por tipo
    tipos = np.array(red_transporte.TIPOS)[red["tipo"][tramo]]
    clave = np.where(tipos == "carretera", red["codigo"][tramo], tipos)
    puntos = pd.DataFrame({"clave": clave, "tipo": tipos, "tramo": tramo, "llamas": t_llamas, "humo": t_humo, "x": x, "y": y})
    puntos = puntos[np.isfinite(puntos.llamas) | np.isfinite(puntos.humo)]
    puntos["primero"] = puntos[["llamas", "humo"]].min(axis=1)
    resumen = []
    for k, g in puntos.groupby("clave"):
        p = g.loc[g.primero.idxmin()]
        plon, plat = A_GEO.transform(p.x, p.y)
        tipo = g.tipo.iloc[0]
        via = (k or "Carreteras sin código") if tipo == "carretera" else ETIQUETA_GRUPO[tipo]
        r = {"via": via, "tipo": tipo, "llamas": _minuto(g.llamas.min()), "humo": _minuto(g.humo.min()),
             "km_llamas": round(float(red["largo"][g[np.isfinite(g.llamas)].tramo.unique()].sum()) / 1000, 1),
             "lon": round(plon, 5), "lat": round(plat, 5)}
        if np.isfinite(g.llamas).any():
            # Punto por el que llega el fuego, para anunciarlo en el mapa (decisión del 12-11-2026)
            q = g.loc[g.llamas.idxmin()]
            llon, llat = A_GEO.transform(q.x, q.y)
            r["lon_llamas"], r["lat_llamas"] = round(llon, 5), round(llat, 5)
        resumen.append(r)
    resumen.sort(key=lambda r: min(m for m in (r["llamas"], r["humo"]) if m is not None))
    return {"tramos": tramos, "resumen": resumen}


def dia_equivalente(dia, desde: str, hasta: str):
    """Fecha del horario con el mismo día de la semana que `dia`, con un día de margen a cada lado, o None si no cabe."""
    primero = datetime.strptime(desde, "%Y%m%d").date() + timedelta(days=1)
    ultimo = datetime.strptime(hasta, "%Y%m%d").date() - timedelta(days=1)
    candidato = primero + timedelta(days=(dia.weekday() - primero.weekday()) % 7)
    return candidato if candidato <= ultimo else None


def trenes_programados(llegada_250: np.ndarray, v: Ventana, zonas_humo, inicio: datetime) -> dict:
    """Estaciones de Cercanías afectadas y trenes programados que pasan por ellas cuando ya lo están.

    Si la fecha simulada cae fuera del horario descargado (30 días), se usan los trenes del mismo día de la semana dentro
    del horario (decisión del 13-11-2026) y la respuesta dice qué día se ha tomado.
    """
    estaciones, pasos = cercanias.cargar()
    fechas = (pasos.fecha.min(), pasos.fecha.max())
    hora0 = inicio.astimezone(MADRID)
    con_horario = fechas[0] <= hora0.strftime("%Y%m%d") <= fechas[1]
    salida = {"horario_desde": fechas[0], "horario_hasta": fechas[1], "con_horario": con_horario, "estaciones": [], "trenes": []}
    if not con_horario:
        equivalente = dia_equivalente(hora0.date(), *fechas)
        if equivalente is not None:
            hora0 = hora0.replace(year=equivalente.year, month=equivalente.month, day=equivalente.day)
            con_horario = True
            salida.update(con_horario=True, dia_equivalente=equivalente.strftime("%Y%m%d"))
    e = estaciones[v.contiene(estaciones.x.values, estaciones.y.values)].copy()
    if e.empty:
        return salida
    f, c = _celdas(v, e.x.values, e.y.values)
    e["llamas"], e["humo"] = llegada_250[f, c], primer_minuto_bajo_humo(zonas_humo, e.x.values, e.y.values)
    e = e[np.isfinite(e.llamas) | np.isfinite(e.humo)]
    e["afectada"] = e[["llamas", "humo"]].min(axis=1)
    salida["estaciones"] = [{"nombre": r.nombre, "lon": r.lon, "lat": r.lat, "llamas": _minuto(r.llamas), "humo": _minuto(r.humo)}
                            for r in e.sort_values("afectada").itertuples()]
    if e.empty or not con_horario:
        return salida
    # Pasos por esas estaciones en las fechas de servicio que tocan las 24 horas simuladas
    dias = [(hora0.date() + timedelta(days=d)) for d in (-1, 0, 1)]
    medianoche = {d.strftime("%Y%m%d"): datetime(d.year, d.month, d.day, tzinfo=MADRID) for d in dias}
    p = pasos[pasos.stop_id.isin(set(e.stop_id)) & pasos.fecha.isin(set(medianoche))].copy()
    if p.empty:
        return salida
    base = p.fecha.map(lambda d: (medianoche[d] - hora0).total_seconds() / 60)
    p["minutos"] = base + p.segundos / 60
    p = p.merge(e[["stop_id", "nombre", "lon", "lat", "llamas", "afectada"]], on="stop_id")
    p = p[(p.minutos >= p.afectada) & (p.minutos >= 0) & (p.minutos <= HORIZONTE_MIN)]
    trenes = []
    for (linea, estacion), g in p.sort_values("minutos").groupby(["linea", "nombre"], sort=False):
        primero, con_llamas = g.iloc[0], g[g.minutos >= g.llamas]
        trenes.append({"linea": linea, "estacion": estacion, "lon": float(primero.lon), "lat": float(primero.lat),
                       "minutos": round(float(primero.minutos), 1), "hacia": str(primero.destino),
                       "efecto": "llamas" if primero.minutos >= primero.llamas else "humo", "trenes": int(g.trip_id.nunique()),
                       "trenes_llamas": int(con_llamas.trip_id.nunique()),
                       "primero_llamas": round(float(con_llamas.minutos.iloc[0]), 1) if len(con_llamas) else None})
    salida["trenes"] = sorted(trenes, key=lambda t: t["minutos"])
    return salida
