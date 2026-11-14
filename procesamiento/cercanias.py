"""Horario de Cercanías Madrid de Renfe: estaciones y paso de cada tren por ellas.

Fuente: Renfe, GTFS estático de Cercanías (data.renfe.com, CC BY 4.0), fichero fomento_transit.zip con
todos los núcleos y los próximos 30 días (un servicio por día). Se usa el núcleo de Madrid (líneas con
identificador que empieza por 10). Renfe lo renueva a diario: la cadena lo vuelve a descargar si la copia
tiene más de 7 días, y registra cada descarga.

Salida:
- datos/procesados/cercanias_estaciones.csv: estaciones del núcleo de Madrid con sus coordenadas.
- datos/procesados/cercanias_pasos.csv.gz: cada paso de un tren por una estación, con su fecha de
  servicio, la línea, el destino y los segundos desde la medianoche de esa fecha (pueden pasar de 24 h).

No se estima cuántas personas lleva cada tren.

Uso: python -m procesamiento.cercanias
"""
import io
import time
import zipfile
from functools import lru_cache

import pandas as pd

from .fuentes import BRUTOS, PROCESADOS, descargar_vivo
from .incendio.entradas import A_UTM

URL = "https://ssl.renfe.com/ftransit/Fichero_CER_FOMENTO/fomento_transit.zip"
GTFS = BRUTOS / "renfe" / "fomento_transit.zip"
ESTACIONES = PROCESADOS / "cercanias_estaciones.csv"
PASOS = PROCESADOS / "cercanias_pasos.csv.gz"
NUCLEO = "10"            # Madrid
CADUCIDAD_DIAS = 7
NOTA = "Renfe, GTFS estático de Cercanías (CC BY 4.0)"


def _tabla(z: zipfile.ZipFile, nombre: str, **kw) -> pd.DataFrame:
    """Un fichero del GTFS como texto, sin los espacios con que Renfe rellena columnas y valores."""
    t = pd.read_csv(io.BytesIO(z.read(nombre)), dtype=str, keep_default_na=False, **kw)
    t.columns = t.columns.str.strip()
    return t.apply(lambda s: s.str.strip())


def descargar_gtfs() -> None:
    if not GTFS.exists() or time.time() - GTFS.stat().st_mtime > CADUCIDAD_DIAS * 86400:
        descargar_vivo(URL, GTFS, NOTA, espera=300)


def construir(forzar: bool = False):
    """Estaciones y pasos del núcleo de Madrid. Devuelve la ruta de los pasos."""
    nuevo = not GTFS.exists() or time.time() - GTFS.stat().st_mtime > CADUCIDAD_DIAS * 86400
    if not (nuevo or forzar) and ESTACIONES.exists() and PASOS.exists():
        return PASOS
    descargar_gtfs()
    with zipfile.ZipFile(GTFS) as z:
        rutas = _tabla(z, "routes.txt")
        rutas = rutas[rutas.route_id.str.startswith(NUCLEO)][["route_id", "route_short_name"]]
        viajes = _tabla(z, "trips.txt").merge(rutas, on="route_id")[["trip_id", "service_id", "route_short_name", "trip_headsign"]]
        calendario = _tabla(z, "calendar.txt")[["service_id", "start_date", "end_date"]]
        if (calendario.start_date != calendario.end_date).any():
            raise RuntimeError("El calendario de Renfe ya no tiene un servicio por día: revisar cercanias.py")
        viajes = viajes.merge(calendario[["service_id", "start_date"]], on="service_id").rename(columns={"start_date": "fecha"})
        ids = set(viajes.trip_id)
        partes = []
        with z.open("stop_times.txt") as f:
            for trozo in pd.read_csv(f, dtype=str, usecols=lambda c: c.strip() in ("trip_id", "departure_time", "stop_id"),
                                     chunksize=1_000_000):
                trozo.columns = trozo.columns.str.strip()
                trozo = trozo.apply(lambda s: s.str.strip())
                partes.append(trozo[trozo.trip_id.isin(ids)])
        horas = pd.concat(partes, ignore_index=True)
        paradas = _tabla(z, "stops.txt")
    h = horas.departure_time.str.split(":", expand=True).astype(int)
    horas["segundos"] = h[0] * 3600 + h[1] * 60 + h[2]
    pasos = horas.merge(viajes, on="trip_id")[["fecha", "trip_id", "route_short_name", "trip_headsign", "stop_id", "segundos"]]
    pasos = pasos.rename(columns={"route_short_name": "linea", "trip_headsign": "destino"})
    # Renfe deja vacío el destino: es la última estación del recorrido
    nombres = paradas.set_index("stop_id").stop_name
    ultima = pasos.loc[pasos.groupby("trip_id").segundos.idxmax(), ["trip_id", "stop_id"]]
    pasos["destino"] = pasos.trip_id.map(dict(zip(ultima.trip_id, ultima.stop_id.map(nombres))))
    estaciones = paradas[paradas.stop_id.isin(set(pasos.stop_id))][["stop_id", "stop_name", "stop_lon", "stop_lat"]].copy()
    estaciones = estaciones.rename(columns={"stop_name": "nombre", "stop_lon": "lon", "stop_lat": "lat"})
    estaciones[["lon", "lat"]] = estaciones[["lon", "lat"]].astype(float)
    estaciones["x"], estaciones["y"] = A_UTM.transform(estaciones.lon.values, estaciones.lat.values)
    estaciones.to_csv(ESTACIONES, index=False, encoding="utf-8")
    pasos.to_csv(PASOS, index=False, encoding="utf-8", compression="gzip")
    cargar.cache_clear()
    return PASOS


@lru_cache(maxsize=1)
def cargar() -> tuple[pd.DataFrame, pd.DataFrame]:
    """(estaciones, pasos) del núcleo de Madrid."""
    estaciones = pd.read_csv(ESTACIONES, dtype={"stop_id": str})
    pasos = pd.read_csv(PASOS, dtype={"fecha": str, "trip_id": str, "linea": str, "destino": str, "stop_id": str})
    return estaciones, pasos


if __name__ == "__main__":
    construir(forzar=True)
    e, p = cargar()
    print(f"{len(e)} estaciones, {p.trip_id.nunique()} trenes y {len(p)} pasos del {p.fecha.min()} al {p.fecha.max()}")
