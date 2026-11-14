"""Modo sin conexión para la defensa (decisión del 13-11-2026).

Con red, el visor pide el mapa base, el relieve y la ortofoto directamente al IGN y las tipografías a MapLibre. Con
el servidor arrancado con --sin-conexion, los pide al servidor local (/externo/...), que los sirve desde la copia
guardada en disco (datos/cache/externo/) y nunca los pide fuera (decisión del 13-11-2026: el servidor no hace de
intermediario cuando hay red). Las librerías del visor (MapLibre GL JS y PMTiles) van en visor/vendor/. En ese modo
cualquier petición a internet del proceso falla en el acto, para que nada se quede esperando a una red que no hay.

Para preparar la defensa, este módulo descarga de antemano lo necesario: las teselas de los tres servicios de toda la
Comunidad hasta el zoom 13 (y su entorno hasta el 11), las tipografías, el MDT de 25 m de toda la Comunidad con el
margen de una ventana de simulación (para poder simular en cualquier punto sin red; el modelo lo usa en lugar de pedir
el relieve de cada ventana) y, opcionalmente, una zona con más zoom y una simulación con viento a mano:

    python -m procesamiento.sin_conexion [--zoom-comunidad 13] [--lon -3.80629 --lat 40.21090 --radio-km 25
        --zoom-max 14] [--simular --hora 2026-07-15T15:00 --viento 20,270]
"""
import argparse
import math
import os
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

from .fuentes import CACHE, registrar

CARPETA = CACHE / "externo"
SIN_CONEXION = os.environ.get("CASCADA_SIN_CONEXION") == "1"

_WMTS = ("https://www.ign.es/wmts/pnoa-ma?service=WMTS&request=GetTile&version=1.0.0&layer=OI.OrthoimageCoverage"
         "&style=default&tilematrixset=GoogleMapsCompatible&tilematrix={z}&tilerow={y}&tilecol={x}&format=image/jpeg")
# servicio: (plantilla de la URL, extensión, tipo MIME, zoom máximo del servicio)
SERVICIOS = {
    "ign-vectorial": ("https://vt-mapabase.idee.es/1.0.0/mapabase/{z}/{x}/{y}.pbf", "pbf", "application/x-protobuf", 17),
    "ign-mdt": ("https://xyz-mdt.idee.es/1.0.0/raster-dem/{z}/{x}/{y}.png", "png", "image/png", 15),
    "ign-pnoa": (_WMTS, "jpeg", "image/jpeg", 19),
}
GLIFOS = "https://demotiles.maplibre.org/font/{fuentes}/{rango}.pbf"
TIPOGRAFIAS = ("Open Sans Semibold", "Open Sans Regular,Arial Unicode MS Regular")
RANGOS = ("0-255", "256-511", "8192-8447")      # latín, latín extendido y puntuación (·, –, ²…)
ENTORNO = (-5.2, 39.5, -2.4, 41.6)              # Comunidad con margen: lo que cabe en pantalla a poco zoom
COMUNIDAD = (-4.65, 39.83, -2.98, 41.22)        # recuadro de la Comunidad de Madrid (lon, lat), con un pequeño margen
ZOOM_ENTORNO = 11
# MDT: recuadro de la Comunidad en EPSG:25830 más media ventana de simulación (25 km) y un margen, en bloques de 20 km
MDT_RECUADRO = (339_000, 4_388_000, 523_000, 4_585_000)
MDT_BLOQUE_M = 20_000


class _SinRed(urllib.request.BaseHandler):
    """Corta en el acto cualquier petición HTTP del proceso (AEMET, FIRMS, trenes, tráfico, relieve…)."""
    handler_order = 100   # antes que los manejadores normales de http y https

    def http_open(self, peticion):
        raise urllib.error.URLError("modo sin conexión: no se piden datos fuera")

    https_open = http_open


def activar() -> None:
    """Modo sin conexión en este proceso: caché como única fuente y ninguna petición a internet, para que lo que
    necesita red falle enseguida en lugar de esperar a que venza el plazo."""
    global SIN_CONEXION
    SIN_CONEXION = True
    urllib.request.install_opener(urllib.request.build_opener(_SinRed))


