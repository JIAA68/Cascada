"""Simulación de la rotura de una presa de la Comunidad de Madrid.

A partir de una presa deducida del catálogo (procesamiento/presas.py) y una hora, calcula cuándo llega el agua a cada
celda de 50 m de la zona inundable (procesamiento/presa/modelo.py) y sus consecuencias: centros, población, municipios,
núcleos, carreteras y vías de tren alcanzados. La respuesta tiene la misma forma que la del incendio
(procesamiento/incendio/simulacion.py), con "tipo": "presa", para que el visor reutilice el reproductor, las cartelas,
la cronología y las comunicaciones; humo y efecto cascada van vacíos. El mapa de llegada se guarda en la misma carpeta
que los incendios y se pide igual.

Un centro, núcleo, carretera o vía se considera alcanzado cuando el agua llega a menos de 50 m (una celda).

Uso: python -m procesamiento.presa.simulacion --presa PRE-14 [--hora 2026-07-15T15:00]
"""
import argparse
import json
import math
from datetime import datetime
from functools import lru_cache

import numpy as np
import rasterio

from ..incendio.consecuencias import isocronas, llegada_en_radio, municipios_alcanzados, poblacion_por_celda, ruta_del_fuego
from ..incendio.entradas import A_GEO, CRS, MADRID, Ventana, municipio_de, municipios_en_ventana
from ..incendio.simulacion import CARPETA, HORIZONTES_H, VULNERABILIDAD_AVISO, ErrorDeEntrada, _lista, activos
from ..incendio.vias import trenes_programados, vias_afectadas
from ..poblaciones import alcanzadas as poblaciones_alcanzadas
from ..presas import REJILLA, cargar as cargar_presas
from .modelo import SUBIDA_MAX_M, VELOCIDAD_MIN_KMH, distancias_aguas_abajo, minutos_de_llegada

HORIZONTE_MAX_MIN = 24 * 60
DISTANCIA_ALCANZADO_M = 50
MARGEN_CELDAS = 20   # 1 km alrededor de la zona inundada


@lru_cache(maxsize=1)
def rejilla():
    from ..presas import construir
    if not REJILLA.exists():
        construir()
    d = np.load(REJILLA)
    return d["nivel"], d["altitud"], tuple(float(v) for v in d["origen"]), float(d["celda"])


def presas() -> list[dict]:
    """Presas para el visor: identificador, nombre, municipio, posición."""
    p = cargar_presas()
    return [{"id": f.id, "nombre": f.nombre, "municipio": f.municipio, "lon": f.lon, "lat": f.lat,
             "longitud_30_min_m": int(f.longitud_30_min_m)} for f in p.itertuples()]


