"""Validación del modelo de incendio con varios incendios reales de la Comunidad de Madrid.

Un solo caso, con el punto de ignición estimado, no basta: el resultado cambia con 15° de viento o 100 m de punto, y
ajustar el modelo a un caso lo sobreajusta. Aquí cada incendio es una ficha (perímetro final de Copernicus EFFIS,
inicio y punto según la prensa o el parte oficial) y se simula con incertidumbre: cinco puntos de ignición (el
estimado y cuatro a RADIO_M) por tres giros del viento (GIROS), con el viento y la humedad medidos por la Red de
Calidad del Aire de la Comunidad. Las métricas (las de validacion.metricas) se resumen por caso con la mediana y el
rango, y sirven para comparar configuraciones del modelo con el conjunto de casos, no con uno.

Validación rigurosa:
- La métrica principal se toma a una hora fijada de antemano: la de contención publicada del caso o, si no se
  conoce, HORA_FIJA_H. La «mejor hora» de las 24 se sigue calculando, pero solo como referencia: elegirla a posteriori
  borra el error de ritmo.
- Al lado, el modelo nulo: un círculo centrado en la ignición con la misma superficie que la simulada, y la ganancia
  del modelo sobre él; y la fracción de lo simulado que cae fuera del perímetro real.
- Tres Cantos es el caso con el que se ajustaron los parámetros (salto, racha, vivo): se resume aparte de los otros
  seis, que son los de evaluación. n = 7.

Fuentes (en datos/registro.csv): EFFIS, áreas quemadas (API REST, por incendio); NASA FIRMS, focos VIIRS anuales de
España (Suomi NPP y NOAA-20); Comunidad de Madrid, Red de Calidad del Aire, datos meteorológicos horarios anuales y
relación de estaciones.

Uso: python -m procesamiento.incendio.casos [--configuracion actual] [--casos loeches_2024 ...]
"""
import argparse
import contextlib
import json
import math
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import rasterio
import shapely

from ..fuentes import BRUTOS, PORTAL, PROCESADOS, descargar
from . import propagacion, rothermel, simulacion, validacion
from .combustibles import VERANO, humedades_del_aire
from .entradas import A_UTM, MADRID
from .propagacion import Viento

CARPETA = BRUTOS / "validacion"
SALIDA = PROCESADOS / "validacion" / "conjunto.json"
METEO_DATASET = PORTAL + "7f3699fc-d646-4efa-9387-1f5aed4a45b6/resource/"
URL_METEO = {
    2022: METEO_DATASET + "6af291f1-adf9-4642-b033-a23120d0a102/download/2022.csv",
    2024: METEO_DATASET + "36ed3df2-a721-429e-85bc-08086a76165c/download/2024.csv",
    2025: METEO_DATASET + "8ee8c3cf-87a0-41ce-95bd-2b1f73879571/download/2025.csv",
}
URL_ESTACIONES = PORTAL + "4cd076a3-e602-48da-b834-58de39d3125c/resource/c05f6436-783e-4b04-b0d2-47848daea984/download/calidad_aire_estaciones.csv"
FIRMS = "https://firms.modaps.eosdis.nasa.gov/data/country/"
RADIO_M = 200.0
GIROS = (-15.0, 0.0, 15.0)
HORA_FIJA_H = 8.0          # hora de comparación cuando no hay hora de contención publicada (la de los casos que la tienen)
CASO_DE_AJUSTE = "tres_cantos_2025"


@dataclass(frozen=True)
class Caso:
    clave: str
    nombre: str
    effis_id: int
    inicio: datetime | None            # hora local de inicio, según la fuente
    punto: tuple[float, float] | None  # (lon, lat) estimado
    fuente: str = ""                   # de dónde salen el inicio y el punto
    racha_primera_hora_kmh: float | None = None   # solo si hay racha documentada (Tres Cantos)
    referencias: dict = field(default_factory=dict)  # avance, superficie con hora, contención, si se conocen


