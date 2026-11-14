"""Cálculo de la prealerta: niveles por municipio y día, activos afectados y resumen de la Comunidad.

Para cada municipio y cada uno de los 7 días:

1. Se traduce la previsión a niveles 0 a 3 con los umbrales de Meteoalerta de su zona de aviso: temperaturas
   máxima y mínima, racha de viento (horaria si la hay, si no la diaria), lluvia en 1 y 12 horas y nieve acumulada
   (solo con la horaria), tormenta (probabilidad horaria o estado del cielo) y peligro meteorológico de incendio
   (índice de Fosberg). Niebla, polvo en suspensión y granizo solo entran por aviso oficial.
2. Donde hay aviso oficial de AEMET para la zona del municipio y el día, manda el aviso (y se etiqueta como tal).
3. Se deduce qué peligros basales activa el día (tabla ACTIVACION de umbrales.py).

Los activos afectados se calculan aparte, a partir de los niveles del día de su municipio:
- efecto directo: su subtipo es sensible al fenómeno (tabla DIRECTO);
- activación: el fenómeno alcanza el amarillo y su peligrosidad en la capa activada es moderada o superior; el riesgo
  es el basal de esa capa (matriz del catálogo).
Los centros sensibles solo se cuentan.
"""
from datetime import date, datetime, timedelta
from functools import lru_cache

import pandas as pd

from ..capas import CAPAS, NIVELES as NIVELES_PELIGRO, RIESGOS, nombre_capa, riesgo
from ..fuentes import PROCESADOS
from ..incendio.entradas import MADRID
from . import avisos as modulo_avisos
from .umbrales import (ACTIVACION, DIRECTO, DIRECTO_SENSIBLES, FENOMENOS, NIVEL_ACTIVACION, NIVELES, ZONAS, clase_fosberg,
                       fosberg, nivel, nivel_tormenta)

N_DIAS = 7
CAMPOS_ACTIVO = ["id", "familia", "subtipo", "tipo", "nombre", "municipio", "vulnerabilidad", "plazas", "lon", "lat"]


# ----------------------------------------------------------------------------- tablas estáticas
@lru_cache(maxsize=1)
def municipios() -> pd.DataFrame:
    return pd.read_csv(PROCESADOS / "municipios.csv", dtype={"codigo": str, "zona": str}).set_index("codigo")


@lru_cache(maxsize=1)
def activos() -> pd.DataFrame:
    """Activos con su municipio, su riesgo basal por capa y el nivel de las capas de la prealerta."""
    a = pd.read_csv(PROCESADOS / "activos_basal.csv").set_index("id", drop=False)
    m = pd.read_csv(PROCESADOS / "activos_municipio.csv", dtype={"codigo_municipio": str}).set_index("id")
    a = a.join(m, how="left")
    ruta = PROCESADOS / "meteo_activos.csv"
    if ruta.exists():
        a = a.join(pd.read_csv(ruta).set_index("id"), how="left", rsuffix="_meteo")
    for capa in ACTIVACION:
        if f"n_{capa}" not in a:
            a[f"n_{capa}"] = 0
        if f"r_{capa}" not in a:
            a[f"r_{capa}"] = [riesgo(int(p), int(v)) for p, v in zip(a[f"n_{capa}"].fillna(0), a["vulnerabilidad_nivel"])]
    return a


# ----------------------------------------------------------------------------- niveles de un municipio
def _dias(prevision_municipio: dict) -> list[str]:
    return [d["fecha"] for d in prevision_municipio["dias"][:N_DIAS]]


