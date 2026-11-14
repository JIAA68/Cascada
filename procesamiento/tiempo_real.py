"""Movilidad en tiempo real: trenes de viajeros y tráfico (decisión del 08-11-2026).

Tres fuentes abiertas, sin clave, que se consultan bajo demanda y se guardan un rato en memoria:

- Trenes de viajeros de Renfe (GTFS-Realtime, CC BY 4.0): posición de cada tren, cada 30 s.
  Activos dinámicos (decisión del 30-10-2026): no se estima cuántas personas llevan.
- Tráfico de la ciudad de Madrid (Ayuntamiento de Madrid, portal de datos abiertos): nivel de
  servicio de unos 3.600 puntos de medida, cada 5 min. Solo cubre el municipio de Madrid.
- Incidencias de la DGT (punto de acceso nacional, DATEX II): obras, cortes, accidentes y
  retenciones en las carreteras de toda la Comunidad, cada 5 min.

Cada descarga se guarda en datos/cache/tiempo_real/ (sustituye a la anterior) y se anota en el
registro local de descargas de uso.
"""
import json
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import numpy as np
import shapely

from .fuentes import CACHE, descargar_vivo

URL_TRENES = "https://gtfsrt.renfe.com/vehicle_positions.json"
URL_CIUDAD = "https://informo.madrid.es/informo/tmadrid/pm.xml"
URL_DGT = "https://nap.dgt.es/datex2/v3/dgt/SituationPublication/datex2_v37.xml"
CARPETA = CACHE / "tiempo_real"
RENOVACION_S = {"trenes": 30, "ciudad": 300, "incidencias": 300}
FUENTES = {
    "trenes": "Renfe, GTFS-Realtime (CC BY 4.0)",
    "ciudad": "Ayuntamiento de Madrid, tráfico en tiempo real",
    "incidencias": "DGT, punto de acceso nacional (DATEX II)",
}

ESTADOS_TREN = {"STOPPED_AT": "parado en estación", "IN_TRANSIT_TO": "en marcha", "INCOMING_AT": "llegando a estación"}
NIVELES_CIUDAD = {0: "fluido", 1: "lento", 2: "retenciones", 3: "congestión"}

# Incidencias de la DGT: subtipo DATEX II -> texto. Los cortes completos se distinguen en el mapa.
INCIDENCIAS = {
    "roadClosed": "Carretera cortada", "carriagewayClosures": "Calzada cortada", "laneClosures": "Carril cortado",
    "intermittentShortTermClosures": "Cortes intermitentes", "singleAlternateLineTraffic": "Paso alternativo",
    "narrowLanes": "Carriles estrechos", "lanesDeviated": "Carriles desviados", "newRoadworksLayout": "Desvío por obras",
    "useOfSpecifiedLanesOrCarriagewaysAllowed": "Uso de carriles habilitados",
    "doNotUseSpecifiedLanesOrCarriageways": "Carriles no utilizables",
    "roadworks": "Obras", "accident": "Accidente", "vehicleStuck": "Vehículo detenido",
    "vehicleOnFire": "Vehículo en llamas", "objectOnTheRoad": "Objeto en la calzada",
    "obstructionOnTheRoad": "Obstáculo en la calzada", "spillageOnTheRoad": "Vertido en la calzada",
    "rockfalls": "Desprendimientos", "avalanches": "Aludes", "flooding": "Inundación", "fog": "Niebla",
    "visibilityReduced": "Visibilidad reducida", "smokeHazard": "Humo", "forestFire": "Incendio forestal",
    "roadSurfaceInPoorCondition": "Firme en mal estado", "weightRestrictionInOperation": "Restricción de peso",
    "vehicleWithOverwideLoad": "Transporte especial", "slowTraffic": "Tráfico lento",
    "stationaryTraffic": "Tráfico detenido", "queuingTraffic": "Retenciones", "heavyTraffic": "Tráfico denso",
}
CORTES = {"roadClosed", "carriagewayClosures"}
TRAFICO = {"slowTraffic", "stationaryTraffic", "queuingTraffic", "heavyTraffic"}
SENTIDOS = {"northBound": "norte", "southBound": "sur", "eastBound": "este", "westBound": "oeste",
            "northEastBound": "noreste", "northWestBound": "noroeste", "southEastBound": "sureste",
            "southWestBound": "suroeste", "bothWays": "ambos sentidos"}


