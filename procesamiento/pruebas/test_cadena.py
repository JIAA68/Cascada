"""Pruebas de la cadena de datos que no necesitan las descargas."""
import numpy as np
import pytest

from procesamiento import basal, capas, rejilla, teselas


# --- matriz de riesgo --------------------------------------------------------------------
@pytest.mark.parametrize("peligrosidad, vulnerabilidad, esperado", [
    (0, 5, 0), (3, 0, 0),          # sin peligro o sin vulnerabilidad: sin riesgo
    (1, 1, 1), (5, 5, 5),          # esquinas de la matriz
    (2, 5, 4), (5, 2, 3), (3, 3, 3), (4, 4, 4),
    (2, 4, 3),                     # nube tóxica (máximo baja) sobre vulnerabilidad alta: moderado
    (2, 5, 4),                     # ... y sobre muy alta: alto (se acepta por decisión del proyecto)
])
def test_matriz_riesgo(peligrosidad, vulnerabilidad, esperado):
    assert capas.riesgo(peligrosidad, vulnerabilidad) == esperado


def test_matriz_es_monotona():
    for v in range(1, 6):
        fila = [capas.riesgo(p, v) for p in range(1, 6)]
        assert fila == sorted(fila)
    for p in range(1, 6):
        columna = [capas.riesgo(p, v) for v in range(1, 6)]
        assert columna == sorted(columna)


def test_trece_capas_con_sus_codigos_del_catalogo():
    assert len(capas.CAPAS) == 13
    assert capas.CAPAS["6_16"][0] == "Transporte por carretera"   # no 6_17 (túneles)
    assert capas.CAPAS["6_15"][0] == "Transporte por tren"
    assert capas.CON_FONDO == {"3_1", "6_14"}
    assert sum(g == "Naturales" for _, g in capas.CAPAS.values()) == 5


# --- rejilla de 1 km ---------------------------------------------------------------------
def test_identificador_de_celda_como_el_ine():
    assert rejilla.id_celda(3160, 2030) == "CRS3035RES1000mN2030000E3160000"


def test_celda_de_un_punto_en_madrid():
    # Puerta del Sol (EPSG:25830) y la misma en lon/lat: misma celda
    e, n = rejilla.celda_de_utm([440300.0], [4474400.0])
    assert rejilla.celda_de_lonlat(-3.7035, 40.4168) == (int(e[0]), int(n[0]))
    contorno = rejilla.contorno(int(e[0]), int(n[0]))
    assert len(contorno) == 5 and contorno[0] == contorno[-1]
    assert all(-4.6 < lon < -3.0 and 39.8 < lat < 41.2 for lon, lat in contorno)


def test_acumulador_cuenta_niveles_por_celda():
    a = basal.Acumulador(n_capas=2)
    claves = np.array([7, 7, 9, 7, 9])
    niveles = np.array([[0, 1, 5, 1, 0],
                        [2, 2, 2, 2, 2]])
    a.sumar(claves, niveles)
    a.sumar(np.array([9]), np.array([[3], [0]]))
    i7, i9 = a.indice[7], a.indice[9]
    assert a.dentro[i7] == 3 and a.dentro[i9] == 3
    assert a.conteo[i7, 0].tolist() == [1, 2, 0, 0, 0, 0]
    assert a.conteo[i9, 0].tolist() == [1, 0, 0, 1, 0, 1]
    assert a.conteo[i9, 1].tolist() == [1, 0, 2, 0, 0, 0]


def test_acumulador_crece():
    a = basal.Acumulador(n_capas=1)
    claves = np.arange(5000)
    a.sumar(claves, np.ones((1, 5000), np.int64))
    assert len(a.indice) == 5000 and a.conteo[:5000, 0, 1].sum() == 5000


