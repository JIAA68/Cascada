"""Pruebas del lector mínimo de teselas vectoriales y de la conversión de coordenadas."""
import math

from procesamiento import nucleos


def _varint(n):
    salida = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        salida.append(b | (0x80 if n else 0))
        if not n:
            return bytes(salida)


def _campo(numero, carga: bytes):
    return _varint(numero << 3 | 2) + _varint(len(carga)) + carga


def _zz(n):
    return (n << 1) ^ (n >> 31)


def _cuadrado(x, y, lado):
    """Geometría MVT de un cuadrado (exterior en sentido horario con el eje y hacia abajo)."""
    return [1 | 1 << 3, _zz(x), _zz(y), 2 | 3 << 3, _zz(lado), 0, 0, _zz(lado), _zz(-lado), 0, 7 | 1 << 3]


def _tesela(capa, geometria):
    paquete = b"".join(_varint(v) for v in geometria)
    rasgo = _varint(3 << 3) + _varint(3) + _campo(4, paquete)        # tipo POLYGON + geometría
    mensaje = _campo(1, capa.encode()) + _campo(2, rasgo) + _varint(5 << 3) + _varint(4096)
    return _campo(3, mensaje)


def test_lee_un_poligono_de_la_capa_pedida():
    tesela = _tesela("nucleo_urbano_pol", _cuadrado(100, 200, 50))
    poligonos = list(nucleos.geometrias_de_capa(tesela, "nucleo_urbano_pol"))
    assert len(poligonos) == 1
    anillos, extension = poligonos[0]
    assert extension == 4096 and len(anillos) == 1
    assert sorted(anillos[0]) == [(100, 200), (100, 250), (150, 200), (150, 250)]
    assert list(nucleos.geometrias_de_capa(tesela, "otra_capa")) == []


def test_hueco_va_con_su_exterior():
    exterior = _cuadrado(0, 0, 100)           # el cursor acaba en (0, 100)
    # Hueco de (10, 10) a (30, 30), en sentido contrario al exterior
    hueco = [1 | 1 << 3, _zz(10), _zz(-90), 2 | 3 << 3, 0, _zz(20), _zz(20), 0, 0, _zz(-20), 7 | 1 << 3]
    poligonos = nucleos.poligonos(exterior + hueco)
    assert len(poligonos) == 1 and len(poligonos[0]) == 2
    assert sorted(poligonos[0][1]) == [(10, 10), (10, 30), (30, 10), (30, 30)]


def test_tesela_y_coordenadas_de_madrid():
    x, y = nucleos.tesela_de(-3.7038, 40.4168, 10)        # Puerta del Sol
    lon, lat = nucleos.a_lonlat(10, x, y, 0, 0, 4096)     # esquina noroeste de su tesela
    assert lon <= -3.7038 < lon + 360 / 1024 and lat >= 40.4168
    assert math.isclose(nucleos.a_lonlat(10, x, y, 4096, 0, 4096)[0], lon + 360 / 1024)
