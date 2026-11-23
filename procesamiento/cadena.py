"""Cadena de datos completa en un solo comando.

Descarga las fuentes oficiales que falten (con registro de trazabilidad), rasteriza a 25 m el mapa de
combustibles de la Comunidad (la primera vez, unos 25 minutos de descarga), construye los
activos, el análisis basal (rejilla de 1 km y riesgos de cada activo), las teselas de las
13 capas de peligrosidad y de las dos combinadas por grupo, los núcleos urbanos del mapa base
para escalas pequeñas y la base de la prealerta (municipios, zonas de aviso de AEMET, capas meteorológicas de cada activo y
sus teselas hasta el zoom 11), y la validación del modelo de incendio con el caso de Tres Cantos
(2025). Todo lo que ya está en disco se reutiliza. La validación necesita la clave de AEMET (la racha del día del
incendio): sin ella, la cadena avisa y termina igual; el resto no la necesita.

Uso: python -m procesamiento.cadena [--sin-teselas] [--zoom-max 15]
"""
import argparse
import time

from . import basal, cercanias, combinadas, conducciones, nucleos, poblaciones, red_transporte, relieve, teselas
from .capas import CAPAS, CAPAS_ACTIVACION_EXTRA, CAPAS_METEO, COMBINADAS, ZOOM_MAX_METEO, tif
from .fuentes import fuente
from .incendio import combustible_cm, validacion
from .prealerta import meteo_basal, territorio


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sin-teselas", action="store_true", help="no regenerar las teselas PMTiles")
    p.add_argument("--zoom-max", type=int, default=15)
    a = p.parse_args(argv)
    inicio = time.time()

    print("1. Fuentes oficiales")
    for clave in ("centros_educativos", "centros_sanitarios", "atencion_social", "poblacion_rejilla", "municipios"):
        print(f"  {clave}: {fuente(clave).name}")
    print(f"  mapa de combustibles de la Comunidad (25 m): {combustible_cm.construir().name}")
    print(f"  carreteras y vías de tren de la BTA: {red_transporte.construir().name}")
    print(f"  horario de Cercanías de Renfe: {cercanias.construir().name}")
    for codigo in [*CAPAS, *CAPAS_METEO, *CAPAS_ACTIVACION_EXTRA]:
        print(f"  capa {codigo}: {tif(codigo).name}")
    print(f"  eje de las conducciones de hidrocarburos (capa 6_12): {conducciones.construir().name}")

    print("2. Activos y análisis basal")
    basal.construir()

    if not a.sin_teselas:
        print("3. Teselas de las capas de peligrosidad")
        teselas.main(["--zoom-max", str(a.zoom_max)])
        print(f"  relieve para la vista en 3D (MDT 25 m del IGN): {relieve.construir().name}")

    print("4. Capas combinadas por grupo (nivel máximo de las naturales y de las tecnológicas)")
    for grupo in COMBINADAS:
        combinadas.construir(grupo)
    if not a.sin_teselas:
        teselas.main(["--zoom-max", str(a.zoom_max), "--capas", *COMBINADAS])

    print("5. Núcleos urbanos del mapa base para escalas pequeñas")
    nucleos.construir()
    print(f"  núcleos de población del nomenclátor del IGN (avisos de la crisis): {poblaciones.construir().name}")

    print("6. Prealerta: municipios, zonas de aviso de AEMET y capas meteorológicas de cada activo")
    territorio.construir()
    meteo_basal.construir()
    if not a.sin_teselas:
        print("7. Teselas de las capas meteorológicas (hasta el zoom 11)")
        teselas.main(["--zoom-max", str(min(a.zoom_max, ZOOM_MAX_METEO)), "--capas", *CAPAS_METEO])

    print("8. Validación del modelo de incendio (Tres Cantos, 11-08-2025)")
    if validacion.SALIDA.exists():
        print("  ya calculada")
    elif validacion.PUNTO_IGNICION is None:
        print("  pendiente: falta fijar el punto de ignición (procesamiento/incendio/validacion.py)")
    else:
        try:
            validacion.ejecutar(*validacion.PUNTO_IGNICION)
            print(f"  {validacion.SALIDA.name}")
        except RuntimeError as e:   # sin clave de AEMET o AEMET sin servicio: paso opcional
            print(f"  omitida: {e}")
    print(f"Cadena completa en {(time.time() - inicio) / 60:.1f} min")


if __name__ == "__main__":
    main()
