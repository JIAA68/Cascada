"""Pruebas de la ruta del fuego para los avisos anticipados (sin red ni motor)."""
import math

import numpy as np

from procesamiento.incendio.consecuencias import ruta_del_fuego
from procesamiento.incendio.entradas import A_UTM, Ventana

V = Ventana(400_000.0, 4_500_000.0, 50.0, 200, 200)


def _llegada(ignicion=(100, 20), velocidad_m_min=10.0):
    """Fuego que se abre en círculo desde la ignición a velocidad constante."""
    f, c = np.mgrid[0:V.filas, 0:V.columnas]
    return np.hypot(f - ignicion[0], c - ignicion[1]) * V.celda / velocidad_m_min


def _xy(fila, col):
    return V.x0 + (col + 0.5) * V.celda, V.y0 - (fila + 0.5) * V.celda


def test_la_ruta_va_de_la_ignicion_al_activo_y_el_tiempo_crece():
    llegada = _llegada()
    x, y = _xy(100, 160)
    ruta = ruta_del_fuego(llegada, V, x, y)
    assert ruta[0][2] == 0.0
    x0, y0 = A_UTM.transform(*ruta[0][:2]); xn, yn = A_UTM.transform(*ruta[-1][:2])
    assert math.hypot(x0 - _xy(100, 20)[0], y0 - _xy(100, 20)[1]) < 1
    assert math.hypot(xn - x, yn - y) < 1
    minutos = [p[2] for p in ruta]
    assert minutos == sorted(minutos)
    # El fuego llega a menos de 250 m: la llegada del activo es la de 5 celdas antes
    assert math.isclose(ruta[-1][2], (140 - 5) * 50 / 10, abs_tol=0.5)
    # En línea recta: ningún punto se aparta más de una celda de la fila 100
    for lon, lat, _ in ruta:
        assert abs(A_UTM.transform(lon, lat)[1] - _xy(100, 0)[1]) <= 50


def test_la_ruta_cruza_una_franja_sin_combustible_por_el_salto():
    llegada = _llegada()
    llegada[:, 80:84] = np.inf          # franja de 200 m que no arde; el fuego sigue al otro lado
    ruta = ruta_del_fuego(llegada, V, *_xy(100, 160))
    assert ruta[0][2] == 0.0 and len(ruta) > 5


def test_sin_llegada_no_hay_ruta():
    llegada = np.full((V.filas, V.columnas), np.inf)
    llegada[100, 20] = 0.0
    assert ruta_del_fuego(llegada, V, *_xy(100, 160)) == []


def test_punto_de_entrada_del_fuego_en_cada_municipio():
    from procesamiento.incendio.consecuencias import municipios_alcanzados
    llegada = _llegada()
    indice = np.zeros((V.filas, V.columnas), dtype="int32")
    indice[:, :60] = 1          # la ignición, en la columna 20
    indice[:, 60:] = 2          # el fuego entra por la columna 60, en la fila de la ignición
    m = municipios_alcanzados(llegada, indice, [("1", "Uno"), ("2", "Dos")], V)
    assert [x["nombre"] for x in m] == ["Uno", "Dos"] and m[0]["minutos"] == 0.0
    x, y = A_UTM.transform(m[1]["lon"], m[1]["lat"])
    assert math.hypot(x - _xy(100, 60)[0], y - _xy(100, 60)[1]) < 1
    assert "lon" not in municipios_alcanzados(llegada, indice, [("1", "Uno"), ("2", "Dos")])[0]


def test_franja_de_la_conduccion_hora_a_hora():
    from procesamiento.incendio.consecuencias import franja_por_hora
    x0, y0 = _xy(100, 100)
    x = x0 + np.arange(0, 3000, 50.0)               # núcleo de 3 km hacia el este
    y = np.full_like(x, y0)
    t = np.arange(len(x)) * 3.0                     # el fuego lo recorre en 3 horas
    f = franja_por_hora(x, y, t)
    assert [p["minutos"] for p in f] == [0.0, 60.0, 120.0]
    assert [p["hasta"] for p in f] == [60.0, 120.0, None]
    # La última franja cubre todo el núcleo con 750 m a cada lado
    lons = [lon for poligono in f[-1]["coords"] for lon, _ in poligono]
    xs = [A_UTM.transform(lon, 40.6)[0] for lon in (min(lons), max(lons))]
    assert xs[0] < x[0] - 700 and xs[1] > x[-1] + 700


def test_tramos_nuevos_de_la_conduccion():
    from procesamiento.incendio.consecuencias import tramos_alcanzados
    # Dos tramos de 1 km separados 5 km: el fuego recorre el primero desde el minuto 0 y llega al segundo en el 60
    x = np.r_[np.arange(0, 1000, 50.0), 6000 + np.arange(0, 1000, 50.0)]
    y = np.zeros_like(x)
    t = np.r_[np.arange(20) * 2.0, 60 + np.arange(20) * 2.0]
    tramos = tramos_alcanzados(x, y, t)
    assert [(tr["minutos"], tr["x"]) for tr in tramos] == [(0.0, 0.0), (60.0, 6000.0)]
    # Si el fuego avanza por la conducción sin saltos, solo cuenta la primera llegada
    assert len(tramos_alcanzados(np.arange(0, 8000, 50.0), np.zeros(160), np.arange(160) * 1.0)) == 1


def test_isocronas_a_cada_hora():
    from procesamiento.incendio.consecuencias import isocronas
    llegada = _llegada(ignicion=(100, 100), velocidad_m_min=20.0)     # círculo que crece 1,2 km por hora
    iso = isocronas(llegada, V, 30.0, horizonte_min=150)
    assert [i["minutos"] for i in iso] == [30.0, 90.0, 150.0]
    for i in iso:
        (anillo,) = i["coords"]
        x, y = np.array([A_UTM.transform(lon, lat) for lon, lat in anillo]).T
        radio = np.hypot(x - _xy(100, 100)[0], y - _xy(100, 100)[1])
        assert abs(radio.mean() - 20.0 * i["minutos"]) < 60     # a menos de una celda y media del círculo teórico
