"""Avisos oficiales de fenómenos meteorológicos adversos de AEMET (Plan Meteoalerta), sin clave.

El RSS público de AEMET enlaza en su primer elemento el paquete tar.gz con todos los avisos vigentes y previstos de
España (hasta pasado mañana), uno por fichero CAP. Se descarga el paquete, se leen los CAP y se conservan los avisos
de las tres zonas de la Comunidad de Madrid de nivel amarillo o superior, con su polígono.

Si AEMET no responde se recurre a Meteoalarm (red europea que redistribuye los avisos de AEMET, licencia equivalente
a CC BY 4.0), que no trae polígono: se usa entonces la delimitación oficial de zonas de la cadena de datos.
"""
import io
import json
import re
import tarfile
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime

from ..fuentes import CACHE, descargar_vivo
from ..incendio.entradas import MADRID
from .umbrales import NIVELES, ZONAS, nombre_fenomeno

RSS = "https://www.aemet.es/documentos_d/eltiempo/prediccion/avisos/rss/CAP_AFAE_RSS.xml"
METEOALARM = "https://feeds.meteoalarm.org/api/v1/warnings/feeds-spain"
CARPETA = CACHE / "prealerta"
RENOVACION_S = 1800
NIVEL_DE_TEXTO = {"verde": 0, "amarillo": 1, "naranja": 2, "rojo": 3}
# Meteoalarm: tipo de aviso (awareness_type) -> código de fenómeno de Meteoalerta
TIPOS_METEOALARM = {"1": "VI", "2": "NE", "3": "TO", "4": "NI", "5": "AT", "6": "BT", "7": "CO", "8": "IF",
                    "9": "AV", "10": "PR", "12": "PR", "13": "PR"}
ZONA_POR_NOMBRE = {z["nombre"]: codigo for codigo, z in ZONAS.items()}
NS = "{urn:oasis:names:tc:emergency:cap:1.2}"
UA = {"User-Agent": "Cascada/1.0"}

_cache: dict = {}
_cerrojo = threading.Lock()


def _texto(nodo, etiqueta):
    e = nodo.find(NS + etiqueta)
    return (e.text or "").strip() if e is not None else ""


def _parametros(info, etiqueta):
    """{valueName: value} de los eventCode o parameter de un bloque info."""
    salida = {}
    for p in info.findall(NS + etiqueta):
        salida[_texto(p, "valueName")] = _texto(p, "value")
    return salida


def leer_cap(xml: bytes) -> list[dict]:
    """Avisos de un fichero CAP de AEMET, uno por zona, en castellano."""
    raiz = ET.fromstring(xml)
    salida = []
    for info in raiz.findall(NS + "info"):
        if not _texto(info, "language").startswith("es"):
            continue
        codigos, parametros = _parametros(info, "eventCode"), _parametros(info, "parameter")
        fenomeno = codigos.get("AEMET-Meteoalerta fenomeno", "")
        codigo, _, texto = fenomeno.partition(";")
        nivel = NIVEL_DE_TEXTO.get(parametros.get("AEMET-Meteoalerta nivel", "").lower())
        for area in info.findall(NS + "area"):
            zona = _parametros(area, "geocode").get("AEMET-Meteoalerta zona", "")
            # Una zona puede tener varios polígonos (exclaves); cada uno, anillo de [lon, lat]
            poligonos = [[[float(b), float(a)] for a, b in (par.split(",") for par in (p.text or "").split())]
                         for p in area.findall(NS + "polygon")]
            salida.append({
                "zona": zona, "zona_nombre": _texto(area, "areaDesc"),
                "fenomeno": codigo.strip(), "fenomeno_nombre": nombre_fenomeno(codigo.strip(), texto.strip()),
                "nivel": nivel if nivel is not None else 0, "nivel_nombre": NIVELES.get(nivel or 0, "verde"),
                "inicio": _texto(info, "onset"), "fin": _texto(info, "expires"),
                "umbral": parametros.get("AEMET-Meteoalerta parametro", "").partition(";")[2].partition(";")[2].strip(),
                "probabilidad": parametros.get("AEMET-Meteoalerta probabilidad", ""),
                "titular": _texto(info, "headline"), "descripcion": _texto(info, "description"),
                "poligonos": poligonos, "fuente": "AEMET",
            })
    return salida