def niveles_dia(d: dict, h: dict | None, zona: str) -> dict:
    """Nivel 0 a 3 de cada fenómeno calculado por Cascada para un día de un municipio, con su valor."""
    u = ZONAS[zona]
    f = {}
    f["AT"] = {"nivel": nivel(d["tmax"], u["tmax"]), "valor": d["tmax"], "texto": f"máxima {d['tmax']:g} °C" if d["tmax"] is not None else "sin dato"}
    f["BT"] = {"nivel": nivel(d["tmin"], u["tmin"], hacia_abajo=True), "valor": d["tmin"], "texto": f"mínima {d['tmin']:g} °C" if d["tmin"] is not None else "sin dato"}
    racha = (h or {}).get("racha_max") if h else None
    racha = racha if racha is not None else d["racha_max"]
    f["VI"] = {"nivel": nivel(racha, u["racha"]), "valor": racha,
               "texto": f"racha {racha:g} km/h" if racha is not None else (f"viento {d['viento_max']:g} km/h, sin racha prevista" if d["viento_max"] is not None else "sin dato")}
    if h and h.get("pr1_max") is not None:
        f["PR"] = {"nivel": max(nivel(h["pr1_max"], u["pr1"]), nivel(h["pr12_max"], u["pr12"])),
                   "valor": h["pr12_max"], "texto": f"{h['pr1_max']:g} mm en 1 h, {h['pr12_max']:g} mm en 12 h"}
    else:
        f["PR"] = {"nivel": 0, "valor": d["prob_precip"],
                   "texto": f"probabilidad {d['prob_precip']:g} %, sin cantidad prevista" if d["prob_precip"] is not None else "sin dato"}
    if h and h.get("nieve24") is not None:
        f["NE"] = {"nivel": nivel(h["nieve24"], u["nieve24"]), "valor": h["nieve24"], "texto": f"{h['nieve24']:g} cm en 24 h"}
    else:
        f["NE"] = {"nivel": 0, "valor": d["cota_nieve"],
                   "texto": (f"cota de nieve {d['cota_nieve']:g} m" if d["cota_nieve"] is not None else "") + (" · nieve en el cielo previsto" if d["nieve_cielo"] else "") or "sin nieve prevista"}
    if h and h.get("prob_tormenta") is not None:
        f["TO"] = {"nivel": nivel_tormenta(h["prob_tormenta"]), "valor": h["prob_tormenta"], "texto": f"probabilidad {h['prob_tormenta']:g} %"}
    else:
        f["TO"] = {"nivel": 1 if d["tormenta_cielo"] else 0, "valor": None,
                   "texto": "tormenta en el cielo previsto" if d["tormenta_cielo"] else "sin tormenta prevista"}
    for codigo in ("NI", "PO", "GR"):
        f[codigo] = {"nivel": 0, "valor": None, "texto": "solo por aviso oficial"}
    if d["tmax"] is not None and d["hr_min"] is not None and d["viento_max"] is not None:
        indice = fosberg(d["tmax"], d["hr_min"], d["viento_max"])
        clase, n = clase_fosberg(indice)
        f["IF"] = {"nivel": n, "valor": indice, "texto": f"Fosberg {indice:g} ({clase}): {d['tmax']:g} °C, humedad {d['hr_min']:g} %, viento {d['viento_max']:g} km/h", "clase": clase}
    else:
        f["IF"] = {"nivel": 0, "valor": None, "texto": "sin dato"}
    for codigo in f:
        f[codigo]["origen"] = "Cascada"
    return f


def aplicar_avisos(fenomenos: dict, avisos_dia: list[dict]) -> list[dict]:
    """Sube cada fenómeno al nivel del aviso oficial de la zona si es mayor; devuelve los avisos aplicados."""
    aplicados = []
    for a in avisos_dia:
        codigo = a["fenomeno"] if a["fenomeno"] in FENOMENOS else None
        if codigo is None:
            fenomenos.setdefault(a["fenomeno"], {"nivel": 0, "valor": None, "texto": a["fenomeno_nombre"], "origen": "Cascada"})
            codigo = a["fenomeno"]
        if a["nivel"] >= fenomenos[codigo]["nivel"]:
            fenomenos[codigo].update(nivel=a["nivel"], origen="AEMET", texto=a["umbral"] or a["titular"] or fenomenos[codigo]["texto"])
        aplicados.append({k: a[k] for k in ("zona", "fenomeno", "fenomeno_nombre", "nivel", "nivel_nombre", "inicio", "fin", "umbral", "fuente")})
    return aplicados


def activaciones(fenomenos: dict) -> dict:
    """Capas basales activadas por los fenómenos que llegan al amarillo: capa -> (nivel, [fenómenos])."""
    salida = {}
    for capa, codigos in ACTIVACION.items():
        activos = [c for c in codigos if fenomenos.get(c, {}).get("nivel", 0) >= 1]
        if activos:
            salida[capa] = {"nivel": max(fenomenos[c]["nivel"] for c in activos), "fenomenos": activos, "nombre": nombre_capa(capa)}
    return salida