CASOS = {
    "tres_cantos_2025": Caso("tres_cantos_2025", "Tres Cantos, 11-08-2025", 278333, validacion.INICIO, validacion.PUNTO_IGNICION,
                             "Ayuntamiento de Colmenar Viejo y prensa; punto estimado por el autor", 70.9,
                             {"avance": (6, 40), "referencia_min": 19 * 60 + 15, "contencion_h": 8}),
    # Inicio y punto según la prensa; donde no hay lugar preciso, el extremo del perímetro
    # real situado de donde venía el viento medido a la hora de inicio, 100 m hacia dentro
    "colmenar_viejo_2024": Caso("colmenar_viejo_2024", "Tres Cantos y Colmenar Viejo, 22-08-2024", 238960,
                                datetime(2024, 8, 22, 14, 6, tzinfo=MADRID), (-3.7030, 40.6226),
                                "primera llamada a las 14:06; glorieta de Casas Viejas, junto a la Avenida de San Juan (prensa)",
                                referencias={"contencion_h": 8}),
    "loeches_2024": Caso("loeches_2024", "Loeches, 31-07-2024", 236151, datetime(2024, 7, 31, 14, 15, tzinfo=MADRID),
                         (-3.44031, 40.36270), "aviso a las 14:15 (Guardia Civil); finca junto a la M-300, sin más precisión: "
                         "extremo del perímetro a barlovento"),
    "pedrezuela_2024": Caso("pedrezuela_2024", "El Molar y Pedrezuela, 05-08-2024", 236946, datetime(2024, 8, 5, 13, 30, tzinfo=MADRID),
                            (-3.59107, 40.72972), "aviso a las 13:30; detrás del cementerio de El Molar (prensa)",
                            referencias={"contencion_h": 6}),
    "aranjuez_2022": Caso("aranjuez_2022", "Aranjuez, 05-07-2022", 205444, datetime(2022, 7, 5, 18, 0, tzinfo=MADRID),
                          (-3.63261, 40.01525), "hacia las 18:00; cuneta de la A-4, km 49 (prensa y 112); se reactivó el 6 a mediodía"),
    "aranjuez_2025": Caso("aranjuez_2025", "Aranjuez, 08-08-2025", 277684, datetime(2025, 8, 8, 19, 15, tzinfo=MADRID),
                          (-3.5538, 40.0422), "hacia las 19:15 (una sola fuente); altos de Sotomayor, junto a la Casa de la Monta"),
    "villa_del_prado_2025": Caso("villa_del_prado_2025", "Villa del Prado, 29-06-2025", 273043,
                                 datetime(2025, 6, 29, 22, 30, tzinfo=MADRID), (-4.30105, 40.25110),
                                 "hacia las 22:30; cerca del municipio, sin más precisión: extremo del perímetro a barlovento",
                                 referencias={"contencion_h": 8}),
}

# Configuraciones del modelo que se comparan con el conjunto de casos
CONFIGURACIONES = {
    "actual": {"limite_viento": False, "salto_m": 300.0, "viento": "cercana"},
    "con_limite": {"limite_viento": True, "salto_m": 300.0, "viento": "cercana"},
    "sin_salto": {"limite_viento": False, "salto_m": 0.0, "viento": "cercana"},
    "cuatro_estaciones": {"limite_viento": False, "salto_m": 300.0, "viento": "cuatro"},
}


# ----------------------------------------------------------------------------- fuentes
def _bajar(url: str, nombre: str, nota: str):
    return descargar(url, CARPETA / nombre, nota)


def perimetro(caso: Caso) -> shapely.Geometry:
    url = f"https://api.effis.emergency.copernicus.eu/rest/2/burntareas/current/?id={caso.effis_id}"
    ruta = _bajar(url, f"effis_{caso.effis_id}.json", f"Copernicus EFFIS, área quemada {caso.effis_id} ({caso.nombre}) (CC BY 4.0)")
    r = json.loads(ruta.read_text(encoding="utf-8"))["results"][0]
    return shapely.transform(shapely.geometry.shape(r["shape"]), lambda c: np.column_stack(A_UTM.transform(c[:, 0], c[:, 1])))


