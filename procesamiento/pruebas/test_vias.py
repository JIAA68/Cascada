"""Pruebas de carreteras, vías y trenes programados afectados por un incendio (sin red ni motor)."""
from datetime import datetime

import numpy as np
import pandas as pd
import pytest
import shapely

from procesamiento import cercanias, red_transporte
from procesamiento.incendio import vias
from procesamiento.incendio.entradas import A_GEO, MADRID, Ventana

V = Ventana(400_000.0, 4_500_000.0, 50.0, 100, 100)    # 5 × 5 km


def _xy(fila, col):
    return V.x0 + (col + 0.5) * V.celda, V.y0 - (fila + 0.5) * V.celda


@pytest.fixture
def llegada_250():
    """El fuego llega a cada celda en tantos minutos como columnas la separan de la columna 10."""
    f, c = np.mgrid[0:V.filas, 0:V.columnas]
    t = np.abs(c - 10).astype(float)
    t[:, 60:] = np.inf          # al este de la columna 60 no llega
    return t


@pytest.fixture
def red(monkeypatch):
    """Una carretera norte-sur en la columna 30 y una pista en la columna 80, cada una de dos puntos."""
    tramos = [np.array([_xy(10, 30), _xy(90, 30)]), np.array([_xy(10, 80), _xy(90, 80)])]
    lineas = shapely.segmentize(shapely.linestrings(tramos), red_transporte.PASO_M)
    puntos, n = shapely.get_coordinates(lineas), shapely.get_num_coordinates(lineas)
    r = {"tipo": np.array([0, 1], dtype=np.uint8), "largo": np.array([4000.0, 4000.0]), "dibujo": np.concatenate(tramos), "inicio_dibujo": np.array([0, 2, 4]),
         "puntos": puntos, "tramo_punto": np.repeat([0, 1], n), "codigo": np.array(["M-1", ""]), "nombre": np.array(["", ""])}
    monkeypatch.setattr(red_transporte, "cargar", lambda: r)
    return r


def test_tramos_por_fuego_y_sin_pistas(llegada_250, red):
    x0, y0 = _xy(0, 70)
    humo = shapely.box(x0, y0 - 5000, x0 + 1000, y0)        # cubre la pista, no la carretera
    d = vias.vias_afectadas(llegada_250, V, [(1, humo)])
    [carretera] = d["tramos"]                               # la pista bajo el humo no entra
    assert carretera["codigo"] == "M-1" and carretera["llamas"] == 20.0 and carretera["humo"] is None
    assert [r["via"] for r in d["resumen"]] == ["M-1"]
    assert d["resumen"][0]["km_llamas"] == 4.0
    # El punto por el que llega el fuego es el primero alcanzado de la carretera
    assert "lon_llamas" in d["resumen"][0] and "lat_llamas" in d["resumen"][0]
    lon, lat = A_GEO.transform(*_xy(10, 30))
    assert carretera["coords"][0] == [round(lon, 5), round(lat, 5)]


def test_sin_tramos_fuera_de_la_ventana(llegada_250, red):
    lejos = Ventana(600_000.0, 4_500_000.0, 50.0, 100, 100)
    assert vias.vias_afectadas(llegada_250, lejos, []) == {"tramos": [], "resumen": []}


def test_trenes_que_pasan_con_la_estacion_ya_afectada(llegada_250, monkeypatch):
    x, y = _xy(50, 40)                                       # el fuego llega a los 30 minutos
    lon, lat = A_GEO.transform(x, y)
    estaciones = pd.DataFrame({"stop_id": ["1"], "nombre": ["Estación"], "lon": [lon], "lat": [lat], "x": [x], "y": [y]})
    # Pasos de tres trenes el 12-11-2026: 15:10 (antes de llegar el fuego), 15:40 y 16:40
    pasos = pd.DataFrame({"fecha": ["20261112"] * 3, "trip_id": ["a", "b", "c"], "linea": ["C1"] * 3,
                          "destino": ["Final"] * 3, "stop_id": ["1"] * 3, "segundos": [15 * 3600 + 600, 15 * 3600 + 2400, 16 * 3600 + 2400]})
    monkeypatch.setattr(cercanias, "cargar", lambda: (estaciones, pasos))
    d = vias.trenes_programados(llegada_250, V, [], datetime(2026, 11, 12, 15, 0, tzinfo=MADRID))
    assert d["con_horario"] and d["estaciones"][0]["llamas"] == 30.0
    (tren,) = d["trenes"]
    assert tren["linea"] == "C1" and tren["minutos"] == 40.0 and tren["trenes"] == 2 and tren["efecto"] == "llamas"
    # Fuera de las fechas del horario de Renfe, el mismo día de la semana dentro del horario (aquí, con un solo día
    # de horario no cabe ninguno: sin trenes, pero con estaciones afectadas)
    d = vias.trenes_programados(llegada_250, V, [], datetime(2026, 7, 15, 15, 0, tzinfo=MADRID))
    assert not d["con_horario"] and d["trenes"] == [] and d["estaciones"]


def test_dia_equivalente_con_el_mismo_dia_de_la_semana():
    from datetime import date
    # Horario del 11-11 (miércoles) al 10-12-2026; el 15-07-2026 es miércoles
    equivalente = vias.dia_equivalente(date(2026, 7, 15), "20261111", "20261210")
    assert equivalente == date(2026, 11, 18) and equivalente.weekday() == date(2026, 7, 15).weekday()
    assert vias.dia_equivalente(date(2026, 7, 15), "20261112", "20261113") is None


def test_trocear_en_trozos_de_200_m_sin_huecos():
    tramo = {"tipo": "carretera", "codigo": "M-1", "nombre": "", "coords": np.array([[0.0, 0.0], [1000.0, 0.0]])}
    trozos = red_transporte.trocear([tramo])
    assert len(trozos) == 5 and all(t["codigo"] == "M-1" for t in trozos)
    for a, b in zip(trozos, trozos[1:]):
        assert (a["coords"][-1] == b["coords"][0]).all()
    assert trozos[0]["coords"][0].tolist() == [0.0, 0.0] and trozos[-1]["coords"][-1].tolist() == [1000.0, 0.0]
    assert max(np.hypot(*np.diff(t["coords"], axis=0).T).max() for t in trozos) <= red_transporte.PASO_M + 1e-9