def niveles_municipio(codigo: str, prevision_municipio: dict, zona: str, avisos_lista: list[dict]) -> list[dict]:
    """Una entrada por día: previsión resumida, niveles por fenómeno, avisos aplicados, activaciones y nivel máximo."""
    salida = []
    horaria = prevision_municipio.get("horaria") or {}
    for d in prevision_municipio["dias"][:N_DIAS]:
        h = horaria.get(d["fecha"])
        fenomenos = niveles_dia(d, h, zona)
        del_dia = modulo_avisos.por_dia(avisos_lista, date.fromisoformat(d["fecha"]))
        aplicados = aplicar_avisos(fenomenos, [a for a in del_dia if a["zona"] == zona])
        for f in fenomenos.values():
            f["nivel_nombre"] = NIVELES[f["nivel"]]
        salida.append({
            "fecha": d["fecha"], "zona": zona,
            "prevision": {k: d[k] for k in ("tmax", "tmin", "hr_min", "hr_max", "viento_max", "racha_max", "prob_precip",
                                            "cota_nieve", "cielo_texto", "uv")} | ({"horaria": h} if h else {}),
            "fenomenos": fenomenos, "avisos": aplicados, "activaciones": activaciones(fenomenos),
            "nivel_max": max(f["nivel"] for f in fenomenos.values()),
        })
    return salida


# ----------------------------------------------------------------------------- toda la Comunidad
def calcular(prevision: dict, avisos_datos: dict) -> dict:
    """Prealerta completa: días, niveles por municipio y día, avisos y resumen por día."""
    m = municipios()
    lista_avisos = [a for a in avisos_datos.get("avisos", []) if a["zona"] in ZONAS]
    por_municipio, fechas = {}, None
    for codigo, pm in prevision["municipios"].items():
        if codigo not in m.index:
            continue
        zona = m.loc[codigo, "zona"]
        niveles = niveles_municipio(codigo, pm, zona, lista_avisos)
        por_municipio[codigo] = niveles
        if fechas is None or len(niveles) > len(fechas):
            fechas = [n["fecha"] for n in niveles]
    fechas = fechas or []
    resumen = []
    for i, fecha in enumerate(fechas):
        dia = date.fromisoformat(fecha)
        f_res = {}
        for codigo in FENOMENOS:
            niveles_f = [n[i]["fenomenos"].get(codigo, {}).get("nivel", 0) for n in por_municipio.values() if i < len(n)]
            origen = "AEMET" if any(i < len(n) and n[i]["fenomenos"].get(codigo, {}).get("origen") == "AEMET" for n in por_municipio.values()) else "Cascada"
            f_res[codigo] = {"nivel": max(niveles_f, default=0), "municipios": sum(1 for v in niveles_f if v >= 1), "origen": origen}
        capas = {}
        for n in por_municipio.values():
            if i < len(n):
                for capa, act in n[i]["activaciones"].items():
                    capas[capa] = max(capas.get(capa, 0), act["nivel"])
        resumen.append({"fecha": fecha, "nombre": nombre_dia(dia), "fenomenos": f_res,
                        "nivel_max": max((v["nivel"] for v in f_res.values()), default=0),
                        "activaciones": {c: {"nivel": v, "nombre": nombre_capa(c)} for c, v in capas.items()},
                        "avisos": [{k: a[k] for k in ("zona", "zona_nombre", "fenomeno", "fenomeno_nombre", "nivel", "nivel_nombre", "inicio", "fin", "umbral", "fuente")}
                                   for a in modulo_avisos.por_dia(lista_avisos, dia)]})
    return {
        "dia_referencia": prevision.get("dia"), "elaborado": prevision.get("elaborado"), "consultado": prevision.get("consultado"),
        "fuente_prevision": "AEMET OpenData, predicción municipal diaria y horaria",
        "fuente_avisos": avisos_datos.get("fuente"), "avisos_consultados": avisos_datos.get("consultado"),
        "municipios_sin_dato": sorted(prevision.get("errores", {})),
        "fechas": fechas, "dias": resumen,
        "fenomenos": {c: {"nombre": f["nombre"], "capa": f["capa"], "umbral": f["umbral"]} for c, f in FENOMENOS.items()},
        "municipios": {codigo: {"nombre": m.loc[codigo, "nombre"], "zona": m.loc[codigo, "zona"],
                                "niveles": [n["nivel_max"] for n in niveles],
                                "fenomeno_max": [max(n["fenomenos"], key=lambda c: n["fenomenos"][c]["nivel"]) if n["nivel_max"] else None for n in niveles],
                                "activaciones": [sorted(n["activaciones"]) for n in niveles]}
                       for codigo, niveles in por_municipio.items()},
        "detalle": por_municipio,
    }


