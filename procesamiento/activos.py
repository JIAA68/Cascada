"""Activos: centros donde se concentra población con menor capacidad de autoprotección.

Lee los tres conjuntos del portal de datos de la Comunidad de Madrid (educativos,
sanitarios y de atención social), aplica el filtrado acordado para el demostrador y asigna a cada
centro su familia, su subtipo, su vulnerabilidad y si es un centro sensible.

Recuentos esperados: 3.163 educativos, 105 sanitarios y 2.643 de atención social.

La salida (datos/procesados/activos.csv) no lleva NIF, teléfonos, correos ni webs
(sin datos personales). Centros sensibles: los que la propia
Comunidad publica con algún campo `RESERVADO` (dirección, municipio, código postal o
teléfono). No se ubican ni se geocodifican: quedan fuera del mapa y solo se cuentan en total.
Los centros sin coordenadas también quedan fuera del mapa, pero se cuentan. En los centros de
colectivos protegidos (mujeres, menores, refugiados, personas sin hogar, reclusos, familias,
inmigrantes…) el rótulo se queda en el tipo de centro, sin el colectivo.

Uso: python -m procesamiento.activos
"""
import pandas as pd
from pyproj import Transformer

from .fuentes import PROCESADOS, fuente

# --- Educativos: subtipo por código de tipo de centro (subtipos acordados) ----------
INFANTIL = {"003", "004", "005", "006", "008"}
PRIMARIA_SECUNDARIA = {"012", "013", "014", "015", "042", "045", "070", "072", "073", "074",
                       "094"}  # 094: colegios extranjeros en España (entran por decisión del proyecto)
EDUCACION_ESPECIAL = {"020", "021", "036", "038", "418"}  # incluye aulas hospitalarias y CET

# --- Sanitarios: tipos que entran ----------------------------------------------------
HOSPITALES = {"Hospital general", "Hospital especializado", "Hospital de media y larga estancia",
              "Hospital de salud mental y tratamiento de toxicomanías", "Otros centros con internamiento"}
DIALISIS = {"Centro de diálisis"}

# --- Atención social -------------------------------------------------------------------
RESIDENCIALES = {"CENTROS RESIDENCIALES", "CENTROS DE ACOGIDA"}
# Pisos tutelados y viviendas comunitarias de adultos autónomos: vulnerabilidad alta en vez
# de muy alta (decisión del proyecto). Los sectores de personas con discapacidad o enfermedad mental y
# los de infancia se consideran no autónomos.
SECTORES_ADULTOS_AUTONOMOS = {
    "Personas mayores", "Refugiados y asilados", "Mujer", "Personas sin hogar", "Presos y ex reclusos",
    "Otros grupos en situación de necesidad", "(Inmigracion) Otros grupos en situación de necesidad",
    "Familia", "Colectivos en situación de necesidad", "Conjunto de la población"}

# --- Tipo corto delante del nombre en el visor ---------------
# Educativos, por código de tipo de centro
TIPO_EDUCATIVO = {
    **dict.fromkeys(("003", "004", "006", "008"), "Escuela infantil"), "005": "Casa de niños",
    **dict.fromkeys(("012", "013", "014", "015"), "Colegio de primaria"),
    **dict.fromkeys(("042", "045"), "Instituto de secundaria"),
    **dict.fromkeys(("070", "072", "073", "074"), "Colegio de primaria y secundaria"),
    **dict.fromkeys(("020", "021"), "Colegio de educación especial"),
    **dict.fromkeys(("036", "418"), "Aula hospitalaria"), "038": "Centro educativo-terapéutico",
    "094": "Colegio extranjero"}
