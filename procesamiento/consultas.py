"""Consultas del análisis basal para la API local: celda de 1 km y activo.

Trabajan sobre los ficheros precalculados por procesamiento.basal, cargados una sola vez.
Los centros sensibles nunca se devuelven uno a uno: de ellos solo sale el
número de centros y de plazas de la celda.
"""
from functools import lru_cache

import pandas as pd

from .capas import CAPAS, CON_FONDO, NIVELES, RIESGOS
from .fuentes import PROCESADOS, VISOR
from .rejilla import celda_de_lonlat, contorno, id_celda

CAMPOS_ACTIVO = ["id", "familia", "subtipo", "tipo", "nombre", "municipio", "vulnerabilidad", "plazas", "lon", "lat"]


class NoEncontrado(LookupError):
    pass


@lru_cache(maxsize=1)
def rejilla() -> pd.DataFrame:
    return pd.read_csv(PROCESADOS / "rejilla_1km.csv").set_index("grd_id")


@lru_cache(maxsize=1)
def activos() -> pd.DataFrame:
    return pd.read_csv(PROCESADOS / "activos_basal.csv").set_index("id", drop=False)


def _valor(v):
    if pd.isna(v):
        return None
    return v.item() if hasattr(v, "item") else v


def riesgos_de_activo(fila) -> list[dict]:
    salida = []
    for codigo, (nombre, grupo) in CAPAS.items():
        peligrosidad, r = int(fila[f"n_{codigo}"]), int(fila[f"r_{codigo}"])
        if peligrosidad == 0:
            continue
        salida.append({"codigo": codigo, "nombre": nombre, "grupo": grupo, "fondo": codigo in CON_FONDO and peligrosidad == 1,
                       "peligrosidad": peligrosidad, "peligrosidad_nombre": NIVELES[peligrosidad],
                       "riesgo": r, "riesgo_nombre": RIESGOS[r]})
    return sorted(salida, key=lambda d: (-d["riesgo"], -d["peligrosidad"]))


def resumen_activo(fila, con_riesgos=True) -> dict:
    d = {c: _valor(fila[c]) for c in CAMPOS_ACTIVO}
    d["riesgo_max"] = int(fila["riesgo_max"])
    d["riesgo_max_nombre"] = RIESGOS[d["riesgo_max"]]
    d["n_amenazas"] = int(fila["n_amenazas"])
    if con_riesgos:
        d["riesgos"] = riesgos_de_activo(fila)
    return d


def activo(id_activo: str) -> dict:
    """Ficha común de un activo no sensible, con sus riesgos."""
    a = activos()
    if id_activo not in a.index or bool(a.loc[id_activo, "sensible"]):
        raise NoEncontrado("Activo no encontrado")
    return resumen_activo(a.loc[id_activo])


@lru_cache(maxsize=1)
def municipios() -> list[dict]:
    """Municipios para el buscador del visor: código, nombre, recuadro y punto de su capital.

    El punto es la capital del municipio en el Nomenclátor del IGN (la que cae dentro de su término); si no hay
    ninguna, un punto interior del término. Ahí se abre la celda de 1 km al elegirlo en el análisis basal.
    """
    import json

    import shapely

    from .incendio.entradas import A_GEO
    g = json.loads((VISOR / "municipios.geojson").read_text(encoding="utf-8"))
    p = pd.read_csv(PROCESADOS / "poblaciones.csv")
    p = p[p.tipo == "Capital de municipio"]
    lon, lat = A_GEO.transform(p.x.values, p.y.values)
    capitales = shapely.points(lon, lat)
    salida = []
    for f in g["features"]:
        forma = shapely.geometry.shape(f["geometry"])
        dentro = capitales[shapely.contains(forma, capitales)]
        punto = dentro[0] if len(dentro) else forma.representative_point()
        oeste, sur, este, norte = forma.bounds
        salida.append({"codigo": f["properties"]["codigo"], "nombre": f["properties"]["nombre"],
                       "lon": round(punto.x, 5), "lat": round(punto.y, 5),
                       "caja": [round(oeste, 5), round(sur, 5), round(este, 5), round(norte, 5)]})
    return sorted(salida, key=lambda m: m["nombre"])


def resumen() -> dict:
    """Población de las celdas de 1 km que tocan la Comunidad (Censo 2021), para el resumen al arrancar el visor."""
    r = rejilla()
    return {"celdas": int(len(r)), "poblacion": {"total": int(r["poblacion"].sum()), "menores_16": int(r["menores_16"].sum()),
                                                 "mayores_64": int(r["mayores_64"].sum())}}


def celda(lon: float, lat: float) -> dict:
    """Riesgos, población y activos de la celda de 1 km que contiene el punto."""
    e_km, n_km = celda_de_lonlat(lon, lat)
    gid = id_celda(e_km, n_km)
    r = rejilla()
    if gid not in r.index:
        raise NoEncontrado("El punto está fuera de la Comunidad de Madrid")
    fila = r.loc[gid]
    riesgos = []
    for codigo, (nombre, grupo) in CAPAS.items():
        nivel, pct = int(fila[f"max_{codigo}"]), float(fila[f"pct_{codigo}"])
        if nivel == 0 or (codigo in CON_FONDO and nivel == 1):
            continue
        riesgos.append({"codigo": codigo, "nombre": nombre, "grupo": grupo, "nivel": nivel,
                        "nivel_nombre": NIVELES[nivel], "porcentaje": pct})
    riesgos.sort(key=lambda d: (-d["nivel"], -d["porcentaje"]))
    en_celda = activos()[activos()["grd_id"] == gid]
    visibles = en_celda[~en_celda["sensible"]].sort_values("riesgo_max", ascending=False)
    sensibles = en_celda[en_celda["sensible"]]
    return {
        "grd_id": gid, "contorno": contorno(e_km, n_km),
        "fraccion_comunidad": float(fila["fraccion_comunidad"]),
        "poblacion": {"total": int(fila["poblacion"]), "menores_16": int(fila["menores_16"]),
                      "mayores_64": int(fila["mayores_64"])},
        "riesgos": riesgos,
        "activos": [resumen_activo(a, con_riesgos=False) for _, a in visibles.iterrows()],
        "sensibles": {"centros": int(len(sensibles)), "plazas": int(sensibles["plazas"].fillna(0).sum())},
    }
