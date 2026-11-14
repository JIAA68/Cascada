"""Validación del modelo de incendio con un caso real: Tres Cantos, 11 de agosto de 2025.

El fuego empezó a las 19:45 en Nuevo Tres Cantos (Ayuntamiento de Colmenar Viejo y prensa), avanzó
hacia el sureste empujado por una tormenta seca, quedó perimetrado durante la noche y quemó 2.037 ha
según Copernicus EFFIS. Es una sola ignición que corrió en pocas horas, compatible con el horizonte
de 24 h y la ventana de 30 km del modelo.

Fuentes (se descargan y se anotan en datos/registro.csv):
- Perímetro final: Copernicus EFFIS, áreas quemadas (API REST), incendio 278333.
- Focos de calor: NASA FIRMS, ficheros anuales de España de VIIRS (Suomi NPP y NOAA-20) de 2025.
- Viento, temperatura y humedad horarios: Comunidad de Madrid, Red de Calidad del Aire, datos meteorológicos
  horarios de 2025, estación de Colmenar Viejo: velocidad (magnitud 81, m/s), dirección (82, grados),
  temperatura (83, °C) y humedad relativa (86, %).
- Racha: AEMET OpenData, valores climatológicos diarios de la estación de Colmenar Viejo (3191E) del 11-08-2025.

Decisiones del 10-11-2026: la racha máxima registrada por AEMET ese día va en la primera hora, cuando la prensa
sitúa la carrera de 6 km, con la dirección del viento medido en la estación de la Red de Calidad del Aire a esa hora
(la del parte diario de AEMET es de otra estación y otra hora); el resto de horas, el viento medio medido. La tabla
compara además lo simulado hasta las 8 h, cuando el incendio real ya estaba perimetrado (el modelo no tiene extinción). La humedad del combustible de cada hora sale
de la temperatura y la humedad del aire medidas, como en el modelo con AEMET. Sin extinción. Se guarda como caso
(datos/procesados/crisis/caso_tres_cantos_2025/, que la poda de simulaciones antiguas no borra). Las
métricas comparan lo simulado con lo ocurrido: superficie, coincidencia con el perímetro (índice de
Sørensen), dirección del avance, avance en los primeros 40 minutos y focos de satélite dentro del
área simulada. El resultado queda en datos/procesados/validacion/tres_cantos_2025.json y lo sirve la
API (/api/validacion).

Uso: python -m procesamiento.incendio.validacion [--lon -3.69 --lat 40.62]
"""
import argparse
import json
import math
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import rasterio
import shapely
from rasterio.features import rasterize

import urllib.request

from ..fuentes import BRUTOS, PORTAL, PROCESADOS, descargar
from . import simulacion
from .combustibles import VERANO, Humedades, humedades_del_aire
from .entradas import A_GEO, A_UTM, AEMET, MADRID, _clave_aemet
from .propagacion import Viento

CASO = "caso_tres_cantos_2025"
NOMBRE = "Incendio de Tres Cantos (11 de agosto de 2025)"
INICIO = datetime(2025, 8, 11, 19, 45, tzinfo=MADRID)
# Punto de ignición (lon, lat). No hay coordenadas oficiales publicadas: punto estimado por el autor del proyecto en los
# pastos de la periferia noreste de la tercera fase de Nuevo Tres Cantos, junto a la Gran Vía, antes del monte.
PUNTO_IGNICION: tuple[float, float] | None = (-3.6936, 40.6141)

EFFIS_ID = 278333
URL_EFFIS = f"https://api.effis.emergency.copernicus.eu/rest/2/burntareas/current/?id={EFFIS_ID}"
FIRMS = "https://firms.modaps.eosdis.nasa.gov/data/country/"
URL_FIRMS = {"Suomi NPP": FIRMS + "viirs-snpp/2025/viirs-snpp_2025_Spain.csv",
             "NOAA-20": FIRMS + "viirs-jpss1/2025/viirs-jpss1_2025_Spain.csv"}
