"""Entradas del modelo de incendio para una ventana alrededor de la ignición.

- Ventana: rejilla de 50 m en EPSG:25830 (el sistema del catálogo), de 50 × 50 km,
  centrada en la ignición y alineada a múltiplos del tamaño de celda.
- Combustible: dentro de la Comunidad, su mapa de modelos de combustibles (LiDAR, rasterizado a 25 m y
  llevado a la rejilla por el modelo más frecuente; combustible_cm.py); fuera, el mapa europeo de EFFIS
  (250 m, EPSG:3035), por vecino más próximo.
- Relieve: MDT de 25 m del IGN (WCS INSPIRE), promediado a la rejilla; de él salen la
  pendiente y la orientación. Cada descarga va a datos/cache y al registro local.
- Viento: AEMET OpenData. La hora de ignición usa la observación de la estación más cercana
  con dato de viento; las siguientes, la predicción horaria del municipio de la ignición.
  Rachas: el viento medio, salvo en las horas con tormenta prevista
  (probabilidad de al menos el 40 %, el umbral de la prealerta) o, en la primera, con racha
  observada que alcance el umbral amarillo de Meteoalerta de la zona: entonces la racha.
  También puede darse a mano (respaldo si AEMET no responde).
- Humedad del combustible: hora a hora, de la temperatura y la humedad
  del aire de la misma observación y predicción (humedades_del_aire); a mano, la fija de verano.
- Municipios: límites de la Comunidad de Madrid (2020), para el municipio de la ignición y
  el primer minuto en que el fuego entra en cada municipio.
"""
import json
import math
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import numpy as np
import pyogrio
import rasterio
import shapely
from pyproj import Transformer
from rasterio import features
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

from ..fuentes import CACHE, PROCESADOS, RAIZ, descargar, fuente
from . import combustible_cm
from .combustibles import VERANO, Humedades, humedades_del_aire
from .propagacion import Viento

MADRID = ZoneInfo("Europe/Madrid")
CRS = "EPSG:25830"
A_GEO = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
A_UTM = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
WCS_MDT = "https://servicios.idee.es/wcs-inspire/mdt"
# MDT 25 m de toda la Comunidad con margen, del mismo WCS, para simular sin conexión (procesamiento/sin_conexion.py)
MDT_COMUNIDAD = CACHE / "mdt25_comunidad.tif"
AEMET = "https://opendata.aemet.es/opendata/api"
RUMBOS = {"N": 0, "NE": 45, "E": 90, "SE": 135, "S": 180, "SO": 225, "O": 270, "NO": 315}
LADO_M, CELDA_M = 50_000, 50.0


