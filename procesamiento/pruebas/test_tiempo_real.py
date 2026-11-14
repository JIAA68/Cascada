"""Pruebas de los trenes y el tráfico en tiempo real y de su cruce con un incendio (sin red)."""
import json

import numpy as np
import pytest
import rasterio
import shapely
from shapely.geometry import box

from procesamiento import tiempo_real
from procesamiento.incendio import movilidad, simulacion
from procesamiento.incendio.entradas import A_GEO, Ventana

DGT = b"""<?xml version="1.0" encoding="UTF-8"?>
<d2:payload xmlns:d2="http://levelC/schema/3/d2Payload" xmlns:sit="http://levelC/schema/3/situation"
  xmlns:com="http://levelC/schema/3/common" xmlns:loc="http://levelC/schema/3/locationReferencing"
  xmlns:lse="http://levelC/schema/3/locationReferencingSpanishExtension"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
 <sit:situation id="1">
  <sit:situationRecord xsi:type="sit:RoadOrCarriagewayOrLaneManagement" id="A">
   <sit:validity><com:validityTimeSpecification><com:overallStartTime>2026-11-08T12:00:00.000+01:00</com:overallStartTime>
   </com:validityTimeSpecification></sit:validity>
   <sit:cause><sit:causeType>roadMaintenance</sit:causeType><sit:detailedCauseType>
    <sit:roadMaintenanceType>roadworks</sit:roadMaintenanceType></sit:detailedCauseType></sit:cause>
   <sit:locationReference xsi:type="loc:SingleRoadLinearLocation">
    <loc:supplementaryPositionalDescription><loc:roadInformation><loc:roadName>M-601</loc:roadName></loc:roadInformation>
    </loc:supplementaryPositionalDescription>
    <loc:tpegLinearLocation><loc:tpegDirection>northBound</loc:tpegDirection>
     <loc:to><loc:pointCoordinates><loc:latitude>40.75</loc:latitude><loc:longitude>-4.02</loc:longitude></loc:pointCoordinates></loc:to>
     <loc:from><loc:pointCoordinates><loc:latitude>40.72</loc:latitude><loc:longitude>-4.01</loc:longitude></loc:pointCoordinates>
      <lse:kilometerPoint>12.0</lse:kilometerPoint><lse:municipality>Navacerrada</lse:municipality></loc:from>
    </loc:tpegLinearLocation>
   </sit:locationReference>
   <sit:roadOrCarriagewayOrLaneManagementType>roadClosed</sit:roadOrCarriagewayOrLaneManagementType>
  </sit:situationRecord>
  <sit:situationRecord xsi:type="sit:GenericSituationRecord" id="B">
   <sit:cause><sit:causeType>accident</sit:causeType><sit:detailedCauseType><sit:accidentType>accident</sit:accidentType>
   </sit:detailedCauseType></sit:cause>
   <sit:locationReference xsi:type="loc:PointLocation"><loc:pointByCoordinates><loc:pointCoordinates>
    <loc:latitude>40.4</loc:latitude><loc:longitude>-3.7</loc:longitude></loc:pointCoordinates></loc:pointByCoordinates>
   </sit:locationReference>
  </sit:situationRecord>
  <sit:situationRecord xsi:type="sit:AbnormalTraffic" id="C">
   <sit:locationReference xsi:type="loc:PointLocation"><loc:roadName>sin coordenadas</loc:roadName></sit:locationReference>
   <sit:abnormalTrafficType>slowTraffic</sit:abnormalTrafficType>
  </sit:situationRecord>
 </sit:situation>
</d2:payload>"""

CIUDAD = """<?xml version="1.0" encoding="UTF-8"?>
<pms><fecha_hora>08/11/2026 13:25:02</fecha_hora>
 <pm><idelem>1</idelem><descripcion>Castellana N-S</descripcion><intensidad>720</intensidad><ocupacion>9</ocupacion>
  <carga>40</carga><nivelServicio>2</nivelServicio><error>N</error><st_x>441617,09</st_x><st_y>4475765,77</st_y></pm>
 <pm><idelem>2</idelem><nivelServicio>1</nivelServicio><error>S</error><st_x>441000</st_x><st_y>4475000</st_y></pm>
 <pm><idelem>3</idelem><nivelServicio>-1</nivelServicio><error>N</error><st_x>441000</st_x><st_y>4475000</st_y></pm>
</pms>""".encode("utf-8")


def test_lee_los_trenes():
    feed = {"entity": [
        {"id": "VP_C8b-1", "vehicle": {"position": {"latitude": 40.71, "longitude": -4.02}, "currentStatus": "STOPPED_AT",
                                        "stopId": "10", "timestamp": "1794141142", "vehicle": {"label": "C8b-1-PLATF.(2)"},
                                        "trip": {"tripId": "T1"}}},
        {"id": "sin-posicion", "vehicle": {"vehicle": {"label": "C1-2"}}}]}
    t = tiempo_real.leer_trenes(feed)
    assert len(t) == 1
    assert t[0]["linea"] == "C8b" and t[0]["estado"] == "parado en estación" and t[0]["hora"].endswith("+01:00")


def test_lee_el_trafico_de_la_ciudad():
    marca, puntos = tiempo_real.leer_ciudad(CIUDAD)
    assert marca == "08/11/2026 13:25:02"
    assert [p["id"] for p in puntos] == ["1"]          # fuera los puntos con error o sin nivel
    p = puntos[0]
    assert p["nivel_nombre"] == "retenciones" and p["intensidad"] == 720
    assert -3.70 < p["lon"] < -3.68 and 40.42 < p["lat"] < 40.44   # Castellana, desde UTM con coma decimal


