"""Simulación de un incendio a partir de una alerta en un punto de la Comunidad de Madrid.

Encadena las entradas (combustible, relieve, viento), el motor de propagación y las
consecuencias (activos alcanzados, efecto cascada, humo, municipios) y deja en
datos/procesados/crisis/<id>/ el mapa de tiempos de llegada (GeoTIFF) y la respuesta para
el visor (JSON). El visor pide el mapa de llegada como enteros de 16 bits (minutos; 65535 si
el fuego no llega) y reproduce cualquier minuto sin recalcular.

Los centros sensibles no se devuelven uno a uno: solo su número y sus plazas.

Uso: python -m procesamiento.incendio.simulacion --lon -4.02 --lat 40.71 [--hora 2026-07-15T15:00]
     [--viento 20,270 | --viento "20,270;25,290;18,300"]   (constante, o una pareja por hora)
"""
import argparse
import hashlib
import json
import re
import shutil
from dataclasses import asdict, replace
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

from .. import activos as modulo_activos
from ..conducciones import sobre_el_eje
from ..fuentes import PROCESADOS
from ..instalaciones import CAPAS_SEVESO, cargar as cargar_instalaciones
from ..poblaciones import alcanzadas as poblaciones_alcanzadas
from .combustibles import MODELOS, VERANO, Humedades, humedad_viva
from .consecuencias import (DISTANCIA_ALCANZADO_M, activos_alcanzados, cascada_conducciones, cascada_seveso, isocronas,
                            llegada_en_radio,
                            ruta_del_fuego,
                            municipios_alcanzados, poblacion_por_celda)
from .entradas import A_GEO, A_UTM, CRS, MADRID, combustible, fuente_combustible, municipio_de, municipios_en_ventana, \
    relieve, ventana_centrada, vientos_horarios
from .humo import ALCANCE_MAX_KM, PASO_MIN, PERMANENCIA_H, SEMIANGULO_GRADOS, activos_bajo_humo, zonas_de_humo
from .propagacion import Viento, tiempos_llegada
from .vias import trenes_programados, vias_afectadas

HORIZONTE_MIN = 24 * 60
HORIZONTES_H = (1, 3, 6, 12, 24)
CARPETA = PROCESADOS / "crisis"
CAMPOS_ACTIVO = ["id", "familia", "subtipo", "tipo", "vulnerabilidad", "nombre", "municipio", "plazas", "lon", "lat"]
ID_VALIDO = re.compile(r"(?!\.+$)[0-9A-Za-z_.-]+")   # con fullmatch: sin «.» ni «..» ni salto de línea final
NUNCA = 65535


class ErrorDeEntrada(ValueError):
    pass


@lru_cache(maxsize=1)
def activos() -> pd.DataFrame:
    ruta = PROCESADOS / "activos.csv"
    if not ruta.exists():
        modulo_activos.escribir()
    a = pd.read_csv(ruta).dropna(subset=["x", "y"])
    a["lon"], a["lat"] = A_GEO.transform(a.x.values, a.y.values)
    return a


VULNERABILIDAD_AVISO = ("alta", "muy_alta")   # centros con aviso anticipado en el visor


def _lista(df: pd.DataFrame, columna: str, extra=()) -> tuple[list, dict]:
    """Activos no sensibles como lista ordenada por tiempo, y los sensibles agregados."""
    if df.empty:
        return [], {"centros": 0, "plazas": 0}
    visibles, sens = df[~df.sensible].sort_values(columna), df[df.sensible]
    lista = [{**{c: (None if pd.isna(f[c]) else f[c]) for c in CAMPOS_ACTIVO}, "minutos": round(float(f[columna]), 1),
              **{c: f[c] for c in extra}} for _, f in visibles.iterrows()]
    return lista, {"centros": int(len(sens)), "plazas": int(sens.plazas.fillna(0).sum())}


