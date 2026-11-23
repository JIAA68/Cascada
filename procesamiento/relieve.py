"""Teselas de relieve para la vista en 3D del visor.

Parten del MDT de 25 m del IGN de toda la Comunidad con margen (el mismo que usa el modelo de incendio y el modo sin
conexión, procesamiento/sin_conexion.py). Cada tesela se reproyecta a Web Mercator con interpolación bilineal y se
codifica en el formato Terrarium (altitud + 32768 = R·256 + G + B/256), el que MapLibre lee como fuente de relieve.
Los píxeles sin dato del borde se rellenan con el valor válido más cercano, para que el relieve no caiga a cero.
Salida: datos/visor/relieve.pmtiles, zooms 7 a 12 (unos 30 m por píxel en Madrid; más cerca, MapLibre amplía).

Uso: python -m procesamiento.relieve
"""
import warnings

import numpy as np
import rasterio
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer
from pyproj import Transformer
from rasterio.errors import NotGeoreferencedWarning
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
from rasterio.vrt import WarpedVRT
from rasterio.warp import Resampling
from scipy.ndimage import distance_transform_edt

from .fuentes import VISOR
from .teselas import LADO, limites, teselas_que_cubren

SALIDA = VISOR / "relieve.pmtiles"
ZOOM_MIN, ZOOM_MAX = 7, 12
SIN_DATO = -32768


def terrarium(altitud: np.ndarray) -> np.ndarray:
    """Altitud en metros a RGB Terrarium (filas, columnas, 3)."""
    v = np.clip(altitud.astype(np.float64) + 32768.0, 0, 65535.996)
    r = np.floor(v / 256)
    g = np.floor(v) - r * 256
    b = np.floor((v - np.floor(v)) * 256)
    return np.stack([r, g, b], axis=-1).astype(np.uint8)


def rellenar(altitud: np.ndarray, vacio: np.ndarray) -> np.ndarray:
    """Cada píxel sin dato toma el valor del píxel válido más cercano."""
    if not vacio.any() or vacio.all():
        return np.where(vacio, 0, altitud)
    _, (filas, columnas) = distance_transform_edt(vacio, return_indices=True)
    return altitud[filas, columnas]


def png_rgb(rgb: np.ndarray) -> bytes:
    with MemoryFile() as mem, warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)  # un PNG no lleva georreferencia
        with mem.open(driver="PNG", width=LADO, height=LADO, count=3, dtype="uint8", zlevel=9) as d:
            d.write(np.moveaxis(rgb, -1, 0))
        return mem.read()


def construir(forzar: bool = False):
    if SALIDA.exists() and not forzar:
        return SALIDA
    from .sin_conexion import preparar_mdt
    mdt = preparar_mdt()
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    parcial = SALIDA.with_suffix(".parcial")
    escritas = 0
    with rasterio.open(mdt) as src:
        a3857 = Transformer.from_crs(src.crs, "EPSG:3857", always_xy=True).transform_bounds(*src.bounds)
        lonlat = Transformer.from_crs(src.crs, "EPSG:4326", always_xy=True).transform_bounds(*src.bounds)
        lista = sorted((zxy_to_tileid(z, x, y), z, x, y)
                       for z in range(ZOOM_MIN, ZOOM_MAX + 1) for x, y in teselas_que_cubren(a3857, z))
        with open(parcial, "wb") as f:
            w = Writer(f)
            for tid, z, x, y in lista:
                with WarpedVRT(src, crs="EPSG:3857", resampling=Resampling.bilinear, nodata=SIN_DATO,
                               transform=from_bounds(*limites(z, x, y), LADO, LADO), width=LADO, height=LADO) as vrt:
                    alt = vrt.read(1)
                vacio = alt == SIN_DATO
                if vacio.all():
                    continue
                w.write_tile(tid, png_rgb(terrarium(rellenar(alt, vacio))))
                escritas += 1
            w.finalize(
                {"tile_type": TileType.PNG, "tile_compression": Compression.NONE,
                 "min_zoom": ZOOM_MIN, "max_zoom": ZOOM_MAX,
                 "min_lon_e7": int(lonlat[0] * 1e7), "min_lat_e7": int(lonlat[1] * 1e7),
                 "max_lon_e7": int(lonlat[2] * 1e7), "max_lat_e7": int(lonlat[3] * 1e7),
                 "center_zoom": 9, "center_lon_e7": int(-3.7e7), "center_lat_e7": int(40.45e7)},
                {"name": "Relieve (Terrarium)", "attribution": "Instituto Geográfico Nacional, MDT 25 m"})
    parcial.replace(SALIDA)
    print(f"  {SALIDA.name}: {escritas} teselas")
    return SALIDA


if __name__ == "__main__":
    construir(forzar=True)