def focos(caso: Caso, zona: shapely.Geometry, horas: int = 24) -> pd.DataFrame:
    """Focos VIIRS (Suomi NPP y NOAA-20) a menos de 3 km de la zona en las horas siguientes al inicio."""
    anio, partes = caso.inicio.year, []
    for satelite, carpeta, fichero in (("Suomi NPP", "viirs-snpp", f"viirs-snpp_{anio}_Spain.csv"),
                                       ("NOAA-20", "viirs-jpss1", f"viirs-jpss1_{anio}_Spain.csv")):
        try:
            ruta = _bajar(f"{FIRMS}{carpeta}/{anio}/{fichero}", fichero, f"NASA FIRMS, focos de calor VIIRS {satelite} de España, {anio}")
        except OSError:
            continue
        d = pd.read_csv(ruta, usecols=validacion.CAMPOS_FIRMS)
        d = d[d.acq_date.between(caso.inicio.strftime("%Y-%m-%d"), (caso.inicio + timedelta(hours=horas)).strftime("%Y-%m-%d"))]
        if len(d):
            hora = pd.to_datetime(d.acq_date + d.acq_time.astype(int).astype(str).str.zfill(4), format="%Y-%m-%d%H%M", utc=True)
            partes.append(d.assign(satelite=satelite, hora=hora.dt.tz_convert(MADRID)))
    if not partes:
        return pd.DataFrame(columns=["lon", "lat", "x", "y", "hora", "minutos", "satelite", "frp"])
    d = pd.concat(partes, ignore_index=True).rename(columns={"latitude": "lat", "longitude": "lon"})
    d["x"], d["y"] = A_UTM.transform(d.lon.values, d.lat.values)
    d["minutos"] = (d.hora - pd.Timestamp(caso.inicio)).dt.total_seconds() / 60
    d = d[(d.minutos >= 0) & (d.minutos <= horas * 60) & shapely.contains_xy(zona.buffer(3000), d.x.values, d.y.values)]
    return d.sort_values("minutos").reset_index(drop=True)


def estaciones() -> pd.DataFrame:
    ruta = _bajar(URL_ESTACIONES, "calidad_aire_estaciones.csv", "Comunidad de Madrid, Red de Calidad del Aire, estaciones")
    e = pd.read_csv(ruta, sep=";", encoding="utf-8-sig", dtype=str)
    for c in ("estacion_coord_longitud", "estacion_coord_latitud"):
        e[c] = e[c].str.replace(",", ".").astype(float)
    e["codigo"] = e.estacion_codigo.astype(int)
    e["x"], e["y"] = A_UTM.transform(e.estacion_coord_longitud.values, e.estacion_coord_latitud.values)
    return e


def meteo(anio: int):
    return _bajar(URL_METEO[anio], f"calidad_aire_meteo_{anio}.csv",
                  f"Comunidad de Madrid, Red de Calidad del Aire, datos meteorológicos horarios de {anio}")


def series_cercanas(caso: Caso, n: int = 4):
    """Las n estaciones más cercanas al punto con viento validado en la primera hora: [(distancia_m, nombre, serie)]."""
    x, y = A_UTM.transform(*caso.punto)
    ruta = meteo(caso.inicio.year)
    e = estaciones().assign(d=lambda t: np.hypot(t.x - x, t.y - y)).sort_values("d")
    salida = []
    for r in e.itertuples():
        serie = validacion.serie_estacion(ruta, r.codigo)
        try:
            validacion.vientos_desde(serie, caso.inicio, 1)
        except RuntimeError:
            continue   # sin viento validado a esa hora
        salida.append((r.d, r.estacion_municipio, serie))
        if len(salida) == n:
            break
    return salida


