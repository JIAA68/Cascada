"""Núcleos urbanos para el mapa base a escalas pequeñas.

El mapa base vectorial del IGN trae las manchas de los núcleos urbanos (CartoCiudad) desde el zoom 10
y las manzanas desde el zoom 12. A la capa de núcleos le faltan poblaciones enteras o su casco
principal (Parla, el centro de Majadahonda, Robregordo, Valverde de Alcalá…), que sí tienen manzanas.
Por eso se extraen una vez, de las teselas de zoom 12 que tocan la Comunidad de Madrid, los núcleos y
las manzanas: las manzanas se engordan unos 30 m para cerrar las calles, se unen con los núcleos (y
así se pegan también los trozos cortados en los bordes de tesela), se simplifican y se guardan como
manchas para pintarlas por debajo del zoom 12. Desde el zoom 12 el visor pinta las dos capas del IGN.

Las teselas se leen con un lector mínimo del formato Mapbox Vector Tile (protobuf), sin
dependencias: solo hace falta la geometría de las capas pedidas.

Salida: datos/visor/nucleos_urbanos.geojson (EPSG:4326).
Uso: python -m procesamiento.nucleos
"""
import gzip
import json
import math

import numpy as np
import shapely
from shapely.geometry import Polygon, box, mapping

from .fuentes import BRUTOS, VISOR, descargar

TESELAS = "https://vt-mapabase.idee.es/1.0.0/mapabase/{z}/{x}/{y}.pbf"
ZOOM = 12
CAPA_NUCLEOS, CAPA_MANZANAS = "nucleo_urbano_pol", "manzana_pol"
# Comunidad de Madrid en lon/lat, con un pequeño margen
LIMITES = (-4.62, 39.86, -3.03, 41.18)
ENGORDE = 0.0003          # grados (unos 30 m): cierra las calles entre manzanas
ADELGAZADO = -0.00015     # y se devuelve la mitad, para no engordar el borde de las manchas
SIMPLIFICACION = 0.0003   # grados, unos 30 m: menos de un píxel por debajo del zoom 12
# Se descartan las manchas de menos de 0,02 km², que a esas escalas no llegan a un píxel
SUPERFICIE_MIN_KM2 = 0.02
KM2_POR_GRADO2 = 111.32 ** 2 * math.cos(math.radians(40.4))   # en la latitud de Madrid
SALIDA = VISOR / "nucleos_urbanos.geojson"


# ----------------------------------------------------------------------------- protobuf mínimo
def _varint(b: bytes, i: int) -> tuple[int, int]:
    resultado, desplazamiento = 0, 0
    while True:
        byte = b[i]
        i += 1
        resultado |= (byte & 0x7F) << desplazamiento
        if not byte & 0x80:
            return resultado, i
        desplazamiento += 7


def _campos(b: bytes):
    """Campos de un mensaje protobuf: (número, valor); los delimitados por longitud, como bytes."""
    i = 0
    while i < len(b):
        clave, i = _varint(b, i)
        numero, tipo = clave >> 3, clave & 7
        if tipo == 0:
            valor, i = _varint(b, i)
        elif tipo == 2:
            n, i = _varint(b, i)
            valor, i = b[i:i + n], i + n
        elif tipo == 1:
            valor, i = b[i:i + 8], i + 8
        elif tipo == 5:
            valor, i = b[i:i + 4], i + 4
        else:
            raise ValueError(f"Tipo de campo protobuf no admitido: {tipo}")
        yield numero, valor


def _empaquetados(b: bytes) -> list[int]:
    salida, i = [], 0
    while i < len(b):
        v, i = _varint(b, i)
        salida.append(v)
    return salida


def _zigzag(n: int) -> int:
    return (n >> 1) ^ -(n & 1)


def anillos(geometria: list[int]) -> list[list[tuple[int, int]]]:
    """Anillos de una geometría poligonal MVT (comandos MoveTo, LineTo y ClosePath)."""
    salida, actual, x, y, i = [], [], 0, 0, 0
    while i < len(geometria):
        comando, cuenta = geometria[i] & 7, geometria[i] >> 3
        i += 1
        if comando == 7:                      # ClosePath
            if actual:
                salida.append(actual)
            actual = []
            continue
        for _ in range(cuenta):
            x += _zigzag(geometria[i])
            y += _zigzag(geometria[i + 1])
            i += 2
            if comando == 1:                  # MoveTo: empieza un anillo
                actual = [(x, y)]
            else:                             # LineTo
                actual.append((x, y))
    return salida


def _area(anillo) -> float:
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(anillo, anillo[1:] + anillo[:1])) / 2


def poligonos(geometria: list[int]) -> list[list[list[tuple[int, int]]]]:
    """Polígonos (exterior y huecos) en coordenadas de tesela. En MVT, con el eje y hacia abajo, el
    exterior tiene área positiva y los huecos negativa."""
    salida = []
    for anillo in anillos(geometria):
        a = _area(anillo)
        if a > 0:
            salida.append([anillo])
        elif a < 0 and salida:
            salida[-1].append(anillo)
    return salida


