"""Capas combinadas por grupo: el nivel máximo de las capas naturales, y el de las tecnológicas, en cada píxel.

Al marcar un grupo entero en el visor no se superponen sus capas (con una sola paleta, el color sería el de la
capa dibujada encima y no se entendería nada), sino que se muestra una capa única con el nivel máximo del grupo
en cada punto. El nivel 1 de fondo de incendios forestales y avión, que cubre todo el
territorio, no cuenta. Es una vista de conjunto para localizar dónde hay algún peligro del grupo y de qué nivel,
no un índice: el nivel de cada capa mide cosas distintas (docs/metodologia.md, apartado 2.1).

Salida: datos/cache/catalogo_tif/combinada_<grupo>.tif, en la misma rejilla de 5 m del catálogo (GeoTIFF
teselado y comprimido). De ahí salen sus teselas, como para cualquier otra capa (procesamiento/teselas.py).

Uso: python -m procesamiento.combinadas
"""
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

from .capas import COMBINADAS, CON_FONDO, SIN_DATO, capas_del_grupo, tif
from .fuentes import CACHE

FILAS_BLOQUE = 512


def combinar(bloques: dict[str, np.ndarray]) -> np.ndarray:
    """Nivel máximo de varias capas (código -> bloque de niveles), sin el fondo de las capas que lo tienen;
    255 solo donde todas las capas son 255 (fuera de la Comunidad)."""
    maximo, fuera = None, None
    for codigo, b in bloques.items():
        sin_dato = b == SIN_DATO
        v = np.where(sin_dato, 0, b)
        if codigo in CON_FONDO:
            v = np.where(v == 1, 0, v)
        maximo = v if maximo is None else np.maximum(maximo, v)
        fuera = sin_dato if fuera is None else (fuera & sin_dato)
    salida = maximo.astype(np.uint8)
    salida[fuera] = SIN_DATO
    return salida


def ruta(grupo: str) -> Path:
    return CACHE / "catalogo_tif" / f"combinada_{grupo}.tif"


def construir(grupo: str) -> Path:
    """Construye la capa combinada de un grupo ("naturales" o "tecnologicos") por bloques de filas."""
    codigos = capas_del_grupo(COMBINADAS[grupo][1])
    destino = ruta(grupo)
    destino.parent.mkdir(parents=True, exist_ok=True)
    fuentes = [rasterio.open(tif(c)) for c in codigos]
    ref = fuentes[0]
    perfil = {"driver": "GTiff", "width": ref.width, "height": ref.height, "count": 1, "dtype": "uint8",
              "crs": ref.crs, "transform": ref.transform, "nodata": SIN_DATO,
              "tiled": True, "blockxsize": 256, "blockysize": 256, "compress": "lzw"}
    parcial = destino.with_name(destino.name + ".parcial")
    inicio = time.time()
    with rasterio.open(parcial, "w", **perfil) as dst:
        for f0 in range(0, ref.height, FILAS_BLOQUE):
            nf = min(FILAS_BLOQUE, ref.height - f0)
            ventana = Window(0, f0, ref.width, nf)
            dst.write(combinar({c: s.read(1, window=ventana) for c, s in zip(codigos, fuentes)}), 1, window=ventana)
    for s in fuentes:
        s.close()
    parcial.replace(destino)
    print(f"  {grupo}: {len(codigos)} capas combinadas en {time.time() - inicio:.0f} s ({destino.stat().st_size / 1e6:.0f} MB)", flush=True)
    return destino


def main():
    for grupo in COMBINADAS:
        construir(grupo)


if __name__ == "__main__":
    main()
