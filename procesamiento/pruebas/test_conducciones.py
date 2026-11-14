"""Pruebas del eje de las conducciones (sin red ni capas del catálogo)."""
import numpy as np
import rasterio
import shapely

from procesamiento.conducciones import adelgazar, podar, vectorizar

T = rasterio.Affine(25.0, 0, 400_000.0, 0, -25.0, 4_500_000.0)


def test_una_banda_recta_queda_en_una_linea_por_el_centro():
    banda = np.zeros((40, 200), bool)
    banda[10:21, 5:195] = True             # 11 celdas de ancho, centro en la fila 15
    eje = adelgazar(banda)
    assert eje.sum() < banda.sum() / 5
    filas = np.nonzero(eje)[0]
    assert abs(np.median(filas) - 15) <= 1
    lineas = podar(vectorizar(eje, T))
    assert len(lineas) == 1
    assert lineas[0].length > 150 * 25
    y_centro = T.f + 15.5 * T.e
    assert all(abs(y - y_centro) <= 50 for _, y in lineas[0].coords)


def test_la_poda_quita_ramitas_cortas_y_deja_las_largas():
    tronco = shapely.LineString([(0, 0), (1000, 0)])
    resto = shapely.LineString([(1000, 0), (2000, 0)])
    ramita = shapely.LineString([(1000, 0), (1000, 100)])
    rama = shapely.LineString([(1000, 0), (1000, -800)])
    lineas = podar([tronco, resto, ramita, rama])
    total = sum(l.length for l in lineas)
    assert abs(total - 2800) < 1e-6