# Atención social: tipo de centro por subtipo del registro, y colectivo por sector
TIPO_SOCIAL = {
    **dict.fromkeys(("RESIDENCIAS DE PERSONAS MAYORES DEPENDIENTES", "RESIDENCIAS DE PERSONAS MAYORES MIXTA",
                     "RESIDENCIAS DE PERSONAS MAYORES AUTONOMAS", "OTRAS RESIDENCIAS", "CENTROS RESIDENCIALES: OTROS"),
                   "Residencia"),
    "PISOS TUTELADOS": "Piso tutelado", "VIVIENDAS COMUNITARIAS": "Vivienda comunitaria",
    "CENTROS DE DÍA: OTROS": "Centro de día", "HOGARES Y CLUBES": "Hogar",
    **dict.fromkeys(("CENTROS OCUPACIONALES GENÉRICOS", "CENTROS OCUPACIONALES:OTROS"), "Centro ocupacional"),
    "TALLERES": "Taller ocupacional", "CENTROS DE REHABILITACIÓN: OTROS": "Centro de rehabilitación",
    "CENTROS DE RECUPERACIÓN": "Centro de recuperación", "CENTROS DE ATENCIÓN": "Centro de atención"}
# Solo los colectivos que no son de protección llevan el colectivo en el rótulo: un piso de
# seis plazas rotulado «· mujeres» o «· reclusos» lo señalaría en el mapa; en esos centros queda solo el tipo
COLECTIVO_SOCIAL = {"Personas mayores": " de mayores", "Personas con discapacidad intelectual": " · discapacidad intelectual",
                    "Personas con enfermedad mental crónica": " · enfermedad mental",
                    "Personas con discapacidad física": " · discapacidad física"}


def tipo_social(subtipo: str, sector: str) -> str:
    """«Residencia de mayores», «Centro ocupacional · discapacidad intelectual», «Piso tutelado»…"""
    if subtipo == "ALBERGUES":
        base = "Albergue"
    elif subtipo in TIPO_SOCIAL:
        base = TIPO_SOCIAL[subtipo]
    else:
        base = "Centro de acogida" if "ACOGIDA" in subtipo or "MALTRATADAS" in subtipo else "Centro social"
    return base + COLECTIVO_SOCIAL.get(sector, "")


VULNERABILIDAD = {"baja": 2, "moderada": 3, "alta": 4, "muy_alta": 5}
COLUMNAS = ["id", "familia", "subtipo", "tipo", "vulnerabilidad", "sensible", "nombre", "municipio", "plazas", "x", "y"]


def _csv(clave: str) -> pd.DataFrame:
    return pd.read_csv(fuente(clave), sep=";", encoding="utf-8-sig", dtype=str, keep_default_na=False)


def educativos() -> pd.DataFrame:
    d = _csv("centros_educativos")
    d = d[d["SITUACIÓN"] == "ALTA"]
    subtipo = pd.Series(pd.NA, index=d.index, dtype="string")
    subtipo[d["COD_TIPO"].isin(INFANTIL)] = "infantil"
    subtipo[d["COD_TIPO"].isin(PRIMARIA_SECUNDARIA)] = "primaria_secundaria"
    subtipo[d["COD_TIPO"].isin(EDUCACION_ESPECIAL)] = "educacion_especial"
    d, subtipo = d[subtipo.notna()], subtipo.dropna()
    vulnerabilidad = subtipo.map({"infantil": "alta", "primaria_secundaria": "moderada",
                                  "educacion_especial": "muy_alta"})
    return pd.DataFrame({"id": "EDU-" + d["CODIGO"], "familia": "educativos", "subtipo": subtipo, "tipo": d["COD_TIPO"].map(TIPO_EDUCATIVO),
                         "vulnerabilidad": vulnerabilidad, "sensible": False, "nombre": d["CENTRO"],
                         "municipio": d["MUNICIPIO"], "plazas": pd.NA, "x": d["UTM_X"], "y": d["UTM_Y"]})


