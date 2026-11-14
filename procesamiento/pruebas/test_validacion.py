"""Pruebas de la validación del modelo con un caso real, con datos sintéticos (sin red ni motor)."""
import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
import shapely
from rasterio.transform import from_origin

from procesamiento import servidor
from procesamiento.incendio import simulacion, validacion
from procesamiento.incendio.entradas import MADRID
from procesamiento.incendio.propagacion import Viento


# --- Viento de la Red de Calidad del Aire -----------------------------------------------------
def fichero_meteo(ruta, dia_utc: datetime, velocidades: dict, direcciones: dict, no_validadas=()):
    """CSV con el formato de la red: una fila por magnitud y día, h01…h24 y su validación."""
    filas = []
    for magnitud, valores in ((81, velocidades), (82, direcciones)):
        f = {"provincia": 28, "municipio": 45, "estacion": 2, "magnitud": magnitud, "punto_muestreo": "x",
             "ano": dia_utc.year, "mes": dia_utc.month, "dia": dia_utc.day}
        for h in range(1, 25):
            f[f"h{h:02d}"] = str(valores.get(h, 0)).replace(".", ",")
            f[f"v{h:02d}"] = "N" if h in no_validadas else "V"
        filas.append(f)
    pd.DataFrame(filas).to_csv(ruta, sep=";", index=False)


def test_las_horas_de_la_red_son_utc_y_cuentan_por_el_punto_medio(tmp_path):
    ruta = tmp_path / "meteo.csv"
    fichero_meteo(ruta, datetime(2025, 8, 11, tzinfo=timezone.utc),
                  velocidades={19: 3.4, 20: 2.3, 21: 2.5}, direcciones={19: 273, 20: 303, 21: 77}, no_validadas=(21,))
    serie = validacion.serie_estacion(ruta, 28045002)
    # 19:45 en Madrid (verano) son las 17:45 UTC: la primera hora de simulación (punto medio 18:15 UTC)
    # cae en la hora que termina a las 19:00 UTC (h19)
    w = validacion.vientos_desde(serie, datetime(2025, 8, 11, 19, 45, tzinfo=MADRID), horas=3)
    assert w[0] == Viento(round(3.4 * 3.6, 1), 273)
    assert w[1] == Viento(round(2.3 * 3.6, 1), 303)
    assert w[2] == w[1]                       # h21 sin validar: se repite la hora anterior


def test_sin_viento_al_empezar_avisa(tmp_path):
    ruta = tmp_path / "meteo.csv"
    fichero_meteo(ruta, datetime(2025, 8, 11, tzinfo=timezone.utc), {}, {}, no_validadas=range(1, 25))
    with pytest.raises(RuntimeError):
        validacion.vientos_desde(validacion.serie_estacion(ruta, 28045002), datetime(2025, 8, 11, 19, 45, tzinfo=MADRID), 2)


# --- Métricas ---------------------------------------------------------------------------------
CELDA = 50.0
TRANSFORM = from_origin(0, 1000, CELDA, CELDA)       # rejilla de 20 × 20 celdas, de (0, 0) a (1000, 1000)


def test_metricas_de_coincidencia():
    llegada = np.full((20, 20), np.inf)
    llegada[:, :10] = 30                               # lo simulado: la mitad oeste, quemada a los 30 min
    real = shapely.box(0, 0, 500, 1000)                # lo real: la misma mitad
    puntos = pd.DataFrame({"x": [250.0, 950.0], "y": [500.0, 500.0], "minutos": [60.0, 60.0]})   # el segundo, a 450 m del borde
    m = validacion.metricas(llegada, TRANSFORM, CELDA, (0.0, 500.0), real, puntos)
    assert m["horizontes"]["1"]["sorensen"] == 1.0
    assert m["horizontes"]["1"]["superficie_ha"] == 50 and m["superficie_real_ha"] == 50
    assert m["direccion"]["real_grados"] == 90.0 and m["direccion"]["simulada_24h_grados"] == 90.0   # hacia el este
    assert m["focos"] == {"total": 2, "dentro_de_lo_simulado": 1, "dentro_del_perimetro": 1}
    assert m["avance"]["minutos_hasta_6_km"] is None   # en la rejilla no hay celdas a 6 km


