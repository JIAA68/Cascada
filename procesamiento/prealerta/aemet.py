"""Previsión de AEMET OpenData para la prealerta: diaria a 7 días y horaria a 3 días de cada municipio.

- La previsión diaria por municipio trae, para 7 días, temperaturas máxima y mínima, humedad relativa, viento por
  periodos, racha máxima (cuando AEMET la da), probabilidad de precipitación, cota de nieve y estado del cielo.
- La horaria (unos 3 días) añade la precipitación y la nieve en milímetros por hora, la racha por hora y la
  probabilidad de tormenta: solo se pide para los municipios cuya diaria anuncia precipitación, tormenta o nieve
  en esos días.
- Cada respuesta se guarda en datos/cache/prealerta/ con el día de referencia en el nombre, de modo que repetir la
  actualización el mismo día no vuelve a llamar a AEMET. Las descargas van al registro local.
- El resultado de una actualización se guarda en prevision_<AAAAMMDD>.json; la última disponible es la que sirve el
  servidor aunque sea de otro día (se indica la fecha de elaboración).

AEMET OpenData se cae o responde despacio con frecuencia: cada municipio se pide con reintentos y, si falla, se anota
el error y se sigue con el resto.
"""
import json
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path

from ..fuentes import CACHE, descargar
from ..incendio.entradas import AEMET, MADRID, _clave_aemet
from .umbrales import CIELO_NIEVE, CIELO_TORMENTA

CARPETA = CACHE / "prealerta"
PROB_PRECIP_HORARIA = 30     # % de probabilidad de precipitación en la diaria a partir del cual se pide la horaria
PAUSA_S = 0.5                # entre peticiones, para no saturar a AEMET
REINTENTOS = 2
ESPERA_S = 15
FALLOS_SEGUIDOS_MAX = 3      # municipios seguidos sin respuesta a partir de los cuales se da AEMET por caído


def _numero(v):
    try:
        return float(str(v).replace(",", ".")) if v not in (None, "") else None
    except ValueError:
        return None


def _decodificar(b: bytes):
    try:
        return json.loads(b.decode("utf-8"))
    except UnicodeDecodeError:
        return json.loads(b.decode("latin-1"))


def _peticion(ruta: str, destino: Path):
    """Llamada de dos pasos a AEMET OpenData, con caché por fichero de destino y reintentos."""
    if destino.exists():
        return _decodificar(destino.read_bytes())
    cab = {"api_key": _clave_aemet()}
    ultimo = None
    for intento in range(REINTENTOS):
        try:
            with urllib.request.urlopen(urllib.request.Request(AEMET + ruta, headers=cab), timeout=ESPERA_S) as r:
                meta = _decodificar(r.read())
            if "datos" not in meta:
                raise RuntimeError(f"AEMET {ruta}: {meta.get('descripcion')}")
            descargar(meta["datos"], destino, f"AEMET OpenData {ruta}")
            return _decodificar(destino.read_bytes())
        except OSError as e:
            ultimo = e
            time.sleep(2 + 3 * intento)
    raise RuntimeError(f"AEMET OpenData no responde ({getattr(ultimo, 'reason', ultimo)})")


def diaria(codigo: str, dia: date):
    return _peticion(f"/prediccion/especifica/municipio/diaria/{codigo}", CARPETA / f"aemet_diaria_{codigo}_{dia:%Y%m%d}.json")


def horaria(codigo: str, dia: date):
    return _peticion(f"/prediccion/especifica/municipio/horaria/{codigo}", CARPETA / f"aemet_horaria_{codigo}_{dia:%Y%m%d}.json")


# ----------------------------------------------------------------------------- lectura de las respuestas
def _maximo(lista, clave="value"):
    valores = [_numero(e.get(clave)) for e in lista or []]
    valores = [v for v in valores if v is not None]
    return max(valores) if valores else None


def leer_diaria(datos) -> dict:
    """Previsión diaria parseada: elaborado, nombre y una entrada por día."""
    raiz = datos[0]
    dias = []
    for d in raiz["prediccion"]["dia"]:
        temp, hum = d.get("temperatura") or {}, d.get("humedadRelativa") or {}
        cielo = [e for e in d.get("estadoCielo") or [] if e.get("value")]
        codigos = {str(e["value"]).replace("n", "") for e in cielo}
        cotas = [_numero(e.get("value")) for e in d.get("cotaNieveProv") or []]
        cotas = [c for c in cotas if c is not None]
        dias.append({
            "fecha": d["fecha"][:10],
            "tmax": _numero(temp.get("maxima")), "tmin": _numero(temp.get("minima")),
            "hr_max": _numero(hum.get("maxima")), "hr_min": _numero(hum.get("minima")),
            "viento_max": _maximo(d.get("viento"), "velocidad"),
            "racha_max": _maximo(d.get("rachaMax")),
            "prob_precip": _maximo(d.get("probPrecipitacion")),
            "cota_nieve": min(cotas) if cotas else None,
            "cielo": sorted(codigos),
            "cielo_texto": next((e.get("descripcion") for e in cielo if e.get("periodo") in ("00-24", None) and e.get("descripcion")),
                                cielo[-1].get("descripcion") if cielo else ""),
            "tormenta_cielo": bool(codigos & CIELO_TORMENTA),
            "nieve_cielo": bool(codigos & CIELO_NIEVE),
            "uv": _numero(d.get("uvMax")),
        })
    return {"elaborado": raiz.get("elaborado"), "nombre": raiz.get("nombre"), "dias": dias}


