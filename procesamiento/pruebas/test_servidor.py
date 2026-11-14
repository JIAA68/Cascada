"""Pruebas del servidor local: ficheros con rangos y API (con datos precalculados ficticios)."""
import json
import threading
import urllib.error
import urllib.request

import pandas as pd
import pytest

from procesamiento import consultas, servidor
from procesamiento.capas import CAPAS


@pytest.fixture(scope="module")
def datos(tmp_path_factory, request):
    """Rejilla y activos mínimos, en una carpeta temporal, cargados en las consultas."""
    carpeta = tmp_path_factory.mktemp("procesados")
    # Celda de la Puerta del Sol y una celda vecina
    e_km, n_km = 3159, 2029
    from procesamiento.rejilla import id_celda
    filas = []
    for i, (e, n) in enumerate([(e_km, n_km), (e_km + 1, n_km)]):
        r = {"grd_id": id_celda(e, n), "e_km": e, "n_km": n, "fraccion_comunidad": 1.0,
             "poblacion": 1000 * (i + 1), "menores_16": 100, "mayores_64": 200,
             "activos_n": 0, "sensibles_n": 0, "sensibles_plazas": 0}
        for c in CAPAS:
            r[f"max_{c}"], r[f"pct_{c}"] = 0, 0.0
        r["max_3_1"], r["pct_3_1"] = 1, 0.0             # fondo: no se devuelve
        r["max_6_15"], r["pct_6_15"] = 4, 12.5
        filas.append(r)
    pd.DataFrame(filas).to_csv(carpeta / "rejilla_1km.csv", index=False)
    activos = []
    for ident, sensible, gid in [("EDU-1", False, filas[0]["grd_id"]), ("SOC-9", True, filas[0]["grd_id"])]:
        a = {"id": ident, "familia": "educativos", "subtipo": "infantil", "tipo": "Escuela infantil", "vulnerabilidad": "alta",
             "vulnerabilidad_nivel": 4, "sensible": sensible, "nombre": "Centro", "municipio": "Madrid",
             "plazas": 30, "x": 0, "y": 0, "lon": -3.7, "lat": 40.4, "riesgo_max": 4, "n_amenazas": 1, "grd_id": gid}
        for c in CAPAS:
            a[f"n_{c}"], a[f"r_{c}"] = 0, 0
        a["n_6_15"], a["r_6_15"] = 4, 4
        activos.append(a)
    pd.DataFrame(activos).to_csv(carpeta / "activos_basal.csv", index=False)
    consultas.rejilla.cache_clear(), consultas.activos.cache_clear()
    original = consultas.PROCESADOS
    consultas.PROCESADOS = carpeta
    yield carpeta
    consultas.PROCESADOS = original
    consultas.rejilla.cache_clear(), consultas.activos.cache_clear()


@pytest.fixture(scope="module")
def base(datos):
    s = servidor.crear_servidor(0)
    hilo = threading.Thread(target=s.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{s.server_address[1]}"
    s.shutdown()


def pedir(url, cabeceras=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=cabeceras or {})) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def test_visor_y_rangos(base):
    estado, cab, cuerpo = pedir(base + "/")
    assert estado == 200 and b"<html" in cuerpo.lower()
    estado, cab, cuerpo = pedir(base + "/index.html", {"Range": "bytes=0-9"})
    assert estado == 206 and len(cuerpo) == 10 and cab["Content-Range"].startswith("bytes 0-9/")
    estado, cab, cuerpo = pedir(base + "/index.html", {"Range": "bytes=-5"})
    assert estado == 206 and len(cuerpo) == 5
    estado, *_ = pedir(base + "/index.html", {"Range": "bytes=999999999-"})
    assert estado == 416


def test_no_sale_de_las_carpetas(base):
    assert pedir(base + "/../requirements.txt")[0] == 404
    assert pedir(base + "/datos/../../requirements.txt")[0] == 404


def test_api_celda(base):
    estado, _, cuerpo = pedir(base + "/api/celda?lon=-3.7035&lat=40.4168")
    assert estado == 200
    d = json.loads(cuerpo)
    assert d["poblacion"]["total"] == 1000
    assert [r["codigo"] for r in d["riesgos"]] == ["6_15"]       # el fondo de incendios no aparece
    assert d["riesgos"][0]["porcentaje"] == 12.5
    assert [a["id"] for a in d["activos"]] == ["EDU-1"]           # el sensible no sale uno a uno
    assert d["sensibles"] == {"centros": 1, "plazas": 30}
    assert len(d["contorno"]) == 5