def _de_aemet() -> list[dict]:
    with urllib.request.urlopen(urllib.request.Request(RSS, headers=UA), timeout=60) as r:
        rss = r.read().decode("utf-8", "replace")
    enlaces = re.findall(r"<link>([^<]+\.tar\.gz)</link>", rss)
    if not enlaces:
        raise RuntimeError("El RSS de avisos de AEMET no enlaza el paquete de avisos")
    ruta = descargar_vivo(enlaces[0], CARPETA / "avisos_cap.tar.gz", "AEMET, avisos CAP (Plan Meteoalerta)", espera=120)
    avisos = []
    with tarfile.open(ruta) as tar:
        for miembro in tar.getmembers():
            if not miembro.name.endswith(".xml"):
                continue
            for a in leer_cap(tar.extractfile(miembro).read()):
                if a["zona"] in ZONAS and a["nivel"] >= 1:
                    avisos.append(a)
    return avisos


def _de_meteoalarm() -> list[dict]:
    with urllib.request.urlopen(urllib.request.Request(METEOALARM, headers=UA), timeout=60) as r:
        datos = json.loads(r.read().decode("utf-8"))
    avisos = []
    for w in datos.get("warnings", []):
        for info in w.get("alert", {}).get("info", []):
            if not str(info.get("language", "es")).startswith("es"):
                continue
            parametros = {p.get("valueName"): p.get("value") for p in info.get("parameter", [])}
            nivel_txt = str(parametros.get("awareness_level", "")).split(";")
            nivel = int(nivel_txt[0]) - 1 if nivel_txt and nivel_txt[0].strip().isdigit() else 0
            tipo = str(parametros.get("awareness_type", "")).split(";")[0].strip()
            codigo = TIPOS_METEOALARM.get(tipo, "")
            if nivel < 1:
                continue
            for area in info.get("area", []):
                # Meteoalarm identifica la zona con el código EMMA ("ES722801"); el nombre, como respaldo
                geocodigos = {g.get("valueName"): str(g.get("value", "")) for g in area.get("geocode", [])}
                zona = geocodigos.get("EMMA_ID", "").removeprefix("ES")
                if zona not in ZONAS:
                    zona = ZONA_POR_NOMBRE.get(area.get("areaDesc", ""))
                if not zona:
                    continue
                avisos.append({
                    "zona": zona, "zona_nombre": ZONAS[zona]["nombre"], "fenomeno": codigo,
                    "fenomeno_nombre": nombre_fenomeno(codigo, info.get("event", "")), "nivel": min(nivel, 3),
                    "nivel_nombre": NIVELES[min(nivel, 3)], "inicio": info.get("onset", ""), "fin": info.get("expires", ""),
                    "umbral": "", "probabilidad": "", "titular": info.get("headline", ""),
                    "descripcion": info.get("description", ""), "poligonos": [], "fuente": "Meteoalarm"})
    return avisos


def avisos() -> dict:
    """Avisos vigentes y previstos de las zonas de Madrid, con caché de media hora."""
    with _cerrojo:
        if _cache and time.time() - _cache["hora"] < RENOVACION_S:
            return _cache["datos"]
        consultado = datetime.now(MADRID).isoformat(timespec="minutes")
        try:
            datos = {"fuente": "AEMET, avisos del Plan Meteoalerta (canal público)", "consultado": consultado, "avisos": _de_aemet()}
        except (OSError, RuntimeError, tarfile.TarError, ET.ParseError) as e:
            try:
                datos = {"fuente": "Meteoalarm (respaldo; AEMET no respondió)", "consultado": consultado,
                         "avisos": _de_meteoalarm(), "aviso_fuente": str(e)[:120]}
            except (OSError, ValueError) as e2:
                raise RuntimeError(f"Ni AEMET ni Meteoalarm responden: {e}; {e2}") from e2
        _cache.update(hora=time.time(), datos=datos)
        return datos


def _fecha(texto: str) -> date | None:
    try:
        return datetime.fromisoformat(texto.replace("-00:00", "+00:00")).astimezone(MADRID).date()
    except ValueError:
        return None


def por_dia(lista: list[dict], dia: date) -> list[dict]:
    """Avisos cuya vigencia toca el día (fechas locales de Madrid)."""
    salida = []
    for a in lista:
        inicio, fin = _fecha(a["inicio"]), _fecha(a["fin"])
        if inicio and fin and inicio <= dia <= fin:
            salida.append(a)
    return salida
