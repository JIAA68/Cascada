// Mapa base operativo de Cascada, dibujado desde el mapa base vectorial del IGN.
//
// Objetivo: localizar a simple vista el escenario de operaciones (poblaciones, carreteras,
// vías de tren, zona forestal, embalses) sin competir con las capas de peligrosidad. Sin
// tonos cálidos, que se reservan para los riesgos. Dos niveles:
//
// - Terreno, por debajo de las capas de peligrosidad: relieve sombreado (MDT del IGN), bosque,
//   núcleos urbanos, ríos y embalses. Capas con id "terreno-…".
// - Referencias, por encima de las capas y por debajo de los activos: carreteras por categoría,
//   ferrocarril y nombres. Capas con id "ref-…"; los nombres, "ref-nombre-…".
"use strict";

// Con red, directamente al IGN; sin conexión, la copia guardada del servidor
const SIN_CONEXION = window.CASCADA_SIN_CONEXION === true;
const COPIA = `${location.origin}/externo`;
const IGN_VECTORIAL = SIN_CONEXION ? `${COPIA}/ign-vectorial/{z}/{x}/{y}.pbf` : "https://vt-mapabase.idee.es/1.0.0/mapabase/{z}/{x}/{y}.pbf";
const IGN_MDT = SIN_CONEXION ? `${COPIA}/ign-mdt/{z}/{x}/{y}.png` : "https://xyz-mdt.idee.es/1.0.0/raster-dem/{z}/{x}/{y}.png";
const zoom = (...paradas) => ["interpolate", ["linear"], ["zoom"], ...paradas];
// Sin conexión, el zoom máximo de las fuentes es el de las teselas guardadas: MapLibre amplía esas al acercarse
const ZOOM_CACHE = SIN_CONEXION ? window.CASCADA_ZOOM_CACHE : null;
const zoomMax = (normal) => ZOOM_CACHE ? Math.min(normal, ZOOM_CACHE) : normal;

/** Terreno: se inserta por debajo de la capa `antes` (la ortofoto, que va oculta en modo mapa). */
function construirTerreno(mapa, antes) {
  mapa.addSource("ign-vectorial", { type: "vector", tiles: [IGN_VECTORIAL], minzoom: 0, maxzoom: zoomMax(17),
    attribution: "© Instituto Geográfico Nacional" });
  mapa.addSource("ign-mdt", { type: "raster-dem", tiles: [IGN_MDT], tileSize: 256, minzoom: 5, maxzoom: zoomMax(15),
    attribution: "© Instituto Geográfico Nacional" });
  const capa = (def) => mapa.addLayer(def, antes);
  const v = { source: "ign-vectorial" };

  capa({ id: "terreno-fondo", type: "background", paint: { "background-color": "#f3f2ee" } });
  capa({ id: "terreno-relieve", type: "hillshade", source: "ign-mdt",
    paint: { "hillshade-exaggeration": 0.45, "hillshade-shadow-color": "#6f6f6f", "hillshade-highlight-color": "#ffffff",
      "hillshade-illumination-anchor": "map" } });
  capa({ id: "terreno-bosque", type: "fill", ...v, "source-layer": "cubierta_vegetal_bosque_pol",
    paint: { "fill-color": "#b9d7a8", "fill-opacity": 0.75 } });
  // Núcleos urbanos: el IGN trae los núcleos (CartoCiudad) desde el zoom 10 y las manzanas desde el 12,
  // y a los núcleos les faltan poblaciones enteras o su casco (Parla, el centro de Majadahonda…), que
  // sí tienen manzanas. Por debajo del zoom 12 se usa el fichero que la cadena de datos extrae de las
  // teselas de zoom 12 con las dos capas (procesamiento/nucleos.py); desde el 12, las dos capas del IGN
  const gris = "#c4c4c4";
  const nucleos = { "fill-color": gris, "fill-outline-color": "#8c8c8c" };
  mapa.addSource("nucleos-urbanos", { type: "geojson", data: "/datos/nucleos_urbanos.geojson",
    attribution: "© Instituto Geográfico Nacional" });
  capa({ id: "terreno-nucleos-lejos", type: "fill", source: "nucleos-urbanos", maxzoom: 12, paint: nucleos });
  capa({ id: "terreno-manzanas", type: "fill", ...v, "source-layer": "manzana_pol", minzoom: 12,
    paint: { "fill-color": gris, "fill-outline-color": gris } });
  capa({ id: "terreno-nucleos", type: "fill", ...v, "source-layer": "nucleo_urbano_pol", minzoom: 12, paint: nucleos });
  // Ríos: los principales siempre; los menores, solo muy cerca
  capa({ id: "terreno-rios", type: "line", ...v, "source-layer": "hidrografia_lin",
    filter: ["all", ["==", ["get", "clase"], "curso_natural"],
      ["any", ["match", ["get", "orden"], ["primero_segundo", "tercero_cuarto"], true, false], [">=", ["zoom"], 13]]],
    paint: { "line-color": "#5b9bd5", "line-width": zoom(8, 0.7, 12, 1.4, 15, 2.2) } });
  capa({ id: "terreno-agua", type: "fill", ...v, "source-layer": "lamina_agua_pol",
    filter: ["match", ["get", "clase"], ["embalse", "lago", "lamina_agua"], true, false],
    paint: { "fill-color": "#7fb5e0", "fill-outline-color": "#3f7fb8" } });
}