def configuracion_visor() -> str:
    """Script de configuración del visor: si el servidor está sin conexión (el visor pide entonces el mapa a /externo/)
    y el zoom hasta el que hay teselas de toda la Comunidad, para que MapLibre amplíe esas en lugar de pedir otras."""
    zoom = None
    if SIN_CONEXION:
        marca = CARPETA / "zoom.txt"
        zoom = int(marca.read_text(encoding="utf-8")) if marca.exists() else 11
    return (f"window.CASCADA_SIN_CONEXION = {'true' if SIN_CONEXION else 'false'};\n"
            f"window.CASCADA_ZOOM_CACHE = {zoom or 'null'};\n")


def _pedir(url: str, destino: Path, nota: str) -> Path | None:
    """Descarga a la caché y la anota en el registro local; None si no hay conexión o el servicio no la tiene."""
    if SIN_CONEXION:
        return None
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".parcial")
    try:
        peticion = urllib.request.Request(url, headers={"User-Agent": "Cascada/1.0"})
        with urllib.request.urlopen(peticion, timeout=15) as r:
            datos = r.read()
    except (urllib.error.URLError, OSError, TimeoutError):
        return None
    parcial.write_bytes(datos)
    parcial.replace(destino)
    registrar(url, destino, nota)
    return destino


def tesela(servicio: str, z: int, x: int, y: int, descargar: bool = False) -> tuple[Path, str] | None:
    """Ruta en la copia guardada de una tesela de un servicio externo y su tipo MIME; None si no está.

    Solo la preparación (descargar=True) la pide fuera si falta: el servidor sirve lo guardado y nada más.
    """
    plantilla, ext, mime, zmax = SERVICIOS[servicio]
    if not (0 <= z <= zmax and 0 <= x < 2 ** z and 0 <= y < 2 ** z):
        return None
    ruta = CARPETA / servicio / str(z) / str(x) / f"{y}.{ext}"
    if ruta.exists() or (descargar and _pedir(plantilla.format(z=z, x=x, y=y), ruta, f"tesela {servicio} (copia sin conexión)")):
        return ruta, mime
    return None


def glifo(fuentes: str, rango: str, descargar: bool = False) -> Path | None:
    """Tipografía de los rótulos del mapa (pbf de glifos) desde la copia guardada; None si no está."""
    if fuentes not in TIPOGRAFIAS or rango.count("-") != 1 or not rango.replace("-", "").isdigit():
        return None
    ruta = CARPETA / "glifos" / fuentes.replace(",", "_").replace(" ", "-") / f"{rango}.pbf"
    if ruta.exists() or (descargar and _pedir(GLIFOS.format(fuentes=quote(fuentes), rango=rango), ruta,
                                               "tipografía del mapa (copia sin conexión)")):
        return ruta
    return None


