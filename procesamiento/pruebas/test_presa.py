"""Rotura de presa: recorrido aguas abajo por la zona inundable y onda frenada calibrada con los 30 minutos del catálogo."""
import numpy as np

from procesamiento.presa.modelo import VELOCIDAD_MIN_KMH, distancias_aguas_abajo, minutos_de_llegada


def test_la_onda_tarda_30_minutos_en_recorrer_la_zona_del_catalogo():
    for L in (2_000.0, 10_000.0, 40_000.0):
        assert abs(float(minutos_de_llegada(np.array([L]), L)[0]) - 30.0) < 1e-6


def test_la_onda_se_frena_y_no_baja_de_la_velocidad_minima():
    L = 10_000.0
    s = np.linspace(0, 200_000, 2001)
    t = minutos_de_llegada(s, L)
    velocidad = np.diff(s) / np.diff(t) * 60 / 1000   # km/h
    assert np.all(np.diff(t) > 0)
    assert velocidad[0] > velocidad[len(velocidad) // 10] > velocidad[-1] - 1e-9
    assert velocidad.min() >= VELOCIDAD_MIN_KMH - 1e-6
    assert abs(velocidad[-1] - VELOCIDAD_MIN_KMH) < 1e-6


def test_el_agua_baja_por_el_valle_y_no_remonta_el_afluente():
    # Valle que baja hacia el este (fila 5) y un afluente que sube hacia el norte desde la columna 10 (40 m por celda)
    mascara = np.zeros((11, 21), dtype=bool)
    mascara[5, :] = True
    mascara[:5, 10] = True
    altitud = np.full(mascara.shape, np.nan)
    altitud[5, :] = 100 - np.arange(21)
    for f in range(5):
        altitud[f, 10] = altitud[5, 10] + 40 * (5 - f)
    d = distancias_aguas_abajo(mascara, altitud, (5, 0), 50.0)
    assert np.isfinite(d[5, :]).all() and abs(d[5, 20] - 1000.0) < 1e-6
    assert not np.isfinite(d[:5, 10]).any()


def test_salva_un_artefacto_del_relieve_de_pocos_metros():
    mascara = np.ones((1, 10), dtype=bool)
    altitud = (100 - np.arange(10, dtype=float))[None, :]
    altitud[0, 4] += 6   # un puente o un talud en la media de 50 m
    d = distancias_aguas_abajo(mascara, altitud, (0, 0), 50.0)
    assert np.isfinite(d).all()
