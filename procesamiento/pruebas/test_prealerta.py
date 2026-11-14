"""Pruebas de la prealerta sin red: umbrales, lectura de AEMET (muestras locales), avisos CAP, cálculo y API."""
import copy
import json
import threading
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from procesamiento import servidor
from procesamiento.capas import CAPAS
from procesamiento.prealerta import aemet, avisos, calculo, servicio, umbrales

DATOS = Path(__file__).parent / "datos"


# --- umbrales e índices ------------------------------------------------------------------
def test_niveles_por_umbral_de_meteoalerta():
    u = umbrales.ZONAS["722802"]
    assert [umbrales.nivel(t, u["tmax"]) for t in (35, 36, 39, 42)] == [0, 1, 2, 3]
    assert [umbrales.nivel(t, u["tmin"], hacia_abajo=True) for t in (-3, -4, -8, -12)] == [0, 1, 2, 3]
    assert umbrales.nivel(None, u["racha"]) == 0
    assert umbrales.ZONAS["722801"]["tmax"] == (34, 37, 40) and umbrales.ZONAS["722801"]["nieve24"] == (5, 20, 40)
    assert umbrales.nivel_tormenta(39) == 0 and umbrales.nivel_tormenta(40) == 1 and umbrales.nivel_tormenta(70) == 2


def test_indice_de_fosberg():
    assert umbrales.clase_fosberg(umbrales.fosberg(10, 70, 10)) == ("bajo", 0)
    alto = umbrales.fosberg(35, 20, 30)
    assert 30 <= alto < 50 and umbrales.clase_fosberg(alto) == ("alto", 1)
    assert umbrales.clase_fosberg(umbrales.fosberg(40, 10, 50)) == ("extremo", 3)
    # más viento o menos humedad, más índice
    assert umbrales.fosberg(30, 30, 40) > umbrales.fosberg(30, 30, 20) > umbrales.fosberg(30, 60, 20)


def test_tabla_de_activacion_usa_capas_conocidas():
    from procesamiento.capas import CAPAS_ACTIVACION_EXTRA
    for capa, fenomenos in umbrales.ACTIVACION.items():
        assert capa in CAPAS or capa in CAPAS_ACTIVACION_EXTRA
        assert all(f in umbrales.FENOMENOS for f in fenomenos)


# --- previsión de AEMET (muestras locales) ------------------------------------------------
def muestra(nombre):
    return aemet._decodificar((DATOS / nombre).read_bytes())


def test_lee_la_prevision_diaria():
    d = aemet.leer_diaria(muestra("aemet_diaria_28079_20261024.json"))
    assert d["nombre"] == "Madrid" and len(d["dias"]) == 7 and d["elaborado"].startswith("2026-10-24")
    d0 = d["dias"][0]
    assert d0["fecha"] == "2026-10-24" and d0["tmax"] == 19 and d0["tmin"] == 6 and d0["hr_min"] == 30
    assert d0["viento_max"] == 10 and d0["racha_max"] is None and d0["prob_precip"] == 0
    assert not d0["tormenta_cielo"] and not d0["nieve_cielo"] and d0["cota_nieve"] is None
    assert not aemet.necesita_horaria(d)


def test_lee_la_prevision_horaria():
    h = aemet.leer_horaria(muestra("aemet_horaria_28079_20261024.json"))
    assert list(h) == ["2026-10-24", "2026-10-25", "2026-10-26"]
    assert h["2026-10-24"]["racha_max"] == 23 and h["2026-10-24"]["pr1_max"] == 0 and h["2026-10-25"]["horas"] == 25


