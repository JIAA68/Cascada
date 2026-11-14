"""Modelos de combustible NFFL (Anderson, 1982) y humedad de escenario.

Parámetros de la tabla 1 de Anderson, H. E. (1982). *Aids to determining fuel models for
estimating fire behavior*. USDA Forest Service, General Technical Report INT-122 (dominio
público). El mapa europeo de combustibles de EFFIS usa los modelos 1 a 10; los modelos 11
a 13 (restos de corta) completan la tabla aunque no aparecen en Madrid.

Las cargas se dan en toneladas cortas por acre, como en la publicación, y se convierten a
lb/ft² porque las ecuaciones de Rothermel trabajan en unidades imperiales.
"""
from dataclasses import dataclass

T_AC_A_LB_FT2 = 2000 / 43560          # 1 tonelada corta por acre = 0,0459 lb/ft²
SAV_10H, SAV_100H = 109.0, 30.0        # relación superficie/volumen (1/ft) de las clases fijas


@dataclass(frozen=True)
class Modelo:
    numero: int
    nombre: str
    carga_1h: float       # t/ac
    carga_10h: float
    carga_100h: float
    carga_viva: float
    sav_1h: float         # 1/ft
    sav_viva: float
    profundidad: float    # ft
    humedad_extincion: float  # fracción, combustible muerto
    calor: float = 8000.0     # BTU/lb

    def cargas(self):
        """Cargas (1 h, 10 h, 100 h, viva) en lb/ft²."""
        return tuple(c * T_AC_A_LB_FT2 for c in (self.carga_1h, self.carga_10h, self.carga_100h, self.carga_viva))


MODELOS = {m.numero: m for m in (
    Modelo(1, "Pasto corto", 0.74, 0.00, 0.00, 0.00, 3500, 0, 1.0, 0.12),
    Modelo(2, "Pasto con arbolado o matorral", 2.00, 1.00, 0.50, 0.50, 3000, 1500, 1.0, 0.15),
    Modelo(3, "Pasto alto", 3.01, 0.00, 0.00, 0.00, 1500, 0, 2.5, 0.25),
    Modelo(4, "Matorral denso alto", 5.01, 4.01, 2.00, 5.01, 2000, 1500, 6.0, 0.20),
    Modelo(5, "Matorral bajo", 1.00, 0.50, 0.00, 2.00, 2000, 1500, 2.0, 0.20),
    Modelo(6, "Matorral seco y restos de frondosas", 1.50, 2.50, 2.00, 0.00, 1750, 0, 2.5, 0.25),
    Modelo(7, "Matorral con sotobosque", 1.13, 1.87, 1.50, 0.37, 1750, 1550, 2.5, 0.40),
    Modelo(8, "Hojarasca bajo bosque cerrado", 1.50, 1.00, 2.50, 0.00, 2000, 0, 0.2, 0.30),
    Modelo(9, "Hojarasca de frondosas", 2.92, 0.41, 0.15, 0.00, 2500, 0, 0.2, 0.25),
    Modelo(10, "Bosque con hojarasca y sotobosque", 3.01, 2.00, 5.01, 2.00, 2000, 1500, 1.0, 0.25),
    Modelo(11, "Restos de corta ligeros", 1.50, 4.51, 5.51, 0.00, 1500, 0, 1.0, 0.15),
    Modelo(12, "Restos de corta medios", 4.01, 14.03, 16.53, 0.00, 1500, 0, 2.3, 0.20),
    Modelo(13, "Restos de corta pesados", 7.01, 23.04, 28.05, 0.00, 1500, 0, 3.0, 0.25),
)}


@dataclass(frozen=True)
class Humedades:
    """Contenido de humedad del combustible, como fracción del peso seco."""
    m_1h: float
    m_10h: float
    m_100h: float
    m_viva: float


# Escenario fijo del demostrador: verano seco. Equivale al escenario D2L2 de
# BehavePlus (muertos 6/7/8 %, vivos 90 %).
VERANO = Humedades(m_1h=0.06, m_10h=0.07, m_100h=0.08, m_viva=0.90)


def humedad_equilibrio(temperatura_c: float, humedad_relativa: float) -> float:
    """Humedad de equilibrio del combustible muerto fino (%), de la temperatura (°C) y la humedad del aire (%).

    Ecuaciones de Simard (1968), las mismas que usa el índice de Fosberg de la prealerta (trabajan en °F).
    """
    t = temperatura_c * 9 / 5 + 32
    h = min(max(humedad_relativa, 0.0), 100.0)
    if h < 10:
        return 0.03229 + 0.281073 * h - 0.000578 * h * t
    if h < 50:
        return 2.22749 + 0.160107 * h - 0.01478 * t
    return 21.0606 + 0.005565 * h * h - 0.00035 * h * t - 0.483199 * h


HUMEDAD_FINA_MIN = 0.02   # el combustible muerto fino no baja en la práctica del 2 %
MESES_SECOS = (7, 8, 9)
VIVA_VERANO_SECO = 0.60   # escenario «muy seco» de BehavePlus para el combustible vivo


def humedad_viva(fecha) -> float:
    """Humedad del combustible vivo según el mes: 60 % de julio a septiembre, 90 % el resto."""
    return VIVA_VERANO_SECO if fecha.month in MESES_SECOS else VERANO.m_viva



def humedades_del_aire(temperatura_c: float, humedad_relativa: float) -> Humedades:
    """Humedades del combustible para una hora: la de equilibrio en el muerto fino (1 h),
    1 y 2 puntos más en el de 10 y 100 h, y el vivo fijo del escenario de verano (no hay dato que lo varíe)."""
    m1 = min(max(humedad_equilibrio(temperatura_c, humedad_relativa) / 100, HUMEDAD_FINA_MIN), 0.30)
    return Humedades(round(m1, 3), round(m1 + 0.01, 3), round(m1 + 0.02, 3), VERANO.m_viva)

# Factor de ajuste del viento a media llama respecto al viento a 6,1 m (20 ft), para
# combustibles sin cubierta arbórea (Albini y Baughman, 1979, INT-RP-221), tal como se
# reproducen habitualmente para los 13 modelos NFFL.
FACTOR_VIENTO = {1: 0.36, 2: 0.36, 3: 0.44, 4: 0.55, 5: 0.42, 6: 0.44, 7: 0.44,
                 8: 0.36, 9: 0.36, 10: 0.36, 11: 0.36, 12: 0.43, 13: 0.46}
