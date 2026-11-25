"""Pruebas del modelo de incendio: Rothermel, propagación y humo, con datos sintéticos."""
import math

import numpy as np
import pandas as pd
import pytest
import shapely

from procesamiento.incendio.combustibles import MODELOS, VERANO, Humedades
from procesamiento.incendio.humo import ALCANCE_MAX_KM, activos_bajo_humo, zona_humo, zonas_de_humo
from procesamiento.incendio.propagacion import Viento, tiempos_llegada
from procesamiento.incendio.rothermel import elipse, lecho, velocidad_en

# --- Rothermel: velocidades nominales de la tabla 1 de Anderson (1982), en cadenas/hora, con
# humedad de muertos del 8 %, vivos del 100 %, viento a media llama de 5 mi/h y terreno llano.
CADENA_H = 0.3048 * 66 / 60        # m/min por cadena/hora
CINCO_MPH = 5 * 1.609344
ANDERSON = Humedades(0.08, 0.08, 0.08, 1.00)
NOMINAL = {1: 78, 2: 35, 3: 104, 4: 75, 5: 18, 6: 32, 7: 20, 8: 1.6, 9: 7.5, 10: 7.9, 11: 6.0, 12: 13.0, 13: 13.5}
# Los modelos 5 y 7 (con combustible vivo) se desvían más de las tablas de Anderson
TOLERANCIA = {5: 0.25, 7: 0.35}


@pytest.mark.parametrize("numero", sorted(NOMINAL))
def test_velocidad_nominal_anderson(numero):
    vel, _, _ = elipse(lecho(MODELOS[numero], ANDERSON), CINCO_MPH, 0, 0.0, 0.0)
    assert vel / CADENA_H == pytest.approx(NOMINAL[numero], rel=TOLERANCIA.get(numero, 0.10))


def test_viento_alarga_y_orienta():
    k = lecho(MODELOS[1], ANDERSON)
    _, _, e0 = elipse(k, 0, 0, 0.0, 0.0)
    vel, dire, exc = elipse(k, 15, 45, 0.0, 0.0)
    assert e0 == pytest.approx(0, abs=1e-9) and exc > 0.8 and dire == pytest.approx(45)
    assert velocidad_en(vel, dire, exc, 45) > 10 * velocidad_en(vel, dire, exc, 225)


@pytest.mark.parametrize("mph, relacion", [(2, 1.18), (5, 1.59), (10, 2.78)])
def test_relacion_largo_ancho_de_anderson(mph, relacion):
    """Anderson (1983): 1,59 con 5 mi/h de viento efectivo (el viento a media llama, en llano)."""
    k = lecho(MODELOS[1], VERANO)
    _, _, exc = elipse(k, mph * 1.609344, 0, 0.0, 0.0)
    assert 1 / math.sqrt(1 - exc ** 2) == pytest.approx(relacion, abs=0.01)


def test_pendiente_acelera_cuesta_arriba():
    k = lecho(MODELOS[4], ANDERSON)
    llano, _, _ = elipse(k, 0, 0, 0.0, 0.0)
    cuesta, dire, _ = elipse(k, 0, 0, 0.5, 180.0)
    assert cuesta > 2 * llano and dire == pytest.approx(180)


def test_humedad_de_extincion_apaga():
    vel, _, _ = elipse(lecho(MODELOS[1], Humedades(0.13, 0.13, 0.13, 1.0)), 10, 0, 0.0, 0.0)
    assert vel == pytest.approx(0, abs=1e-9)


# --- Propagación -------------------------------------------------------------------------
CELDA = 50.0


def rejilla(lado=81, modelo=1):
    comb = np.full((lado, lado), modelo, dtype=np.int16)
    return comb, np.zeros((lado, lado)), np.zeros((lado, lado))


