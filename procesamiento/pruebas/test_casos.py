"""Pruebas de la validación con varios casos (sin red ni motor)."""
import math

from procesamiento.incendio import casos, propagacion, rothermel
from procesamiento.incendio.entradas import A_UTM


def test_todos_los_casos_tienen_inicio_y_punto():
    for c in casos.CASOS.values():
        assert c.inicio is not None and c.punto is not None and c.inicio.tzinfo is not None


def test_cinco_puntos_a_la_distancia_fijada():
    c = casos.CASOS["tres_cantos_2025"]
    puntos = casos.puntos_ignicion(c)
    x0, y0 = A_UTM.transform(*c.punto)
    assert len(puntos) == 5 and puntos[0] == c.punto
    for p in puntos[1:]:
        x, y = A_UTM.transform(*p)
        assert math.isclose(math.hypot(x - x0, y - y0), casos.RADIO_M, rel_tol=1e-3)


def test_la_configuracion_se_aplica_y_se_deshace():
    salto, factor = propagacion.SALTO_M, rothermel.factor_viento
    with casos.configuracion("con_limite"):
        assert rothermel.factor_viento is not factor
    with casos.configuracion("sin_salto"):
        assert propagacion.SALTO_M == 0.0
    assert propagacion.SALTO_M == salto and rothermel.factor_viento is factor


def test_resumen():
    assert casos.resumen([0.2, 0.6, None, 0.4]) == {"mediana": 0.4, "min": 0.2, "max": 0.6, "n": 3}
    assert casos.resumen([None]) is None
