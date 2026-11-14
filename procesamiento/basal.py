"""Análisis basal precalculado: rejilla de 1 km y riesgos de cada activo.

Una sola pasada por bloques de filas sobre las 13 capas de peligrosidad (5 m, rejilla
común en EPSG:25830) produce:

- datos/procesados/rejilla_1km.csv: para cada celda de la rejilla europea de 1 km y cada
  capa, el nivel máximo y el porcentaje de la celda (de su parte dentro de la Comunidad)
  con peligro. En incendios forestales y avión el nivel 1 es fondo y no cuenta. Lleva la
  población del Censo 2021 y el recuento de activos de la celda.
- datos/procesados/activos_basal.csv: nivel de cada capa en el punto de cada activo y
  riesgo con la matriz del catálogo (el fondo de incendios y avión no da riesgo). Incluye
  los centros sensibles: no se publica.
- datos/visor/activos.geojson: activos no sensibles para el mapa.

Uso: python -m procesamiento.basal
"""
import json

import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window

from .activos import escribir as escribir_activos
from .capas import CAPAS, CON_FONDO, SIN_DATO, riesgo, tif
from .fuentes import PROCESADOS, VISOR
from .rejilla import A3035, celda_de_utm, id_celda, poblacion

FILAS_BLOQUE = 512
PIXELES_CELDA = 200 * 200  # píxeles de 5 m en 1 km²


class Acumulador:
    """Recuento de píxeles por celda de 1 km, capa y nivel, que crece según aparecen celdas."""

    def __init__(self, n_capas):
        self.indice: dict[int, int] = {}
        self.n_capas = n_capas
        self.conteo = np.zeros((1024, n_capas, 6), np.int64)
        self.dentro = np.zeros(1024, np.int64)

    def _asegurar(self, n):
        while n > len(self.dentro):
            self.conteo = np.concatenate([self.conteo, np.zeros_like(self.conteo)])
            self.dentro = np.concatenate([self.dentro, np.zeros_like(self.dentro)])

    def sumar(self, claves: np.ndarray, niveles: np.ndarray):
        """claves: clave de celda por píxel; niveles: (n_capas, n_píxeles) con 0 a 5."""
        unicas, inversa = np.unique(claves, return_inverse=True)
        idx = np.fromiter((self.indice.setdefault(int(k), len(self.indice)) for k in unicas), np.int64, len(unicas))
        n = len(self.indice)
        self._asegurar(n)
        g = idx[inversa]
        self.dentro[:n] += np.bincount(g, minlength=n)
        for j in range(self.n_capas):
            self.conteo[:n, j] += np.bincount(g * 6 + niveles[j], minlength=n * 6).reshape(n, 6)


def clave_celda(e_km, n_km):
    return (n_km.astype(np.int64) << 20) | e_km.astype(np.int64)


