"""Pruebas de las rachas con tormenta y de la humedad del combustible hora a hora (decisiones del 10-11-2026)."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from procesamiento.incendio import validacion
from procesamiento.incendio.combustibles import VERANO, Humedades, humedad_equilibrio, humedades_del_aire
from procesamiento.incendio.entradas import MADRID, _en_periodo, leer_prevision, meteo_horaria
from procesamiento.incendio.propagacion import Viento, tiempos_llegada
from procesamiento.prealerta import umbrales

INICIO = datetime(2026, 8, 11, 19, 45, tzinfo=MADRID)


# --- Humedad del combustible --------------------------------------------------------------
def test_la_humedad_de_equilibrio_es_la_de_fosberg():
    # sin viento, el índice de Fosberg solo depende de la humedad de equilibrio
    m = humedad_equilibrio(35, 20)
    eta = 1 - 2 * (m / 30) + 1.5 * (m / 30) ** 2 - 0.5 * (m / 30) ** 3
    assert umbrales.fosberg(35, 20, 0) == round(eta / 0.3002, 1)


def test_aire_seco_y_caliente_seca_el_combustible():
    seco, humedo = humedades_del_aire(37, 12), humedades_del_aire(15, 80)
    assert seco.m_1h < VERANO.m_1h < humedo.m_1h
    assert seco.m_10h == pytest.approx(seco.m_1h + 0.01) and seco.m_viva == VERANO.m_viva
    assert humedades_del_aire(45, 0).m_1h == 0.02          # nunca por debajo del 2 %


def rejilla(lado=81):
    comb = np.full((lado, lado), 1)
    return comb, np.zeros((lado, lado)), np.zeros((lado, lado))


def test_combustible_mas_seco_arde_mas_deprisa_y_la_humedad_cambia_por_hora():
    comb, pend, sub = rejilla()
    viento = [Viento(15, 270)] * 3
    normal = tiempos_llegada(comb, pend, sub, 50, (40, 40), viento, VERANO, 120)
    seco = tiempos_llegada(comb, pend, sub, 50, (40, 40), viento, Humedades(0.03, 0.04, 0.05, 0.9), 120)
    assert seco[40, 70] < normal[40, 70]
    por_hora = tiempos_llegada(comb, pend, sub, 50, (40, 40), viento, [VERANO, Humedades(0.03, 0.04, 0.05, 0.9)], 120)
    assert (por_hora[normal <= 60] == normal[normal <= 60]).all()   # la primera hora es la de verano


# --- Predicción de AEMET y rachas ------------------------------------------------------
def test_periodos_de_aemet():
    assert _en_periodo("1420", 19) and not _en_periodo("1420", 20)
    assert _en_periodo("2002", 23) and _en_periodo("2002", 1) and not _en_periodo("2002", 2)


def prevision_json(prob_tormenta_tarde):
    horas = [f"{h:02d}" for h in range(18, 24)]
    return [{"prediccion": {"dia": [{
        "fecha": "2026-08-11T00:00:00",
        "vientoAndRachaMax": [x for h in horas for x in ({"direccion": ["NO"], "velocidad": ["15"], "periodo": h},
                                                            {"value": "60", "periodo": h})],
        "temperatura": [{"value": "33", "periodo": h} for h in horas],
        "humedadRelativa": [{"value": "20", "periodo": h} for h in horas],
        "probTormenta": [{"value": "0", "periodo": "1420"}, {"value": str(prob_tormenta_tarde), "periodo": "2002"}],
    }]}}]


def test_leer_prevision():
    p = leer_prevision(prevision_json(55))
    h = datetime(2026, 8, 11, 21, tzinfo=MADRID)
    assert p[h]["viento"] == Viento(15, 315) and p[h]["racha_kmh"] == 60
    assert p[h]["temperatura"] == 33 and p[h]["humedad"] == 20 and p[h]["prob_tormenta"] == 55
    assert p[datetime(2026, 8, 11, 19, tzinfo=MADRID)]["prob_tormenta"] == 0


def test_racha_solo_en_las_horas_de_tormenta():
    observado = Viento(10, 300)
    estacion = {"racha_kmh": 30.0, "racha_desde": 310.0, "temperatura": 34.0, "humedad": 18.0}
    v, h, origen, rachas = meteo_horaria(observado, estacion, leer_prevision(prevision_json(55)), 70, INICIO, horas=4)
    # 19:00 sin tormenta y racha observada floja: viento medio; 20:00 a 22:00, tormenta prevista: la racha prevista
    assert rachas == [False, True, True, True]
    assert v[0] == observado and v[1] == Viento(60, 315)
    assert h[0] == humedades_del_aire(34, 18) and h[1] == humedades_del_aire(33, 20)
    assert origen == ["observado", "previsto", "previsto", "previsto"]
    v, _, _, rachas = meteo_horaria(observado, estacion, leer_prevision(prevision_json(10)), 70, INICIO, horas=4)
    assert rachas == [False] * 4 and v[1] == Viento(15, 315)


def test_racha_fuerte_observada_en_la_primera_hora():
    estacion = {"racha_kmh": 75.0, "racha_desde": 320.0, "temperatura": None, "humedad": None}
    v, h, _, rachas = meteo_horaria(Viento(20, 300), estacion, leer_prevision(prevision_json(0)), 70, INICIO, horas=2)
    assert rachas[0] and v[0] == Viento(75, 320)
    assert h[0] == humedades_del_aire(33, 20)                 # sin dato observado, la temperatura y humedad previstas


def test_sin_prevision_se_repite_y_la_humedad_es_la_de_verano():
    v, h, origen, rachas = meteo_horaria(Viento(12, 270), {}, {}, 70, INICIO, horas=3)
    assert v == [Viento(12, 270)] * 3 and h == [VERANO] * 3 and origen == ["observado", "repetido", "repetido"]


# --- Validación: humedad medida -----------------------------------------------------------
def test_humedad_de_la_red_de_calidad_del_aire():
    marca = datetime(2025, 8, 11, 19, tzinfo=timezone.utc)      # hora de la red que contiene las 20:15 de Madrid
    serie = {(marca, 83): 33.0, (marca, 86): 19.0}
    h = validacion.humedades_desde(serie, datetime(2025, 8, 11, 19, 45, tzinfo=MADRID), horas=2)
    assert h[0] == humedades_del_aire(33, 19) and h[1] == h[0]
    assert validacion.humedades_desde({}, datetime(2025, 8, 11, 19, 45, tzinfo=MADRID), 1) == [VERANO]


# --- Salto de franjas sin combustible (pavesas) --------------------------------------------
def franja(anchura_celdas: int, lado: int = 61):
    """Pasto con una franja sin combustible de norte a sur al este de la ignición (en la columna 35)."""
    comb = np.full((lado, lado), 1)
    comb[:, 35:35 + anchura_celdas] = 0
    return comb, np.zeros((lado, lado)), np.zeros((lado, lado))


def test_con_viento_fuerte_el_fuego_salta_una_franja_estrecha():
    comb, pend, sub = franja(4)                    # 200 m
    fuerte = tiempos_llegada(comb, pend, sub, 50, (30, 30), [Viento(40, 270)], VERANO, 180)
    flojo = tiempos_llegada(comb, pend, sub, 50, (30, 30), [Viento(20, 270)], VERANO, 180)
    assert np.isfinite(fuerte[30, 45]) and np.isinf(flojo[30, 45])
    assert np.isinf(fuerte[:, 35:39]).all()        # la franja no arde: se salta


def test_no_salta_franjas_anchas_ni_viento_arriba():
    comb, pend, sub = franja(8)                    # 400 m, más que el salto máximo
    t = tiempos_llegada(comb, pend, sub, 50, (30, 30), [Viento(60, 270)], VERANO, 180)
    assert np.isinf(t[:, 43:]).all()
    comb, pend, sub = franja(4)
    t = tiempos_llegada(comb, pend, sub, 50, (30, 30), [Viento(60, 90)], VERANO, 180)   # viento del este
    assert np.isinf(t[:, 39:]).all()


# --- Combustible vivo estacional y sin límite de viento ------------------------------------
def test_el_vivo_se_seca_de_julio_a_septiembre():
    from procesamiento.incendio.combustibles import humedad_viva
    assert humedad_viva(datetime(2025, 8, 11)) == 0.60 and humedad_viva(datetime(2025, 7, 1)) == 0.60
    assert humedad_viva(datetime(2025, 10, 1)) == VERANO.m_viva and humedad_viva(datetime(2025, 6, 30)) == VERANO.m_viva


def test_sin_limite_el_viento_fuerte_sigue_acelerando():
    from procesamiento.incendio.combustibles import MODELOS
    from procesamiento.incendio.rothermel import KMH_A_FT_MIN, factor_viento, lecho
    k = lecho(MODELOS[1], VERANO)
    limite_antiguo_kmh = 0.9 * k.intensidad_reaccion / KMH_A_FT_MIN
    assert factor_viento(k, 2 * limite_antiguo_kmh) > factor_viento(k, limite_antiguo_kmh) * 1.5


# --- Ventana de AEMET y explicación cuando no arde -----------------------------------------
def test_ventana_de_aemet():
    from procesamiento.incendio.entradas import comprobar_ventana
    prev = leer_prevision(prevision_json(0))                       # 11-08-2026 de 18:00 a 23:00
    obs = "2026-08-11T17:00:00+0000"                                # 19:00 en Madrid
    assert comprobar_ventana(datetime(2026, 8, 11, 19, 30, tzinfo=MADRID), obs, prev) is True
    assert comprobar_ventana(datetime(2026, 8, 11, 17, 0, tzinfo=MADRID), obs, prev) is True     # 2 h antes: aún vale
    assert comprobar_ventana(datetime(2026, 8, 11, 22, 0, tzinfo=MADRID), obs, prev) is False    # futura: la previsión
    with pytest.raises(ValueError, match="viento a mano"):
        comprobar_ventana(datetime(2026, 8, 1, 11, 0, tzinfo=MADRID), obs, prev)                 # días antes
    with pytest.raises(ValueError):
        comprobar_ventana(datetime(2026, 8, 13, 12, 0, tzinfo=MADRID), obs, prev)                # más allá de la previsión


def test_ignicion_futura_usa_la_prevision_en_la_primera_hora():
    observado = Viento(10, 300)
    v, h, origen, _ = meteo_horaria(observado, {"temperatura": 20.0, "humedad": 50.0}, leer_prevision(prevision_json(0)), 70,
                                    datetime(2026, 8, 11, 21, 0, tzinfo=MADRID), horas=2, primera_observada=False)
    assert v[0] == Viento(15, 315) and origen[0] == "previsto" and h[0] == humedades_del_aire(33, 20)


def test_por_que_no_arde():
    from procesamiento.incendio.combustibles import MODELOS
    from procesamiento.incendio.simulacion import sin_propagacion
    solo = np.full((3, 3), np.inf); solo[1, 1] = 0
    humedo = sin_propagacion(solo, MODELOS[2], [Humedades(0.265, 0.275, 0.285, 0.9)])
    assert "26,5" in humedo.replace(".", ",") and "15 %" in humedo
    assert "combustible continuo" in sin_propagacion(solo, MODELOS[2], [VERANO])
    arde = solo.copy(); arde[1, 2] = 30
    assert sin_propagacion(arde, MODELOS[2], [VERANO]) is None
