"""Modo sin conexión: caché de teselas y tipografías del mapa (sin red)."""
from procesamiento import sin_conexion


def test_teselas_de_un_recuadro_cubren_madrid():
    teselas = sin_conexion.teselas_de((-3.8, 40.3, -3.6, 40.5), 12)
    # Puerta del Sol (-3.7038, 40.4168) en el zoom 12
    assert (12, *sin_conexion._xy(-3.7038, 40.4168, 12)) in teselas
    assert all(z == 12 for z, _, _ in teselas) and len(teselas) == len(set(teselas))


def test_sin_conexion_sirve_solo_lo_guardado(tmp_path, monkeypatch):
    monkeypatch.setattr(sin_conexion, "CARPETA", tmp_path)
    monkeypatch.setattr(sin_conexion, "SIN_CONEXION", True)
    assert sin_conexion.tesela("ign-vectorial", 10, 501, 387) is None          # no está guardada: no se pide fuera
    guardada = tmp_path / "ign-vectorial" / "10" / "501" / "387.pbf"
    guardada.parent.mkdir(parents=True)
    guardada.write_bytes(b"\x1f\x8b")
    assert sin_conexion.tesela("ign-vectorial", 10, 501, 387) == (guardada, "application/x-protobuf")


def test_rechaza_peticiones_fuera_de_rango(tmp_path, monkeypatch):
    monkeypatch.setattr(sin_conexion, "CARPETA", tmp_path)
    monkeypatch.setattr(sin_conexion, "SIN_CONEXION", True)
    assert sin_conexion.tesela("ign-mdt", 16, 0, 0) is None                   # por encima del zoom del servicio
    assert sin_conexion.tesela("ign-pnoa", 3, 9, 0) is None                   # x fuera de la rejilla
    assert sin_conexion.glifo("Comic Sans", "0-255") is None                  # tipografía no prevista
    assert sin_conexion.glifo("Open Sans Semibold", "../x") is None


def test_activar_corta_las_peticiones_en_el_acto(monkeypatch):
    import time
    import urllib.error
    import urllib.request
    monkeypatch.setattr(sin_conexion, "SIN_CONEXION", False)
    try:
        sin_conexion.activar()
        inicio = time.monotonic()
        try:
            urllib.request.urlopen("https://opendata.aemet.es/opendata/api", timeout=30)
            raise AssertionError("debería fallar sin conexión")
        except urllib.error.URLError as e:
            assert "sin conexión" in str(e.reason)
        assert time.monotonic() - inicio < 1
    finally:
        urllib.request.install_opener(None)