def construir():
    codigos = list(CAPAS)
    activos = escribir_activos()
    fuentes = [rasterio.open(tif(c)) for c in codigos]
    ref = fuentes[0]
    t = ref.transform
    alto, ancho = ref.height, ref.width

    # Píxel de cada activo
    fila_a = np.floor((activos["y"].to_numpy() - t.f) / t.e).astype(np.int64)
    col_a = np.floor((activos["x"].to_numpy() - t.c) / t.a).astype(np.int64)
    niveles_activos = np.zeros((len(activos), len(codigos)), np.uint8)

    acumulador = Acumulador(len(codigos))
    xs = t.c + (np.arange(ancho) + 0.5) * t.a
    for f0 in range(0, alto, FILAS_BLOQUE):
        nf = min(FILAS_BLOQUE, alto - f0)
        bloque = np.stack([s.read(1, window=Window(0, f0, ancho, nf)) for s in fuentes])
        en_bloque = (fila_a >= f0) & (fila_a < f0 + nf) & (col_a >= 0) & (col_a < ancho)
        if en_bloque.any():
            v = bloque[:, fila_a[en_bloque] - f0, col_a[en_bloque]].T
            niveles_activos[en_bloque] = np.where(v == SIN_DATO, 0, v)
        dentro = bloque[0] != SIN_DATO
        if not dentro.any():
            continue
        ys = t.f + (np.arange(f0, f0 + nf) + 0.5) * t.e
        X, Y = np.meshgrid(xs, ys)
        e_km, n_km = celda_de_utm(X[dentro], Y[dentro])
        acumulador.sumar(clave_celda(e_km, n_km), np.minimum(bloque[:, dentro], 5).astype(np.int64))
        print(f"  filas {f0 + nf}/{alto}", flush=True)
    for s in fuentes:
        s.close()

    # Activos: niveles, riesgo y celda
    for j, c in enumerate(codigos):
        activos[f"n_{c}"] = niveles_activos[:, j]
        # El nivel 1 de fondo de incendios y avión no da riesgo (decisión del 13-11-2026)
        fondo = 1 if c in CON_FONDO else 0
        activos[f"r_{c}"] = [0 if p <= fondo else riesgo(int(p), int(v))
                             for p, v in zip(niveles_activos[:, j], activos["vulnerabilidad_nivel"])]
    activos["riesgo_max"] = activos[[f"r_{c}" for c in codigos]].max(axis=1)
    activos["n_amenazas"] = sum((activos[f"n_{c}"] > (1 if c in CON_FONDO else 0)).astype(int) for c in codigos)
    e_km, n_km = celda_de_utm(activos["x"].to_numpy(), activos["y"].to_numpy())
    activos["grd_id"] = [id_celda(int(e), int(n)) for e, n in zip(e_km, n_km)]

    # Rejilla
    filas = []
    for clave, i in acumulador.indice.items():
        n_km, e_km = clave >> 20, clave & ((1 << 20) - 1)
        total = int(acumulador.dentro[i])
        r = {"grd_id": id_celda(e_km, n_km), "e_km": e_km, "n_km": n_km,
             "fraccion_comunidad": round(total / PIXELES_CELDA, 3)}
        for j, c in enumerate(codigos):
            cuenta = acumulador.conteo[i, j]
            con_peligro = cuenta[2:].sum() if c in CON_FONDO else cuenta[1:].sum()
            presentes = np.flatnonzero(cuenta[1:]) + 1
            r[f"max_{c}"] = int(presentes.max()) if presentes.size else 0
            r[f"pct_{c}"] = round(100 * con_peligro / total, 1)
        filas.append(r)
    rejilla = pd.DataFrame(filas).merge(poblacion(), on="grd_id", how="left")
    for c in ("poblacion", "menores_16", "mayores_64"):
        rejilla[c] = rejilla[c].fillna(0).astype(int)
    por_celda = activos.groupby("grd_id").agg(activos_n=("id", "size"), sensibles_n=("sensible", "sum"),
                                              sensibles_plazas=("plazas", lambda s: s[activos.loc[s.index, "sensible"]].fillna(0).sum()))
    rejilla = rejilla.merge(por_celda, on="grd_id", how="left")
    for c in ("activos_n", "sensibles_n", "sensibles_plazas"):
        rejilla[c] = rejilla[c].fillna(0).astype(int)

    PROCESADOS.mkdir(parents=True, exist_ok=True)
    rejilla.to_csv(PROCESADOS / "rejilla_1km.csv", index=False, encoding="utf-8")
    activos.to_csv(PROCESADOS / "activos_basal.csv", index=False, encoding="utf-8")
    escribir_geojson(activos[~activos["sensible"]])
    print(f"  celdas: {len(rejilla)}; población: {rejilla['poblacion'].sum()}; activos: {len(activos)}"
          f" (en el mapa: {int((~activos['sensible']).sum())})")
    return rejilla, activos


def escribir_geojson(visibles: pd.DataFrame):
    """Activos no sensibles para el mapa, sin datos personales."""
    rasgos = [{"type": "Feature",
               "geometry": {"type": "Point", "coordinates": [round(a.lon, 6), round(a.lat, 6)]},
               "properties": {"id": a.id, "familia": a.familia, "subtipo": a.subtipo, "tipo": a.tipo, "nombre": a.nombre,
                              "municipio": a.municipio, "vulnerabilidad": a.vulnerabilidad,
                              "riesgo_max": int(a.riesgo_max), "n_amenazas": int(a.n_amenazas)}}
              for a in visibles.itertuples()]
    VISOR.mkdir(parents=True, exist_ok=True)
    (VISOR / "activos.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": rasgos}, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    construir()