def test_horaria_acumula_lluvia_en_12_horas():
    lluvia = [0, 5, 20, 20, 0, 0, 0, 0, 0, 0, 0, 0, 0, 10]
    datos = [{"prediccion": {"dia": [{
        "fecha": "2026-11-09T00:00:00",
        "precipitacion": [{"value": str(v), "periodo": f"{i:02d}"} for i, v in enumerate(lluvia)],
        "nieve": [{"value": "Ip", "periodo": "00"}],
        "probTormenta": [{"value": "60", "periodo": "0006"}],
        "vientoAndRachaMax": [{"direccion": ["N"], "velocidad": ["20"], "periodo": "01"}, {"value": "75", "periodo": "01"}],
    }]}}]
    h = aemet.leer_horaria(datos)["2026-11-09"]
    assert h["pr1_max"] == 20 and h["pr12_max"] == 50 and h["pr24"] == 55     # 12 h deslizantes: 20+20+…+10
    assert h["nieve24"] == 0 and h["prob_tormenta"] == 60 and h["racha_max"] == 75


def test_necesita_horaria_con_lluvia_o_tormenta():
    d = aemet.leer_diaria(muestra("aemet_diaria_28079_20261024.json"))
    d["dias"][1]["prob_precip"] = 35
    assert aemet.necesita_horaria(d)
    d["dias"][1]["prob_precip"] = 0
    d["dias"][5]["tormenta_cielo"] = True      # fuera de los tres primeros días: no cuenta
    assert not aemet.necesita_horaria(d)


# --- avisos oficiales ---------------------------------------------------------------------
def test_lee_un_cap_de_aemet():
    lista = avisos.leer_cap((DATOS / "aemet_cap_ejemplo.xml").read_bytes())
    assert [a["zona"] for a in lista] == ["722801", "722802", "722803"]   # solo el bloque en castellano
    a = lista[0]
    assert a["fenomeno"] == "AT" and a["fenomeno_nombre"] == "Temperaturas máximas"
    assert a["nivel"] == 0 and a["nivel_nombre"] == "verde" and a["zona_nombre"] == "Sierra de Madrid"
    assert a["inicio"].startswith("2026-10-26")
    assert len(a["poligonos"]) == 2 and len(a["poligonos"][0]) > 10 and a["poligonos"][0][0] == [-4.32, 40.52]   # dos anillos: exclave


def test_cap_con_nivel_y_umbral():
    xml = (DATOS / "aemet_cap_ejemplo.xml").read_text(encoding="utf-8").replace("<value>verde</value>", "<value>naranja</value>")
    xml = xml.replace("</parameter>", "</parameter><parameter><valueName>AEMET-Meteoalerta parametro</valueName>"
                      "<value>AT;Temperaturas máximas;39 ºC</value></parameter>", 1)
    a = avisos.leer_cap(xml.encode("utf-8"))[0]
    assert a["nivel"] == 2 and a["umbral"] == "39 ºC"


def test_avisos_por_dia_en_hora_local():
    lista = [{"inicio": "2026-11-09T00:00:00+01:00", "fin": "2026-11-09T20:59:59+01:00"},
             {"inicio": "2026-11-08T23:00:00+00:00", "fin": "2026-11-10T22:59:59+00:00"}]
    assert len(avisos.por_dia(lista, date(2026, 11, 9))) == 2
    assert len(avisos.por_dia(lista, date(2026, 11, 10))) == 1
    assert len(avisos.por_dia(lista, date(2026, 11, 8))) == 0   # el segundo empieza a las 00:00 del 9 en Madrid


class _Respuesta:
    def __init__(self, cuerpo):
        self.cuerpo = cuerpo

    def read(self):
        return self.cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


METEOALARM = {"warnings": [{"alert": {"info": [
    {"language": "es-ES", "event": "Lluvias", "onset": "2026-11-09T00:00:00+01:00", "expires": "2026-11-09T20:59:59+01:00",
     "headline": "Aviso amarillo por lluvias", "description": "",
     "parameter": [{"valueName": "awareness_level", "value": "2; yellow; Moderate"}, {"valueName": "awareness_type", "value": "10; Rain"}],
     "area": [{"areaDesc": "Sierra de Madrid", "geocode": [{"valueName": "EMMA_ID", "value": "ES722801"}]},
              {"areaDesc": "Litoral de Cádiz", "geocode": [{"valueName": "EMMA_ID", "value": "ES611101"}]}]},
    {"language": "en-GB", "event": "Rain", "parameter": [], "area": []},
]}}]}


