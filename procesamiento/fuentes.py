"""Fuentes oficiales: descarga con trazabilidad.

Toda descarga queda anotada con su URL, la fecha (UTC), la huella SHA-256 y el tamaño
(regla de trazabilidad del proyecto). Hay dos registros:

- datos/registro.csv: fuentes de la cadena de datos (catálogo, centros, población,
  combustibles, municipios). Se publica con el código.
- datos/cache/registro.csv: descargas de uso (AEMET, FIRMS, relieve de cada simulación, trenes
  y tráfico en tiempo real).
  No se publica, porque crece con cada uso.

Un fichero que ya está en disco no se vuelve a descargar: la cadena es reproducible
desde cero y, a la vez, no castiga repetir ejecuciones.
"""
import csv
import hashlib
import threading
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DATOS = RAIZ / "datos"
BRUTOS = DATOS / "brutos"
CACHE = DATOS / "cache"
PROCESADOS = DATOS / "procesados"
VISOR = DATOS / "visor"

PORTAL = "https://datos.comunidad.madrid/dataset/"
CATALOGO = "https://idem.comunidad.madrid/recursos_cat_geo/Catalogo/recursos/ZonasRiesgo/PCivil/"

# clave -> (url, fichero dentro de datos/brutos, nota para el registro)
FUENTES = {
    "centros_educativos": (
        PORTAL + "c750856d-3166-4dac-8e80-d1b824c968b5/resource/28d60557-1d73-4281-ab08-6cfd3b2f5f83/"
        "download/centros_educativos.csv",
        "centros_educativos.csv", "Comunidad de Madrid, centros educativos"),
    "centros_sanitarios": (
        PORTAL + "d8a0a444-adf5-4c04-8999-0eac3de52cb7/resource/2948b4da-8b39-42b7-b667-779a5284f39d/"
        "download/centros_servicios_establecimientos_sanitarios.csv",
        "centros_sanitarios.csv", "Comunidad de Madrid, centros y establecimientos sanitarios"),
    "atencion_social": (
        PORTAL + "b8cdb7f7-3185-4938-800a-fefda72333f5/resource/0d815439-396e-4975-983e-5bb421f617a0/"
        "download/atencion_social_registro_centros.csv",
        "atencion_social.csv", "Comunidad de Madrid, registro de centros de atención social"),
    "municipios": (
        PORTAL + "6c63b14c-9f5d-414f-958f-b8a9c53d69fc/resource/3f4435b7-ecdb-4c1e-961a-dd55506c2e10/"
        "download/municipios_y_distritos_madrid_20.zip",
        "municipios_y_distritos_madrid_20.zip", "Comunidad de Madrid, municipios y distritos 2020"),
    "poblacion_rejilla": (
        "https://www.ine.es/censos2021/Poblacion_Rejilla_Europea.csv",
        "Poblacion_Rejilla_Europea.csv", "INE, Censo 2021, rejilla europea de 1 km"),
    "combustibles": (
        "https://forest-fire.emergency.copernicus.eu/effis/applications/data-and-services/FuelMap_LAEA.zip",
        "FuelMap_LAEA.zip", "Copernicus EFFIS, mapa de combustibles (CC BY 4.0)"),
}


def huella(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


_registro_cerrojo = threading.Lock()   # descargas en paralelo: una línea del registro cada vez


def registrar(url: str, ruta: Path, nota: str = "") -> None:
    """Anota una descarga en el registro que le corresponde (público o local)."""
    with _registro_cerrojo:
        _registrar(url, ruta, nota)


def _registrar(url: str, ruta: Path, nota: str) -> None:
    registro = CACHE / "registro.csv" if ruta.is_relative_to(CACHE) else DATOS / "registro.csv"
    registro.parent.mkdir(parents=True, exist_ok=True)
    nuevo = not registro.exists()
    with open(registro, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        if nuevo:
            w.writerow(["url", "fichero", "fecha_descarga", "sha256", "bytes", "nota"])
        w.writerow([url, ruta.relative_to(RAIZ).as_posix(),
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    huella(ruta), ruta.stat().st_size, nota])


def descargar(url: str, destino: Path, nota: str = "", cabeceras: dict | None = None) -> Path:
    """Descarga url en destino si no existe ya, y la registra. Devuelve la ruta."""
    if destino.exists():
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".parcial")
    peticion = urllib.request.Request(url, headers={"User-Agent": "Cascada/1.0", **(cabeceras or {})})
    with urllib.request.urlopen(peticion, timeout=300) as r, open(parcial, "wb") as f:
        while bloque := r.read(1 << 20):
            f.write(bloque)
    parcial.replace(destino)
    registrar(url, destino, nota)
    return destino


def descargar_vivo(url: str, destino: Path, nota: str = "", cabeceras: dict | None = None, espera: int = 60) -> Path:
    """Descarga siempre (datos en tiempo real), sustituye la copia anterior y la registra."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".parcial")
    peticion = urllib.request.Request(url, headers={"User-Agent": "Cascada/1.0", **(cabeceras or {})})
    with urllib.request.urlopen(peticion, timeout=espera) as r, open(parcial, "wb") as f:
        while bloque := r.read(1 << 20):
            f.write(bloque)
    parcial.replace(destino)
    registrar(url, destino, nota)
    return destino


def fuente(clave: str) -> Path:
    """Ruta local de una fuente de FUENTES, descargándola si hace falta."""
    url, fichero, nota = FUENTES[clave]
    return descargar(url, BRUTOS / fichero, nota)


def capa_catalogo(codigo: str) -> Path:
    """Zip de una capa de peligrosidad del Catálogo de Riesgos Potenciales ('3_1', '6_12'...)."""
    nombre = f"peligrosid_{codigo}.zip"
    return descargar(CATALOGO + nombre, BRUTOS / "catalogo" / nombre,
                     "Comunidad de Madrid, Catálogo de Riesgos Potenciales, peligrosidad")