def viento_y_humedad(caso: Caso, modo: str = "cercana", horas: int = 25):
    """Viento por hora (de la estación más cercana o media vectorial de las cuatro más cercanas, por 1/d²), humedad
    del combustible por hora (de la estación más cercana) y nombres de las estaciones usadas."""
    cercanas = series_cercanas(caso, 1 if modo == "cercana" else 4)
    vientos_est = [validacion.vientos_desde(s, caso.inicio, horas) for _, _, s in cercanas]
    pesos = [1 / max(d, 1.0) ** 2 for d, _, _ in cercanas]
    vientos = []
    for k in range(horas):
        sx = sum(p * w[k].velocidad_kmh * math.sin(math.radians(w[k].desde)) for p, w in zip(pesos, vientos_est))
        sy = sum(p * w[k].velocidad_kmh * math.cos(math.radians(w[k].desde)) for p, w in zip(pesos, vientos_est))
        vel = sum(p * w[k].velocidad_kmh for p, w in zip(pesos, vientos_est)) / sum(pesos)
        vientos.append(Viento(round(vel, 1), round(math.degrees(math.atan2(sx, sy)) % 360, 1)))
    if caso.racha_primera_hora_kmh:
        vientos[0] = Viento(caso.racha_primera_hora_kmh, vientos[0].desde)
    humedades = validacion.humedades_desde(cercanas[0][2], caso.inicio, horas)
    return vientos, humedades, [f"{n} ({d / 1000:.1f} km)" for d, n, _ in cercanas]


# ----------------------------------------------------------------------------- configuración del modelo
@contextlib.contextmanager
def configuracion(nombre: str):
    """Aplica una configuración del modelo mientras dura el bloque."""
    cfg = CONFIGURACIONES[nombre]
    salto, factor = propagacion.SALTO_M, rothermel.factor_viento

    def con_limite(k, u_kmh):
        u = min(u_kmh * rothermel.KMH_A_FT_MIN, 0.9 * k.intensidad_reaccion)
        return k.c * u ** k.b * k.relativa ** -k.e if u > 0 else 0.0

    propagacion.SALTO_M = cfg["salto_m"] if cfg["salto_m"] > 0 else 0.0
    if cfg["limite_viento"]:
        rothermel.factor_viento = con_limite
    try:
        yield cfg
    finally:
        propagacion.SALTO_M, rothermel.factor_viento = salto, factor


# ----------------------------------------------------------------------------- simulación con incertidumbre
def puntos_ignicion(caso: Caso) -> list[tuple[float, float]]:
    from .entradas import A_GEO
    x, y = A_UTM.transform(*caso.punto)
    return [caso.punto] + [A_GEO.transform(x + RADIO_M * math.sin(math.radians(a)), y + RADIO_M * math.cos(math.radians(a)))
                           for a in (0, 90, 180, 270)]


def resumen(valores: list[float]) -> dict | None:
    v = [x for x in valores if x is not None]
    return {"mediana": round(float(np.median(v)), 3), "min": round(float(min(v)), 3), "max": round(float(max(v)), 3), "n": len(v)} if v else None


