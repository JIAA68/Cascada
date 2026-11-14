"""Alertas automáticas de incendio: focos de calor detectados por satélite (NASA FIRMS).

Ficheros públicos casi en tiempo real de Europa (sin clave) de los tres satélites con sensor
VIIRS (375 m): Suomi NPP, NOAA-20 y NOAA-21.

- Focos actuales: detecciones de las últimas 24 horas dentro de la Comunidad de Madrid.
- Fuentes fijas: un foco con detecciones a menos de 500 m en 3 o más días de la última semana
  se marca como posible fuente fija (industria, vertedero).
"""
from datetime import datetime, timezone
from functools import lru_cache

import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree

from ..fuentes import CACHE, descargar
from .entradas import A_UTM, MADRID, municipios

BASE = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/"
SATELITES = {"Suomi NPP": "suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_Europe_{p}.csv",
             "NOAA-20": "noaa-20-viirs-c2/csv/J1_VIIRS_C2_Europe_{p}.csv",
             "NOAA-21": "noaa-21-viirs-c2/csv/J2_VIIRS_C2_Europe_{p}.csv"}
RENOVACION_MIN = 30       # los ficheros de FIRMS se actualizan cada hora: caché de media hora
RADIO_FIJA_M, DIAS_FIJA = 500, 3


def _descargar(periodo: str) -> pd.DataFrame:
    ahora = datetime.now(timezone.utc)
    tramo = ahora.strftime("%Y%m%dT%H") + f"{(ahora.minute // RENOVACION_MIN) * RENOVACION_MIN:02d}"
    tablas = []
    for nombre, ruta in SATELITES.items():
        destino = CACHE / "firms" / f"{tramo}_{nombre.replace(' ', '_')}_{periodo}.csv"
        t = pd.read_csv(descargar(BASE + ruta.format(p=periodo), destino, "NASA FIRMS, VIIRS casi en tiempo real"))
        tablas.append(t.assign(satelite=nombre))
    return pd.concat(tablas, ignore_index=True)


@lru_cache(maxsize=1)
def _comunidad():
    return shapely.union_all([g for _, _, g in municipios()])


def en_comunidad(t: pd.DataFrame) -> pd.DataFrame:
    x, y = A_UTM.transform(t.longitude.values, t.latitude.values)
    t = t.assign(x=x, y=y)
    return t[shapely.contains_xy(_comunidad(), t.x.values, t.y.values)]


def marcar_fuentes_fijas(actuales: pd.DataFrame, semana: pd.DataFrame) -> pd.Series:
    """True si el foco tiene detecciones cercanas en al menos DIAS_FIJA días de la semana."""
    if actuales.empty or semana.empty:
        return pd.Series(False, index=actuales.index)
    vecinos = cKDTree(np.c_[semana.x, semana.y]).query_ball_point(np.c_[actuales.x, actuales.y], RADIO_FIJA_M)
    fechas = semana.acq_date.values
    return pd.Series([len(set(fechas[v])) >= DIAS_FIJA for v in vecinos], index=actuales.index)


def focos_actuales() -> dict:
    actuales = en_comunidad(_descargar("24h"))
    actuales = actuales.assign(fuente_fija=marcar_fuentes_fijas(actuales, en_comunidad(_descargar("7d"))))
    focos = []
    for f in actuales.sort_values(["acq_date", "acq_time"], ascending=False).itertuples():
        hora = datetime.strptime(f"{f.acq_date} {int(f.acq_time):04d}", "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc)
        focos.append({"lon": float(f.longitude), "lat": float(f.latitude), "hora": hora.astimezone(MADRID).isoformat(timespec="minutes"),
                      "satelite": f.satelite, "confianza": str(f.confidence), "potencia_mw": float(f.frp),
                      "dia_noche": "día" if f.daynight == "D" else "noche", "fuente_fija": bool(f.fuente_fija)})
    return {"fuente": "NASA FIRMS (VIIRS 375 m: Suomi NPP, NOAA-20, NOAA-21), últimas 24 h",
            "consultado": datetime.now(MADRID).isoformat(timespec="minutes"), "focos": focos}