def test_meteoalarm_de_respaldo(monkeypatch):
    monkeypatch.setattr(avisos.urllib.request, "urlopen", lambda *a, **k: _Respuesta(json.dumps(METEOALARM).encode()))
    lista = avisos._de_meteoalarm()
    assert len(lista) == 1
    a = lista[0]
    assert a["zona"] == "722801" and a["fenomeno"] == "PR" and a["fenomeno_nombre"] == "Lluvias" and a["nivel"] == 1
    assert a["fuente"] == "Meteoalarm" and a["poligonos"] == []


def test_avisos_cae_a_meteoalarm_si_aemet_no_responde(monkeypatch):
    def falla():
        raise OSError("sin red")
    monkeypatch.setattr(avisos, "_de_aemet", falla)
    monkeypatch.setattr(avisos, "_de_meteoalarm", lambda: [{"zona": "722801", "nivel": 1}])
    monkeypatch.setattr(avisos, "_cache", {})
    d = avisos.avisos()
    assert d["fuente"].startswith("Meteoalarm") and d["avisos"] == [{"zona": "722801", "nivel": 1}]
    monkeypatch.setattr(avisos, "_de_meteoalarm", falla)
    assert avisos.avisos() is d     # caché de media hora


# --- cálculo ------------------------------------------------------------------------------
MUNICIPIOS = [("28001", "La Acebeda", "722801"), ("28079", "Madrid", "722802")]


@pytest.fixture
def territorio(tmp_path, monkeypatch):
    """Dos municipios y tres activos (uno sensible) en una carpeta temporal."""
    pd.DataFrame([{"codigo": c, "nombre": n, "zona": z, "lon": -3.7, "lat": 40.5, "superficie_km2": 10} for c, n, z in MUNICIPIOS]
                 ).to_csv(tmp_path / "municipios.csv", index=False)
    activos = []
    for ident, subtipo, vul, sensible, municipio, extra in [
            ("EDU-1", "infantil", "alta", False, "28001", {"3_1": 4, "6_27": 3}),
            ("SOC-1", "residencial", "muy_alta", False, "28079", {"3_1": 1}),
            ("SOC-S", "residencial", "muy_alta", True, "28001", {"3_1": 3})]:
        a = {"id": ident, "familia": "educativos" if ident.startswith("EDU") else "atencion_social", "subtipo": subtipo, "tipo": "Escuela infantil",
             "vulnerabilidad": vul, "vulnerabilidad_nivel": {"alta": 4, "muy_alta": 5}[vul], "sensible": sensible, "nombre": ident,
             "municipio": municipio, "plazas": 20, "x": 0, "y": 0, "lon": -3.7, "lat": 40.5, "riesgo_max": 0, "n_amenazas": 0, "grd_id": "X"}
        for c in CAPAS:
            a[f"n_{c}"], a[f"r_{c}"] = 0, 0
        for c, n in extra.items():
            a[f"n_{c}"], a[f"r_{c}"] = n, {1: 2, 3: 4, 4: 4}[n]
        activos.append((a, municipio))
    pd.DataFrame([a for a, _ in activos]).to_csv(tmp_path / "activos_basal.csv", index=False)
    pd.DataFrame([{"id": a["id"], "codigo_municipio": m} for a, m in activos]).to_csv(tmp_path / "activos_municipio.csv", index=False)
    monkeypatch.setattr(calculo, "PROCESADOS", tmp_path)
    monkeypatch.setattr(servicio, "PROCESADOS", tmp_path)
    calculo.municipios.cache_clear(), calculo.activos.cache_clear()
    yield tmp_path
    calculo.municipios.cache_clear(), calculo.activos.cache_clear()