def test_api_resumen(base):
    estado, _, cuerpo = pedir(base + "/api/resumen")
    assert estado == 200
    assert json.loads(cuerpo) == {"celdas": 2, "poblacion": {"total": 3000, "menores_16": 200, "mayores_64": 400}}


def test_api_municipios(base, datos, monkeypatch, tmp_path):
    # Un municipio cuadrado con su capital dentro y otro sin capital (punto interior del término)
    cuadrado = lambda x0, y0: [[[x0, y0], [x0 + 0.1, y0], [x0 + 0.1, y0 + 0.1], [x0, y0 + 0.1], [x0, y0]]]
    (tmp_path / "municipios.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"codigo": "28079", "nombre": "Madrid"}, "geometry": {"type": "Polygon", "coordinates": cuadrado(-3.75, 40.37)}},
        {"type": "Feature", "properties": {"codigo": "28001", "nombre": "La Acebeda"}, "geometry": {"type": "Polygon", "coordinates": cuadrado(-3.65, 41.05)}},
    ]}), encoding="utf-8")
    from procesamiento.incendio.entradas import A_UTM
    x, y = A_UTM.transform(-3.7035, 40.4168)
    pd.DataFrame([{"nombre": "Madrid", "tipo": "Capital de municipio", "x": x, "y": y}]).to_csv(datos / "poblaciones.csv", index=False)
    monkeypatch.setattr(consultas, "VISOR", tmp_path)
    consultas.municipios.cache_clear()
    estado, _, cuerpo = pedir(base + "/api/municipios")
    consultas.municipios.cache_clear()
    assert estado == 200
    acebeda, madrid = json.loads(cuerpo)                          # por orden alfabético
    assert (madrid["lon"], madrid["lat"]) == (-3.7035, 40.4168)
    assert madrid["caja"] == [-3.75, 40.37, -3.65, 40.47]
    assert -3.65 < acebeda["lon"] < -3.55 and 41.05 < acebeda["lat"] < 41.15


def test_api_celda_fuera_y_parametros(base):
    assert pedir(base + "/api/celda?lon=2.17&lat=41.38")[0] == 404
    assert pedir(base + "/api/celda?lon=x")[0] == 400
    assert pedir(base + "/api/celda?lon=-3.7&lat=95")[0] == 400        # antes cerraba la conexión sin responder
    assert pedir(base + "/api/celda?lon=nan&lat=40")[0] == 400
    assert pedir(base + "/api/otra")[0] == 404


def enviar(url, cuerpo: bytes, cabeceras=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=cuerpo, headers=cabeceras or {}, method="POST")) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


@pytest.mark.parametrize("cuerpo", [
    {"lon": -3.8, "lat": 40.2, "viento": {"velocidad_kmh": 25, "desde": float("nan")}},
    {"lon": float("inf"), "lat": 40.2},
    {"lon": -3.8, "lat": 40.2, "hora": "9999-12-31T23:59"},
    [1, 2, 3],
])
def test_alertas_incorrectas_responden_400(base, cuerpo):
    estado, d = enviar(base + "/api/incendio", json.dumps(cuerpo).encode())
    assert estado == 400 and d["error"].startswith("Alerta incorrecta")


def test_cuerpo_demasiado_grande(base):
    estado, d = enviar(base + "/api/incendio", b"{}", {"Content-Length": str(servidor.CUERPO_MAX + 1)})
    assert estado == 413


def test_error_inesperado_responde_500(base, monkeypatch):
    def falla(*_):
        raise ZeroDivisionError("fallo de prueba")
    monkeypatch.setattr(servidor, "coordenadas", falla)
    estado, _, cuerpo = pedir(base + "/api/celda?lon=-3.7&lat=40.4")
    assert estado == 500 and "consola" in json.loads(cuerpo)["error"]


def test_no_arranca_dos_veces_en_el_mismo_puerto():
    s = servidor.crear_servidor(0)
    try:
        with pytest.raises(OSError):
            servidor.crear_servidor(s.server_address[1])
    finally:
        s.server_close()


def test_api_activo(base):
    estado, _, cuerpo = pedir(base + "/api/activo?id=EDU-1")
    d = json.loads(cuerpo)
    assert estado == 200 and d["riesgo_max_nombre"] == "alto"
    assert d["riesgos"][0]["nombre"] == "Transporte por tren" and d["riesgos"][0]["riesgo"] == 4
    assert pedir(base + "/api/activo?id=SOC-9")[0] == 404          # sensible: no se sirve
    assert pedir(base + "/api/activo?id=NO")[0] == 404