URL_METEO = PORTAL + "7f3699fc-d646-4efa-9387-1f5aed4a45b6/resource/8ee8c3cf-87a0-41ce-95bd-2b1f73879571/download/2025.csv"
ESTACION, NOMBRE_ESTACION = 28045002, "Colmenar Viejo"
ESTACION_AEMET = "3191E"   # Colmenar Viejo
AEMET_CLIMA = "/valores/climatologicos/diarios/datos/fechaini/{f}T00:00:00UTC/fechafin/{f}T23:59:59UTC/estacion/{e}"
CARPETA_BRUTOS = BRUTOS / "validacion"
SALIDA = PROCESADOS / "validacion" / "tres_cantos_2025.json"

HORIZONTES_H = (1, 3, 6, 12, 24)
CONTENCION_H = 8   # el incendio quedó perimetrado durante la noche del 11 al 12
# Lo que se sabe de la evolución real, con su fuente
REFERENCIAS = {
    "inicio": {"valor": "19:45 del 11-08-2025", "fuente": "el seguimiento del Ayuntamiento de Colmenar Viejo y la prensa"},
    "superficie_final_ha": {"valor": 2037, "fuente": "Copernicus EFFIS, área quemada 278333"},
    "superficie_12_08_15h_ha": {"valor": 1500, "minutos": 19 * 60 + 15,
                                "fuente": "Ayuntamiento de Colmenar Viejo: «supera las 1.500 hectáreas» a las 15:00 del 12-08"},
    "avance_40_min_km": {"valor": 6, "minutos": 40, "fuente": "prensa: «más de seis kilómetros en apenas 40 minutos»"},
    "direccion": {"valor": "sureste", "fuente": "Ayuntamiento de Colmenar Viejo: «se extiende hacia el sur-este»"},
    "perimetrado": {"valor": "durante la noche del 11 al 12-08", "fuente": "Ayuntamiento de Colmenar Viejo, 08:00 del 12-08"},
}
RADIO_FOCO_M = 375          # resolución de los focos VIIRS
CAMPOS_FIRMS = ["latitude", "longitude", "acq_date", "acq_time", "confidence", "frp", "daynight"]


# ----------------------------------------------------------------------------- fuentes
def _brutos(url: str, fichero: str, nota: str):
    return descargar(url, CARPETA_BRUTOS / fichero, nota)


def perimetro() -> shapely.Geometry:
    """Perímetro final de EFFIS en EPSG:25830."""
    ruta = _brutos(URL_EFFIS, f"effis_{EFFIS_ID}.json",
                   "Copernicus EFFIS, área quemada del incendio de Tres Cantos 2025 (CC BY 4.0)")
    r = json.loads(ruta.read_text(encoding="utf-8"))["results"][0]
    geo = shapely.geometry.shape(r["shape"])
    return shapely.transform(geo, lambda c: np.column_stack(A_UTM.transform(c[:, 0], c[:, 1])))


def focos(zona: shapely.Geometry, horas: int = 24) -> pd.DataFrame:
    """Focos VIIRS a menos de 3 km de la zona en las `horas` siguientes a la ignición, con sus minutos desde ella."""
    partes = []
    for satelite, url in URL_FIRMS.items():
        ruta = _brutos(url, url.rsplit("/", 1)[1], f"NASA FIRMS, focos de calor VIIRS {satelite} de España, 2025")
        d = pd.read_csv(ruta, usecols=CAMPOS_FIRMS)
        d = d[d.acq_date.between(INICIO.strftime("%Y-%m-%d"), (INICIO + timedelta(hours=horas)).strftime("%Y-%m-%d"))]
        if d.empty:
            continue
        d = d.assign(satelite=satelite)
        hora = pd.to_datetime(d.acq_date + d.acq_time.astype(int).astype(str).str.zfill(4), format="%Y-%m-%d%H%M", utc=True)
        d["hora"] = hora.dt.tz_convert(MADRID)
        partes.append(d)
    if not partes:
        return pd.DataFrame(columns=["lon", "lat", "x", "y", "hora", "minutos", "satelite", "frp"])
    d = pd.concat(partes, ignore_index=True).rename(columns={"latitude": "lat", "longitude": "lon"})
    d["x"], d["y"] = A_UTM.transform(d.lon.values, d.lat.values)
    d["minutos"] = (d.hora - pd.Timestamp(INICIO)).dt.total_seconds() / 60
    cerca = zona.buffer(3000)
    d = d[(d.minutos >= 0) & (d.minutos <= horas * 60) & shapely.contains_xy(cerca, d.x.values, d.y.values)]
    return d.sort_values("minutos").reset_index(drop=True)