# ----------------------------------------------------------------------------- utilidades
def _comunidad():
    from .incendio.focos import _comunidad as limite
    return limite()


def dentro(elementos: list[dict], limite=None) -> list[dict]:
    """Elementos (con lon y lat) dentro de la Comunidad de Madrid."""
    from .incendio.entradas import A_UTM
    if not elementos:
        return []
    x, y = A_UTM.transform(np.array([e["lon"] for e in elementos], dtype=float),
                           np.array([e["lat"] for e in elementos], dtype=float))
    si = shapely.contains_xy(limite if limite is not None else _comunidad(), x, y)
    return [e for e, d in zip(elementos, si) if d]


def hora_local(segundos_o_iso) -> str | None:
    """Marca de tiempo (segundos Unix o ISO 8601) en hora de Madrid, o None."""
    from .incendio.entradas import MADRID
    if segundos_o_iso in (None, ""):
        return None
    try:
        t = datetime.fromtimestamp(int(segundos_o_iso), timezone.utc)
    except (TypeError, ValueError):
        try:
            t = datetime.fromisoformat(str(segundos_o_iso))
        except ValueError:
            return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=MADRID)
    return t.astimezone(MADRID).isoformat(timespec="minutes")


def _numero(texto):
    """'436008,175' -> 436008.175; None si no es un número."""
    try:
        return float(str(texto).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def _local(etiqueta: str) -> str:
    return etiqueta.rsplit("}", 1)[-1]


# ----------------------------------------------------------------------------- lectores (sin red)
def leer_trenes(feed: dict) -> list[dict]:
    """Trenes del feed GTFS-Realtime de posiciones, con los campos que usa el visor."""
    trenes = []
    for e in feed.get("entity", []):
        v = e.get("vehicle") or {}
        p = v.get("position") or {}
        if "latitude" not in p or "longitude" not in p:
            continue
        etiqueta = (v.get("vehicle") or {}).get("label", "") or ""
        trenes.append({"id": e.get("id"), "lon": float(p["longitude"]), "lat": float(p["latitude"]),
                       "linea": etiqueta.split("-")[0].strip() or "?", "etiqueta": etiqueta,
                       "estado": ESTADOS_TREN.get(v.get("currentStatus"), v.get("currentStatus") or "sin dato"),
                       "parada": v.get("stopId"), "viaje": (v.get("trip") or {}).get("tripId"),
                       "hora": hora_local(v.get("timestamp"))})
    return trenes


def leer_ciudad(xml: bytes) -> tuple[str | None, list[dict]]:
    """Puntos de medida del tráfico de la ciudad con nivel de servicio válido y sin error."""
    from .incendio.entradas import A_GEO
    raiz = ET.fromstring(xml)
    puntos = []
    for pm in raiz.iter("pm"):
        d = {c.tag: (c.text or "").strip() for c in pm}
        nivel, x, y = _numero(d.get("nivelServicio")), _numero(d.get("st_x")), _numero(d.get("st_y"))
        if d.get("error") == "S" or nivel not in (0, 1, 2, 3) or x is None or y is None:
            continue
        puntos.append({"id": d.get("idelem"), "descripcion": d.get("descripcion") or "", "nivel": int(nivel),
                       "nivel_nombre": NIVELES_CIUDAD[int(nivel)], "intensidad": _numero(d.get("intensidad")),
                       "ocupacion": _numero(d.get("ocupacion")), "carga": _numero(d.get("carga")),
                       "velocidad": _numero(d.get("velocidad")), "x": x, "y": y})
    if puntos:
        lon, lat = A_GEO.transform(np.array([p["x"] for p in puntos]), np.array([p["y"] for p in puntos]))
        for p, a, b in zip(puntos, lon, lat):
            p["lon"], p["lat"] = round(float(a), 6), round(float(b), 6)
            del p["x"], p["y"]
    return raiz.findtext("fecha_hora"), puntos


def _coordenadas(nodo):
    lat, lon = _numero(nodo.findtext(".//{*}latitude")), _numero(nodo.findtext(".//{*}longitude"))
    return (lon, lat) if lat is not None and lon is not None else None


def leer_incidencias(xml: bytes) -> list[dict]:
    """Incidencias de la DGT (DATEX II v3): tipo, carretera, tramo y coordenadas de inicio y fin."""
    incidencias = []
    for registro in ET.fromstring(xml).iter():
        if _local(registro.tag) != "situationRecord":
            continue
        valores, extremos, punto = {}, {}, None
        for nodo in registro.iter():
            nombre = _local(nodo.tag)
            if nombre in ("from", "to") and nombre not in extremos:
                extremos[nombre] = _coordenadas(nodo)
            elif nombre == "pointCoordinates" and punto is None:
                punto = _coordenadas(nodo)
            if nodo.text and nodo.text.strip() and nombre not in valores:
                valores[nombre] = nodo.text.strip()
        gestion = valores.get("roadOrCarriagewayOrLaneManagementType")
        subtipos = [v for k, v in valores.items() if k.endswith("Type") and v in INCIDENCIAS]
        clave = gestion if gestion in CORTES else next(iter(subtipos), gestion)
        inicio, fin = extremos.get("from") or punto or extremos.get("to"), extremos.get("to")
        if inicio is None:
            continue
        incidencias.append({
            "id": registro.get("id"), "tipo": INCIDENCIAS.get(clave, "Incidencia"),
            "categoria": "corte" if clave in CORTES else "trafico" if clave in TRAFICO else "incidencia",
            "carretera": valores.get("roadName", ""), "sentido": SENTIDOS.get(valores.get("tpegDirection"), ""),
            "municipio": valores.get("municipality", ""), "km": _numero(valores.get("kilometerPoint")),
            "gravedad": valores.get("severity"), "desde": hora_local(valores.get("overallStartTime")),
            "hasta": hora_local(valores.get("overallEndTime")),
            "lon": inicio[0], "lat": inicio[1], "fin": list(fin) if fin and fin != inicio else None})
    return incidencias


# ----------------------------------------------------------------------------- consultas con caché
_cache: dict[str, tuple[float, dict]] = {}
_cerrojos = {clave: threading.Lock() for clave in RENOVACION_S}


def _con_cache(clave: str, obtener) -> dict:
    with _cerrojos[clave]:
        guardado = _cache.get(clave)
        if guardado and time.time() - guardado[0] < RENOVACION_S[clave]:
            return guardado[1]
        datos = {"fuente": FUENTES[clave], "consultado": hora_local(time.time()), **obtener()}
        _cache[clave] = (time.time(), datos)
        return datos


def _trenes():
    ruta = descargar_vivo(URL_TRENES, CARPETA / "renfe_posiciones.json", "Renfe, GTFS-Realtime, posiciones de trenes")
    feed = json.loads(ruta.read_bytes().decode("utf-8"))
    return {"marca": hora_local((feed.get("header") or {}).get("timestamp")), "trenes": dentro(leer_trenes(feed))}


def _ciudad():
    ruta = descargar_vivo(URL_CIUDAD, CARPETA / "madrid_trafico_pm.xml", "Ayuntamiento de Madrid, tráfico en tiempo real")
    marca, puntos = leer_ciudad(ruta.read_bytes())
    return {"marca": marca, "puntos": puntos}


def _incidencias():
    ruta = descargar_vivo(URL_DGT, CARPETA / "dgt_incidencias.xml", "DGT, incidencias DATEX II", espera=120)
    return {"incidencias": dentro(leer_incidencias(ruta.read_bytes()))}


def trenes() -> dict:
    return _con_cache("trenes", _trenes)


def ciudad() -> dict:
    return _con_cache("ciudad", _ciudad)


def incidencias() -> dict:
    return _con_cache("incidencias", _incidencias)


def con_error(clave: str, obtener) -> dict:
    """Consulta una fuente; si falla, devuelve el error en lugar de propagarlo."""
    try:
        return obtener()
    except (OSError, ValueError, ET.ParseError) as e:
        return {"fuente": FUENTES[clave], "error": f"No responde: {e}"}


def trafico() -> dict:
    """Tráfico de la ciudad e incidencias de la DGT; si una fuente falla, la otra se devuelve igual."""
    return {"ciudad": con_error("ciudad", ciudad), "incidencias": con_error("incidencias", incidencias)}
