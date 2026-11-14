"""Pruebas del mapa de combustibles de la Comunidad: lectura de páginas del WFS, ráster y combinación con EFFIS."""
import gzip
import json

import numpy as np
import pytest

from procesamiento.incendio import combustible_cm
from procesamiento.incendio.entradas import combinar


def pagina(ruta, poligonos, comprimir=True):
    """Página como la que devuelve el WFS: FeatureCollection con NM_BEHAVE y la geometría en EPSG:25830."""
    d = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": f"f{i}", "properties": {"NM_BEHAVE": modelo},
         "geometry": {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}}
        for i, ((x0, y0, x1, y1), modelo) in enumerate(poligonos)]}
    datos = json.dumps(d).encode()
    ruta.write_bytes(gzip.compress(datos) if comprimir else datos)
    return ruta


def test_pagina_comprimida_y_sin_comprimir(tmp_path):
    a = combustible_cm.leer_pagina(pagina(tmp_path / "a.json.gz", [((0, 0, 100, 100), 1)]))
    b = combustible_cm.leer_pagina(pagina(tmp_path / "b.json", [((0, 0, 100, 100), 4)], comprimir=False))
    assert a[0][1] == 1 and b[0][1] == 4 and a[0][0].area == 10000


def test_respuesta_de_error_del_wfs(tmp_path):
    ruta = tmp_path / "error.json.gz"
    ruta.write_bytes(gzip.compress(b'{"type": "ExceptionReport"}'))
    with pytest.raises(RuntimeError):
        combustible_cm.leer_pagina(ruta)


def test_rasterizar_varias_paginas(tmp_path):
    p1 = pagina(tmp_path / "p1.json.gz", [((0, 0, 100, 200), 1)])             # mitad oeste: pasto
    p2 = pagina(tmp_path / "p2.json.gz", [((100, 0, 150, 200), 0)])           # franja sin combustible
    modelo, transform = combustible_cm.rasterizar([p1, p2], extension=(0, 0, 200, 200), celda=25)
    assert modelo.shape == (8, 8)
    assert (modelo[:, :4] == 1).all() and (modelo[:, 4:6] == 0).all()
    assert (modelo[:, 6:] == combustible_cm.SIN_DATO).all()                   # sin polígono: sin dato


def test_la_comunidad_manda_y_effis_rellena():
    sd = combustible_cm.SIN_DATO
    comunidad = np.array([[1, 0], [sd, sd]], dtype=np.uint8)
    effis = np.array([[0, 2], [4, 0]], dtype=np.int16)
    assert combinar(comunidad, effis).tolist() == [[1, 0], [4, 0]]           # el 0 de la Comunidad es real
    assert combinar(None, effis).tolist() == effis.tolist()                    # sin ráster, solo EFFIS