def serie_estacion(ruta, estacion: int = ESTACION, magnitudes=(81, 82, 83, 86)) -> dict:
    """Valores validados de una estación: {(fin de la hora en UTC, magnitud): valor}. Por defecto, velocidad (81) y
    dirección (82) del viento, temperatura (83) y humedad relativa (86).

    La red rotula cada valor como h01…h24 («h01 hace referencia a la 1 de la mañana») sin indicar el huso. Es UTC:
    el máximo de radiación solar (magnitud 88) cae en h13 tanto en junio como en diciembre, sin cambio de hora, y el
    mediodía solar de Madrid es hacia las 12:15 UTC. Cada valor se toma como el de la hora que termina en su marca.
    """
    d = pd.read_csv(ruta, sep=";", decimal=",")
    d = d[(d.provincia * 1_000_000 + d.municipio * 1000 + d.estacion == estacion) & d.magnitud.isin(list(magnitudes))]
    serie = {}
    for _, f in d.iterrows():
        dia = datetime(int(f.ano), int(f.mes), int(f.dia), tzinfo=timezone.utc)
        for h in range(1, 25):
            if f[f"v{h:02d}"] == "V":
                serie[(dia + timedelta(hours=h), int(f.magnitud))] = float(str(f[f"h{h:02d}"]).replace(",", "."))
    return serie


def vientos_desde(serie: dict, inicio: datetime, horas: int = 25) -> list[Viento]:
    """Viento de cada hora de simulación: el valor de la hora de la red que contiene su punto medio.

    Una hora sin dato validado repite la anterior.
    """
    resultado, anterior = [], None
    for k in range(horas):
        medio = (inicio + timedelta(hours=k, minutes=30)).astimezone(timezone.utc)
        marca = medio.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        vel, dire = serie.get((marca, 81)), serie.get((marca, 82))
        if vel is None or dire is None:
            if anterior is None:
                raise RuntimeError(f"No hay viento validado en la estación a las {marca:%d-%m %H:%M}")
            resultado.append(anterior)
            continue
        anterior = Viento(round(vel * 3.6, 1), dire % 360)
        resultado.append(anterior)
    return resultado


def humedades_desde(serie: dict, inicio: datetime, horas: int = 25) -> list[Humedades]:
    """Humedad del combustible de cada hora de simulación, de la temperatura (83) y la humedad relativa (86) de la hora
    de la red que contiene su punto medio. Una hora sin dato repite la anterior; sin ninguno, la fija de verano."""
    resultado, anterior = [], VERANO
    for k in range(horas):
        medio = (inicio + timedelta(hours=k, minutes=30)).astimezone(timezone.utc)
        marca = medio.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        t, h = serie.get((marca, 83)), serie.get((marca, 86))
        anterior = humedades_del_aire(t, h) if t is not None and h is not None else anterior
        resultado.append(anterior)
    return resultado


def _meteo():
    return serie_estacion(_brutos(URL_METEO, "calidad_aire_meteo_2025.csv",
                                  "Comunidad de Madrid, Red de Calidad del Aire, datos meteorológicos horarios de 2025"))


def vientos(horas: int = 25) -> list[Viento]:
    """Viento medio horario en la estación de Colmenar Viejo desde la ignición."""
    return vientos_desde(_meteo(), INICIO, horas)


def humedades(horas: int = 25) -> list[Humedades]:
    """Humedad del combustible por hora con la temperatura y la humedad medidas en Colmenar Viejo."""
    return humedades_desde(_meteo(), INICIO, horas)