def evaluar_caso(caso: Caso, config: str = "actual") -> dict:
    """Simula el caso con incertidumbre (puntos × giros) en una configuración y resume las métricas.

    Llama directamente al cálculo de propagación (las mismas entradas y el mismo motor que la simulación del visor),
    sin calcular las consecuencias, que la validación no usa.
    """
    from dataclasses import replace
    from .combustibles import humedad_viva
    from .entradas import combustible, relieve, ventana_centrada
    real, miembros = perimetro(caso), []
    ref = caso.referencias
    hora_fija = ref.get("contencion_h") or HORA_FIJA_H
    with configuracion(config) as cfg:
        vientos, humedades, usadas = viento_y_humedad(caso, cfg["viento"])
        humedades = [replace(h, m_viva=humedad_viva(caso.inicio)) for h in humedades]
        puntos_f = focos(caso, real)
        for i, punto in enumerate(puntos_ignicion(caso)):
            x, y = A_UTM.transform(*punto)
            v = ventana_centrada(x, y)
            comb = combustible(v)
            fila, col = v.fila_columna(x, y)
            if int(comb[fila, col]) not in propagacion.MODELOS:
                continue   # sin combustible en ese punto
            _, pendiente, subida = relieve(v)
            for giro in GIROS:
                serie = [Viento(w.velocidad_kmh, (w.desde + giro) % 360) for w in vientos]
                llegada = propagacion.tiempos_llegada(comb, pendiente, subida, v.celda, (fila, col), serie, humedades,
                                                      simulacion.HORIZONTE_MIN)
                m = validacion.metricas(llegada, v.transform, v.celda, (x, y), real, puntos_f,
                                        referencia_min=ref.get("referencia_min"), avance=ref.get("avance"),
                                        contencion_h=ref.get("contencion_h"), hora_fija_h=hora_fija)
                f = m["hora_fija"]
                miembros.append({"punto": i, "giro": giro,
                                 "sorensen_fija": f["sorensen"], "sorensen_circulo_fija": f["sorensen_circulo"],
                                 "ganancia_fija": f["ganancia_sobre_circulo"], "fuera_fija_pct": f["simulado_fuera_pct"],
                                 "razon_superficie_fija": f["razon_superficie"],
                                 "mejor_sorensen": m["mejor_hora"]["sorensen"], "mejor_hora": m["mejor_hora"]["hora"],
                                 "sup_3h": m["horizontes"]["3"]["superficie_ha"], "sup_6h": m["horizontes"]["6"]["superficie_ha"],
                                 "focos_acierto": (m["focos"]["dentro_de_lo_simulado"] / m["focos"]["total"]) if m["focos"]["total"] else None})
    return {"caso": caso.clave, "nombre": caso.nombre, "configuracion": config, "superficie_real_ha": round(real.area / 1e4),
            "hora_fija_h": hora_fija, "hora_fija_fuente": "contención publicada" if ref.get("contencion_h") else "valor fijado de antemano",
            "ajuste": caso.clave == CASO_DE_AJUSTE, "estaciones": usadas, "focos": len(puntos_f), "miembros": miembros,
            "resumen": {k: resumen([m[k] for m in miembros]) for k in
                        ("sorensen_fija", "sorensen_circulo_fija", "ganancia_fija", "fuera_fija_pct", "razon_superficie_fija",
                         "mejor_sorensen", "mejor_hora", "sup_3h", "sup_6h", "focos_acierto")}}


def resumen_global(resultados: dict, config: str = "actual") -> dict:
    """Mediana de las medianas por caso: el caso de ajuste aparte y los de evaluación juntos."""
    casos_cfg = [r for r in resultados.values() if isinstance(r, dict) and r.get("configuracion") == config]
    salida = {"n_casos": len(casos_cfg)}
    for grupo, filtro in (("ajuste", lambda r: r["ajuste"]), ("evaluacion", lambda r: not r["ajuste"])):
        sel = [r for r in casos_cfg if filtro(r)]
        salida[grupo] = {"casos": [r["caso"] for r in sel], **{
            k: resumen([r["resumen"][k]["mediana"] for r in sel if r["resumen"].get(k)])
            for k in ("sorensen_fija", "sorensen_circulo_fija", "ganancia_fija", "fuera_fija_pct", "razon_superficie_fija",
                      "mejor_sorensen")}}
    return salida


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--configuracion", nargs="*", default=["actual"])
    p.add_argument("--casos", nargs="*", default=None)
    a = p.parse_args(argv)
    casos = [CASOS[c] for c in (a.casos or CASOS) if CASOS[c].punto and CASOS[c].inicio]
    resultados = json.loads(SALIDA.read_text(encoding="utf-8")) if SALIDA.exists() else {}
    for config in a.configuracion:
        for caso in casos:
            r = evaluar_caso(caso, config)
            resultados[f"{caso.clave}|{config}"] = r
            s = r["resumen"]
            print(f"{config:18s} {caso.nombre:32s} a {r['hora_fija_h']:g} h: Sørensen {s['sorensen_fija']}  "
                  f"círculo {s['sorensen_circulo_fija']}  ganancia {s['ganancia_fija']}  fuera {s['fuera_fija_pct']} %", flush=True)
            resultados[f"resumen|{config}"] = resumen_global(resultados, config)
            SALIDA.parent.mkdir(parents=True, exist_ok=True)
            SALIDA.write_text(json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
