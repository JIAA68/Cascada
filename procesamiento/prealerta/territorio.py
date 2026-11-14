"""Territorio de la prealerta: municipios, zonas de aviso de AEMET y municipio de cada activo.

Genera, en la cadena de datos:

- datos/visor/municipios.geojson: los 179 municipios de la Comunidad (los 21 distritos de Madrid unidos), con su
  código INE y su nombre, simplificados para pintarlos por nivel de prealerta.
- datos/brutos/aemet/AEMET-meteoalerta-delimitacion-zonas.zip: delimitación oficial de las zonas de aviso del Plan
  Meteoalerta (AEMET, versión 6), registrada como fuente de la cadena.
- datos/visor/zonas_aviso.geojson: las tres zonas de aviso de la Comunidad de Madrid.
- datos/procesados/municipios.csv: código, nombre, zona de aviso (la de mayor solape) y centroide en lon/lat.
- datos/procesados/activos_municipio.csv: municipio de cada activo, por cruce espacial.

Uso: python -m procesamiento.prealerta.territorio
"""
import json

import numpy as np
import pandas as pd
import pyogrio.raw
import shapely
from pyproj import Transformer
from shapely.geometry import mapping

from ..activos import escribir as escribir_activos
from ..fuentes import BRUTOS, PROCESADOS, VISOR, descargar
from ..incendio.entradas import A_GEO
from ..incendio.entradas import municipios as municipios_fuente

URL_ZONAS = ("https://www.aemet.es/documentos/es/eltiempo/prediccion/avisos/plan_meteoalerta/"
             "AEMET-meteoalerta-delimitacion-zonas.zip")
ZIP_ZONAS = BRUTOS / "aemet" / "AEMET-meteoalerta-delimitacion-zonas.zip"
SHP_ZONAS = "AEMET-meteoalerta-delimitacion-zonas/AEMET-meteoalerta-v6-zonas-32630.shp"
CCAA_MADRID = "72"
SIMPLIFICACION_M = 30
PRECISION = 1e-5
DESDE_32630 = Transformer.from_crs("EPSG:32630", "EPSG:25830", always_xy=True)


def _reproyectar(geometria, transformador):
    return shapely.transform(geometria, lambda xy: np.column_stack(transformador.transform(xy[:, 0], xy[:, 1])))


def a_lonlat(geometria):
    return shapely.set_precision(_reproyectar(geometria, A_GEO), PRECISION)


def municipios() -> list[tuple[str, str, shapely.Geometry]]:
    """Un polígono por municipio (código INE de 5 cifras, nombre), con los distritos de Madrid unidos."""
    partes, nombres = {}, {}
    for codigo, nombre, g in municipios_fuente():
        partes.setdefault(codigo, []).append(g)
        nombres.setdefault(codigo, nombre)
    salida = []
    for codigo, lista in sorted(partes.items()):
        geometria = shapely.union_all(lista) if len(lista) > 1 else lista[0]
        salida.append((codigo, "Madrid" if codigo == "28079" else nombres[codigo], geometria))
    return salida


def zonas_aviso() -> list[tuple[str, str, shapely.Geometry]]:
    """(código, nombre, geometría en EPSG:25830) de las zonas de aviso de Meteoalerta de la Comunidad de Madrid."""
    descargar(URL_ZONAS, ZIP_ZONAS, "AEMET, delimitación de las zonas de aviso del Plan Meteoalerta (v6)")
    meta, _, geoms, campos = pyogrio.raw.read(f"/vsizip/{ZIP_ZONAS.as_posix()}/{SHP_ZONAS}")
    nombres = list(meta["fields"])
    codigos, textos, ccaa = (campos[nombres.index(c)] for c in ("COD_Z", "NOM_Z", "COD_CCAA"))
    return [(str(c), str(n), _reproyectar(g, DESDE_32630))
            for c, n, a, g in zip(codigos, textos, ccaa, shapely.from_wkb(geoms)) if str(a) == CCAA_MADRID]


def _geojson(rasgos, ruta):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({"type": "FeatureCollection", "features": rasgos}, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")


def construir() -> pd.DataFrame:
    lista = municipios()
    zonas = zonas_aviso()

    # Municipios para el visor y su zona de aviso (la de mayor solape; si no toca ninguna, la más cercana)
    rasgos, filas = [], []
    for codigo, nombre, g in lista:
        simple = g.simplify(SIMPLIFICACION_M, preserve_topology=True)
        rasgos.append({"type": "Feature", "properties": {"codigo": codigo, "nombre": nombre},
                       "geometry": mapping(a_lonlat(simple))})
        solapes = [(g.intersection(zg).area, cz) for cz, _, zg in zonas]
        zona = max(solapes)[1] if max(solapes)[0] > 0 else min((g.distance(zg), cz) for cz, _, zg in zonas)[1]
        lon, lat = A_GEO.transform(g.centroid.x, g.centroid.y)
        filas.append({"codigo": codigo, "nombre": nombre, "zona": zona, "lon": round(lon, 5), "lat": round(lat, 5),
                      "superficie_km2": round(g.area / 1e6, 2)})
    _geojson(rasgos, VISOR / "municipios.geojson")
    tabla = pd.DataFrame(filas)
    PROCESADOS.mkdir(parents=True, exist_ok=True)
    tabla.to_csv(PROCESADOS / "municipios.csv", index=False, encoding="utf-8")

    # Zonas de aviso para el visor: el polígono y un punto en su parte mayor para el rótulo (hay exclaves)
    rasgos_zonas = []
    for cz, nz, zg in zonas:
        mayor = max(zg.geoms, key=lambda p: p.area) if zg.geom_type == "MultiPolygon" else zg
        rasgos_zonas.append({"type": "Feature", "properties": {"zona": cz, "nombre": nz},
                             "geometry": mapping(a_lonlat(zg.simplify(100, preserve_topology=True)))})
        rasgos_zonas.append({"type": "Feature", "properties": {"zona": cz, "nombre": nz},
                             "geometry": mapping(a_lonlat(mayor.representative_point()))})
    _geojson(rasgos_zonas, VISOR / "zonas_aviso.geojson")

    # Municipio de cada activo (cruce espacial; los de fuera, al más cercano)
    ruta_activos = PROCESADOS / "activos.csv"
    activos = pd.read_csv(ruta_activos) if ruta_activos.exists() else escribir_activos()
    activos = activos.dropna(subset=["x", "y"])
    puntos = shapely.points(activos["x"].to_numpy(), activos["y"].to_numpy())
    arbol = shapely.STRtree([g for _, _, g in lista])
    asignado = np.full(len(puntos), -1)
    i_punto, i_mun = arbol.query(puntos, predicate="within")
    asignado[i_punto] = i_mun
    fuera = asignado < 0
    if fuera.any():
        asignado[fuera] = arbol.nearest(puntos[fuera])
    codigos = [lista[i][0] for i in asignado]
    pd.DataFrame({"id": activos["id"].to_numpy(), "codigo_municipio": codigos}).to_csv(
        PROCESADOS / "activos_municipio.csv", index=False, encoding="utf-8")
    print(f"  municipios: {len(tabla)} ({tabla['zona'].value_counts().to_dict()}); zonas: {len(zonas)}; "
          f"activos asignados: {len(codigos)} ({int(fuera.sum())} fuera de todo municipio)")
    return tabla


if __name__ == "__main__":
    construir()