def prevision_sintetica():
    """La muestra de Madrid repetida en los dos municipios: calor el día 2 y viento el día 3."""
    d = aemet.leer_diaria(muestra("aemet_diaria_28079_20261024.json"))
    prev = {"dia": "2026-10-24", "elaborado": d["elaborado"], "consultado": "2026-10-24T13:00", "municipios": {}, "errores": {}}
    for codigo, nombre, _ in MUNICIPIOS:
        dias = copy.deepcopy(d["dias"])
        dias[2].update(tmax=38, hr_min=15, viento_max=25)
        dias[3].update(racha_max=85)
        prev["municipios"][codigo] = {"nombre": nombre, "elaborado": d["elaborado"], "dias": dias, "horaria": None}
    return prev


AVISO_NIEVE = {"zona": "722801", "zona_nombre": "Sierra de Madrid", "fenomeno": "NE", "fenomeno_nombre": "Nevadas", "nivel": 2,
               "nivel_nombre": "naranja", "inicio": "2026-10-25T00:00:00+02:00", "fin": "2026-10-25T23:59:59+02:00", "umbral": "20 cm",
               "probabilidad": "40%-70%", "titular": "Aviso de nevadas de nivel naranja. Sierra de Madrid", "descripcion": "",
               "poligonos": [], "fuente": "AEMET"}
AVISOS = {"fuente": "prueba", "consultado": "2026-10-24T13:05", "avisos": [AVISO_NIEVE]}


def test_niveles_por_municipio_y_dia(territorio):
    res = calculo.calcular(prevision_sintetica(), AVISOS)
    assert res["fechas"][0] == "2026-10-24" and len(res["dias"]) == 7 and res["municipios_sin_dato"] == []
    # Sierra: aviso de nieve el día 1; 38 °C es naranja (37) el día 2; racha de 85 es amarillo (80) el día 3
    assert res["municipios"]["28001"]["niveles"] == [0, 2, 2, 1, 0, 0, 0]
    assert res["municipios"]["28001"]["fenomeno_max"][1:4] == ["NE", "AT", "VI"]
    # Madrid: el aviso no es de su zona; 38 °C es amarillo (36); 85 km/h es amarillo (70)
    assert res["municipios"]["28079"]["niveles"] == [0, 0, 1, 1, 0, 0, 0]
    dia1 = res["detalle"]["28001"][1]
    assert dia1["fenomenos"]["NE"]["nivel"] == 2 and dia1["fenomenos"]["NE"]["origen"] == "AEMET" and dia1["fenomenos"]["NE"]["texto"] == "20 cm"
    assert dia1["avisos"][0]["umbral"] == "20 cm" and dia1["activaciones"] == {"6_16": {"nivel": 2, "fenomenos": ["NE"], "nombre": "Transporte por carretera"}}
    assert res["detalle"]["28079"][1]["fenomenos"]["NE"]["nivel"] == 0
    dia2 = res["detalle"]["28001"][2]
    assert dia2["fenomenos"]["IF"]["nivel"] == 1 and dia2["fenomenos"]["IF"]["clase"] == "alto"
    assert list(dia2["activaciones"]) == ["3_1"] and dia2["activaciones"]["3_1"]["fenomenos"] == ["IF"]
    assert sorted(res["detalle"]["28001"][3]["activaciones"]) == ["3_1", "6_27"]
    # resumen de la Comunidad
    assert res["dias"][1]["fenomenos"]["NE"] == {"nivel": 2, "municipios": 1, "origen": "AEMET"}
    assert res["dias"][2]["fenomenos"]["AT"] == {"nivel": 2, "municipios": 2, "origen": "Cascada"}
    assert res["dias"][2]["nivel_max"] == 2 and res["dias"][0]["nivel_max"] == 0
    assert res["dias"][1]["avisos"][0]["zona_nombre"] == "Sierra de Madrid"