def racha_aemet() -> tuple[Viento, dict]:
    """Racha máxima del día de la ignición en la estación de AEMET de Colmenar Viejo (valores climatológicos diarios)."""
    fecha = INICIO.strftime("%Y-%m-%d")
    destino = CARPETA_BRUTOS / f"aemet_climatologico_{ESTACION_AEMET}_{fecha}.json"
    if not destino.exists():
        ruta = AEMET_CLIMA.format(f=fecha, e=ESTACION_AEMET)
        peticion = urllib.request.Request(AEMET + ruta, headers={"api_key": _clave_aemet()})
        for intento in range(3):   # AEMET corta o rechaza peticiones de forma intermitente
            try:
                with urllib.request.urlopen(peticion, timeout=60) as r:
                    meta = json.loads(r.read().decode("latin-1"))
                break
            except OSError:
                if intento == 2:
                    raise
                time.sleep(5)
        if "datos" not in meta:
            raise RuntimeError(f"AEMET {ruta}: {meta.get('descripcion')}")
        descargar(meta["datos"], destino, f"AEMET OpenData, valores climatológicos diarios ({ruta})")
    d = json.loads(destino.read_bytes().decode("latin-1"))[0]
    kmh = round(float(d["racha"].replace(",", ".")) * 3.6, 1)
    desde = float(d["dir"]) * 10 % 360          # AEMET da la dirección de la racha en decenas de grado
    return Viento(kmh, desde), {"estacion": d.get("nombre"), "indicativo": ESTACION_AEMET, "fecha": d.get("fecha"),
                                "racha_ms": d["racha"], "dir_decenas_grado": d["dir"], "hora": d.get("horaracha")}


# ----------------------------------------------------------------------------- métricas
def _rumbo(dx: float, dy: float) -> float:
    return round(math.degrees(math.atan2(dx, dy)) % 360, 1)