# --- teselas -----------------------------------------------------------------------------
def test_colorear_respeta_fondo_y_engrosa():
    niveles = np.zeros((8, 8), np.uint8)
    niveles[4, 4] = 3
    niveles[0, 0] = 1
    rgba = teselas.colorear(niveles, con_fondo=True, bordes=False)
    assert tuple(rgba[0, 0]) == teselas.FONDO
    assert tuple(rgba[4, 4]) == teselas.PALETA[3]
    assert (rgba[..., 3] > 0).sum() == 2
    engrosada = teselas.colorear(niveles, con_fondo=False, engrosar=3, bordes=False)
    assert (engrosada[3:6, 3:6, 3] == teselas.PALETA[3][3]).all()


def test_borde_oscuro_y_sin_borde_en_el_fondo():
    niveles = np.ones((9, 9), np.uint8)       # fondo de incendios en todo
    niveles[2:7, 2:7] = 4                     # una zona de nivel 4
    rgba = teselas.colorear(niveles, con_fondo=True)
    assert tuple(rgba[2, 2]) == teselas.BORDE[4] and tuple(rgba[2, 4]) == teselas.BORDE[4]
    assert tuple(rgba[4, 4]) == teselas.PALETA[4]          # interior sin borde
    assert tuple(rgba[0, 0]) == teselas.FONDO              # el fondo no lleva borde


def test_engrosado_por_tipo_de_capa_y_zoom():
    assert teselas.engrosado("6_16", 7) == teselas.engrosado("6_16", 13) == 3   # lineal
    assert teselas.engrosado("6_11", 9) > teselas.engrosado("6_11", 12) > teselas.engrosado("6_11", 13) == 1
    assert teselas.engrosado("3_1", 9) == 1                                      # superficie


def test_moda_2x2_prefiere_el_mas_frecuente_y_en_empate_el_mayor():
    a = np.array([[5, 1, 2, 3],
                  [1, 1, 3, 2]], np.uint8)
    assert teselas.moda_2x2(a).tolist() == [[1, 3]]


def test_factor_de_reduccion_por_zoom():
    assert teselas.factor_para(13) == 1
    assert teselas.factor_para(7) == 32
    for z in range(7, 14):
        assert teselas.factor_para(z) >= teselas.factor_para(z + 1)


def test_teselas_que_cubren_madrid_en_zoom_7():
    # Madrid en Web Mercator, aprox. x -480000..-330000, y 4880000..5080000
    lista = list(teselas.teselas_que_cubren((-480000, 4880000, -330000, 5080000), 7))
    assert 1 <= len(lista) <= 4 and all(x == 62 and y in (47, 48) for x, y in lista)


# --- capas combinadas por grupo ------------------------------------------------------------
def test_combinar_toma_el_maximo_sin_el_fondo():
    from procesamiento import combinadas
    incendios = np.array([[1, 1, 3], [255, 1, 5]], dtype=np.uint8)     # el 1 es fondo: no cuenta
    avenidas = np.array([[0, 2, 1], [255, 0, 0]], dtype=np.uint8)
    derrumbes = np.array([[0, 0, 0], [255, 0, 4]], dtype=np.uint8)
    salida = combinadas.combinar({"3_1": incendios, "2_1": avenidas, "6_27": derrumbes})
    assert salida.dtype == np.uint8
    assert salida.tolist() == [[0, 2, 3], [255, 0, 5]]   # fondo solo -> 0; fuera de todas -> 255


def test_capas_combinadas_cubren_los_dos_grupos():
    assert sorted(capas.capas_del_grupo("Naturales")) == sorted(c for c, (_, g) in capas.CAPAS.items() if g == "Naturales")
    assert len(capas.capas_del_grupo("Naturales")) == 5 and len(capas.capas_del_grupo("Tecnológicos")) == 8
    assert capas.nombre_capa("naturales") == "Peligrosidad natural máxima"
    assert teselas.fichero("naturales").name == "combinada_naturales.pmtiles" and teselas.fichero("3_1").name == "peligrosid_3_1.pmtiles"