@dataclass(frozen=True)
class Ventana:
    x0: float       # esquina superior izquierda (EPSG:25830)
    y0: float
    celda: float
    filas: int
    columnas: int

    @property
    def transform(self):
        return from_origin(self.x0, self.y0, self.celda, self.celda)

    @property
    def limites(self):
        return (self.x0, self.y0 - self.filas * self.celda, self.x0 + self.columnas * self.celda, self.y0)

    def fila_columna(self, x, y):
        return int((self.y0 - y) // self.celda), int((x - self.x0) // self.celda)

    def contiene(self, x, y):
        xmin, ymin, xmax, ymax = self.limites
        return (x >= xmin) & (x < xmax) & (y > ymin) & (y <= ymax)

    def esquinas_lonlat(self):
        """Esquinas en lon/lat en el orden de MapLibre: NO, NE, SE, SO."""
        xmin, ymin, xmax, ymax = self.limites
        return [list(A_GEO.transform(x, y)) for x, y in ((xmin, ymax), (xmax, ymax), (xmax, ymin), (xmin, ymin))]


def ventana_centrada(x: float, y: float, lado_m: float = LADO_M, celda: float = CELDA_M) -> Ventana:
    n = int(lado_m // celda)
    return Ventana(math.floor((x - lado_m / 2) / celda) * celda, math.ceil((y + lado_m / 2) / celda) * celda,
                   celda, n, n)


# ---------------------------------------------------------------- combustible y relieve

def combustible_effis(v: Ventana) -> np.ndarray:
    """Modelos NFFL del mapa europeo de EFFIS por celda (0 = sin combustible o sin dato)."""
    destino = np.zeros((v.filas, v.columnas), dtype=np.uint8)
    with rasterio.open(f"/vsizip/{fuente('combustibles').as_posix()}/FuelMap2000_NFFL_LAEA.tif") as src:
        reproject(rasterio.band(src, 1), destino, dst_transform=v.transform, dst_crs=CRS, dst_nodata=0,
                  resampling=Resampling.nearest)
    return destino.astype(np.int16)


def combustible_comunidad(v: Ventana) -> np.ndarray | None:
    """Modelos NFFL del mapa de la Comunidad por celda (SIN_DATO fuera de ella); None si el ráster no existe."""
    if not combustible_cm.RASTER.exists():
        return None
    destino = np.full((v.filas, v.columnas), combustible_cm.SIN_DATO, dtype=np.uint8)
    with rasterio.open(combustible_cm.RASTER) as src:
        reproject(rasterio.band(src, 1), destino, dst_transform=v.transform, dst_crs=CRS,
                  src_nodata=combustible_cm.SIN_DATO, dst_nodata=combustible_cm.SIN_DATO, resampling=Resampling.mode)
    return destino


def combinar(comunidad: np.ndarray | None, effis: np.ndarray) -> np.ndarray:
    """El mapa de la Comunidad donde tiene dato; EFFIS en el resto."""
    if comunidad is None:
        return effis.astype(np.int16)
    return np.where(comunidad != combustible_cm.SIN_DATO, comunidad, effis).astype(np.int16)


def combustible(v: Ventana) -> np.ndarray:
    """Modelos NFFL por celda (0 = sin combustible o sin dato)."""
    return combinar(combustible_comunidad(v), combustible_effis(v))


def fuente_combustible(v: Ventana, fila: int, columna: int) -> str:
    """Mapa del que sale el combustible de una celda (para explicar la simulación)."""
    cm = combustible_comunidad(v)
    if cm is not None and cm[fila, columna] != combustible_cm.SIN_DATO:
        return "mapa de modelos de combustibles de la Comunidad de Madrid (LiDAR, 25 m)"
    return "mapa europeo de combustibles de EFFIS (250 m)"


def relieve(v: Ventana):
    """Altitud (m), pendiente (tangente) y dirección de máxima subida (grados) por celda."""
    margen = 2 * v.celda
    xmin, ymin, xmax, ymax = v.limites
    xmin, ymin, xmax, ymax = xmin - margen, ymin - margen, xmax + margen, ymax + margen
    mdt = None
    if MDT_COMUNIDAD.exists():   # el mosaico de la Comunidad, si cubre la ventana (modo sin conexión)
        with rasterio.open(MDT_COMUNIDAD) as m:
            b = m.bounds
            if b.left <= xmin and b.bottom <= ymin and b.right >= xmax and b.top >= ymax:
                mdt = MDT_COMUNIDAD
    if mdt is None:
        url = (f"{WCS_MDT}?service=WCS&version=2.0.1&request=GetCoverage&CoverageId=Elevacion25830_25"
               f"&subset=x({xmin:.0f},{xmax:.0f})&subset=y({ymin:.0f},{ymax:.0f})&format=image/tiff")
        mdt = descargar(url, CACHE / f"mdt25_{xmin:.0f}_{ymax:.0f}_{xmax - xmin:.0f}.tif", "IGN, MDT 25 m (WCS INSPIRE)")
    ampliada = Ventana(v.x0 - v.celda, v.y0 + v.celda, v.celda, v.filas + 2, v.columnas + 2)  # para derivar en los bordes
    z = np.full((ampliada.filas, ampliada.columnas), np.nan, dtype=np.float32)
    with rasterio.open(mdt) as src:
        reproject(rasterio.band(src, 1), z, dst_transform=ampliada.transform, dst_crs=CRS, src_nodata=src.nodata,
                  dst_nodata=np.nan, resampling=Resampling.average)
    dz_df, dz_dc = np.gradient(z, v.celda)
    este, norte = dz_dc, -dz_df
    pendiente = np.nan_to_num(np.hypot(este, norte)[1:-1, 1:-1])
    subida = np.nan_to_num((np.degrees(np.arctan2(este, norte)) % 360)[1:-1, 1:-1])
    return z[1:-1, 1:-1], pendiente, subida


# ---------------------------------------------------------------- municipios

@lru_cache(maxsize=1)
def municipios() -> list[tuple[str, str, shapely.Geometry]]:
    """(código INE de 5 cifras, nombre, geometría) de cada municipio de la Comunidad."""
    ruta = f"/vsizip/{fuente('municipios').as_posix()}/municipios_y_distritos_madrid.shp"
    meta, _, geom, campos = pyogrio.raw.read(ruta)
    nombres = list(meta["fields"])
    codigos, textos = campos[nombres.index("codigo_geo")], campos[nombres.index("municipio_")]
    return [("28" + str(c)[:3], str(n), g) for c, n, g in zip(codigos, textos, shapely.from_wkb(geom))]


def municipio_de(x: float, y: float) -> tuple[str, str]:
    punto = shapely.Point(x, y)
    for codigo, nombre, g in municipios():
        if g.contains(punto):
            return codigo, nombre
    raise ValueError("El punto no está en la Comunidad de Madrid")


def municipios_en_ventana(v: Ventana) -> tuple[np.ndarray, list[tuple[str, str]]]:
    """Índice de municipio por celda (0 = ninguno) y la lista (código, nombre) correspondiente."""
    lista = [(c, n) for c, n, g in municipios()]
    formas = [(g, i + 1) for i, (_, _, g) in enumerate(municipios())]
    indice = features.rasterize(formas, out_shape=(v.filas, v.columnas), transform=v.transform, fill=0, dtype="int32")
    return indice, lista


# ---------------------------------------------------------------- viento (AEMET)

def _clave_aemet() -> str:
    env = RAIZ / ".env"
    if env.exists():
        for linea in env.read_text(encoding="utf-8").splitlines():
            if linea.startswith("AEMET_API_KEY=") and linea.split("=", 1)[1].strip():
                return linea.split("=", 1)[1].strip()
    raise RuntimeError("Falta AEMET_API_KEY en el fichero .env (copia .env.ejemplo)")


def _aemet(ruta: str, nombre: str):
    """Llama a AEMET (dos pasos), guarda la respuesta en la caché con su registro y la devuelve."""
    cab = {"api_key": _clave_aemet()}
    for intento in range(2):  # el servidor de AEMET corta conexiones o no responde de forma intermitente
        try:
            with urllib.request.urlopen(urllib.request.Request(AEMET + ruta, headers=cab), timeout=20) as r:
                meta = json.loads(r.read().decode("latin-1"))
            break
        except OSError as e:
            if intento == 1:
                raise RuntimeError(f"AEMET OpenData no responde ({e.reason if hasattr(e, 'reason') else e}): "
                                   "introduce el viento a mano") from e
            time.sleep(3)
    if "datos" not in meta:
        raise RuntimeError(f"AEMET {ruta}: {meta.get('descripcion')}")
    sello = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    destino = descargar(meta["datos"], CACHE / f"aemet_{nombre}_{sello}.json", f"AEMET OpenData {ruta}")
    return json.loads(destino.read_bytes().decode("latin-1"))


def viento_observado(x: float, y: float):
    """Último viento observado en la estación de AEMET más cercana con dato de viento."""
    mejor = None
    for o in _aemet("/observacion/convencional/todas", "observacion"):
        if o.get("dv") is None or o.get("vv") is None:
            continue
        ox, oy = A_UTM.transform(o["lon"], o["lat"])
        d = math.hypot(ox - x, oy - y)
        if mejor is None or d < mejor[0] or (d == mejor[0] and o["fint"] > mejor[1]["fint"]):
            mejor = (d, o)
    d, o = mejor
    return Viento(round(o["vv"] * 3.6, 1), float(o["dv"])), {
        "estacion": o["ubi"], "idema": o["idema"], "distancia_km": round(d / 1000, 1), "hora_utc": o["fint"],
        "racha_kmh": round(o["vmax"] * 3.6, 1) if o.get("vmax") is not None else None,
        "racha_desde": float(o["dmax"]) if o.get("dmax") is not None else None,
        "temperatura": o.get("ta"), "humedad": o.get("hr")}


def _numero(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _en_periodo(periodo: str, hora: int) -> bool:
    """Si una hora (0 a 23) cae en un periodo de AEMET como "0814" o "2002" (de 20 a 02, pasando la medianoche)."""
    a, b = int(periodo[:2]), int(periodo[2:4])
    return a <= hora < b if a < b else (hora >= a or hora < b)


def leer_prevision(datos) -> dict[datetime, dict]:
    """Predicción horaria de AEMET ya descargada: por hora local, viento medio, racha (km/h), temperatura (°C),
    humedad relativa (%) y probabilidad de tormenta (%) de su periodo."""
    salida = {}
    for dia in datos[0]["prediccion"]["dia"]:
        fecha = datetime.fromisoformat(dia["fecha"]).date()
        hora_de = lambda p: datetime(fecha.year, fecha.month, fecha.day, int(p), tzinfo=MADRID)
        for e in dia.get("vientoAndRachaMax", []):
            if "direccion" in e:
                rumbo, vel = e["direccion"][0], float(e["velocidad"][0])
                salida.setdefault(hora_de(e["periodo"]), {})["viento"] = Viento(0.0 if rumbo == "C" else vel, RUMBOS.get(rumbo, 0.0))
            elif "value" in e:   # las entradas con "value" son la racha máxima de esa hora
                salida.setdefault(hora_de(e["periodo"]), {})["racha_kmh"] = _numero(e["value"])
        for clave, campo in (("temperatura", "temperatura"), ("humedad", "humedadRelativa")):
            for e in dia.get(campo) or []:
                salida.setdefault(hora_de(e["periodo"]), {})[clave] = _numero(e.get("value"))
        tormentas = [(e["periodo"], _numero(e.get("value"))) for e in dia.get("probTormenta") or [] if e.get("periodo")]
        for hora, d in salida.items():
            if hora.date() == fecha:
                d["prob_tormenta"] = max([p for per, p in tormentas if p is not None and _en_periodo(per, hora.hour)], default=None)
    return {h: d for h, d in salida.items() if "viento" in d}


def prevision_horaria(codigo_ine: str) -> dict[datetime, dict]:
    """Predicción horaria del municipio (unos tres días): ver leer_prevision."""
    return leer_prevision(_aemet(f"/prediccion/especifica/municipio/horaria/{codigo_ine}", f"horaria_{codigo_ine}"))


def viento_previsto(codigo_ine: str) -> dict[datetime, Viento]:
    """Predicción horaria del municipio: viento medio a 10 m por hora local."""
    return {h: d["viento"] for h, d in prevision_horaria(codigo_ine).items()}


TORMENTA_PROB_MIN = 40      # la prealerta marca tormenta desde el 40 % (prealerta/umbrales.py, TORMENTA_PROB)
RACHA_FUERTE_KMH = 70       # umbral amarillo de rachas de Meteoalerta más bajo de la Comunidad, si no se sabe la zona


def umbral_racha(codigo_ine: str) -> float:
    """Umbral amarillo de rachas de Meteoalerta (km/h) de la zona de aviso del municipio."""
    from ..prealerta.umbrales import ZONAS
    ruta = PROCESADOS / "municipios.csv"
    if ruta.exists():
        import pandas as pd
        m = pd.read_csv(ruta, dtype=str)
        fila = m[m.codigo == str(codigo_ine)]
        if not fila.empty and fila.zona.iloc[0] in ZONAS:
            return float(ZONAS[fila.zona.iloc[0]]["racha"][0])
    return float(RACHA_FUERTE_KMH)


OBSERVACION_VIGENTE_H = 3   # una ignición hasta 3 h antes de la última observación aún se simula con ella


def comprobar_ventana(inicio: datetime, hora_observacion_utc: str, prevision: dict[datetime, dict]) -> bool:
    """Comprueba que AEMET tiene datos para la hora de la ignición y dice si la primera hora usa la observación.

    AEMET solo da la última observación y la predicción horaria de unos tres días: una ignición anterior a la
    observación en más de OBSERVACION_VIGENTE_H horas, o posterior a la última hora prevista, no se puede simular con
    AEMET (se rechaza con un mensaje que lleva al viento a mano). Si la ignición es posterior a la observación, la
    primera hora sale de la predicción, como las demás.
    """
    observada = datetime.fromisoformat(hora_observacion_utc.replace("+0000", "+00:00")).astimezone(MADRID)
    hora = inicio.astimezone(MADRID)
    ultima = max(prevision) if prevision else observada
    if hora < observada - timedelta(hours=OBSERVACION_VIGENTE_H) or hora > ultima + timedelta(minutes=59):
        raise ValueError(f"AEMET solo tiene datos desde la última observación ({observada:%d-%m %H:%M}) hasta el final de su "
                         f"predicción ({ultima:%d-%m %H:%M}); para otra hora, introduce el viento a mano")
    return hora < observada + timedelta(hours=1)


def meteo_horaria(observado: Viento, estacion: dict, prevision: dict[datetime, dict], umbral: float,
                  inicio: datetime, horas: int = 25, primera_observada: bool = True):
    """Viento y humedad del combustible de cada hora desde la ignición, y qué hora lleva racha y de dónde sale cada una.

    Primera hora: la observación (con su temperatura y humedad; si faltan, las previstas). Siguientes: la predicción
    horaria; si falta una hora, se repite la anterior. En una hora se usa la racha en lugar del viento medio si hay
    tormenta prevista en su periodo (al menos el 40 %) o, en la primera, si la racha observada alcanza el umbral
    amarillo de Meteoalerta de la zona. La racha conserva la dirección del viento medio (la observada, la de la racha).
    """
    inicio = inicio.astimezone(MADRID).replace(minute=0, second=0, microsecond=0)
    vientos, humedades, origen, rachas = [], [], [], []
    ultimo_viento, ultima_humedad = observado, None
    for h in range(horas):
        p = prevision.get(inicio + timedelta(hours=h))
        tormenta = bool(p) and (p.get("prob_tormenta") or 0) >= TORMENTA_PROB_MIN
        if h == 0 and primera_observada:
            obs = estacion.get("racha_kmh")
            fuerte = obs is not None and obs >= umbral
            racha = obs if obs is not None else (p or {}).get("racha_kmh")
            usar = (fuerte or tormenta) and racha is not None
            viento = Viento(racha, estacion.get("racha_desde") or observado.desde) if usar and obs is not None \
                else Viento(racha, observado.desde) if usar else observado
            temp, hum = estacion.get("temperatura"), estacion.get("humedad")
            if (temp is None or hum is None) and p:
                temp, hum = p.get("temperatura"), p.get("humedad")
            origen.append("observado")
        elif p:
            usar = tormenta and p.get("racha_kmh") is not None
            viento = Viento(p["racha_kmh"], p["viento"].desde) if usar else p["viento"]
            temp, hum = p.get("temperatura"), p.get("humedad")
            origen.append("previsto")
        else:
            usar, viento, temp, hum = False, ultimo_viento, None, None
            origen.append("repetido")
        humedad = humedades_del_aire(temp, hum) if temp is not None and hum is not None else (ultima_humedad or VERANO)
        vientos.append(viento); humedades.append(humedad); rachas.append(bool(usar))
        ultimo_viento, ultima_humedad = viento, humedad
    return vientos, humedades, origen, rachas


def vientos_horarios(x: float, y: float, inicio: datetime, horas: int = 25):
    """Viento y humedad del combustible por hora desde la ignición (AEMET), y su origen."""
    codigo, nombre = municipio_de(x, y)
    observado, estacion = viento_observado(x, y)
    umbral = umbral_racha(codigo)
    prevision = prevision_horaria(codigo)
    primera_observada = comprobar_ventana(inicio, estacion["hora_utc"], prevision)
    vientos, humedades, origen, rachas = meteo_horaria(observado, estacion, prevision, umbral, inicio, horas, primera_observada)
    return vientos, humedades, {
        "origen": "AEMET", "municipio": nombre, "codigo_ine": codigo, "estacion": estacion,
        "horas_previstas": origen.count("previsto"), "horas_repetidas": origen.count("repetido"),
        "racha_por_hora": rachas, "horas_con_racha": sum(rachas), "umbral_racha_kmh": umbral,
        "humedad": "la temperatura y la humedad del aire de AEMET, hora a hora"}
