"""Pruebas de la API de crisis con una simulación ficticia (sin red ni motor)."""
import json
import threading
import urllib.error
import urllib.request

import numpy as np
import pytest
import rasterio

from procesamiento import servidor
from procesamiento.incendio import simulacion


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("crisis")
    original = simulacion.CARPETA
    simulacion.CARPETA = carpeta
    (carpeta / "sim-1").mkdir()
    t = np.full((3, 4), -1, dtype="float32")
    t[0, 0], t[0, 1], t[1, 1] = 0, 12.4, 1500
    with rasterio.open(carpeta / "sim-1" / "llegada.tif", "w", driver="GTiff", height=3, width=4, count=1,
                       dtype="float32", crs="EPSG:25830", transform=rasterio.transform.from_origin(0, 0, 50, 50), nodata=-1) as d:
        d.write(t, 1)
    s = servidor.crear_servidor(0)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}"
    s.shutdown()
    simulacion.CARPETA = original


def pedir(url, cuerpo=None):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(url, data=datos, headers={"Content-Type": "application/json"} if datos else {})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_mapa_de_llegada_en_uint16(base):
    estado, cuerpo = pedir(base + "/api/incendio/llegada?id=sim-1")
    assert estado == 200
    v = np.frombuffer(cuerpo, dtype="<u2").reshape(3, 4)
    assert v[0, 0] == 0 and v[0, 1] == 13 and v[1, 1] == 1500 and v[2, 3] == 65535   # minutos redondeados hacia arriba
    assert pedir(base + "/api/incendio/llegada?id=../otra")[0] == 404
    assert pedir(base + "/api/incendio/llegada?id=no-existe")[0] == 404
    assert pedir(base + "/api/incendio/movilidad?id=no-existe")[0] == 404
    assert pedir(base + "/api/incendio/movilidad?id=../otra")[0] == 404


def test_simulacion_valida_la_alerta(base, monkeypatch):
    recibido = {}

    def falsa(lon, lat, hora, viento):
        recibido.update(lon=lon, lat=lat, hora=hora, viento=viento)
        return {"id": "sim-1", "llegada_url": "/api/incendio/llegada?id=sim-1"}

    monkeypatch.setattr(simulacion, "simular", falsa)
    estado, cuerpo = pedir(base + "/api/incendio", {"lon": -4.02, "lat": 40.71, "hora": "2026-07-15T15:00",
                                                    "viento": {"velocidad_kmh": 20, "desde": 270}})
    assert estado == 200 and json.loads(cuerpo)["id"] == "sim-1"
    assert recibido["viento"].velocidad_kmh == 20 and recibido["hora"].tzinfo is not None
    assert pedir(base + "/api/incendio", {"lat": 40.71})[0] == 400
    assert pedir(base + "/api/incendio", {"lon": -4.02, "lat": 40.71, "viento": {"velocidad_kmh": 999, "desde": 0}})[0] == 400


def test_errores_del_motor(base, monkeypatch):
    monkeypatch.setattr(simulacion, "simular", lambda *a: (_ for _ in ()).throw(simulacion.ErrorDeEntrada("sin combustible")))
    estado, cuerpo = pedir(base + "/api/incendio", {"lon": -3.7, "lat": 40.4})
    assert estado == 400 and "sin combustible" in json.loads(cuerpo)["error"]
    monkeypatch.setattr(simulacion, "simular", lambda *a: (_ for _ in ()).throw(RuntimeError("AEMET no responde")))
    assert pedir(base + "/api/incendio", {"lon": -3.7, "lat": 40.4})[0] == 503