def sanitarios() -> pd.DataFrame:
    d = _csv("centros_sanitarios").drop_duplicates("centro_nro_registro")
    d = d[d["centro_tipo"].isin(HOSPITALES | DIALISIS)]
    hospital = d["centro_tipo"].isin(HOSPITALES)
    return pd.DataFrame({"id": "SAN-" + d["centro_nro_registro"], "familia": "sanitarios",
                         "subtipo": hospital.map({True: "hospital", False: "dialisis"}), "tipo": d["centro_tipo"],
                         "vulnerabilidad": hospital.map({True: "muy_alta", False: "alta"}), "sensible": False,
                         "nombre": d["centro_tipo"],  # el conjunto no publica el nombre del centro
                         "municipio": d["municipio_nombre"], "plazas": pd.NA,
                         "x": d["localizacion_coordenada_x"], "y": d["localizacion_coordenada_y"]})


def atencion_social() -> pd.DataFrame:
    d = _csv("atencion_social")
    residencial = d["tipo"].isin(RESIDENCIALES)
    vulnerabilidad = residencial.map({True: "muy_alta", False: "moderada"})
    autonomos = ((d["subtipo"] == "RESIDENCIAS DE PERSONAS MAYORES AUTONOMAS")
                 | (d["subtipo"].isin({"PISOS TUTELADOS", "VIVIENDAS COMUNITARIAS"})
                    & d["sector"].isin(SECTORES_ADULTOS_AUTONOMOS)))
    vulnerabilidad[residencial & autonomos] = "alta"
    vulnerabilidad[d["subtipo"] == "HOGARES Y CLUBES"] = "baja"
    return pd.DataFrame({"id": "SOC-" + d["numero_registro"], "familia": "atencion_social",
                         "subtipo": residencial.map({True: "residencial", False: "de_dia"}),
                         "tipo": [tipo_social(s, c) for s, c in zip(d["subtipo"], d["sector"])],
                         "vulnerabilidad": vulnerabilidad, "sensible": (d == "RESERVADO").any(axis=1),
                         "nombre": d["denominacion"], "municipio": d["municipio_nombre"],
                         "plazas": pd.to_numeric(d["plazas_autorizadas_numero"], errors="coerce"),
                         "x": d["direccion_coor_x"], "y": d["direccion_coor_y"]})


def construir() -> tuple[pd.DataFrame, dict]:
    """Activos con coordenadas (EPSG:25830 y lon/lat) y resumen de recuentos."""
    todos = pd.concat([educativos(), sanitarios(), atencion_social()], ignore_index=True)[COLUMNAS]
    reservados = todos["sensible"]
    resumen = {"por_familia": todos.groupby("familia").size().to_dict(), "reservados": int(reservados.sum()),
               "plazas_reservados": int(pd.to_numeric(todos.loc[reservados, "plazas"], errors="coerce").fillna(0).sum())}
    for c in ("x", "y"):
        todos[c] = pd.to_numeric(todos[c].str.replace(",", ".", regex=False), errors="coerce")
    todos.loc[reservados, ["x", "y"]] = float("nan")   # los reservados no se ubican, aunque traigan coordenadas
    con = todos.dropna(subset=["x", "y"]).reset_index(drop=True)
    resumen["sin_coordenadas"] = len(todos) - len(con) - resumen["reservados"]
    resumen["sensibles"] = int(con["sensible"].sum())
    a4326 = Transformer.from_crs("EPSG:25830", "EPSG:4326", always_xy=True)
    con["lon"], con["lat"] = a4326.transform(con["x"].to_numpy(), con["y"].to_numpy())
    con["vulnerabilidad_nivel"] = con["vulnerabilidad"].map(VULNERABILIDAD).astype(int)
    return con, resumen


def escribir() -> pd.DataFrame:
    con, resumen = construir()
    PROCESADOS.mkdir(parents=True, exist_ok=True)
    con.to_csv(PROCESADOS / "activos.csv", index=False, encoding="utf-8")
    familias = resumen["por_familia"]
    print(f"  activos: {sum(familias.values())} ({familias}); con algún campo reservado: {resumen['reservados']}"
          f" ({resumen['plazas_reservados']} plazas);"
          f" sin coordenadas: {resumen['sin_coordenadas']}; ubicados: {len(con)}, de ellos sensibles:"
          f" {resumen['sensibles']}")
    return con


if __name__ == "__main__":
    escribir()