def test_lee_las_incidencias_de_la_dgt():
    inc = {i["id"]: i for i in tiempo_real.leer_incidencias(DGT)}
    assert set(inc) == {"A", "B"}                      # la que no tiene coordenadas se descarta
    a = inc["A"]
    assert a["tipo"] == "Carretera cortada" and a["categoria"] == "corte"   # el corte manda sobre la causa (obras)
    assert a["carretera"] == "M-601" and a["sentido"] == "norte" and a["km"] == 12.0
    assert (a["lon"], a["lat"]) == (-4.01, 40.72) and a["fin"] == [-4.02, 40.75]
    assert a["desde"] == "2026-11-08T12:00+01:00"
    assert inc["B"]["tipo"] == "Accidente" and inc["B"]["fin"] is None


def test_dentro_de_la_comunidad():
    limite = box(400000, 4400000, 480000, 4520000)     # rectángulo en EPSG:25830 alrededor de Madrid
    elementos = [{"lon": -3.7, "lat": 40.4}, {"lon": -2.0, "lat": 40.4}]
    assert tiempo_real.dentro(elementos, limite) == [elementos[0]]


def test_una_fuente_caida_no_tumba_la_otra(monkeypatch):
    monkeypatch.setattr(tiempo_real, "ciudad", lambda: (_ for _ in ()).throw(OSError("sin red")))
    monkeypatch.setattr(tiempo_real, "incidencias", lambda: {"fuente": "DGT", "incidencias": []})
    t = tiempo_real.trafico()
    assert "sin red" in t["ciudad"]["error"] and t["incidencias"]["incidencias"] == []


# ----------------------------------------------------------------------------- cruce con un incendio
V = Ventana(420000.0, 4510000.0, 50.0, 40, 40)


def _en(fila, col):
    lon, lat = A_GEO.transform(V.x0 + (col + 0.5) * V.celda, V.y0 - (fila + 0.5) * V.celda)
    return {"lon": float(lon), "lat": float(lat)}


def test_evalua_llamas_y_humo():
    llegada = np.full((V.filas, V.columnas), np.inf)
    llegada[20, 20] = 30
    llegada_250 = movilidad.llegada_en_radio(llegada, V.celda, 250)
    humo = [(180.0, box(V.x0, V.y0 - 5 * V.celda, V.x0 + 5 * V.celda, V.y0))]     # esquina noroeste, a las 3 h
    elementos = [{"id": "cerca", **_en(20, 23)}, {"id": "lejos", **_en(20, 35)}, {"id": "humo", **_en(2, 2)},
                 {"id": "tramo", **_en(39, 39), "fin": list(_en(20, 22).values())}, {"id": "fuera", "lon": -3.0, "lat": 40.0}]
    r = {e["id"]: e for e in movilidad.evaluar(elementos, llegada_250, V, humo)}
    assert set(r) == {"cerca", "humo", "tramo"}
    assert r["cerca"]["minutos_llamas"] == 30 and r["cerca"]["minutos_humo"] is None
    assert r["humo"]["minutos_humo"] == 180 and r["humo"]["minutos_llamas"] is None
    assert r["tramo"]["minutos"] == 30                  # el extremo final del tramo está junto al fuego
    assert [e["id"] for e in movilidad.evaluar(elementos, llegada_250, V, humo)][-1] == "humo"   # ordenados


@pytest.fixture
def simulacion_guardada(tmp_path, monkeypatch):
    monkeypatch.setattr(simulacion, "CARPETA", tmp_path)
    (tmp_path / "sim-1").mkdir()
    t = np.full((V.filas, V.columnas), -1, dtype="float32")
    t[18:23, 18:23] = 10
    with rasterio.open(tmp_path / "sim-1" / "llegada.tif", "w", driver="GTiff", height=V.filas, width=V.columnas, count=1,
                       dtype="float32", crs="EPSG:25830", transform=V.transform, nodata=-1) as d:
        d.write(t, 1)
    (tmp_path / "sim-1" / "respuesta.json").write_text(json.dumps(
        {"vientos_por_hora": [{"velocidad_kmh": 0, "desde": 0}] * 25}), encoding="utf-8")
    return "sim-1"


def test_cruce_con_una_simulacion_guardada(simulacion_guardada):
    fuentes = {
        "trenes": (lambda: {"fuente": "Renfe", "consultado": "x", "trenes": [{"id": "T", **_en(20, 20)}, {"id": "U", "lon": -3, "lat": 40}]}, "trenes"),
        "ciudad": (lambda: (_ for _ in ()).throw(OSError("sin red")), "puntos"),
    }
    r = movilidad.cruce(simulacion_guardada, fuentes)
    assert r["trenes"]["total"] == 2 and [t["id"] for t in r["trenes"]["afectados"]] == ["T"]
    assert r["trenes"]["afectados"][0]["minutos_llamas"] == 10
    assert r["trenes"]["afectados"][0]["minutos_humo"] == 10       # sin viento, el humo cubre el fuego desde que arde
    assert "sin red" in r["ciudad"]["error"]
    with pytest.raises(FileNotFoundError):
        movilidad.cruce("../fuera", fuentes)
