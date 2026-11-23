"""Teselas de relieve para la vista en 3D: codificación Terrarium y relleno del borde sin dato."""
import numpy as np

from procesamiento.relieve import rellenar, terrarium


def decodificar(rgb):
    r, g, b = (rgb[..., i].astype(float) for i in range(3))
    return r * 256 + g + b / 256 - 32768


def test_terrarium_ida_y_vuelta():
    alt = np.array([[0.0, 648.0, 2428.25], [-12.5, 495.75, 1000.0]])
    assert np.allclose(decodificar(terrarium(alt)), alt, atol=1 / 256)


def test_rellenar_con_el_valor_mas_cercano():
    alt = np.array([[100, 100, -32768], [200, 200, -32768]], dtype=np.int16)
    lleno = rellenar(alt, alt == -32768)
    assert lleno.tolist() == [[100, 100, 100], [200, 200, 200]]