def metricas(llegada: np.ndarray, transform, celda: float, xy0: tuple[float, float], real: shapely.Geometry,
             puntos: pd.DataFrame, referencia_min: float | None = REFERENCIAS["superficie_12_08_15h_ha"]["minutos"],
             avance: tuple[float, float] | None = (REFERENCIAS["avance_40_min_km"]["valor"], REFERENCIAS["avance_40_min_km"]["minutos"]),
             contencion_h: float | None = CONTENCION_H, hora_fija_h: float | None = None) -> dict:
    """Compara el mapa de llegada (minutos; infinito o negativo si no llega) con el perímetro real y los focos.

    Los valores por defecto son los de Tres Cantos: superficie conocida a las 15:00 del día siguiente, carrera de
    6 km en 40 minutos y perimetrado a las 8 h. En otros casos se pasan los suyos, o None si no se conocen.

    hora_fija_h (decisión del 13-11-2026): la hora a la que se compara, fijada de antemano (no la mejor de las 24).
    Ahí se da también el modelo nulo: un círculo centrado en la ignición con la misma superficie que la simulada, y la
    ganancia del modelo sobre él (si el modelo no acierta mejor que un círculo, la forma y la dirección no aportan).
    """
    llegada = np.where(np.isfinite(llegada) & (llegada >= 0), llegada, np.inf)
    filas, columnas = llegada.shape
    b = rasterize([real], out_shape=(filas, columnas), transform=transform).astype(bool)
    ha = celda * celda / 1e4
    cols, fils = np.meshgrid(np.arange(columnas), np.arange(filas))
    xs, ys = transform.c + (cols + 0.5) * transform.a, transform.f + (fils + 0.5) * transform.e   # centros (sin giro)

    def comparar(minutos):
        a = llegada <= minutos
        inter, na, nb = (a & b).sum(), a.sum(), b.sum()
        return {"superficie_ha": round(float(na * ha)),
                "sorensen": round(float(2 * inter / (na + nb)), 3) if na + nb else 0.0,
                "real_quemado_pct": round(float(100 * inter / nb), 1) if nb else 0.0,
                "simulado_fuera_pct": round(float(100 * (a & ~b).sum() / na), 1) if na else 0.0}

    por_hora = {h: comparar(h * 60) for h in range(1, 25)}
    mejor = max(por_hora, key=lambda h: por_hora[h]["sorensen"])
    a24 = llegada <= 24 * 60
    dist = dist_ignicion = np.hypot(xs - xy0[0], ys - xy0[1])
    km_ref, min_ref = avance if avance else (6, 40)
    lejos = dist >= km_ref * 1000
    t_6km = float(llegada[lejos].min()) if lejos.any() else math.inf
    a40 = llegada <= min_ref
    cr = real.centroid

    fija = None
    if hora_fija_h is not None:
        fija = {"horas": hora_fija_h, **comparar(hora_fija_h * 60)}
        a = llegada <= hora_fija_h * 60
        nb = int(b.sum())
        radio = math.sqrt(a.sum() * celda * celda / math.pi)
        circulo = dist_ignicion <= radio if a.any() else np.zeros_like(b)
        nc = int(circulo.sum())
        fija["sorensen_circulo"] = round(float(2 * (circulo & b).sum() / (nc + nb)), 3) if nc + nb else 0.0
        fija["ganancia_sobre_circulo"] = round(fija["sorensen"] - fija["sorensen_circulo"], 3)
        fija["razon_superficie"] = round(float(a.sum() / nb), 2) if nb else None

    dentro_sim = [bool((llegada[np.hypot(xs - f.x, ys - f.y) <= RADIO_FOCO_M] <= f.minutos).any())
                  for _, f in puntos.iterrows()]
    zona_real = real.buffer(RADIO_FOCO_M)
    dentro_real = [bool(shapely.contains_xy(zona_real, f.x, f.y)) for _, f in puntos.iterrows()]

    return {
        "superficie_real_ha": round(real.area / 1e4),
        "horizontes": {str(h): por_hora[h] for h in HORIZONTES_H},
        "referencia_12_08_15h": comparar(referencia_min) if referencia_min is not None else None,
        "contencion": {"horas": contencion_h, **comparar(contencion_h * 60),
                       "rumbo_grados": _rumbo(xs[llegada <= contencion_h * 60].mean() - xy0[0],
                                              ys[llegada <= contencion_h * 60].mean() - xy0[1]) if (llegada <= contencion_h * 60).any() else None}
        if contencion_h is not None else None,
        "hora_fija": fija,
        "mejor_hora": {"hora": mejor, **por_hora[mejor]},
        "direccion": {
            "real_grados": _rumbo(cr.x - xy0[0], cr.y - xy0[1]),
            "simulada_24h_grados": _rumbo(xs[a24].mean() - xy0[0], ys[a24].mean() - xy0[1]) if a24.any() else None,
        },
        "avance": {
            "distancia_max_40_min_km": round(float(dist[a40].max()) / 1000, 2) if a40.any() else 0.0,
            "minutos_hasta_6_km": round(t_6km) if math.isfinite(t_6km) else None,
        },
        "focos": {"total": len(puntos), "dentro_de_lo_simulado": int(sum(dentro_sim)),
                  "dentro_del_perimetro": int(sum(dentro_real))},
        "por_hora": {str(h): por_hora[h] for h in range(1, 25)},
    }


# ----------------------------------------------------------------------------- caso completo
def _geojson(geom_utm: shapely.Geometry) -> dict:
    geo = shapely.transform(geom_utm, lambda c: np.column_stack(A_GEO.transform(c[:, 0], c[:, 1])))
    return shapely.geometry.mapping(geo)