def test_sin_viento_es_casi_circular():
    comb, pend, sub = rejilla()
    t = tiempos_llegada(comb, pend, sub, CELDA, (40, 40), [Viento(0, 0)], VERANO, 600)
    norte, este, sur, oeste = t[20, 40], t[40, 60], t[60, 40], t[40, 20]
    assert norte == pytest.approx(este, rel=0.02) == pytest.approx(sur, rel=0.02) == pytest.approx(oeste, rel=0.02)
    assert t[26, 54] == pytest.approx(norte * math.hypot(14, 14) / 20, rel=0.08)


def test_viento_del_oeste_empuja_al_este():
    comb, pend, sub = rejilla()
    t = tiempos_llegada(comb, pend, sub, CELDA, (40, 40), [Viento(20, 270)], VERANO, 600)
    assert t[40, 60] < t[40, 20] / 5 and t[40, 60] < t[20, 40]


@pytest.mark.parametrize("anchura", [1, 2])
def test_sin_combustible_es_barrera(anchura):
    comb, pend, sub = rejilla()
    comb[:, 50:50 + anchura] = 0           # ni una franja de una celda se cruza sin salto
    t = tiempos_llegada(comb, pend, sub, CELDA, (40, 40), [Viento(20, 270)], VERANO, 600)
    assert np.isinf(t[:, 50:]).all()


def avance_de_cabeza(desde, kmh=40, minutos=45):
    comb, pend, sub = rejilla(lado=201)    # unos 3,4 km de avance: lejos del borde en cualquier rumbo
    t = tiempos_llegada(comb, pend, sub, CELDA, (100, 100), [Viento(kmh, desde)], VERANO, minutos)
    f, c = np.nonzero(t <= minutos)
    hacia = math.radians((desde + 180) % 360)
    return np.max(((c - 100) * math.sin(hacia) - (f - 100) * math.cos(hacia)) * CELDA)


@pytest.mark.parametrize("desde", [283.3, 292.5, 315.0])
def test_la_velocidad_no_depende_del_rumbo_respecto_de_la_rejilla(desde):
    assert avance_de_cabeza(desde) == pytest.approx(avance_de_cabeza(270.0), rel=0.06)


def test_ignicion_sin_combustible_avisa():
    comb, pend, sub = rejilla()
    comb[40, 40] = 0
    with pytest.raises(ValueError):
        tiempos_llegada(comb, pend, sub, CELDA, (40, 40), [Viento(10, 0)], VERANO, 60)


def test_cambio_de_viento_por_hora():
    comb, pend, sub = rejilla(lado=121)
    fijo = tiempos_llegada(comb, pend, sub, CELDA, (60, 60), [Viento(20, 270)] * 3, VERANO, 180)
    gira = tiempos_llegada(comb, pend, sub, CELDA, (60, 60), [Viento(20, 270), Viento(20, 180)], VERANO, 180)
    assert gira[20, 70] < fijo[20, 70]     # tras girar el viento al sur, el fuego llega antes al norte
    assert (fijo[fijo <= 60] == gira[fijo <= 60]).all()   # la primera hora es idéntica


def test_el_cambio_de_hora_no_actua_hacia_atras():
    """Un viento fuerte que entra en la cuarta hora no quema de golpe lo que habría quemado desde el principio."""
    comb, pend, sub = rejilla(lado=301)
    t = tiempos_llegada(comb, pend, sub, CELDA, (150, 20), [Viento(10, 270)] * 3 + [Viento(60, 270)], VERANO, 240)
    antes, justo = np.sum(t < 179.999), np.sum(t <= 180.0)
    assert justo == antes                  # nada arde exactamente en el instante del cambio
    fijo = tiempos_llegada(comb, pend, sub, CELDA, (150, 20), [Viento(10, 270)], VERANO, 180)
    assert (t[fijo <= 180] == fijo[fijo <= 180]).all()   # las tres primeras horas no cambian