def nombre_dia(dia: date) -> str:
    hoy = datetime.now(MADRID).date()
    if dia == hoy:
        return "hoy"
    if dia == hoy + timedelta(days=1):
        return "mañana"
    return ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")[dia.weekday()]


# ----------------------------------------------------------------------------- activos afectados
def _resumen(fila) -> dict:
    d = {c: (None if pd.isna(fila[c]) else (fila[c].item() if hasattr(fila[c], "item") else fila[c])) for c in CAMPOS_ACTIVO}
    d["vulnerabilidad_nivel"] = int(fila["vulnerabilidad_nivel"])
    return d


def activos_afectados(resultado: dict, i_dia: int, codigo_municipio: str | None = None) -> dict:
    """Activos con riesgo focal un día (directos y activados) y recuento de sensibles."""
    a = activos()
    detalle = resultado["detalle"]
    if codigo_municipio:
        a = a[a["codigo_municipio"] == codigo_municipio]
    directos, activados, sensibles = [], [], {"centros": 0, "plazas": 0, "fenomenos": set()}
    for codigo, grupo in a.groupby("codigo_municipio"):
        niveles = detalle.get(codigo)
        if not niveles or i_dia >= len(niveles):
            continue
        dia = niveles[i_dia]
        fen = dia["fenomenos"]
        # efecto directo
        for cf, subtipos in DIRECTO.items():
            n = fen.get(cf, {}).get("nivel", 0)
            if n < 1:
                continue
            sel = grupo[grupo["subtipo"].isin(subtipos) & ~grupo["sensible"]]
            for _, fila in sel.iterrows():
                directos.append(_resumen(fila) | {"fenomeno": cf, "fenomeno_nombre": FENOMENOS[cf]["nombre"], "nivel": n,
                                                  "nivel_nombre": NIVELES[n], "origen": fen[cf]["origen"]})
            if cf in DIRECTO_SENSIBLES:
                sens = grupo[grupo["sensible"]]
                if len(sens):
                    sensibles["fenomenos"].add(cf)
                    sensibles["centros"] += int(len(sens))
                    sensibles["plazas"] += int(sens["plazas"].fillna(0).sum())
        # activación de peligros basales
        for capa, act in dia["activaciones"].items():
            sel = grupo[(grupo[f"n_{capa}"].fillna(0) >= NIVEL_ACTIVACION) & ~grupo["sensible"]]
            for _, fila in sel.iterrows():
                r = int(fila[f"r_{capa}"])
                activados.append(_resumen(fila) | {"capa": capa, "capa_nombre": nombre_capa(capa), "nivel": act["nivel"], "nivel_nombre": NIVELES[act["nivel"]],
                                                   "fenomenos": act["fenomenos"], "peligrosidad": int(fila[f"n_{capa}"]),
                                                   "peligrosidad_nombre": NIVELES_PELIGRO[int(fila[f"n_{capa}"])], "riesgo": r, "riesgo_nombre": RIESGOS[r]})
    directos.sort(key=lambda d: (-d["nivel"], -d["vulnerabilidad_nivel"], d["nombre"] or ""))
    activados.sort(key=lambda d: (-d["riesgo"], -d["nivel"], d["nombre"] or ""))
    sensibles["fenomenos"] = sorted(sensibles["fenomenos"])
    return {"directos": directos, "activados": activados, "sensibles": sensibles}