def leer_horaria(datos) -> dict:
    """Por fecha: precipitación máxima en 1 h y en 12 h, acumulada, nieve acumulada, racha y probabilidad de tormenta."""
    salida = {}
    for d in datos[0]["prediccion"]["dia"]:
        lluvia = [_numero(e.get("value")) or 0.0 for e in d.get("precipitacion") or []]
        nieve = [_numero(e.get("value")) or 0.0 for e in d.get("nieve") or []]
        rachas = [_numero(e.get("value")) for e in d.get("vientoAndRachaMax") or [] if "value" in e]
        rachas = [r for r in rachas if r is not None]
        acumulado = [sum(lluvia[max(0, i - 11):i + 1]) for i in range(len(lluvia))]
        salida[d["fecha"][:10]] = {
            "pr1_max": round(max(lluvia), 1) if lluvia else None,
            "pr12_max": round(max(acumulado), 1) if acumulado else None,
            "pr24": round(sum(lluvia), 1) if lluvia else None,
            "nieve24": round(sum(nieve), 1) if nieve else None,
            "racha_max": max(rachas) if rachas else None,
            "prob_tormenta": _maximo(d.get("probTormenta")),
            "prob_nieve": _maximo(d.get("probNieve")),
            "horas": len(lluvia),
        }
    return salida


def necesita_horaria(diaria_leida: dict) -> bool:
    """Si en los tres primeros días la diaria anuncia precipitación, tormenta o nieve."""
    for d in diaria_leida["dias"][:3]:
        if (d["prob_precip"] or 0) >= PROB_PRECIP_HORARIA or d["tormenta_cielo"] or d["nieve_cielo"]:
            return True
    return False


# ----------------------------------------------------------------------------- actualización completa
def fichero_prevision(dia: date) -> Path:
    return CARPETA / f"prevision_{dia:%Y%m%d}.json"


def actualizar(municipios: list[tuple[str, str]], progreso=None, dia: date | None = None) -> dict:
    """Previsión de todos los municipios para el día de referencia (hoy); guarda y devuelve el resultado."""
    dia = dia or datetime.now(MADRID).date()
    resultado = {"dia": dia.isoformat(), "elaborado": None, "consultado": datetime.now(MADRID).isoformat(timespec="minutes"),
                 "municipios": {}, "errores": {}, "interrumpido": None}
    fallos_seguidos = 0
    for i, (codigo, nombre) in enumerate(municipios):
        if progreso:
            progreso(i, len(municipios), nombre)
        en_cache = (CARPETA / f"aemet_diaria_{codigo}_{dia:%Y%m%d}.json").exists()
        try:
            d = leer_diaria(diaria(codigo, dia))
            entrada = {"nombre": nombre, "elaborado": d["elaborado"], "dias": d["dias"], "horaria": None}
            if necesita_horaria(d):
                try:
                    entrada["horaria"] = leer_horaria(horaria(codigo, dia))
                except RuntimeError as e:
                    entrada["horaria_error"] = str(e)
            resultado["municipios"][codigo] = entrada
            fallos_seguidos = 0
            if d["elaborado"] and (resultado["elaborado"] is None or d["elaborado"] > resultado["elaborado"]):
                resultado["elaborado"] = d["elaborado"]
        except (RuntimeError, KeyError, IndexError, TypeError, ValueError) as e:
            resultado["errores"][codigo] = str(e)[:160]
            fallos_seguidos += 1
            if fallos_seguidos >= FALLOS_SEGUIDOS_MAX:
                # AEMET caído: no tiene sentido seguir pidiendo uno a uno; se reintentará más tarde
                restantes = municipios[i + 1:]
                for c, _ in restantes:
                    resultado["errores"][c] = "no pedido: AEMET OpenData no respondía"
                resultado["interrumpido"] = f"{str(e)[:120]}; {len(restantes)} municipios sin pedir"
                break
        if not en_cache:
            time.sleep(PAUSA_S)     # solo cuando ha habido llamada a la red
    if progreso:
        progreso(len(municipios), len(municipios), "")
    if resultado["municipios"]:
        CARPETA.mkdir(parents=True, exist_ok=True)
        fichero_prevision(dia).write_text(json.dumps(resultado, ensure_ascii=False), encoding="utf-8")
    return resultado


def cargar() -> dict | None:
    """La última previsión guardada (la de hoy si existe), o None."""
    if not CARPETA.exists():
        return None
    ficheros = sorted(CARPETA.glob("prevision_*.json"))
    if not ficheros:
        return None
    return json.loads(ficheros[-1].read_text(encoding="utf-8"))
