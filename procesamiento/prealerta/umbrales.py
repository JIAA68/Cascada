"""Umbrales y niveles de la prealerta.

- Umbrales del Plan Meteoalerta de AEMET (anexo 1, versión de 31-05-2022) para las tres zonas de aviso de la Comunidad
  de Madrid: temperatura máxima y mínima (°C), racha máxima (km/h), precipitación acumulada en 12 h y en 1 h (mm) y
  nieve acumulada en 24 h (cm). Cada umbral da los niveles amarillo, naranja y rojo.
- Niveles de la prealerta: 0 verde (sin aviso), 1 amarillo, 2 naranja, 3 rojo. Son los de Meteoalerta; los que
  calcula Cascada a partir de la previsión usan los mismos umbrales y se etiquetan con su origen.
- Peligro meteorológico de incendio: índice de Fosberg (1978) a partir de temperatura, humedad relativa y viento,
  con clases propias de Cascada (AEMET solo publica su predicción de riesgo como imagen).
- Tormenta y nieve prevista sin acumulación conocida: criterios propios, documentados en la metodología.
"""
import math

from ..incendio.combustibles import humedad_equilibrio

NIVELES = {0: "verde", 1: "amarillo", 2: "naranja", 3: "rojo"}

# Zonas de aviso de Meteoalerta en la Comunidad de Madrid: (amarillo, naranja, rojo)
ZONAS = {
    "722801": {"nombre": "Sierra de Madrid", "tmax": (34, 37, 40), "tmin": (-6, -10, -14), "racha": (80, 100, 140),
               "pr12": (40, 80, 120), "pr1": (15, 30, 60), "nieve24": (5, 20, 40)},
    "722802": {"nombre": "Metropolitana y Henares", "tmax": (36, 39, 42), "tmin": (-4, -8, -12), "racha": (70, 90, 130),
               "pr12": (40, 80, 120), "pr1": (15, 30, 60), "nieve24": (2, 5, 20)},
    "722803": {"nombre": "Sur, Vegas y Oeste", "tmax": (36, 39, 42), "tmin": (-4, -8, -12), "racha": (70, 90, 130),
               "pr12": (40, 80, 120), "pr1": (15, 30, 60), "nieve24": (2, 5, 20)},
}

# Fenómenos de la prealerta. "umbral": clave de ZONAS con la que se calcula el nivel desde la previsión;
# "oficial": solo entra por aviso de AEMET; "incendio": índice de Fosberg.
FENOMENOS = {
    "AT": {"nombre": "Temperaturas máximas", "umbral": "tmax", "capa": "1_1"},
    "BT": {"nombre": "Temperaturas mínimas", "umbral": "tmin", "capa": "1_2"},
    "VI": {"nombre": "Vientos", "umbral": "racha", "capa": "1_3"},
    "PR": {"nombre": "Lluvias", "umbral": "pr1_pr12", "capa": "1_5"},
    "NE": {"nombre": "Nevadas", "umbral": "nieve24", "capa": "1_6"},
    "TO": {"nombre": "Tormentas", "umbral": "tormenta", "capa": "1_7"},
    "NI": {"nombre": "Nieblas", "umbral": "oficial", "capa": "1_8"},
    "PO": {"nombre": "Polvo en suspensión", "umbral": "oficial", "capa": "1_11"},
    "GR": {"nombre": "Granizo", "umbral": "oficial", "capa": "1_13"},
    "IF": {"nombre": "Peligro meteorológico de incendio", "umbral": "fosberg", "capa": "3_1"},
}
# Otros códigos que AEMET usa en sus avisos y que no son fenómenos de la prealerta de Madrid
OTROS_CODIGOS = {"CO": "Fenómenos costeros", "DP": "Deshielos", "DH": "Deshielos", "AV": "Aludes", "AL": "Aludes",
                 "RI": "Rissaga", "OL": "Olas", "VS": "Viento en superficie (mar)", "GA": "Galerna"}

# Activación de peligros basales: capa del catálogo -> fenómenos que la activan.
# Un activo queda activado si el fenómeno alcanza al menos el nivel amarillo en su municipio y su nivel de
# peligrosidad en la capa es moderado (3) o superior.
ACTIVACION = {
    "3_1": ("VI", "IF"),        # incendios forestales: viento fuerte o peligro meteorológico de incendio
    "2_1": ("PR", "TO"),        # avenidas y crecidas: lluvias fuertes o persistentes y tormentas
    "2_2": ("PR", "TO"),        # torrencialidad en cauces
    "6_16": ("NE",),            # transporte por carretera: nevadas
    "6_27": ("VI",),            # derrumbes y colapso de edificaciones: viento fuerte
}
NIVEL_ACTIVACION = 3

# Efecto directo sobre las personas: fenómeno -> subtipos de activo afectados.
# Los centros sensibles solo se cuentan.
DIRECTO = {
    "AT": ("residencial", "de_dia", "infantil", "educacion_especial", "hospital", "dialisis"),
    "BT": ("residencial", "de_dia"),
    "NE": ("residencial", "de_dia"),
}
DIRECTO_SENSIBLES = ("BT", "NE")   # fenómenos en los que los centros sensibles se cuentan como afectados

# Clases del índice de Fosberg (propias de Cascada) y el nivel de prealerta que se les asigna
CLASES_FOSBERG = ((15, "bajo", 0), (30, "moderado", 0), (50, "alto", 1), (70, "muy alto", 2), (math.inf, "extremo", 3))
# Tormenta: probabilidad horaria de tormenta (AEMET) a partir de la cual se asigna cada nivel
TORMENTA_PROB = (40, 70, 101)
# Códigos de estado del cielo de AEMET que indican tormenta (5x y 6x) y nieve (3x y 7x)
CIELO_TORMENTA = {"51", "52", "53", "54", "61", "62", "63", "64"}
CIELO_NIEVE = {"33", "34", "35", "36", "71", "72", "73", "74"}


def nivel(valor, umbrales, hacia_abajo=False) -> int:
    """Nivel 0 a 3 de un valor frente a (amarillo, naranja, rojo); hacia_abajo para las temperaturas mínimas."""
    if valor is None:
        return 0
    n = 0
    for i, u in enumerate(umbrales, start=1):
        if (valor <= u) if hacia_abajo else (valor >= u):
            n = i
    return n


def fosberg(temperatura_c: float, humedad: float, viento_kmh: float) -> float:
    """Índice de Fosberg (Fosberg, 1978): humedad de equilibrio del combustible fino y viento.

    Entradas en °C, % y km/h; el índice es adimensional (0 a unos 100)."""
    u = viento_kmh / 1.609344
    m = min(max(humedad_equilibrio(temperatura_c, humedad), 0.0), 30.0)
    eta = 1 - 2 * (m / 30) + 1.5 * (m / 30) ** 2 - 0.5 * (m / 30) ** 3
    return round(eta * math.sqrt(1 + u * u) / 0.3002, 1)


def clase_fosberg(indice: float) -> tuple[str, int]:
    """(clase, nivel de prealerta) del índice de Fosberg."""
    for limite, clase, n in CLASES_FOSBERG:
        if indice < limite:
            return clase, n
    return CLASES_FOSBERG[-1][1], CLASES_FOSBERG[-1][2]


def nivel_tormenta(probabilidad) -> int:
    return nivel(probabilidad, TORMENTA_PROB)


def nombre_fenomeno(codigo: str, texto: str = "") -> str:
    if codigo in FENOMENOS:
        return FENOMENOS[codigo]["nombre"]
    return OTROS_CODIGOS.get(codigo) or texto or codigo