def _xy(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def teselas_de(recuadro: tuple[float, float, float, float], z: int) -> list[tuple[int, int, int]]:
    oeste, sur, este, norte = recuadro
    x0, y0 = _xy(oeste, norte, z)
    x1, y1 = _xy(este, sur, z)
    return [(z, x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]


def preparar(zoom_comunidad: int = 13, lon: float | None = None, lat: float | None = None, radio_km: float = 25,
             zoom_max: int = 14) -> dict:
    """Descarga de antemano las teselas del entorno, de la Comunidad y, si se da, de una zona con más zoom, y las
    tipografías. Devuelve recuentos."""
    pedidas = set()
    for z in range(7, ZOOM_ENTORNO + 1):
        pedidas.update(teselas_de(ENTORNO, z))
    for z in range(ZOOM_ENTORNO + 1, zoom_comunidad + 1):
        pedidas.update(teselas_de(COMUNIDAD, z))
    if lon is not None and lat is not None:
        dlat = radio_km / 111.32
        dlon = radio_km / (111.32 * math.cos(math.radians(lat)))
        zona = (lon - dlon, lat - dlat, lon + dlon, lat + dlat)
        for z in range(ZOOM_ENTORNO + 1, zoom_max + 1):
            pedidas.update(teselas_de(zona, z))
    trabajos = [(s, *t) for s in SERVICIOS for t in sorted(pedidas) if t[0] <= SERVICIOS[s][3]]
    CARPETA.mkdir(parents=True, exist_ok=True)
    (CARPETA / "zoom.txt").write_text(str(zoom_comunidad), encoding="utf-8")   # lo que el visor puede pedir sin red
    with ThreadPoolExecutor(max_workers=6) as pool:
        resultados = list(pool.map(lambda a: tesela(*a, descargar=True) is not None, trabajos))
    glifos = [glifo(f, r, descargar=True) is not None for f in TIPOGRAFIAS for r in RANGOS]
    return {"teselas": len(trabajos), "en_cache": sum(resultados), "glifos": f"{sum(glifos)}/{len(glifos)}"}


def preparar_mdt() -> Path:
    """MDT de 25 m de toda la Comunidad con margen (mismo WCS del IGN que el relieve de cada simulación), descargado por
    bloques y unido en un solo GeoTIFF."""
    import rasterio
    from rasterio.merge import merge
    from .fuentes import descargar
    from .incendio.entradas import MDT_COMUNIDAD, WCS_MDT
    x0, y0, x1, y1 = MDT_RECUADRO
    if MDT_COMUNIDAD.exists():
        with rasterio.open(MDT_COMUNIDAD) as m:
            b = m.bounds
        if b.left <= x0 and b.bottom <= y0 and b.right >= x1 and b.top >= y1:
            return MDT_COMUNIDAD
    bloques = []
    for x in range(x0, x1, MDT_BLOQUE_M):
        for y in range(y0, y1, MDT_BLOQUE_M):
            xa, ya = min(x + MDT_BLOQUE_M, x1), min(y + MDT_BLOQUE_M, y1)
            url = (f"{WCS_MDT}?service=WCS&version=2.0.1&request=GetCoverage&CoverageId=Elevacion25830_25"
                   f"&subset=x({x},{xa})&subset=y({y},{ya})&format=image/tiff")
            bloques.append(descargar(url, CARPETA / "mdt25" / f"{x}_{y}.tif",
                                     "IGN, MDT 25 m (WCS INSPIRE), bloque para el modo sin conexión"))
    fuentes = [rasterio.open(b) for b in bloques]
    try:
        mosaico, transformacion = merge(fuentes)
        perfil = {k: v for k, v in fuentes[0].profile.items() if k not in ("blockxsize", "blockysize", "tiled")}
        perfil |= {"driver": "GTiff", "height": mosaico.shape[1], "width": mosaico.shape[2], "transform": transformacion,
                   "compress": "deflate", "tiled": True, "blockxsize": 256, "blockysize": 256}
    finally:
        for f in fuentes:
            f.close()
    parcial = MDT_COMUNIDAD.with_name(MDT_COMUNIDAD.stem + "_parcial.tif")
    with rasterio.open(parcial, "w", **perfil) as dst:
        dst.write(mosaico)
    parcial.replace(MDT_COMUNIDAD)
    return MDT_COMUNIDAD


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--zoom-comunidad", type=int, default=13)
    p.add_argument("--sin-mdt", action="store_true", help="no descargar el MDT de la Comunidad")
    p.add_argument("--lon", type=float)
    p.add_argument("--lat", type=float)
    p.add_argument("--radio-km", type=float, default=25)
    p.add_argument("--zoom-max", type=int, default=14)
    p.add_argument("--simular", action="store_true", help="deja calculada la simulación del punto (viento a mano)")
    p.add_argument("--hora", help="hora local de la ignición, ISO (con --simular)")
    p.add_argument("--viento", default="25,270", help="velocidad en km/h y dirección de origen en grados (con --simular)")
    a = p.parse_args(argv)
    print("Teselas y tipografías:", preparar(a.zoom_comunidad, a.lon, a.lat, a.radio_km, a.zoom_max), flush=True)
    if not a.sin_mdt:
        print("MDT de la Comunidad:", preparar_mdt(), flush=True)
    if a.simular and a.lon is not None and a.lat is not None:
        from .incendio import simulacion
        argumentos = ["--lon", str(a.lon), "--lat", str(a.lat), "--viento", a.viento] + (["--hora", a.hora] if a.hora else [])
        simulacion.main(argumentos)


if __name__ == "__main__":
    main()