def test_condiciones_constantes_por_horas_o_de_una_vez():
    comb, pend, sub = rejilla(lado=121)
    una = tiempos_llegada(comb, pend, sub, CELDA, (60, 60), [Viento(20, 250)], VERANO, 180)
    seco = Humedades(VERANO.m_1h, VERANO.m_10h, VERANO.m_100h, VERANO.m_viva)
    por_horas = tiempos_llegada(comb, pend, sub, CELDA, (60, 60), [Viento(20, 250)] * 3, [VERANO, seco, VERANO], 180)
    assert np.allclose(np.where(np.isfinite(una), una, -1), np.where(np.isfinite(por_horas), por_horas, -1), atol=1e-4)


# --- Humo --------------------------------------------------------------------------------
FOCO = shapely.box(0, 0, 500, 500)


def test_el_humo_va_viento_abajo():
    z = zona_humo(FOCO, 10, 270, 2)        # viento del oeste: el humo va al este
    assert z.contains(shapely.Point(15_000, 250)) and not z.contains(shapely.Point(-5_000, 250))


def test_el_alcance_crece_con_el_tiempo_y_tiene_tope():
    assert zona_humo(FOCO, 10, 270, 2).bounds[2] > zona_humo(FOCO, 10, 270, 1).bounds[2]
    assert zona_humo(FOCO, 100, 270, 2).bounds[2] < (ALCANCE_MAX_KM + 15) * 1000


def test_activos_bajo_humo_con_el_primer_minuto():
    zonas = [(60.0, shapely.box(0, 0, 1000, 1000)), (360.0, shapely.box(0, 0, 5000, 1000))]
    activos = pd.DataFrame({"id": ["cerca", "lejos", "fuera"], "x": [500.0, 3000.0, 9000.0], "y": [500.0] * 3})
    a = activos_bajo_humo(zonas, activos).set_index("id")
    assert a.humo_min.to_dict() == {"cerca": 60.0, "lejos": 360.0}


def test_el_humo_no_pasa_del_alcance_maximo():
    z = zona_humo(FOCO, 100, 270, 2)      # 200 km de recorrido teórico, recortado a 25 km
    assert z.bounds[2] == pytest.approx(500 + ALCANCE_MAX_KM * 1000)


def test_un_foco_que_no_avanza_no_echa_humo():
    from procesamiento.incendio.entradas import Ventana
    t = np.full((81, 81), np.inf)
    t[40, 40] = 0.0                       # solo arde la celda de la ignición
    t[40, 41] = 600.0                     # y una más a las 10 h: 0,5 ha, por debajo de 1 ha
    v = Ventana(0.0, 81 * CELDA, CELDA, 81, 81)
    assert zonas_de_humo(t, v, [Viento(20, 270)], horizonte_min=1440) == []
    t[41, 40:42] = 700.0                  # a las 11 h 40 min, 4 celdas: 1 ha
    zonas = zonas_de_humo(t, v, [Viento(20, 270)], horizonte_min=1440)
    assert zonas[0][0] == 700.0
    # el alcance cuenta desde que hay humo: en el primer paso, 5 min a 20 km/h (unos 1,7 km), no 25 km
    assert zonas[0][1].bounds[2] < 41 * CELDA + 2_000 + 1


def test_zonas_de_humo_cada_paso_y_con_el_viento_de_su_hora():
    comb, pend, sub = rejilla(lado=81)
    t = tiempos_llegada(comb, pend, sub, CELDA, (40, 40), [Viento(20, 270)], VERANO, 120)
    from procesamiento.incendio.entradas import Ventana
    v = Ventana(0.0, 81 * CELDA, CELDA, 81, 81)
    zonas = zonas_de_humo(t, v, [Viento(20, 270), Viento(20, 0)], horizonte_min=120)
    minutos = [m for m, _ in zonas]
    assert minutos[0] == 10.0 and minutos[-1] == 120.0 and len(minutos) == 23   # 1 ha quemada a los 10 min
    primera_hora, segunda = dict(zonas)[55.0], dict(zonas)[65.0]
    assert primera_hora.centroid.x > 40 * CELDA          # viento del oeste: humo al este
    assert segunda.centroid.y < 40 * CELDA                # viento del norte: humo al sur
