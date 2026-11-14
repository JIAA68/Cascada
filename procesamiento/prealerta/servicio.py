"""Servicio de la prealerta para el servidor: previsión en caché, actualización en segundo plano y resultados.

- La previsión de AEMET de los 179 municipios se guarda en datos/cache/prealerta/ (aemet.py). Si la guardada no
  es de hoy, o le faltan municipios, se lanza una actualización en segundo plano (como mucho una cada 15 minutos)
  y mientras tanto se sirve la última disponible, con su fecha de elaboración.
- Los avisos oficiales se consultan con caché de media hora (avisos.py).
- El resultado (calculo.calcular) se recalcula solo cuando cambian la previsión o los avisos.
"""
import json
import threading
from datetime import datetime

import pandas as pd

from ..consultas import NoEncontrado
from ..fuentes import PROCESADOS
from ..incendio.entradas import MADRID
from . import aemet, calculo
from . import avisos as modulo_avisos
from .umbrales import ZONAS

REINTENTO_S = 900
_estado = {"actualizando": False, "progreso": None, "error": None, "ultimo_intento": None}
_prevision = {"ruta": None, "mtime": None, "datos": None}
_resultado = {"clave": None, "datos": None}
_cerrojo = threading.Lock()


def lista_municipios() -> list[tuple[str, str]]:
    m = pd.read_csv(PROCESADOS / "municipios.csv", dtype={"codigo": str})
    return list(zip(m["codigo"], m["nombre"]))


def _progreso(i, n, nombre):
    _estado["progreso"] = {"hechos": i, "total": n, "municipio": nombre}


def _hilo_actualizar():
    try:
        r = aemet.actualizar(lista_municipios(), _progreso)
        if r.get("interrumpido"):
            _estado["error"] = r["interrumpido"] + "; se reintentará en unos minutos"
        elif not r["municipios"]:
            _estado["error"] = "AEMET OpenData no ha devuelto ninguna previsión"
        elif r["errores"]:
            _estado["error"] = f"{len(r['errores'])} municipios sin previsión (AEMET no respondió); se reintentará"
        else:
            _estado["error"] = None
    except Exception as e:  # noqa: BLE001  (el hilo debe dejar constancia de cualquier fallo)
        _estado["error"] = str(e)[:200]
    finally:
        _estado["ultimo_intento"] = datetime.now(MADRID).isoformat(timespec="minutes")
        _estado["actualizando"] = False
        _estado["progreso"] = None


def actualizar() -> dict:
    """Lanza la actualización de la previsión en segundo plano, si no hay otra en marcha."""
    with _cerrojo:
        if not _estado["actualizando"]:
            _estado["actualizando"] = True
            _estado["progreso"] = {"hechos": 0, "total": 0, "municipio": ""}
            threading.Thread(target=_hilo_actualizar, daemon=True).start()
    return estado()


def estado() -> dict:
    return dict(_estado)


def prevision() -> dict | None:
    """Última previsión guardada, releída solo si el fichero ha cambiado."""
    ficheros = sorted(aemet.CARPETA.glob("prevision_*.json")) if aemet.CARPETA.exists() else []
    if not ficheros:
        return None
    ruta = ficheros[-1]
    mtime = ruta.stat().st_mtime
    if _prevision["ruta"] != ruta or _prevision["mtime"] != mtime:
        _prevision.update(ruta=ruta, mtime=mtime, datos=json.loads(ruta.read_text(encoding="utf-8")))
    return _prevision["datos"]


def _conviene_actualizar(p) -> bool:
    if _estado["actualizando"]:
        return False
    hoy = datetime.now(MADRID).date().isoformat()
    if p is not None and p.get("dia") == hoy and not p.get("errores"):
        return False
    ultimo = _estado["ultimo_intento"]
    return ultimo is None or (datetime.now(MADRID) - datetime.fromisoformat(ultimo)).total_seconds() > REINTENTO_S


def resultado() -> dict:
    """Prealerta completa (con el detalle por municipio) con la última previsión y los avisos vigentes."""
    p = prevision()
    if _conviene_actualizar(p):
        actualizar()
    try:
        datos_avisos = modulo_avisos.avisos()
    except RuntimeError as e:
        datos_avisos = {"fuente": None, "consultado": None, "avisos": [], "error": str(e)[:200]}
    if p is None:
        return {"sin_prevision": True, "estado": estado(), "avisos": datos_avisos}
    clave = (p.get("consultado"), len(p["municipios"]), datos_avisos.get("consultado"), datos_avisos.get("fuente"))
    with _cerrojo:
        if _resultado["clave"] != clave:
            _resultado["datos"] = calculo.calcular(p, datos_avisos)
            _resultado["clave"] = clave
        datos = _resultado["datos"]
    datos["estado"] = estado()
    datos["avisos_error"] = datos_avisos.get("error")
    return datos


def _indice_dia(res, dia) -> int:
    fechas = res.get("fechas", [])
    if not fechas:
        raise NoEncontrado("No hay previsión")
    dia = str(dia)
    if "-" in dia:
        if dia not in fechas:
            raise NoEncontrado(f"No hay previsión para {dia}")
        return fechas.index(dia)
    i = int(dia)
    if not 0 <= i < len(fechas):
        raise NoEncontrado(f"No hay previsión para el día {i}")
    return i


def resumen() -> dict:
    """Lo que el visor necesita para el mapa y la tabla semanal (sin el detalle por municipio)."""
    return {k: v for k, v in resultado().items() if k != "detalle"}


def municipio(codigo: str, dia="0") -> dict:
    """Niveles de los 7 días de un municipio y sus activos con riesgo focal el día pedido."""
    res = resultado()
    if res.get("sin_prevision"):
        raise NoEncontrado("No hay previsión")
    if codigo not in res["detalle"]:
        raise NoEncontrado(f"Municipio {codigo} sin previsión")
    i = _indice_dia(res, dia)
    m = res["municipios"][codigo]
    return {"codigo": codigo, "nombre": m["nombre"], "zona": m["zona"], "zona_nombre": ZONAS[m["zona"]]["nombre"],
            "dia": i, "fecha": res["fechas"][i], "dias": res["detalle"][codigo],
            "activos": calculo.activos_afectados(res, i, codigo)}


def activos(dia="0") -> dict:
    """Activos de toda la Comunidad con riesgo focal un día."""
    res = resultado()
    if res.get("sin_prevision"):
        raise NoEncontrado("No hay previsión")
    i = _indice_dia(res, dia)
    return {"dia": i, "fecha": res["fechas"][i]} | calculo.activos_afectados(res, i)
