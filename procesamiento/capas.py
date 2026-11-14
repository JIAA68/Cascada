"""Capas de peligrosidad del Catálogo de Riesgos Potenciales y matriz de riesgo.

Los GeoTIFF del catálogo (5 m, EPSG:25830, rejilla común a todas las capas) se extraen
del zip a datos/cache/catalogo_tif/ porque leer por ventanas dentro del zip es muy lento.
Valores: 0 sin peligro, 1 a 5 niveles de muy baja a muy alta, 255 fuera de la Comunidad.
"""
import zipfile
from pathlib import Path

from .fuentes import CACHE, capa_catalogo

# Las 13 capas del análisis basal: código -> (nombre, grupo)
CAPAS = {
    "3_1": ("Incendios forestales", "Naturales"),
    "2_1": ("Avenidas y crecidas", "Naturales"),
    "2_3": ("Rotura de presas", "Naturales"),
    "6_27": ("Derrumbes y colapso de edificaciones", "Naturales"),
    "5_4": ("Subsidencias", "Naturales"),
    "6_3": ("Nube tóxica", "Tecnológicos"),
    "6_4": ("Sobrepresión por explosión", "Tecnológicos"),
    "6_11": ("Centrales energéticas", "Tecnológicos"),
    "6_12": ("Transporte de energía", "Tecnológicos"),
    "6_16": ("Transporte por carretera", "Tecnológicos"),
    "6_15": ("Transporte por tren", "Tecnológicos"),
    "6_14": ("Transporte por avión", "Tecnológicos"),
    "6_6": ("Actividades extractivas", "Tecnológicos"),
}
# Capa adicional del efecto cascada (radiación térmica de instalaciones Seveso)
CAPA_RADIACION = "6_5"
# Capas combinadas por grupo (decisión del 09-11-2026): nivel máximo de las capas del grupo en cada píxel, sin el
# fondo de incendios y avión. Es lo que se muestra al marcar un grupo entero, en vez de superponer sus capas.
# código -> (nombre, grupo de CAPAS que combina)
COMBINADAS = {
    "naturales": ("Peligrosidad natural máxima", "Naturales"),
    "tecnologicos": ("Peligrosidad tecnológica máxima", "Tecnológicos"),
}
# Las 13 capas de peligrosidad por fenómenos meteorológicos adversos: referencia de la prealerta
# (propensión climática de cada punto, que la previsión activa). Se muestrean y se teselan hasta el zoom 11.
CAPAS_METEO = {
    "1_1": "Temperaturas máximas", "1_2": "Temperaturas mínimas", "1_3": "Vientos fuertes",
    "1_4": "Lluvias persistentes (12 h)", "1_5": "Lluvias fuertes (1 h)", "1_6": "Nevadas",
    "1_7": "Tormentas", "1_8": "Niebla", "1_9": "Ola de calor", "1_10": "Ola de frío",
    "1_11": "Polvo en suspensión", "1_12": "Sequías (consumo humano)", "1_13": "Granizo",
}
# Capa basal que la prealerta activa y que no está en el análisis basal (se muestrea en los activos)
CAPAS_ACTIVACION_EXTRA = {"2_2": "Torrencialidad en cauces"}
ZOOM_MAX_METEO = 11
# Capas cuyo nivel 1 cubre todo el territorio como fondo: no cuenta en el porcentaje de celda
CON_FONDO = {"3_1", "6_14"}
# Capas lineales (vías, carreteras, conducciones), que hay que engrosar en las teselas
LINEALES = {"6_15", "6_16", "6_12"}
# Capas de superficie: al alejarse se pinta el nivel más frecuente, no el máximo
SUPERFICIE = {"3_1", "5_4", "6_14"}
# Capas de elementos pequeños, que se engrosan al alejarse para que no desaparezcan
PEQUENAS = {"6_4", "6_11", "6_6"}
# Capas muy fragmentadas, en las que el borde de cada zona se convierte en un punteado oscuro
SIN_BORDE = {"3_1", "6_27"}

NIVELES = {0: "nula", 1: "muy baja", 2: "baja", 3: "moderada", 4: "alta", 5: "muy alta"}
RIESGOS = {0: "sin riesgo", 1: "muy bajo", 2: "bajo", 3: "moderado", 4: "alto", 5: "muy alto"}
SIN_DATO = 255

# Matriz peligrosidad × vulnerabilidad de la memoria metodológica del catálogo (apartado 3,
# "Cartografías de riesgo"): MATRIZ[vulnerabilidad - 1][peligrosidad - 1] = riesgo
MATRIZ = (
    (1, 1, 2, 2, 3),  # vulnerabilidad muy baja
    (1, 2, 3, 3, 3),  # baja
    (2, 3, 3, 4, 4),  # moderada
    (2, 3, 4, 4, 5),  # alta
    (3, 4, 4, 5, 5),  # muy alta
)


def nombre_capa(codigo: str) -> str:
    """Nombre de cualquier capa conocida (basal, combinada, meteorológica o de activación)."""
    if codigo in CAPAS:
        return CAPAS[codigo][0]
    if codigo in COMBINADAS:
        return COMBINADAS[codigo][0]
    return CAPAS_METEO.get(codigo) or CAPAS_ACTIVACION_EXTRA.get(codigo) or codigo


def capas_del_grupo(grupo: str) -> list[str]:
    """Códigos de las capas basales de un grupo ("Naturales" o "Tecnológicos")."""
    return [c for c, (_, g) in CAPAS.items() if g == grupo]


def riesgo(peligrosidad: int, vulnerabilidad: int) -> int:
    """Nivel de riesgo de 1 a 5, o 0 si no hay peligro."""
    if peligrosidad <= 0 or vulnerabilidad <= 0:
        return 0
    return MATRIZ[min(vulnerabilidad, 5) - 1][min(peligrosidad, 5) - 1]


def tif(codigo: str) -> Path:
    """GeoTIFF de una capa: extraído del zip del catálogo (descargándolo si hace falta) o, para las combinadas,
    construido a partir de las capas de su grupo."""
    if codigo in COMBINADAS:
        destino = CACHE / "catalogo_tif" / f"combinada_{codigo}.tif"
        if not destino.exists():
            from .combinadas import construir
            construir(codigo)
        return destino
    destino = CACHE / "catalogo_tif" / f"peligrosid_{codigo}.tif"
    if not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(capa_catalogo(codigo)) as z, z.open(f"peligrosid_{codigo}.tif") as origen:
            parcial = destino.with_name(destino.name + ".parcial")
            with open(parcial, "wb") as f:
                while bloque := origen.read(1 << 22):
                    f.write(bloque)
            parcial.replace(destino)
    return destino