/** Referencias: se añaden encima de lo que ya hay (las capas de peligrosidad). */
function construirReferencias(mapa) {
  const v = { source: "ign-vectorial" };
  const enUso = ["==", ["get", "estado"], "en_uso"];
  const redondo = { "line-join": "round", "line-cap": "round" };

  // Carreteras: gris más oscuro y más ancho cuanto más importantes, sin borde (el borde
  // blanco quedaba raro, sobre todo en la ortofoto)
  const via = (id, capaFuente, minzoom, ancho, color) => {
    mapa.addLayer({ id: `ref-${id}`, type: "line", ...v, "source-layer": capaFuente, minzoom, filter: enUso,
      layout: redondo, paint: { "line-color": color, "line-width": ancho } });
  };
  via("autonomica-3", "carretera_autonomica_3er_nivel_lin", 11, zoom(11, 0.6, 14, 1.5), "#5a5a5a");
  via("autonomica-2", "carretera_autonomica_2do_nivel_lin", 10, zoom(10, 0.7, 14, 1.8), "#4a4a4a");
  via("autonomica-1", "carretera_autonomica_1er_nivel_lin", 8, zoom(8, 0.7, 11, 1.4, 14, 2.4), "#3c3c3c");
  via("general", "carretera_general_lin", 7, zoom(7, 0.6, 11, 1.3, 14, 2.6), "#4a4a4a");
  via("autovia", "autovia_lin", 6, zoom(6, 0.8, 11, 1.8, 14, 3.4), "#2e2e2e");
  via("autopista", "autopista_lin", 6, zoom(6, 0.8, 11, 1.8, 14, 3.4), "#2e2e2e");

  // Ferrocarril (vías troncales a cielo abierto): negro con discontinuo blanco
  const tren = ["all", enUso, ["match", ["get", "clase"], ["tren", "tren_ligero"], true, false],
    ["!=", ["get", "tipo_tramo"], "playa_de_vias"], ["!=", ["get", "tunel"], "T"]];
  mapa.addLayer({ id: "ref-tren", type: "line", ...v, "source-layer": "ferrocarril_lin", filter: tren,
    paint: { "line-color": "#1f1f1f", "line-width": zoom(7, 1, 11, 2, 14, 3) } });
  mapa.addLayer({ id: "ref-tren-blanco", type: "line", ...v, "source-layer": "ferrocarril_lin", minzoom: 9, filter: tren,
    paint: { "line-color": "#ffffff", "line-width": zoom(9, 0.6, 11, 1, 14, 1.6), "line-dasharray": [3, 3] } });

  // Nombres, con halo blanco para leerse sobre cualquier capa
  const halo = { "text-halo-color": "rgba(255,255,255,0.95)", "text-halo-width": 1.6 };
  const texto = (campo, tam) => ({ "text-field": ["get", campo], "text-font": ["Open Sans Semibold"], "text-size": tam });
  mapa.addLayer({ id: "ref-nombre-carreteras", type: "symbol", ...v, "source-layer": "autovia_lin", minzoom: 10,
    filter: ["!=", ["get", "ref"], ""],
    layout: { ...texto("ref", 10), "symbol-placement": "line", "symbol-spacing": 400 },
    paint: { "text-color": "#2e2e2e", ...halo } });
  for (const [capaFuente, minzoom] of [["carretera_general_lin", 10], ["carretera_autonomica_1er_nivel_lin", 11]])
    mapa.addLayer({ id: `ref-nombre-${capaFuente}`, type: "symbol", ...v, "source-layer": capaFuente, minzoom,
      filter: ["!=", ["get", "ref"], ""],
      layout: { ...texto("ref", 10), "symbol-placement": "line", "symbol-spacing": 400 },
      paint: { "text-color": "#3c3c3c", ...halo } });
  const poblacion = (id, clases, minzoom, tam, color) => mapa.addLayer({
    id: `ref-nombre-${id}`, type: "symbol", ...v, "source-layer": "nombre_poblacion_construccion_pto", minzoom,
    filter: ["match", ["get", "clase"], clases, true, false],
    layout: { ...texto("nombre", tam), "text-padding": 4 }, paint: { "text-color": color, ...halo } });
  poblacion("capitales", ["capital_estado", "capital_comunidad_autonoma_ciudad_autonoma"], 6, zoom(6, 13, 12, 18), "#111111");
  poblacion("municipios", ["capital_municipio"], 8.5, zoom(9, 11, 12, 14), "#222222");
  poblacion("nucleos", ["nucleo_poblacion"], 11, zoom(11, 10, 14, 12), "#444444");
  mapa.addLayer({ id: "ref-nombre-embalses", type: "symbol", ...v, "source-layer": "nombre_hidrografia_pto", minzoom: 12,
    filter: ["==", ["get", "clase"], "embalse"],
    layout: { ...texto("nombre", 11), "text-padding": 4 }, paint: { "text-color": "#1f5f99", ...halo } });
}

/** Ids de las capas del estilo que empiezan por un prefijo. */
function capasCon(mapa, prefijo) {
  return mapa.getStyle().layers.map((l) => l.id).filter((id) => id.startsWith(prefijo));
}