def simular(lon: float, lat: float, hora: datetime, viento_manual: Viento | list[Viento] | None = None, *,
            id_simulacion: str | None = None, descripcion_viento: dict | None = None,
            humedades: Humedades | list[Humedades] | None = None) -> dict:
    """Simula el incendio y devuelve la respuesta para el visor (también guardada en disco).

    viento_manual: un viento constante o una serie hora a hora desde la ignición (si es más corta que el
    horizonte, se mantiene la última hora). Sin él, el viento de AEMET, con racha en las horas de tormenta, y la
    humedad del combustible de cada hora calculada de la temperatura y la humedad del aire de AEMET. Con viento a mano,
    la humedad es la fija de verano salvo que se den `humedades` (una o una por hora). id_simulacion fija la carpeta de
    salida (casos guardados, como la validación); descripcion_viento se añade al origen del viento.
    """
    if id_simulacion is not None and not ID_VALIDO.fullmatch(id_simulacion):
        raise ErrorDeEntrada("identificador de simulación no válido")
    x, y = A_UTM.transform(lon, lat)
    try:
        codigo_ine, municipio = municipio_de(x, y)
    except ValueError as e:
        raise ErrorDeEntrada(str(e)) from e
    v = ventana_centrada(x, y)
    comb = combustible(v)
    fila, col = v.fila_columna(x, y)
    if int(comb[fila, col]) not in MODELOS:
        raise ErrorDeEntrada("En el punto de la alerta no hay combustible forestal (según el mapa de combustibles): "
                             "elige un punto con vegetación")
    altitud, pendiente, subida = relieve(v)
    horas = HORIZONTE_MIN // 60 + 1
    serie = [viento_manual] if isinstance(viento_manual, Viento) else list(viento_manual or [])[:horas]
    if serie:
        vientos = serie + [serie[-1]] * (horas - len(serie))
        origen = {"origen": "manual", "municipio": municipio, "constante": len(set(serie)) == 1, **(descripcion_viento or {})}
        lista_h = [humedades] if isinstance(humedades, Humedades) else list(humedades or [VERANO])
        lista_h = (lista_h + [lista_h[-1]] * horas)[:horas]
    else:
        vientos, lista_h, origen = vientos_horarios(x, y, hora, horas)
    # El combustible vivo, según el mes de la ignición (60 % de julio a septiembre)
    viva = humedad_viva(hora.astimezone(MADRID))
    muerto_fijo = all((h.m_1h, h.m_10h, h.m_100h) == (VERANO.m_1h, VERANO.m_10h, VERANO.m_100h) for h in lista_h)
    lista_h = [replace(h, m_viva=viva) for h in lista_h]
    llegada = tiempos_llegada(comb, pendiente, subida, v.celda, (fila, col), vientos, lista_h, HORIZONTE_MIN)

    sello = hora.astimezone(MADRID).strftime("%Y%m%dT%H%M") + f"_{lon:.4f}_{lat:.4f}"
    if len(set(serie)) == 1:
        sello += f"_v{serie[0].velocidad_kmh:g}_{serie[0].desde:g}"
    elif serie:
        sello += "_vh" + hashlib.sha1(repr([(w.velocidad_kmh, w.desde) for w in serie]).encode()).hexdigest()[:8]
    sello = id_simulacion or sello
    carpeta = CARPETA / sello
    carpeta.mkdir(parents=True, exist_ok=True)
    with rasterio.open(carpeta / "llegada.tif", "w", driver="GTiff", height=v.filas, width=v.columnas, count=1,
                       dtype="float32", crs=CRS, transform=v.transform, nodata=-1, compress="deflate") as dst:
        dst.write(np.where(np.isfinite(llegada), llegada, -1).astype("float32"), 1)

    act = activos()
    alcanzados = activos_alcanzados(llegada, v, act)
    llamas, llamas_sens = _lista(alcanzados[alcanzados.llegada_min.notna()], "llegada_min")
    for a in llamas:   # avisos anticipados: ruta del fuego hasta los centros de vulnerabilidad alta y muy alta
        if a["vulnerabilidad"] in VULNERABILIDAD_AVISO:
            a["ruta"] = ruta_del_fuego(llegada, v, *A_UTM.transform(a["lon"], a["lat"]))
    seveso, der_sev = cascada_seveso(llegada, v, cargar_instalaciones(), act)
    conduccion, der_cond = cascada_conducciones(llegada, v, act)
    derivados = pd.concat([d for d in (der_sev, der_cond) if not d.empty], ignore_index=True) \
        if not (der_sev.empty and der_cond.empty) else pd.DataFrame()
    if not derivados.empty:
        derivados = derivados.sort_values("activacion_min").drop_duplicates("id")
    der_lista, der_sens = _lista(derivados, "activacion_min", extra=("origen", "zona", "amenaza_derivada"))
    instalaciones = []
    for iid, g in (seveso.groupby("id") if not seveso.empty else []):
        glon, glat = A_GEO.transform(g.x.mean(), g.y.mean())
        instalaciones.append({"id": iid, "lon": glon, "lat": glat, "minutos": round(float(g.activacion_min.min()), 1),
                              "ruta": ruta_del_fuego(llegada, v, g.x.mean(), g.y.mean()),
                              "amenazas": [CAPAS_SEVESO[c] for c in g.capa],
                              "radio_intervencion_m": round(float(g.radio_intervencion_m.max())),
                              "radio_alerta_m": round(float(g.radio_alerta_m.max())),
                              # Radios de cada amenaza, de mayor a menor alcance: los de la instalación son los mayores
                              "zonas": [{"amenaza": CAPAS_SEVESO[z.capa], "radio_intervencion_m": round(float(z.radio_intervencion_m)),
                                         "radio_alerta_m": round(float(z.radio_alerta_m))}
                                        for z in g.sort_values("radio_alerta_m", ascending=False).itertuples()]})
    if conduccion:
        # El punto alcanzado se coloca sobre el eje de la conducción que pinta el visor
        conduccion["x"], conduccion["y"] = sobre_el_eje(conduccion["x"], conduccion["y"])
        conduccion["ruta"] = ruta_del_fuego(llegada, v, conduccion["x"], conduccion["y"])
        conduccion["lon"], conduccion["lat"] = A_GEO.transform(conduccion.pop("x"), conduccion.pop("y"))
        for tr in conduccion["tramos"]:   # cada tramo nuevo alcanzado, con su punto en el eje y su ruta del fuego
            tx, ty = sobre_el_eje(tr.pop("x"), tr.pop("y"))
            tr["ruta"] = ruta_del_fuego(llegada, v, tx, ty)
            tr["lon"], tr["lat"] = A_GEO.transform(tx, ty)
    zonas_humo = zonas_de_humo(llegada, v, vientos, HORIZONTE_MIN)
    humo_lista, humo_sens = _lista(activos_bajo_humo(zonas_humo, act), "humo_min")
    indice, lista_mun = municipios_en_ventana(v)

    respuesta = {
        "id": sello,
        "ignicion": {"lon": lon, "lat": lat, "hora": hora.astimezone(MADRID).isoformat(timespec="minutes"),
                     "municipio": municipio, "codigo_ine": codigo_ine, "combustible": int(comb[fila, col]),
                     "combustible_nombre": MODELOS[int(comb[fila, col])].nombre, "combustible_fuente": fuente_combustible(v, fila, col),
                     "altitud_m": round(float(altitud[fila, col]))},
        "ventana": {"esquinas": v.esquinas_lonlat(), "filas": v.filas, "columnas": v.columnas, "celda_m": v.celda},
        "horizonte_min": HORIZONTE_MIN,
        "horizontes_h": list(HORIZONTES_H),
        "viento": origen,
        "vientos_por_hora": [asdict(w) for w in vientos],
        "humedades": asdict(lista_h[0]),
        "humedades_por_hora": [asdict(h) for h in lista_h],
        "humedad_fija": muerto_fijo,
        "humedad_viva": viva,
        "distancia_alcanzado_m": DISTANCIA_ALCANZADO_M,
        "superficie_km2": {h: round(float((llegada <= h * 60).sum()) * v.celda ** 2 / 1e6, 2) for h in HORIZONTES_H},
        "municipios": municipios_alcanzados(llegada, indice, lista_mun, v),
        # Población del Censo 2021 en las celdas de 1 km que toca el fuego
        "poblacion_celdas": poblacion_por_celda(llegada, v),
        "activos_llamas": llamas, "sensibles_llamas": llamas_sens,
        "cascada": {"instalaciones_seveso": instalaciones, "conduccion": conduccion, "activos": der_lista, "sensibles": der_sens},
        "humo": {"activos": humo_lista, "sensibles": humo_sens,
                 "parametros": {"semiangulo_grados": SEMIANGULO_GRADOS, "permanencia_h": PERMANENCIA_H,
                                "alcance_max_km": ALCANCE_MAX_KM, "paso_min": PASO_MIN},
                 # La misma geometría que marca los afectados, para que el visor la dibuje
                 "zonas": [{"minutos": m, "coords": np.round(np.column_stack(A_GEO.transform(*np.asarray(z.exterior.coords).T)), 5).tolist()}
                           for m, z in zonas_humo]},
        "llegada_url": f"/api/incendio/llegada?id={sello}",
        # Minuto en que el fuego toca el borde de la ventana de cálculo: desde ahí, lo que
        # queda fuera no se calcula y superficie y afectados se quedan cortos; None si no lo toca
        "borde_min": borde_de_la_ventana(llegada),
    }
    motivo = sin_propagacion(llegada, MODELOS[int(comb[fila, col])], lista_h)
    if motivo:
        respuesta["sin_propagacion"] = motivo
    # Carreteras, pistas y vías de tren afectadas, y trenes de Cercanías programados
    llegada_250 = llegada_en_radio(llegada, v.celda, DISTANCIA_ALCANZADO_M)
    respuesta["vias"] = vias_afectadas(llegada_250, v, zonas_humo)
    respuesta["trenes_programados"] = trenes_programados(llegada_250, v, zonas_humo, hora)
    # Núcleos de población a los que llega el fuego, para anunciarlos en el mapa
    respuesta["poblaciones"] = poblaciones_alcanzadas(llegada_250, v)
    # Isocronas a cada hora en punto
    local = hora.astimezone(MADRID)
    respuesta["isocronas"] = isocronas(llegada, v, 60 - local.minute - local.second / 60 if local.minute or local.second else 60)
    (carpeta / "respuesta.json").write_text(json.dumps(respuesta, ensure_ascii=False, indent=1), encoding="utf-8")
    return respuesta