def test_activos_con_riesgo_focal(territorio):
    res = calculo.calcular(prevision_sintetica(), AVISOS)
    # día 1: nieve en la Sierra; el sensible solo se cuenta, el infantil no es de los afectados por nieve
    a = calculo.activos_afectados(res, 1)
    assert a["directos"] == [] and a["activados"] == []
    assert a["sensibles"] == {"centros": 1, "plazas": 20, "fenomenos": ["NE"]}
    # día 2: calor en toda la Comunidad e incendios activados por Fosberg
    a = calculo.activos_afectados(res, 2)
    assert [(x["id"], x["nivel"]) for x in a["directos"]] == [("EDU-1", 2), ("SOC-1", 1)]
    assert a["directos"][0]["fenomeno"] == "AT" and a["directos"][0]["origen"] == "Cascada"
    assert [(x["id"], x["capa"], x["riesgo"]) for x in a["activados"]] == [("EDU-1", "3_1", 4)]
    assert a["activados"][0]["peligrosidad_nombre"] == "alta" and a["activados"][0]["riesgo_nombre"] == "alto"
    assert a["sensibles"]["centros"] == 0    # el calor no cuenta a los sensibles
    # día 3: viento, que activa incendios y derrumbes
    a = calculo.activos_afectados(res, 3)
    assert a["directos"] == [] and sorted((x["id"], x["capa"]) for x in a["activados"]) == [("EDU-1", "3_1"), ("EDU-1", "6_27")]
    # un solo municipio
    a = calculo.activos_afectados(res, 2, "28079")
    assert [x["id"] for x in a["directos"]] == ["SOC-1"] and a["activados"] == []


# --- API ----------------------------------------------------------------------------------
@pytest.fixture
def base(territorio, tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "prevision_20261024.json").write_text(json.dumps(prevision_sintetica()), encoding="utf-8")
    monkeypatch.setattr(aemet, "CARPETA", cache)
    monkeypatch.setattr(avisos, "avisos", lambda: AVISOS)
    monkeypatch.setattr(servicio, "actualizar", lambda: {"actualizando": False, "simulado": True})   # sin llamar a AEMET
    monkeypatch.setattr(servicio, "_prevision", {"ruta": None, "mtime": None, "datos": None})
    monkeypatch.setattr(servicio, "_resultado", {"clave": None, "datos": None})
    s = servidor.crear_servidor(0)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}"
    s.shutdown()


def pedir(url, metodo="GET"):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method=metodo, data=b"" if metodo == "POST" else None)) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_api_prealerta(base):
    estado, d = pedir(base + "/api/prealerta")
    assert estado == 200 and "detalle" not in d and d["fechas"][2] == "2026-10-26"
    assert d["municipios"]["28001"]["niveles"] == [0, 2, 2, 1, 0, 0, 0] and d["fuente_avisos"] == "prueba"
    assert d["dias"][2]["activaciones"]["3_1"]["nombre"] == "Incendios forestales"
    assert d["fenomenos"]["IF"]["nombre"] == "Peligro meteorológico de incendio"

    estado, m = pedir(base + "/api/prealerta/municipio?codigo=28001&dia=1")
    assert estado == 200 and m["nombre"] == "La Acebeda" and m["zona_nombre"] == "Sierra de Madrid" and m["fecha"] == "2026-10-25"
    assert len(m["dias"]) == 7 and m["dias"][1]["fenomenos"]["NE"]["nivel"] == 2 and m["activos"]["sensibles"]["centros"] == 1

    estado, a = pedir(base + "/api/prealerta/activos?dia=2026-10-26")
    assert estado == 200 and a["dia"] == 2 and [x["id"] for x in a["directos"]] == ["EDU-1", "SOC-1"]

    assert pedir(base + "/api/prealerta/activos?dia=9")[0] == 404
    assert pedir(base + "/api/prealerta/municipio?codigo=99999")[0] == 404
    assert pedir(base + "/api/prealerta/municipio")[0] == 400
    estado, e = pedir(base + "/api/prealerta/actualizar", "POST")
    assert estado == 200 and e["simulado"]
