"""Velocidad de propagación de un incendio de superficie (Rothermel, 1972).

Implementación propia de Cascada a partir de las publicaciones:

- Rothermel, R. C. (1972). *A mathematical model for predicting fire spread in wildland
  fuels*. USDA Forest Service, Research Paper INT-115.
- Albini, F. A. (1976). *Estimating wildfire behavior and effects*. USDA Forest Service,
  General Technical Report INT-30 (correcciones y forma con varias clases de combustible).
- Anderson, H. E. (1983). *Predicting wind-driven wild land fire size and shape*. USDA Forest
  Service, Research Paper INT-305 (relación longitud/anchura de la elipse).

Las ecuaciones trabajan en unidades imperiales (ft, lb, BTU, min), como en las publicaciones.
Las funciones públicas reciben y devuelven unidades métricas (km/h, m/min).
"""
import math
from dataclasses import dataclass

import numpy as np

from .combustibles import SAV_10H, SAV_100H, Humedades, Modelo

DENSIDAD_PARTICULA = 32.0     # lb/ft³
MINERAL_TOTAL = 0.0555
MINERAL_EFECTIVO = 0.010
FT_MIN_A_M_MIN = 0.3048
KMH_A_FT_MIN = 1000 / 0.3048 / 60
FT_MIN_A_M_S = 0.3048 / 60


@dataclass(frozen=True)
class Lecho:
    """Propiedades del lecho de combustible que no dependen del viento ni de la pendiente."""
    r0: float                  # ft/min, velocidad sin viento ni pendiente
    intensidad_reaccion: float  # BTU/ft²/min
    compacidad: float          # beta
    relativa: float            # beta / beta óptima
    c: float                   # coeficientes del factor de viento
    b: float
    e: float


def _amortiguamiento(humedad, extincion):
    r = min(humedad / extincion, 1.0) if extincion > 0 else 1.0
    return max(0.0, 1 - 2.59 * r + 5.11 * r ** 2 - 3.52 * r ** 3)


def lecho(modelo: Modelo, humedades: Humedades) -> Lecho:
    """Propiedades del lecho (Rothermel, 1972, con la ponderación por clases de Albini, 1976)."""
    w1, w10, w100, wv = modelo.cargas()
    muertos = [(w, s, m) for w, s, m in ((w1, modelo.sav_1h, humedades.m_1h), (w10, SAV_10H, humedades.m_10h),
                                          (w100, SAV_100H, humedades.m_100h)) if w > 0]
    vivos = [(wv, modelo.sav_viva, humedades.m_viva)] if wv > 0 else []

    def areas(clases):
        return [s * w / DENSIDAD_PARTICULA for w, s, _ in clases]

    a_total = sum(areas(muertos)) + sum(areas(vivos))
    categorias = []
    for clases in (muertos, vivos):
        if not clases:
            continue
        a = areas(clases)
        f = [x / sum(a) for x in a]
        categorias.append({
            "f": f, "clases": clases, "f_cat": sum(a) / a_total,
            "sav": sum(fi * s for fi, (_, s, _) in zip(f, clases)),
            "carga_neta": sum(fi * w * (1 - MINERAL_TOTAL) for fi, (w, _, _) in zip(f, clases)),
            "humedad": sum(fi * m for fi, (_, _, m) in zip(f, clases)),
        })
    sav = sum(c["f_cat"] * c["sav"] for c in categorias)

    # Humedad de extinción de los vivos (Albini, 1976)
    extinciones = [modelo.humedad_extincion]
    if vivos:
        fino_m = [(w * math.exp(-138 / s), m) for w, s, m in muertos]
        fino_v = sum(w * math.exp(-500 / s) for w, s, _ in vivos)
        w_rel = sum(x for x, _ in fino_m) / fino_v
        humedad_fina = sum(x * m for x, m in fino_m) / sum(x for x, _ in fino_m)
        extinciones.append(max(2.9 * w_rel * (1 - humedad_fina / modelo.humedad_extincion) - 0.226,
                               modelo.humedad_extincion))

    carga_total = sum(w for w, _, _ in muertos + vivos)
    densidad_aparente = carga_total / modelo.profundidad
    compacidad = densidad_aparente / DENSIDAD_PARTICULA
    relativa = compacidad / (3.348 * sav ** -0.8189)

    gamma_max = sav ** 1.5 / (495 + 0.0594 * sav ** 1.5)
    a = 133 * sav ** -0.7913
    gamma = gamma_max * relativa ** a * math.exp(a * (1 - relativa))
    eta_s = 0.174 * MINERAL_EFECTIVO ** -0.19
    intensidad = gamma * sum(c["carga_neta"] * modelo.calor * eta_s * _amortiguamiento(c["humedad"], mx)
                             for c, mx in zip(categorias, extinciones))
    flujo = math.exp((0.792 + 0.681 * sav ** 0.5) * (compacidad + 0.1)) / (192 + 0.2595 * sav)
    sumidero = densidad_aparente * sum(
        c["f_cat"] * sum(fi * math.exp(-138 / s) * (250 + 1116 * m) for fi, (_, s, m) in zip(c["f"], c["clases"]))
        for c in categorias)
    r0 = intensidad * flujo / sumidero if sumidero > 0 else 0.0
    return Lecho(r0=r0, intensidad_reaccion=intensidad, compacidad=compacidad, relativa=relativa,
                 c=7.47 * math.exp(-0.133 * sav ** 0.55), b=0.02526 * sav ** 0.54,
                 e=0.715 * math.exp(-3.59e-4 * sav))