def borde_de_la_ventana(llegada: np.ndarray) -> float | None:
    """Primer minuto en que arde una celda del borde de la ventana, o None si el fuego no llega al borde."""
    borde = np.concatenate([llegada[0], llegada[-1], llegada[:, 0], llegada[:, -1]])
    borde = borde[np.isfinite(borde)]
    return round(float(borde.min()), 1) if len(borde) else None


def sin_propagacion(llegada: np.ndarray, modelo, humedades: list[Humedades]) -> str | None:
    """Por qué el fuego no sale de la celda de ignición, o None si avanza."""
    if np.isfinite(llegada).sum() > 1:
        return None
    mas_seco = min(h.m_1h for h in humedades)
    if mas_seco >= modelo.humedad_extincion:
        humedad = f"{mas_seco * 100:.1f}".replace(".", ",")
        return (f"el combustible muerto fino no baja del {humedad} % de humedad en las 24 horas, y "
                f"{modelo.nombre.lower()} deja de propagar el fuego a partir del {modelo.humedad_extincion * 100:.0f} %")
    return "alrededor del punto de ignición no hay combustible continuo por el que avance el fuego"


def podar(conservar: int = 50) -> int:
    """Borra las simulaciones más antiguas y deja las últimas `conservar`. Devuelve cuántas borra.

    Los casos guardados (carpetas que empiezan por "caso_", como la validación) no se borran nunca."""
    if not CARPETA.exists():
        return 0
    carpetas = sorted((p for p in CARPETA.iterdir() if p.is_dir() and not p.name.startswith("caso_")),
                      key=lambda p: p.stat().st_mtime)
    sobrantes = carpetas[:max(len(carpetas) - conservar, 0)]
    for p in sobrantes:
        shutil.rmtree(p, ignore_errors=True)
    return len(sobrantes)