def simular(id_presa: str, hora: datetime) -> dict:
    p = cargar_presas()
    fila_presa = p[p.id == id_presa]
    if fila_presa.empty:
        raise ErrorDeEntrada(f"no hay ninguna presa {id_presa!r}")
    presa = fila_presa.iloc[0]
    nivel, altitud, (ox, oy), celda = rejilla()
    distancia = distancias_aguas_abajo(nivel >= 1, altitud, (int(presa.fila), int(presa.columna)), celda)
    minutos = minutos_de_llegada(distancia, float(presa.longitud_30_min_m))
    minutos[minutos > HORIZONTE_MAX_MIN] = np.inf
    ff, cc = np.nonzero(np.isfinite(minutos))
    f0, f1 = max(int(ff.min()) - MARGEN_CELDAS, 0), min(int(ff.max()) + 1 + MARGEN_CELDAS, minutos.shape[0])
    c0, c1 = max(int(cc.min()) - MARGEN_CELDAS, 0), min(int(cc.max()) + 1 + MARGEN_CELDAS, minutos.shape[1])
    v = Ventana(ox + c0 * celda, oy - f0 * celda, celda, f1 - f0, c1 - c0)
    llegada = minutos[f0:f1, c0:c1].astype("float64")
    fin = float(llegada[np.isfinite(llegada)].max())
    horizonte = int(min(HORIZONTE_MAX_MIN, max(180, math.ceil(fin / 60) * 60 + 60)))

    sello = f"presa_{id_presa}_" + hora.astimezone(MADRID).strftime("%Y%m%dT%H%M")
    carpeta = CARPETA / sello
    carpeta.mkdir(parents=True, exist_ok=True)
    with rasterio.open(carpeta / "llegada.tif", "w", driver="GTiff", height=v.filas, width=v.columnas, count=1,
                       dtype="float32", crs=CRS, transform=v.transform, nodata=-1, compress="deflate") as dst:
        dst.write(np.where(np.isfinite(llegada), llegada, -1).astype("float32"), 1)

    try:
        codigo_ine, municipio = municipio_de(float(presa.x), float(presa.y))
    except ValueError:
        codigo_ine, municipio = "", presa.municipio
    llegada_50 = llegada_en_radio(llegada, v.celda, DISTANCIA_ALCANZADO_M)
    act = activos()
    a = act[v.contiene(act.x.values, act.y.values)].copy()
    fa, ca = ((v.y0 - a.y.values) // v.celda).astype(int), ((a.x.values - v.x0) // v.celda).astype(int)
    t = llegada_50[fa, ca]
    a["llegada_min"] = np.where(np.isfinite(t), t, np.nan)
    alcanzados, alcanzados_sens = _lista(a[a.llegada_min.notna()], "llegada_min")
    for x in alcanzados:   # avisos anticipados: camino del agua hasta los centros de vulnerabilidad alta y muy alta
        if x["vulnerabilidad"] in VULNERABILIDAD_AVISO:
            x["ruta"] = ruta_del_fuego(llegada, v, *_utm(x["lon"], x["lat"]), radio_m=DISTANCIA_ALCANZADO_M)
    indice, lista_mun = municipios_en_ventana(v)
    local = hora.astimezone(MADRID)
    respuesta = {
        "id": sello,
        "tipo": "presa",
        "presa": {"id": presa.id, "nombre": presa.nombre, "municipio": presa.municipio, "lon": float(presa.lon),
                  "lat": float(presa.lat), "longitud_30_min_m": int(presa.longitud_30_min_m),
                  "area_30_min_km2": float(presa.area_30_min_km2)},
        # Mismos nombres que en el incendio: el punto de partida de la crisis es la presa
        "ignicion": {"lon": float(presa.lon), "lat": float(presa.lat), "hora": local.isoformat(timespec="minutes"),
                     "municipio": municipio, "codigo_ine": codigo_ine, "nombre": presa.nombre,
                     "altitud_m": round(float(altitud[int(presa.fila), int(presa.columna)]))},
        "ventana": {"esquinas": v.esquinas_lonlat(), "filas": v.filas, "columnas": v.columnas, "celda_m": v.celda},
        "horizonte_min": horizonte,
        "horizontes_h": [h for h in HORIZONTES_H if h * 60 <= horizonte] or [1],
        "modelo": {"subida_max_m": SUBIDA_MAX_M, "velocidad_min_kmh": VELOCIDAD_MIN_KMH,
                   "velocidad_inicial_kmh": round(1.5 * float(presa.longitud_30_min_m) / 30 * 60 / 1000, 1),
                   "fin_min": round(fin, 1)},
        "viento": {"origen": "no aplica"}, "vientos_por_hora": [],
        "distancia_alcanzado_m": DISTANCIA_ALCANZADO_M,
        "superficie_km2": {h: round(float((llegada <= h * 60).sum()) * v.celda ** 2 / 1e6, 2) for h in HORIZONTES_H},
        "municipios": municipios_alcanzados(llegada, indice, lista_mun, v),
        "poblacion_celdas": poblacion_por_celda(llegada, v),
        "activos_llamas": alcanzados, "sensibles_llamas": alcanzados_sens,
        "cascada": {"instalaciones_seveso": [], "conduccion": None, "activos": [], "sensibles": {"centros": 0, "plazas": 0}},
        "humo": {"activos": [], "sensibles": {"centros": 0, "plazas": 0}, "parametros": {}, "zonas": []},
        "llegada_url": f"/api/incendio/llegada?id={sello}",
        "borde_min": None,
        "vias": vias_afectadas(llegada_50, v, []),
        "trenes_programados": trenes_programados(llegada_50, v, [], hora),
        "poblaciones": poblaciones_alcanzadas(llegada_50, v),
        "isocronas": isocronas(llegada, v, 60 - local.minute - local.second / 60 if local.minute or local.second else 60,
                               horizonte_min=horizonte),
    }
    (carpeta / "respuesta.json").write_text(json.dumps(respuesta, ensure_ascii=False, indent=1), encoding="utf-8")
    return respuesta


def _utm(lon, lat):
    from ..incendio.entradas import A_UTM
    return A_UTM.transform(lon, lat)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--presa", required=True)
    p.add_argument("--hora", type=datetime.fromisoformat, default=None, help="hora local de la rotura (por defecto, ahora)")
    a = p.parse_args(argv)
    hora = a.hora.replace(tzinfo=MADRID) if a.hora and a.hora.tzinfo is None else a.hora or datetime.now(MADRID)
    r = simular(a.presa, hora)
    print(f"Rotura de {r['presa']['nombre']} ({r['ignicion']['municipio']}): el agua deja de avanzar a los "
          f"{r['modelo']['fin_min'] / 60:.1f} h; velocidad inicial {r['modelo']['velocidad_inicial_kmh']} km/h")
    print("Superficie inundada:", " · ".join(f"{h} h: {k} km²" for h, k in r["superficie_km2"].items()))
    print(f"Municipios: {', '.join(m['nombre'] for m in r['municipios'])}")
    print(f"Centros alcanzados: {len(r['activos_llamas'])} (+{r['sensibles_llamas']['centros']} sensibles)")
    for x in r["activos_llamas"][:12]:
        print(f"  {x['minutos'] / 60:5.1f} h  {x['familia']:15s} {x['nombre'][:50]} ({x['municipio']})")
    print(f"Núcleos: {[(n['nombre'], round(n['minutos'])) for n in r['poblaciones']][:10]}")
    print(f"Vías: {[(x['via'], x['llamas']) for x in r['vias']['resumen']][:10]}")


if __name__ == "__main__":
    main()