def ejecutar(lon: float, lat: float) -> dict:
    """Simula el caso con el viento medido, calcula las métricas y guarda el resultado para el visor."""
    real = perimetro()
    racha, racha_info = racha_aemet()
    medido = vientos()
    serie = [Viento(racha.velocidad_kmh, medido[0].desde)] + medido[1:]   # la racha con la dirección medida a esa hora
    sim = simulacion.simular(lon, lat, INICIO, serie, id_simulacion=CASO, humedades=humedades(), descripcion_viento={
        "fuente": f"medido en la estación de {NOMBRE_ESTACION} de la Red de Calidad del Aire de la Comunidad de Madrid",
        "racha": f"velocidad de la racha máxima del día registrada por AEMET en {NOMBRE_ESTACION}, con la dirección medida a esa hora",
        "racha_por_hora": [True] + [False] * (len(serie) - 1), "horas_con_racha": 1,
        "humedad": f"la temperatura y la humedad del aire medidas en la estación de {NOMBRE_ESTACION}, hora a hora"})
    with rasterio.open(simulacion.CARPETA / CASO / "llegada.tif") as src:
        llegada, transform, celda = src.read(1), src.transform, src.res[0]
    xy0 = A_UTM.transform(lon, lat)
    puntos = focos(real)
    resultado = {
        "caso": CASO, "nombre": NOMBRE, "inicio": INICIO.isoformat(timespec="minutes"),
        "ignicion": {"lon": lon, "lat": lat,
                     "nota": "punto fijado por el autor del proyecto; no hay coordenadas oficiales publicadas"},
        "simulacion_id": sim["id"], "llegada_url": sim["llegada_url"],
        "viento": {"estacion": NOMBRE_ESTACION, "codigo": ESTACION, "por_hora": sim["vientos_por_hora"], "racha": racha_info},
        "humedad_por_hora": sim["humedades_por_hora"],
        "referencias": REFERENCIAS,
        "metricas": metricas(llegada, transform, celda, xy0, real, puntos),
        "perimetro": {"type": "Feature", "geometry": _geojson(real), "properties": {"fuente": "Copernicus EFFIS", "id": EFFIS_ID}},
        "focos": {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(f.lon, 5), round(f.lat, 5)]},
             "properties": {"hora": f.hora.isoformat(timespec="minutes"), "minutos": round(f.minutos),
                            "satelite": f.satelite, "potencia_mw": float(f.frp)}} for _, f in puntos.iterrows()]},
        "fuentes": {"perimetro": URL_EFFIS, "focos": list(URL_FIRMS.values()), "viento": URL_METEO},
        "calculado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    return resultado


def cargar() -> dict:
    """Resultado guardado de la validación, con la respuesta completa de la simulación del caso (para la API)."""
    respuesta = simulacion.CARPETA / CASO / "respuesta.json"
    if not SALIDA.is_file() or not respuesta.is_file():
        raise FileNotFoundError(SALIDA)
    resultado = json.loads(SALIDA.read_text(encoding="utf-8"))
    resultado["simulacion"] = json.loads(respuesta.read_text(encoding="utf-8"))
    return resultado


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lon", type=float, default=None)
    p.add_argument("--lat", type=float, default=None)
    a = p.parse_args(argv)
    punto = (a.lon, a.lat) if a.lon is not None and a.lat is not None else PUNTO_IGNICION
    if punto is None:
        raise SystemExit("Falta el punto de ignición: pásalo con --lon y --lat o fíjalo en PUNTO_IGNICION")
    r = ejecutar(*punto)
    m = r["metricas"]
    print(f"{r['nombre']}: simulación {r['simulacion_id']}")
    print(f"Superficie real (EFFIS): {m['superficie_real_ha']} ha")
    for h, c in m["horizontes"].items():
        print(f"  {h:>2} h: {c['superficie_ha']:>6} ha  Sørensen {c['sorensen']:.2f}  real quemado {c['real_quemado_pct']} %  "
              f"simulado fuera {c['simulado_fuera_pct']} %")
    print(f"  Mejor coincidencia a las {m['mejor_hora']['hora']} h: Sørensen {m['mejor_hora']['sorensen']:.2f}")
    print(f"Dirección: real {m['direccion']['real_grados']}°, simulada {m['direccion']['simulada_24h_grados']}°")
    print(f"Avance: {m['avance']['distancia_max_40_min_km']} km a los 40 min; 6 km a los {m['avance']['minutos_hasta_6_km']} min")
    print(f"Focos de satélite: {m['focos']['dentro_de_lo_simulado']} de {m['focos']['total']} dentro de lo simulado")


if __name__ == "__main__":
    main()