def test_metricas_a_hora_fija_con_el_circulo_como_modelo_nulo():
    llegada = np.full((20, 20), np.inf)
    llegada[:, :10] = 30                               # el modelo acierta la mitad oeste, ignición en su borde oeste
    real = shapely.box(0, 0, 500, 1000)
    m = validacion.metricas(llegada, TRANSFORM, CELDA, (0.0, 500.0), real, pd.DataFrame(columns=["x", "y", "minutos"]),
                            hora_fija_h=1)
    f = m["hora_fija"]
    assert f["horas"] == 1 and f["sorensen"] == 1.0 and f["razon_superficie"] == 1.0
    # El círculo de la misma superficie centrado en la ignición se sale de la rejilla y acierta mucho menos
    assert f["sorensen_circulo"] < 0.8 and f["ganancia_sobre_circulo"] == pytest.approx(1.0 - f["sorensen_circulo"])
    assert validacion.metricas(llegada, TRANSFORM, CELDA, (0.0, 500.0), real,
                               pd.DataFrame(columns=["x", "y", "minutos"]))["hora_fija"] is None


def test_metricas_sin_coincidencia():
    llegada = np.full((20, 20), -1.0)
    llegada[:, 10:] = 30
    m = validacion.metricas(llegada, TRANSFORM, CELDA, (0.0, 500.0), shapely.box(0, 0, 500, 1000),
                            pd.DataFrame(columns=["x", "y", "minutos"]))
    assert m["mejor_hora"]["sorensen"] == 0.0 and m["mejor_hora"]["simulado_fuera_pct"] == 100.0


# --- API y poda ------------------------------------------------------------------------------
@pytest.fixture()
def servidor_local(tmp_path, monkeypatch):
    monkeypatch.setattr(simulacion, "CARPETA", tmp_path / "crisis")
    monkeypatch.setattr(validacion, "SALIDA", tmp_path / "validacion" / "caso.json")
    s = servidor.crear_servidor(0)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}", tmp_path
    s.shutdown()


def pedir(url, cuerpo=None):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(url, data=datos, headers={"Content-Type": "application/json"} if datos else {})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_api_de_validacion(servidor_local):
    base, carpeta = servidor_local
    estado, d = pedir(base + "/api/validacion")
    assert estado == 404 and "no está calculada" in d["error"]
    (carpeta / "crisis" / validacion.CASO).mkdir(parents=True)
    (carpeta / "crisis" / validacion.CASO / "respuesta.json").write_text('{"id": "caso"}', encoding="utf-8")
    validacion.SALIDA.parent.mkdir(parents=True)
    validacion.SALIDA.write_text('{"caso": "caso", "metricas": {}}', encoding="utf-8")
    estado, d = pedir(base + "/api/validacion")
    assert estado == 200 and d["simulacion"]["id"] == "caso" and "metricas" in d


def test_api_acepta_viento_hora_a_hora(servidor_local, monkeypatch):
    base, _ = servidor_local
    recibido = {}

    def falsa(lon, lat, hora, viento):
        recibido["viento"] = viento
        return {"id": "sim"}

    monkeypatch.setattr(simulacion, "simular", falsa)
    serie = [{"velocidad_kmh": 12, "desde": 273}, {"velocidad_kmh": 8, "desde": 303}]
    assert pedir(base + "/api/incendio", {"lon": -3.7, "lat": 40.6, "vientos": serie})[0] == 200
    assert recibido["viento"] == [Viento(12, 273), Viento(8, 303)]
    assert pedir(base + "/api/incendio", {"lon": -3.7, "lat": 40.6, "vientos": serie * 13})[0] == 400   # más de 25 horas
    assert pedir(base + "/api/incendio", {"lon": -3.7, "lat": 40.6, "vientos": [{"velocidad_kmh": 400, "desde": 0}]})[0] == 400


def test_la_poda_no_borra_los_casos_guardados(tmp_path, monkeypatch):
    monkeypatch.setattr(simulacion, "CARPETA", tmp_path)
    for nombre in ("caso_tres_cantos_2025", "a", "b", "c"):
        (tmp_path / nombre).mkdir()
    assert simulacion.podar(conservar=1) == 2
    assert (tmp_path / "caso_tres_cantos_2025").exists()


def test_un_identificador_de_caso_no_valido_se_rechaza():
    with pytest.raises(simulacion.ErrorDeEntrada):
        simulacion.simular(-3.7, 40.6, datetime.now(MADRID) - timedelta(days=1), id_simulacion="../fuera")


def test_metricas_de_contencion():
    llegada = np.full((20, 20), np.inf)
    llegada[:, :10] = 30
    llegada[:, 10:] = 600                              # lo de después de la contención (8 h) no cuenta
    m = validacion.metricas(llegada, TRANSFORM, CELDA, (0.0, 500.0), shapely.box(0, 0, 500, 1000),
                            pd.DataFrame(columns=["x", "y", "minutos"]))
    assert m["contencion"]["horas"] == 8 and m["contencion"]["sorensen"] == 1.0 and m["contencion"]["rumbo_grados"] == 90.0