def geometrias_de_capas(tesela: bytes, capas):
    """(capa, polígono, extensión de la tesela) de los polígonos de las capas pedidas."""
    for numero, mensaje in _campos(tesela):
        if numero != 3:
            continue
        nombre, extension, rasgos = None, 4096, []
        for n, v in _campos(mensaje):
            if n == 1:
                nombre = v.decode("utf-8")
            elif n == 5:
                extension = v
            elif n == 2:
                rasgos.append(v)
        if nombre not in capas:
            continue
        for rasgo in rasgos:
            tipo, geometria = 0, []
            for n, v in _campos(rasgo):
                if n == 3:
                    tipo = v
                elif n == 4:
                    geometria = _empaquetados(v)
            if tipo == 3:                     # POLYGON
                for p in poligonos(geometria):
                    yield nombre, p, extension


def geometrias_de_capa(tesela: bytes, capa: str):
    """Polígonos de una capa de una tesela y la extensión de la tesela."""
    for _, p, extension in geometrias_de_capas(tesela, (capa,)):
        yield p, extension


# ----------------------------------------------------------------------------- teselas
def tesela_de(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2 ** z
    return int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


def a_lonlat(z: int, x: int, y: int, px: float, py: float, extension: int) -> tuple[float, float]:
    n = 2 ** z
    gx, gy = (x + px / extension) / n, (y + py / extension) / n
    return gx * 360 - 180, math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * gy))))


def contorno_comunidad():
    """Límite de la Comunidad en lon/lat (unión de los municipios), para elegir las teselas que la tocan."""
    from .incendio.entradas import A_GEO, municipios
    union = shapely.union_all([g for _, _, g in municipios()])
    return shapely.transform(union, lambda xy: np.column_stack(A_GEO.transform(xy[:, 0], xy[:, 1])))


def teselas_comunidad(z: int) -> list[tuple[int, int]]:
    contorno = contorno_comunidad()
    x0, y0 = tesela_de(LIMITES[0], LIMITES[3], z)
    x1, y1 = tesela_de(LIMITES[2], LIMITES[1], z)
    salida = []
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            lon0, lat1 = a_lonlat(z, x, y, 0, 0, 1)
            lon1, lat0 = a_lonlat(z, x, y, 1, 1, 1)
            if contorno.intersects(box(lon0, lat0, lon1, lat1)):
                salida.append((x, y))
    return salida


def construir() -> int:
    teselas = teselas_comunidad(ZOOM)
    nucleos, manzanas = [], []
    for i, (x, y) in enumerate(teselas):
        ruta = descargar(TESELAS.format(z=ZOOM, x=x, y=y), BRUTOS / "ign_vectorial" / f"{ZOOM}_{x}_{y}.pbf",
                         "IGN, mapa base vectorial (núcleos urbanos y manzanas)")
        datos = ruta.read_bytes()
        if datos[:2] == b"\x1f\x8b":
            datos = gzip.decompress(datos)
        for capa, anillos_tesela, extension in geometrias_de_capas(datos, (CAPA_NUCLEOS, CAPA_MANZANAS)):
            anillos_geo = [[a_lonlat(ZOOM, x, y, px, py, extension) for px, py in a] for a in anillos_tesela]
            p = shapely.make_valid(Polygon(anillos_geo[0], anillos_geo[1:]))
            destino = nucleos if capa == CAPA_NUCLEOS else manzanas
            destino.extend(g for g in shapely.get_parts(p) if g.geom_type == "Polygon")
        if (i + 1) % 50 == 0:
            print(f"  teselas {i + 1}/{len(teselas)}", flush=True)
    # Las manzanas se engordan para cerrar las calles; la unión pega también los trozos cortados en los bordes
    engordadas = shapely.buffer(np.array(manzanas, dtype=object), ENGORDE, quad_segs=2) if manzanas else []
    manchas = shapely.union_all([*nucleos, *engordadas]).buffer(ADELGAZADO).simplify(SIMPLIFICACION, preserve_topology=True)
    piezas = [g for g in shapely.get_parts(manchas)
              if g.geom_type == "Polygon" and g.area * KM2_POR_GRADO2 >= SUPERFICIE_MIN_KM2]
    rasgos = [{"type": "Feature", "properties": {},
               "geometry": json.loads(json.dumps(mapping(shapely.set_precision(g, 1e-5))))} for g in piezas]
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps({"type": "FeatureCollection", "features": rasgos}, separators=(",", ":")),
                      encoding="utf-8")
    print(f"  núcleos urbanos: {len(rasgos)} manchas de {len(teselas)} teselas de zoom {ZOOM} ({len(nucleos)} polígonos de"
          f" núcleo y {len(manzanas)} manzanas), {SALIDA.stat().st_size / 1e6:.1f} MB")
    return len(rasgos)


if __name__ == "__main__":
    construir()