def llegada_u16(id_simulacion: str) -> bytes:
    """Mapa de llegada de una simulación guardada: uint16 little-endian por filas (minutos; 65535 = no llega)."""
    if not ID_VALIDO.fullmatch(id_simulacion):
        raise FileNotFoundError(id_simulacion)
    ruta = CARPETA / id_simulacion / "llegada.tif"
    if not ruta.is_file():
        raise FileNotFoundError(id_simulacion)
    with rasterio.open(ruta) as src:
        t = src.read(1)
    return np.where(t < 0, NUNCA, np.minimum(np.ceil(t), NUNCA - 1)).astype("<u2").tobytes()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lon", type=float, required=True)
    p.add_argument("--lat", type=float, required=True)
    p.add_argument("--hora", type=datetime.fromisoformat, default=None, help="hora local de ignición (por defecto, ahora)")
    p.add_argument("--viento", default=None,
                   help="viento a 10 m 'km/h,grados de donde viene', constante, o una pareja por hora separada por ';' "
                        "(por defecto, AEMET)")
    a = p.parse_args(argv)
    hora = a.hora.replace(tzinfo=MADRID) if a.hora and a.hora.tzinfo is None else a.hora or datetime.now(MADRID)
    manual = [Viento(*(float(s) for s in par.split(","))) for par in a.viento.split(";") if par.strip()] if a.viento else None
    r = simular(a.lon, a.lat, hora, manual)
    print(f"Simulación {r['id']} en {r['ignicion']['municipio']} ({r['ignicion']['combustible_nombre']})")
    print("Superficie quemada:", " · ".join(f"{h} h: {k} km²" for h, k in r["superficie_km2"].items()))
    print(f"Municipios: {', '.join(m['nombre'] for m in r['municipios'])}")
    print(f"Activos alcanzados por las llamas: {len(r['activos_llamas'])} (+{r['sensibles_llamas']['centros']} sensibles)")
    for x in r["activos_llamas"][:10]:
        print(f"  {x['minutos'] / 60:5.1f} h  {x['familia']:15s} {x['nombre'][:50]}")
    print(f"Seveso alcanzadas: {[i['id'] for i in r['cascada']['instalaciones_seveso']]}; conducción: {bool(r['cascada']['conduccion'])}")
    print(f"Activos bajo amenaza derivada: {len(r['cascada']['activos'])}; bajo el humo: {len(r['humo']['activos'])}")


if __name__ == "__main__":
    main()