def factor_viento(k: Lecho, viento_media_llama_kmh: float) -> float:
    """Factor de viento de Rothermel (adimensional).

    Sin el límite de viento efectivo de Rothermel (U ≤ 0,9·I_R; decisión del 10-11-2026): Andrews, Cruz y Rothermel
    (2013, International Journal of Wildland Fire 22, 959-969) lo consideran demasiado restrictivo, y BehavePlus y
    FlamMap ya no lo aplican por defecto. Con él, el pasto apenas acelera con vientos fuertes.
    """
    u = viento_media_llama_kmh * KMH_A_FT_MIN
    return k.c * u ** k.b * k.relativa ** -k.e if u > 0 else 0.0


def excentricidad(k: Lecho, phi):
    """Excentricidad de la elipse de propagación a partir del factor combinado viento + pendiente.

    Convierte phi en el viento efectivo equivalente (m/s) y aplica la relación
    longitud/anchura de Anderson (1983) con sus coeficientes para m/s (los de FARSITE; en mi/h
    serían 0,1147 y 0,0692), limitada a 8: 1,59 con 5 mi/h. Admite escalares y arrays.
    """
    phi = np.asarray(phi, dtype=float)
    u_ms = np.where(phi > 0, (np.maximum(phi, 1e-12) * k.relativa ** k.e / k.c) ** (1 / k.b), 0.0) * FT_MIN_A_M_S
    lb = np.clip(0.936 * np.exp(0.2566 * u_ms) + 0.461 * np.exp(-0.1548 * u_ms) - 0.397, 1.0, 8.0)
    e = np.sqrt(lb ** 2 - 1) / lb
    return float(e) if e.ndim == 0 else e


def elipse(k: Lecho, viento_media_llama_kmh: float, viento_hacia: float, pendiente, subida):
    """Velocidad máxima (m/min), dirección (grados, 0 = norte) y excentricidad.

    viento_hacia: dirección hacia la que sopla el viento (grados). pendiente: tangente.
    subida: dirección de máxima subida (grados). Viento y pendiente se suman como vectores.
    """
    pendiente, subida = np.asarray(pendiente, dtype=float), np.radians(subida)
    hacia = math.radians(viento_hacia)
    phi_w = factor_viento(k, viento_media_llama_kmh)
    phi_s = 5.275 * k.compacidad ** -0.3 * pendiente ** 2
    vx = phi_w * math.sin(hacia) + phi_s * np.sin(subida)
    vy = phi_w * math.cos(hacia) + phi_s * np.cos(subida)
    phi = np.hypot(vx, vy)
    return k.r0 * (1 + phi) * FT_MIN_A_M_MIN, np.degrees(np.arctan2(vx, vy)) % 360, excentricidad(k, phi)


def velocidad_en(vel_max, direccion_max, exc, direccion):
    """Velocidad de avance en una dirección, con la ignición en el foco de la elipse."""
    cos = np.cos(np.radians(direccion - direccion_max))
    return vel_max * (1 - exc) / (1 - exc * cos)
