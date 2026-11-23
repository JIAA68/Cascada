// Gestión de crisis por incendio: alerta (manual o foco de satélite), simulación y simulador
// visual del avance. El motor devuelve el mapa completo de tiempos de llegada y aquí se pinta
// cualquier minuto sin recalcular: área quemada y frente activo (lienzo sobre el mapa), humo
// viento abajo (cono geométrico), activos e instalaciones Seveso marcados cuando el fuego les llega.
"use strict";

const NUNCA = 65535;
const FRENTE_MIN = 20;                                   // el frente activo: quemado en los últimos 20 min
const QUEMADO = [110, 18, 8, 150], FRENTE = [255, 96, 0, 240];
// Palabras y colores de cada amenaza: el incendio y la rotura de presa comparten reproductor, cartelas, cronología y
// comunicaciones
const VOCES = {
  incendio: { Agente: "Fuego", agente: "fuego", ElAgente: "El fuego", elAgente: "el fuego", superficie: "Superficie quemada",
    celdas: "celdas con fuego", colores: [QUEMADO, FRENTE] },
  presa: { Agente: "Agua", agente: "agua", ElAgente: "El agua", elAgente: "el agua", superficie: "Superficie inundada",
    celdas: "celdas inundadas", colores: [[25, 80, 160, 165], [90, 185, 255, 235]] },
};
let voz = VOCES.incendio, tipoCrisis = "incendio", listaPresas = [], presaElegida = null;
const RUMBOS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"];
const rumbo = (grados) => RUMBOS[Math.round(((grados % 360) + 360) % 360 / 45) % 8];
const vacioFC = () => ({ type: "FeatureCollection", features: [] });
const hhmm = (fecha) => fecha.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
const duracion = (min) => min < 60 ? `${Math.round(min)} min` : `${Math.floor(min / 60)} h ${String(Math.round(min % 60)).padStart(2, "0")} min`;

let alerta = null, marcador = null, focos = [];
let sim = null, llegada = null, lienzo = null, dibujo = null, pixeles = null;
let t = 0, minutoPintado = -1, reproduciendo = false, ultimoCuadro = 0;
let afectadosBase = [];   // cosas afectadas según la simulación; movilidad.js añade trenes y tráfico
// Avisos anticipados: globo con cuenta atrás para todo lo que alcanzará el fuego (centros de cualquier vulnerabilidad,
// carreteras, vías de tren, núcleos de población, instalaciones Seveso y conducción), desde 3 h antes de la llegada;
// los 5 más próximos a la vez, de cualquier tipo, y las instalaciones Seveso y la conducción, además, fuera de ese
// cupo. Flecha por la ruta del fuego solo en los centros de vulnerabilidad alta y muy alta, que traen la ruta. Al
// llegar, el globo se pone rojo con la hora y se apaga a los 30 minutos simulados.
const AVISO = { antelacion_min: 180, simultaneos: 5, permanencia_min: 30, urgente_min: 60 };
// La animación arranca solo con la ignición: en las 3 primeras horas, avisos e isocronas miran
// tan lejos como tiempo lleva el incendio (en el minuto 10, lo que llega antes del 20), y desde ahí, 3 horas
const antelacion = (minuto, maximo) => Math.min(maximo, minuto);
let avisos = [];
const globos = new Map();
// Cronología de sucesos: los últimos 5 sobre el mapa y la lista completa en el panel, con
// tipos seleccionables, marcas en la barra de tiempo, pausa en los sucesos clave (Seveso y conducciones alcanzadas,
// centros de vulnerabilidad muy alta) y cámara fija, que sigue los sucesos clave o que sigue todos.
const TIPOS_SUCESO = { municipios: "Municipios y poblaciones", centros: "Centros alcanzados", cascada: "Seveso y conducciones",
  vias: "Carreteras y trenes de Cercanías", otros: "Trenes y tráfico ahora, y humo sobre centros" };
const tiposActivos = new Set(["municipios", "centros", "cascada", "vias"]);
// Carreteras y vías de tren: gris bajo el humo, rojo con el fuego a menos de 250 m. Sin
// pistas forestales
const NUNCA_MIN = 1e9;
// Cascada animada: flecha del frente a la instalación Seveso o la conducción en la hora antes
// de alcanzarla; al alcanzarla, pulso y zonas que crecen desde ella en 2 s reales; flechas a los centros de
// vulnerabilidad alta y muy alta de sus zonas durante 30 minutos simulados; esquema de la cadena en el panel.
const CASCADA = { duracion_ms: 2000, aproximacion_min: 60, flechas_min: 30, naranja: "#d9772b" };
let origenesCascada = [], minutoCascada = -1;
// Isocronas: hasta dónde habrá llegado el fuego a cada hora en punto de las 3 siguientes,
// con la hora del reloj; la próxima, más marcada, y las siguientes, más tenues.
const ISOCRONAS_MIN = 180;
const animando = new Map();
const ANCHO_VIA = ["match", ["get", "tipo"], "carretera", 4, 3];
const SUCESOS_EN_MAPA = 5;
let sucesos = [], cronologiaPintada = "";

// ----------------------------------------------------------------------------- capas del mapa
document.addEventListener("mapa-listo", () => {
  for (const id of ["humo", "seveso-zonas", "cascada-destinos", "afectados", "focos", "validacion-perimetro", "validacion-focos"])
    mapa.addSource(id, { type: "geojson", data: vacioFC() });
  mapa.addLayer({ id: "humo", type: "fill", source: "humo", paint: { "fill-color": "#555", "fill-opacity": 0.28 } }, "activos-grupos");
  mapa.addLayer({ id: "seveso-zonas", type: "fill", source: "seveso-zonas", filter: ["<=", ["get", "minutos"], -1],
    paint: { "fill-color": ["match", ["get", "zona"], "intervención", "#ff7f00", "#ffd000"], "fill-opacity": 0.22 } }, "activos-grupos");
  mapa.addLayer({ id: "seveso-bordes", type: "line", source: "seveso-zonas", filter: ["<=", ["get", "minutos"], -1],
    paint: { "line-color": "#c65a00", "line-width": 1.5, "line-dasharray": [3, 2] } }, "activos-grupos");
  // Cada cosa afectada aparece en el mapa al llegarle el fuego, la zona Seveso o el humo: los
  // centros, con su propio símbolo; estaciones, trenes y tráfico, con un punto del color del efecto; carreteras y
  // municipios, sin marca (la carretera ya cambia de color). El nombre, del color del efecto, hasta el final (si choca con
// otro de más prioridad, se oculta hasta que haya sitio); la casilla
  // «Nombres» lo apaga (app.js).
  mapa.addLayer({ id: "afectados", type: "symbol", source: "afectados", filter: ["<=", ["get", "minutos"], -1],
    layout: { "icon-image": ["concat", "activo-", ["get", "subtipo"]], "icon-size": 1.15, "icon-allow-overlap": true, "icon-ignore-placement": true } });
  mapa.addLayer({ id: "afectados-punto", type: "circle", source: "afectados", filter: ["<=", ["get", "minutos"], -1],
    paint: { "circle-radius": 5, "circle-color": ["get", "color"], "circle-stroke-color": "#fff", "circle-stroke-width": 1.5 } });
  mapa.addLayer({ id: "afectados-nombre", type: "symbol", source: "afectados", filter: ["<=", ["get", "minutos"], -1],
    layout: { "text-field": ["get", "nombre"], "text-size": ["case", ["==", ["get", "clase"], "municipio"], 13, 11.5],
      "text-font": ["Open Sans Semibold"], "text-max-width": 14,
      "text-variable-anchor": ["left", "right", "top", "bottom"], "text-radial-offset": 0.9, "symbol-sort-key": ["get", "orden"],
      // Nombres que chocan: se oculta el de menor prioridad según "orden" (poblaciones,
      // Seveso y conducción; fuego antes que amenaza derivada y humo; mayor vulnerabilidad primero) y reaparece al acercarse
      "text-allow-overlap": false, "text-ignore-placement": false },
    paint: { "text-color": ["get", "color"], "text-halo-color": "#fff", "text-halo-width": 2 } });
  mapa.addSource("vias", { type: "geojson", data: vacioFC() });
  const sinDato = (campo) => ["coalesce", ["get", campo], NUNCA_MIN];
  mapa.addLayer({ id: "vias-borde", type: "line", source: "vias", filter: ["<=", ["min", sinDato("llamas"), sinDato("humo")], -1],
    layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#fff", "line-width": ["+", ANCHO_VIA, 2.5], "line-opacity": 0.8 } }, "activos-grupos");
  // Carreteras con línea continua; vías de tren, discontinua (una capa por estado y por clase)
  for (const [estado, color] of [["humo", "#5f5f5f"], ["fuego", "#d1121b"]]) {
    mapa.addLayer({ id: `vias-${estado}`, type: "line", source: "vias", filter: ["<=", sinDato("llamas"), -1],
      layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": color, "line-width": ANCHO_VIA } }, "activos-grupos");
    mapa.addLayer({ id: `vias-${estado}-tren`, type: "line", source: "vias", filter: ["<=", sinDato("llamas"), -1],
      layout: { "line-join": "round" }, paint: { "line-color": color, "line-width": 3, "line-dasharray": [2, 1] } }, "activos-grupos");
  }
  mapa.addSource("isocronas", { type: "geojson", data: vacioFC() });
  mapa.addLayer({ id: "isocronas-halo", type: "line", source: "isocronas", filter: ["<=", ["get", "minutos"], -1],
    layout: { "line-join": "round" }, paint: { "line-color": "#fff", "line-width": 4.5 } }, "activos-grupos");
  mapa.addLayer({ id: "isocronas", type: "line", source: "isocronas", filter: ["<=", ["get", "minutos"], -1],
    layout: { "line-join": "round" }, paint: { "line-color": "#7a1f0e", "line-width": 2, "line-dasharray": [3, 1.5] } }, "activos-grupos");
  mapa.addLayer({ id: "isocronas-hora", type: "symbol", source: "isocronas", filter: ["<=", ["get", "minutos"], -1],
    layout: { "symbol-placement": "line", "symbol-spacing": 350, "text-field": ["get", "hora"], "text-size": 11,
      "text-font": ["Open Sans Semibold"], "text-keep-upright": true },
    paint: { "text-color": "#7a1f0e", "text-halo-color": "#fff", "text-halo-width": 2 } });
  // Franja activada de la conducción de hidrocarburos, hora a hora
  mapa.addSource("conduccion-franja", { type: "geojson", data: vacioFC() });
  mapa.addLayer({ id: "conduccion-franja", type: "fill", source: "conduccion-franja", filter: ["<=", ["get", "minutos"], -1],
    paint: { "fill-color": "#ff7f00", "fill-opacity": 0.2 } }, "activos-grupos");
  mapa.addLayer({ id: "conduccion-borde", type: "line", source: "conduccion-franja", filter: ["<=", ["get", "minutos"], -1],
    paint: { "line-color": "#c65a00", "line-width": 1.5, "line-dasharray": [3, 2] } }, "activos-grupos");
  // Conducciones de hidrocarburos: solo la línea, siempre visible en los tres modos. Es el eje
  // del núcleo de la capa 6_12, calculado en la cadena de datos (procesamiento/conducciones.py)
  mapa.addSource("conducciones", { type: "geojson", data: "/datos/conducciones.geojson" });
  mapa.addLayer({ id: "conducciones", type: "line", source: "conducciones", layout: { "line-join": "round", "line-cap": "round" },
    paint: { "line-color": "#f5c400", "line-width": ["interpolate", ["linear"], ["zoom"], 8, 1.8, 13, 3.5] } }, "activos-grupos");
  mapa.addLayer({ id: "conducciones-nombre", type: "symbol", source: "conducciones", minzoom: 12,
    layout: { "symbol-placement": "line", "symbol-spacing": 500, "text-field": "conducción de hidrocarburos", "text-size": 11,
      "text-font": ["Open Sans Semibold"], "text-offset": [0, -0.9] },
    paint: { "text-color": "#3b2f00", "text-halo-color": "#fff", "text-halo-width": 1.8 } });
  // Zonas que crecen al activarse, pulso sobre la instalación y flechas a los centros de sus zonas
  for (const id of ["cascada-anim", "cascada-pulso", "cascada-flechas", "cascada-puntas"]) mapa.addSource(id, { type: "geojson", data: vacioFC() });
  mapa.addLayer({ id: "cascada-anim", type: "fill", source: "cascada-anim",
    paint: { "fill-color": ["match", ["get", "zona"], "intervención", "#ff7f00", "alerta", "#ffd000", "#ff7f00"], "fill-opacity": 0.25 } }, "activos-grupos");
  mapa.addLayer({ id: "cascada-anim-borde", type: "line", source: "cascada-anim", paint: { "line-color": "#c65a00", "line-width": 2 } }, "activos-grupos");
  mapa.addLayer({ id: "cascada-pulso", type: "circle", source: "cascada-pulso",
    paint: { "circle-radius": ["get", "r"], "circle-opacity": 0, "circle-stroke-width": 3, "circle-stroke-color": CASCADA.naranja,
      "circle-stroke-opacity": ["get", "o"] } });
  mapa.addLayer({ id: "cascada-flechas", type: "line", source: "cascada-flechas", filter: ["<=", ["get", "minutos"], -1],
    layout: { "line-cap": "round" }, paint: { "line-color": CASCADA.naranja, "line-width": 2.5, "line-dasharray": [2, 1.5] } });
  // Flecha de los avisos anticipados: el tramo de la ruta del fuego que queda entre el frente y el centro
  mapa.addSource("aviso-rutas", { type: "geojson", data: vacioFC() });
  mapa.addSource("aviso-puntas", { type: "geojson", data: vacioFC() });
  const tam = 32, lienzoPunta = document.createElement("canvas"); lienzoPunta.width = lienzoPunta.height = tam;
  const g = lienzoPunta.getContext("2d");
  g.beginPath(); g.moveTo(tam / 2, 3); g.lineTo(tam - 5, tam - 5); g.lineTo(tam / 2, tam - 11); g.lineTo(5, tam - 5); g.closePath();
  g.fillStyle = "#d1121b"; g.fill(); g.strokeStyle = "#fff"; g.lineWidth = 2.5; g.lineJoin = "round"; g.stroke();
  mapa.addImage("punta-aviso", g.getImageData(0, 0, tam, tam), { pixelRatio: 2 });
  g.fillStyle = CASCADA.naranja; g.fill(); g.stroke();
  mapa.addImage("punta-cascada", g.getImageData(0, 0, tam, tam), { pixelRatio: 2 });
  mapa.addLayer({ id: "aviso-rutas-halo", type: "line", source: "aviso-rutas", layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": "#fff", "line-width": 6, "line-opacity": 0.85 } });
  mapa.addLayer({ id: "aviso-rutas", type: "line", source: "aviso-rutas", layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": ["coalesce", ["get", "color"], "#d1121b"], "line-width": 3, "line-dasharray": [2, 1.2] } });
  mapa.addLayer({ id: "aviso-puntas", type: "symbol", source: "aviso-puntas",
    layout: { "icon-image": ["coalesce", ["get", "icono"], "punta-aviso"], "icon-size": 1.1, "icon-rotate": ["get", "rumbo"], "icon-rotation-alignment": "map",
      // La punta se retrasa unos píxeles por la propia línea para que el símbolo del centro no la tape
      "icon-offset": [0, 14], "icon-allow-overlap": true, "icon-ignore-placement": true } });
  mapa.addLayer({ id: "cascada-puntas", type: "symbol", source: "cascada-puntas", filter: ["<=", ["get", "minutos"], -1],
    layout: { "icon-image": "punta-cascada", "icon-size": 1, "icon-rotate": ["get", "rumbo"], "icon-rotation-alignment": "map",
      "icon-allow-overlap": true, "icon-ignore-placement": true } });
  // Punto de los destinos de la cascada (Seveso y punto de la conducción que alcanza el fuego), desde el principio:
  // tenue hasta la hora previa a la llegada; el nombre y la hora van en su globo de aviso
  mapa.addLayer({ id: "cascada-destinos-punto", type: "circle", source: "cascada-destinos",
    paint: { "circle-radius": 7, "circle-color": "#fff", "circle-stroke-width": 3.5, "circle-stroke-color": CASCADA.naranja } });
  mapa.addLayer({ id: "focos", type: "circle", source: "focos",
    paint: { "circle-radius": 7, "circle-color": ["case", ["get", "fuente_fija"], "#888", "#ff3b00"], "circle-stroke-color": "#fff", "circle-stroke-width": 2 } });
  // Caso de validación: perímetro final real (EFFIS) y focos de satélite, que aparecen a su hora
  mapa.addLayer({ id: "validacion-halo", type: "line", source: "validacion-perimetro", paint: { "line-color": "#fff", "line-width": 5, "line-opacity": 0.8 } });
  mapa.addLayer({ id: "validacion-linea", type: "line", source: "validacion-perimetro", paint: { "line-color": "#111", "line-width": 2.5, "line-dasharray": [2, 1.5] } });
  mapa.addLayer({ id: "validacion-focos", type: "circle", source: "validacion-focos", filter: ["<=", ["get", "minutos"], -1],
    paint: { "circle-radius": 6, "circle-color": "#ffd400", "circle-stroke-color": "#111", "circle-stroke-width": 1.5 } });
  capasClicables.push("focos");
  // Presas deducidas del catálogo (procesamiento/presas.py), para elegir la que se rompe; solo en la alerta de presa
  mapa.addSource("presas", { type: "geojson", data: vacioFC() });
  mapa.addLayer({ id: "presas", type: "circle", source: "presas", layout: { visibility: "none" },
    paint: { "circle-radius": 7, "circle-color": "#1d5fae", "circle-stroke-color": "#fff", "circle-stroke-width": 2 } });
  mapa.addLayer({ id: "presas-nombre", type: "symbol", source: "presas",
    layout: { visibility: "none", "text-field": ["get", "nombre"], "text-font": ["Open Sans Semibold"], "text-size": 12,
      "text-offset": [0, 1.1], "text-anchor": "top" },
    paint: { "text-color": "#123c6e", "text-halo-color": "#fff", "text-halo-width": 1.5 } });
  capasClicables.push("presas");
  mapa.on("click", "presas", (ev) => { if (modo === "crisis" && tipoCrisis === "presa") elegirPresa(ev.features[0].properties.id); });
  mapa.on("mouseenter", "presas", () => mapa.getCanvas().style.cursor = "pointer");
  mapa.on("mouseleave", "presas", () => mapa.getCanvas().style.cursor = "");
  mapa.on("click", "focos", (ev) => { if (modo === "crisis") registrarAlerta(ev.lngLat, "FIRMS"); });
  mapa.on("click", "afectados", (ev) => { if (modo === "crisis") mapa.easeTo({ center: ev.lngLat, zoom: Math.max(mapa.getZoom(), 14) }); });
  mapa.on("moveend", () => { if (sim) colocarCartelas(minutoPintado); });
  mapa.on("mouseenter", "focos", () => mapa.getCanvas().style.cursor = "pointer");
  mapa.on("mouseleave", "focos", () => mapa.getCanvas().style.cursor = "");
  mapa.on("click", (ev) => {
    if (modo !== "crisis" || sobreElemento(ev.point)) return;
    if (tipoCrisis === "presa") return presaCercana(ev.lngLat);
    registrarAlerta(ev.lngLat, "manual");
  });
});

document.addEventListener("modo", (ev) => {
  const crisis = ev.detail === "crisis";
  for (const id of ["humo", "seveso-zonas", "seveso-bordes", "cascada-destinos-punto", "afectados", "afectados-punto", "afectados-nombre", "focos",
    "validacion-halo", "validacion-linea", "validacion-focos", "aviso-rutas-halo", "aviso-rutas", "aviso-puntas", "vias-borde", "vias-humo", "vias-fuego", "vias-humo-tren", "vias-fuego-tren", "conduccion-franja", "conduccion-borde",
    "cascada-anim", "cascada-anim-borde", "cascada-pulso", "cascada-flechas", "cascada-puntas", "isocronas-halo", "isocronas", "isocronas-hora"]) visible(id, crisis);
  for (const m of globos.values()) m.getElement().hidden = !crisis;
  if (crisis && sim) colocarCartelas(minutoPintado);
  $("#cronologia-mapa").hidden = !crisis || !sim;
  $("#esalert-mapa").hidden = !crisis || !sim;
  if (mapa.getLayer("fuego")) visible("fuego", crisis);
  for (const id of ["presas", "presas-nombre"]) if (mapa.getLayer(id)) visible(id, crisis && tipoCrisis === "presa" && !sim);
  if (marcador) crisis ? marcador.addTo(mapa) : marcador.remove();
  $("#reproductor").hidden = !crisis || !sim;
  if (!crisis) reproducir(false);
});

// ----------------------------------------------------------------------------- alerta
function registrarAlerta(lngLat, origen) {
  alerta = { lon: +lngLat.lng.toFixed(5), lat: +lngLat.lat.toFixed(5), origen };
  if (marcador) marcador.remove();
  marcador = new maplibregl.Marker({ color: "#b3261e" }).setLngLat(lngLat).addTo(mapa);
  $("#alerta-ayuda").hidden = true;
  $("#alerta-datos").hidden = false;
  requestAnimationFrame(() => $("#alerta-datos").scrollIntoView({ block: "nearest", behavior: "smooth" }));
  $("#alerta-punto").innerHTML = `<strong>${origen === "FIRMS" ? "Alerta automática (foco de satélite)" : "Alerta manual"}</strong>` +
    `<br><span class="meta">${alerta.lat.toFixed(4)}, ${alerta.lon.toFixed(4)} · haz clic en otro punto para moverla</span>`;
  horaPorDefecto();
  $("#estado").textContent = ""; $("#estado").className = "";
}

function horaPorDefecto() {
  if ($("#alerta-hora").value) return;
  const ahora = new Date(); ahora.setMinutes(ahora.getMinutes() - ahora.getTimezoneOffset());
  $("#alerta-hora").value = ahora.toISOString().slice(0, 16);
}

// ----------------------------------------------------------------------------- amenaza: incendio o rotura de presa
async function cambiarTipoCrisis(tipo) {
  tipoCrisis = tipo;
  const presa = tipo === "presa";
  $("#crisis-incendio").classList.toggle("activo", !presa);
  $("#crisis-presa").classList.toggle("activo", presa);
  $("#alerta-titulo").textContent = presa ? "Alerta de rotura de presa" : "Alerta de incendio";
  $("#alerta-ayuda").textContent = presa ? "Elige una presa de la lista o púlsala en el mapa."
    : "Haz clic en el mapa para situar la alerta, o elige un foco de calor detectado por satélite.";
  $("#focos-boton").hidden = presa; $("#focos-lista").hidden = presa;
  $("#presa-eleccion").hidden = !presa;
  $("#alerta-viento").hidden = presa;
  $("#alerta-hora-texto").textContent = presa ? "Hora de la rotura" : "Hora de la ignición";
  $("#simular").textContent = presa ? "Simular la rotura" : "Simular la evolución (24 h)";
  alerta = null; presaElegida = null; $("#presa-lista").value = "";
  if (marcador) { marcador.remove(); marcador = null; }
  $("#alerta-datos").hidden = true; $("#alerta-ayuda").hidden = false;
  $("#estado").textContent = ""; $("#estado").className = "";
  for (const id of ["presas", "presas-nombre"]) visible(id, presa && modo === "crisis");
  if (presa && !listaPresas.length) {
    try {
      listaPresas = await consultar("/api/presas");
    } catch (e) {
      $("#estado").className = "error"; $("#estado").textContent = `No se han podido cargar las presas: ${e.message}`;
      $("#alerta-datos").hidden = false;
      return;
    }
    mapa.getSource("presas").setData({ type: "FeatureCollection", features: listaPresas.map((p) => ({ type: "Feature",
      geometry: { type: "Point", coordinates: [p.lon, p.lat] }, properties: { id: p.id, nombre: p.nombre } })) });
    $("#presa-lista").innerHTML = `<option value="">Elige una presa…</option>` +
      listaPresas.map((p) => `<option value="${p.id}">${html(p.nombre)} (${html(p.municipio)})</option>`).join("");
  }
}
$("#crisis-incendio").onclick = () => cambiarTipoCrisis("incendio");
$("#crisis-presa").onclick = () => cambiarTipoCrisis("presa");
$("#presa-lista").onchange = () => { if ($("#presa-lista").value) elegirPresa($("#presa-lista").value, true); };

function elegirPresa(id, volar = false) {
  const p = listaPresas.find((x) => x.id === id);
  if (!p) return;
  presaElegida = p;
  $("#presa-lista").value = id;
  if (marcador) marcador.remove();
  marcador = new maplibregl.Marker({ color: "#1d5fae" }).setLngLat([p.lon, p.lat]).addTo(mapa);
  if (volar) mapa.flyTo({ center: [p.lon, p.lat], zoom: Math.max(mapa.getZoom(), 11) });
  $("#alerta-ayuda").hidden = true;
  $("#alerta-datos").hidden = false;
  $("#alerta-punto").innerHTML = `<strong>${html(p.nombre)}</strong><br><span class="meta">${html(p.municipio)} · ` +
    `presa deducida de la capa de rotura de presas del Catálogo de Riesgos Potenciales</span>`;
  horaPorDefecto();
  $("#estado").textContent = ""; $("#estado").className = "";
}

// La presa más cercana al clic, si está a menos de 3 km
function presaCercana(lngLat) {
  let mejor = null, dmin = Infinity;
  for (const p of listaPresas) {
    const d = Math.hypot((p.lon - lngLat.lng) * Math.cos((lngLat.lat * Math.PI) / 180), p.lat - lngLat.lat) * 111.32;
    if (d < dmin) { dmin = d; mejor = p; }
  }
  if (mejor && dmin <= 3) elegirPresa(mejor.id);
}

$("#ver-focos").onclick = async () => {
  $("#focos-lista").innerHTML = `<p class="meta">Consultando NASA FIRMS…</p>`;
  try {
    const d = await consultar("/api/focos");
    focos = d.focos;
    mapa.getSource("focos").setData({ type: "FeatureCollection", features: focos.map((f) => ({
      type: "Feature", geometry: { type: "Point", coordinates: [f.lon, f.lat] }, properties: { fuente_fija: f.fuente_fija } })) });
    $("#focos-lista").innerHTML = `<p class="meta">Consultado a las ${d.consultado.slice(11, 16)}. ${d.fuente}.</p>` +
      (focos.length ? `<ul class="activos">${focos.map((f, i) =>
        `<li data-foco="${i}"><span class="hora">${f.hora.slice(11, 16)}</span><span class="nombre">` +
        (f.fuente_fija ? "Posible fuente fija (se repite en la semana)" : "<strong>Foco de calor</strong>") +
        `<br><span class="meta">${f.satelite} · ${f.dia_noche} · ${f.potencia_mw.toLocaleString("es-ES")} MW · confianza ${f.confianza}</span></span></li>`).join("")}</ul>` +
        `<p class="meta">Haz clic en un foco para abrir una alerta en ese punto.</p>`
      : `<p>No hay focos de calor en la Comunidad en las últimas 24 horas.</p>`);
    for (const li of $("#focos-lista").querySelectorAll("li[data-foco]")) li.onclick = () => {
      const f = focos[+li.dataset.foco];
      mapa.flyTo({ center: [f.lon, f.lat], zoom: 12 });
      registrarAlerta({ lng: f.lon, lat: f.lat }, "FIRMS");
    };
  } catch (e) {
    $("#focos-lista").innerHTML = `<p class="error">No se han podido consultar los focos: ${html(e.message)}</p>`;
  }
};

for (const r of document.querySelectorAll("input[name=viento]")) r.onchange = () => { $("#viento-manual").hidden = $("input[name=viento]:checked").value !== "manual"; };

$("#simular").onclick = async () => {
  const presa = tipoCrisis === "presa";
  if (presa ? !presaElegida : !alerta) return;
  limpiarValidacion();
  const hora = $("#alerta-hora").value || undefined;
  const cuerpo = presa ? { presa: presaElegida.id, hora } : { lon: alerta.lon, lat: alerta.lat, hora };
  if (!presa && $("input[name=viento]:checked").value === "manual") cuerpo.viento = { velocidad_kmh: +$("#viento-vel").value, desde: +$("#viento-desde").value };
  $("#simular").disabled = true;
  $("#estado").className = "";
  $("#estado").textContent = presa ? "Calculando la llegada del agua aguas abajo de la presa…"
    : "Calculando la evolución del incendio (relieve, combustible, viento y propagación)…";
  try {
    const r = await fetch(presa ? "/api/presa" : "/api/incendio", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || r.statusText);
    const mapaLlegada = await fetch(d.llegada_url).then((x) => x.arrayBuffer());
    cargarSimulacion(d, new Uint16Array(mapaLlegada));
    for (const id of ["presas", "presas-nombre"]) visible(id, false);   // con la simulación, solo la presa rota
    $("#estado").textContent = "";
  } catch (e) {
    $("#estado").className = "error"; $("#estado").textContent = `No se ha podido simular: ${e.message}`;
  } finally { $("#simular").disabled = false; }
};

// ----------------------------------------------------------------------------- geometría de la ventana
// Celda (columna, fila), también fraccionaria o fuera de la ventana, a lon/lat por interpolación de las esquinas
function lonlat(col, fila) {
  const [no, ne, se, so] = sim.ventana.esquinas;
  const u = col / sim.ventana.columnas, v = fila / sim.ventana.filas;
  return [0, 1].map((k) => no[k] + u * (ne[k] - no[k]) + v * (so[k] - no[k]) + u * v * (se[k] - ne[k] - so[k] + no[k]));
}

function circulo(lon, lat, radioM, pasos = 64) {
  const anillo = [];
  for (let i = 0; i <= pasos; i++) {
    const a = (2 * Math.PI * i) / pasos;
    anillo.push([lon + (radioM * Math.cos(a)) / (111320 * Math.cos((lat * Math.PI) / 180)), lat + (radioM * Math.sin(a)) / 110540]);
  }
  return { type: "Polygon", coordinates: [anillo] };
}

// Zona de humo en el minuto t: la que calcula el servidor cada pocos minutos, la misma con la
// que marca los centros, carreteras y estaciones bajo el humo (procesamiento/incendio/humo.py)
function zonaHumo(minuto) {
  let zona = null;
  for (const z of sim.humo.zonas || []) { if (z.minutos > minuto) break; zona = z; }
  return zona ? { type: "Feature", geometry: { type: "Polygon", coordinates: [zona.coords] }, properties: {} } : vacioFC();
}
// La zona solo cambia cada pocos minutos: se manda al mapa solo cuando cambia. Mandarla en cada minuto atasca al mapa,
// que va reprocesándola con retraso y llega a pintar el humo de minutos antes (cortado)
let humoPintado = null;
function pintarHumo(minuto) {
  let zona = null;
  for (const z of sim.humo.zonas || []) { if (z.minutos > minuto) break; zona = z; }
  if (zona === humoPintado && humoPintado !== null) return;
  humoPintado = zona;
  mapa.getSource("humo").setData(zonaHumo(minuto));
}

// ----------------------------------------------------------------------------- carga de una simulación
function cargarSimulacion(d, mapaLlegada, historico = false) {
  sim = d; llegada = mapaLlegada; humoPintado = null;
  voz = d.tipo === "presa" ? VOCES.presa : VOCES.incendio;
  const { filas, columnas, esquinas } = d.ventana;
  lienzo = document.createElement("canvas"); lienzo.width = columnas; lienzo.height = filas;
  dibujo = lienzo.getContext("2d"); pixeles = dibujo.createImageData(columnas, filas);
  if (mapa.getLayer("fuego")) { mapa.removeLayer("fuego"); mapa.removeSource("fuego"); }
  mapa.addSource("fuego", { type: "canvas", canvas: lienzo, coordinates: esquinas, animate: true });
  // Bordes suavizados al pintar: el cálculo sigue en celdas de 50 m, pero sin cuadrados
  mapa.addLayer({ id: "fuego", type: "raster", source: "fuego", paint: { "raster-fade-duration": 0, "raster-resampling": "linear" } }, "humo");

  const zonas = [], destinos = [], horaCascada = (min) => hhmm(new Date(new Date(d.ignicion.hora).getTime() + min * 60000));
  const destino = (lon, lat, id, nombre, minutos) => ({ type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] },
    properties: { id, nombre, minutos, hora: horaCascada(minutos) } });
  for (const i of d.cascada.instalaciones_seveso) {
    for (const [zona, radio] of [["alerta", i.radio_alerta_m], ["intervención", i.radio_intervencion_m]])
      zonas.push({ type: "Feature", geometry: circulo(i.lon, i.lat, radio), properties: { zona, minutos: i.minutos, id: i.id } });
    destinos.push(destino(i.lon, i.lat, i.id, `Seveso ${i.id} · ${i.amenazas.join(", ")}`, i.minutos));
  }
  for (const tr of tramosConduccion(d)) destinos.push(destino(tr.lon, tr.lat, tr.id, "Conducción de hidrocarburos", Math.round(tr.minutos * 10) / 10));
  mapa.getSource("seveso-zonas").setData({ type: "FeatureCollection", features: zonas });
  mapa.getSource("cascada-destinos").setData({ type: "FeatureCollection", features: destinos });
  afectadosBase = cosasAfectadas(d);
  mapa.getSource("afectados").setData({ type: "FeatureCollection", features: afectadosBase });
  for (const m of globos.values()) m.remove();
  globos.clear();
  cartelasVigentes = [];
  avisos = listaAvisos(d);
  prepararCascada(d, zonas);
  const horaIso = (min) => hhmm(new Date(new Date(d.ignicion.hora).getTime() + min * 60000));
  mapa.getSource("isocronas").setData({ type: "FeatureCollection", features: (d.isocronas || []).flatMap((i) => i.coords.map((anillo) => ({
    type: "Feature", geometry: { type: "LineString", coordinates: anillo }, properties: { minutos: i.minutos, hora: horaIso(i.minutos) } }))) });
  mapa.getSource("vias").setData({ type: "FeatureCollection", features: ((d.vias || {}).tramos || []).map((v) => ({
    type: "Feature", geometry: { type: "LineString", coordinates: v.coords }, properties: { tipo: v.tipo, llamas: v.llamas, humo: v.humo } })) });

  // Encuadre: lo quemado en 24 h y las zonas Seveso activadas
  let r0 = filas, r1 = 0, c0 = columnas, c1 = 0;
  for (let i = 0; i < llegada.length; i++) if (llegada[i] !== NUNCA) {
    const f = Math.floor(i / columnas), c = i % columnas;
    if (f < r0) r0 = f; if (f > r1) r1 = f; if (c < c0) c0 = c; if (c > c1) c1 = c;
  }
  const caja = new maplibregl.LngLatBounds(lonlat(c0, r1 + 1), lonlat(c1 + 1, r0));
  for (const z of zonas) for (const p of z.geometry.coordinates[0]) caja.extend(p);
  mapa.fitBounds(caja, { padding: { top: 40, bottom: 120, left: 40, right: 40 }, maxZoom: 13 });

  mostrarResultado(d);
  sucesos = construirSucesos(d);
  cronologiaPintada = "";
  pintarCronologia();
  $("#cronologia-mapa").hidden = false;
  $("#reproductor").hidden = false;
  $("#comunicaciones").hidden = false;
  $("#esalert-mapa").hidden = false;
  emisionesAlerta = [0, ...d.municipios.map((m) => Math.max(0, m.minutos - 60))]
    .filter((e, i, l) => l.indexOf(e) === i).sort((a, b) => a - b);
  minutoPintado = -1;
  fijarTiempo(0);
  if (!historico && d.tipo !== "presa") cruzarMovilidad(d);   // trenes y tráfico actuales en la zona afectada (movilidad.js); no en casos pasados
}

// Todo lo que el fuego, las zonas Seveso o el humo alcanzan, como puntos con su minuto, su efecto y su nombre
const COLOR_EFECTO = { llamas: "#b3261e", derivada: "#a14a00", humo: "#4a4a4a" };
const ORDEN_EFECTO = { llamas: 0, derivada: 1, humo: 2 };
const ORDEN_VULNERABILIDAD = { muy_alta: 0, alta: 1, moderada: 2, baja: 3 };
function afectado(lon, lat, props) {
  const efecto = props.tipo;
  return { type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] },
    properties: { ...props, color: COLOR_EFECTO[efecto], orden: props.orden ?? 10 * ORDEN_EFECTO[efecto] } };
}

function cosasAfectadas(d) {
  const lista = [];
  const centros = (arr, tipo) => { for (const a of arr) lista.push(afectado(a.lon, a.lat, { id: a.id, clase: "centro", tipo, minutos: a.minutos,
    subtipo: a.subtipo, nombre: rotulo(a), orden: 10 * ORDEN_EFECTO[tipo] + ORDEN_VULNERABILIDAD[a.vulnerabilidad] })); };
  centros(d.activos_llamas, "llamas"); centros(d.cascada.activos, "derivada"); centros(d.humo.activos, "humo");
  for (const m of d.municipios) if (m.minutos > 0)
    lista.push(afectado(m.lon, m.lat, { clase: "municipio", tipo: "llamas", minutos: m.minutos, nombre: `${voz.ElAgente} entra en ${m.nombre}`, orden: -1 }));
  // Carreteras y vías de tren: con el humo, en su primer punto bajo el humo; con el fuego, en el punto por el que llega
  for (const r of (d.vias || {}).resumen || []) {
    const nombre = unir(...tipoVia(r));
    if (r.humo != null) lista.push(afectado(r.lon, r.lat, { clase: "via", tipo: "humo", minutos: r.humo, nombre }));
    if (r.llamas != null) lista.push(afectado(r.lon_llamas ?? r.lon, r.lat_llamas ?? r.lat, { clase: "via", tipo: "llamas", minutos: r.llamas, nombre }));
  }
  // Núcleos de población, instalaciones Seveso y conducción alcanzados por el fuego
  for (const p of d.poblaciones || [])
    lista.push(afectado(p.lon, p.lat, { clase: "poblacion", tipo: "llamas", minutos: p.minutos, nombre: `Núcleo (IGN) · ${p.nombre}`, punto: true, orden: -1 }));
  for (const i of d.cascada.instalaciones_seveso)
    lista.push(afectado(i.lon, i.lat, { clase: "seveso", tipo: "llamas", minutos: i.minutos, nombre: `Instalación Seveso · ${i.id}`, orden: -1 }));
  for (const tr of tramosConduccion(d))
    lista.push(afectado(tr.lon, tr.lat, { clase: "conduccion", tipo: "llamas", minutos: tr.minutos, nombre: "Conducción de hidrocarburos", orden: -1 }));
  const tp = d.trenes_programados || { estaciones: [], trenes: [] };
  for (const e of tp.estaciones) {
    const lineas = [...new Set(tp.trenes.filter((t) => t.estacion === e.nombre).map((t) => t.linea))];
    for (const tipo of ["humo", "llamas"]) if (e[tipo] != null)
      lista.push(afectado(e.lon, e.lat, { clase: "estacion", tipo, minutos: e[tipo], punto: true,
        nombre: `Estación de Cercanías · ${e.nombre}${lineas.length ? ` (${lineas.join(", ")})` : ""}` }));
  }
  return lista;
}

// Avisos en globo: todo lo que va a alcanzar el fuego, cada uno con su símbolo, en el punto
// por el que llega, con la cuenta atrás; los centros, además, con la flecha por la ruta del fuego
const SIMBOLO_AVISO = {
  via: `<span class="linea-via" style="border-color:#d1121b"></span>`,
  tren: `<span class="linea-via tren-aviso"></span>`,
  poblacion: `<span class="simbolo poblacion-aviso"></span>`,
  seveso: `<span class="simbolo circulo seveso-aviso"></span>`,
  conduccion: `<span class="linea-via conduccion"></span>`,
};
// Tipo y nombre de una vía del resumen: «Carretera · A-6», «Carretera · sin código», «Vía de ferrocarril»
const tipoVia = (r) => r.tipo === "carretera"
  ? ["Carretera", r.via === "Carreteras sin código" ? "sin código" : r.via] : [r.via.replace(/^Vías/, "Vía"), ""];
const unir = (tipo, nombre) => nombre ? `${tipo} · ${nombre}` : tipo;
// Color de la franja de la cartela según lo que es; el cuerpo, según la urgencia
const COLOR_CARTELA = { poblacion: "#5f5f5f", via: "#2b2b2b", cascada: CASCADA.naranja };
function listaAvisos(d) {
  const dist = d.distancia_alcanzado_m, lista = [];
  for (const a of d.activos_llamas) {   // todos los centros alcanzados por el fuego, de cualquier vulnerabilidad
    const f = FAMILIAS[a.familia];
    lista.push({ id: a.id, tipo: a.tipo || f.subtipos[a.subtipo][0], nombre: a.tipo && a.tipo !== a.nombre ? a.nombre : a.municipio,
      color: f.color, minutos: a.minutos, lon: a.lon, lat: a.lat, ruta: a.ruta && a.ruta.length > 1 ? a.ruta : null,
      simbolo: `<span class="simbolo ${f.subtipos[a.subtipo][1]}" style="background:${f.color};color:${f.color}"></span>`,
      alcanzado: (h) => `${voz.Agente} a menos de ${dist} m desde las ${h}` });
  }
  for (const r of (d.vias || {}).resumen || []) if (r.llamas != null) {
    const [tipo, nombre] = tipoVia(r);
    lista.push({ id: `via-${r.via}`, tipo, nombre, color: COLOR_CARTELA.via, minutos: r.llamas, lon: r.lon_llamas ?? r.lon, lat: r.lat_llamas ?? r.lat,
      simbolo: r.tipo === "carretera" ? SIMBOLO_AVISO.via : SIMBOLO_AVISO.tren,
      alcanzado: (h) => `${voz.Agente} a menos de ${dist} m desde las ${h}: probable corte` });
  }
  for (const p of d.poblaciones || [])
    // «Núcleo (IGN)» y no «Población»: el Nomenclátor llama núcleo de población también a
    // polígonos, bases, campings o instalaciones como «Iberdrola»
    lista.push({ id: `poblacion-${p.nombre}-${p.lon}`, tipo: "Núcleo (IGN)", nombre: p.nombre, color: COLOR_CARTELA.poblacion, minutos: p.minutos, lon: p.lon, lat: p.lat,
      simbolo: SIMBOLO_AVISO.poblacion, alcanzado: (h) => `${voz.Agente} a menos de ${dist} m del casco desde las ${h}` });
  for (const i of d.cascada.instalaciones_seveso)
    lista.push({ id: `seveso-${i.id}`, tipo: "Instalación Seveso", nombre: `${i.id} · ${zonasSeveso(i).map((z) => `${AMENAZA_CORTA[z.amenaza] || z.amenaza} ${km(z.radio_alerta_m)}`).join(", ")}`, color: COLOR_CARTELA.cascada, minutos: i.minutos, lon: i.lon, lat: i.lat,
      fuera_de_cupo: true, simbolo: SIMBOLO_AVISO.seveso, alcanzado: (h) => `Alcanzada a las ${h}: se activan sus zonas` });
  for (const tr of tramosConduccion(d))
    lista.push({ id: `conduccion-${tr.k}`, tipo: "Conducción de hidrocarburos", nombre: tr.k ? "otro tramo" : "", color: COLOR_CARTELA.cascada,
      minutos: tr.minutos, lon: tr.lon, lat: tr.lat, fuera_de_cupo: true, simbolo: SIMBOLO_AVISO.conduccion,
      alcanzado: (h) => tr.k ? `Alcanzado a las ${h}: se amplía la franja de 750 m` : `Alcanzada a las ${h}: se activa su franja de 750 m` });
  return lista;
}

// Tramos de la conducción que alcanza el fuego: la primera llegada y cada tramo nuevo, a más
// de 1,5 km de lo ya alcanzado, con su aviso. Las simulaciones anteriores solo traen la primera llegada
function tramosConduccion(d) {
  const c = d.cascada.conduccion;
  if (!c) return [];
  const tramos = c.tramos && c.tramos.length ? c.tramos : [{ minutos: c.primera_llegada_min, lon: c.lon, lat: c.lat, ruta: c.ruta }];
  return tramos.map((tr, k) => ({ ...tr, k, id: k ? `conducción ${k + 1}` : "conducción", ruta: tr.ruta || [] }));
}

// Trenes, incidencias y puntos de tráfico alcanzados (movilidad.js), junto a lo demás
function anadirAfectados(features) {
  mapa.getSource("afectados").setData({ type: "FeatureCollection", features: [...afectadosBase, ...features] });
  minutoPintado = -1;
  fijarTiempo(t);
}

// ----------------------------------------------------------------------------- simulador visual
function pintar(minuto) {
  const { filas, columnas, celda_m } = sim.ventana;
  const datos = pixeles.data;
  let quemadas = 0;
  for (let fila = 0; fila < filas; fila++) {
    for (let col = 0; col < columnas; col++) {
      const i = fila * columnas + col, v = llegada[i], p = i * 4;
      if (v <= minuto) {
        quemadas++;
        const color = v > minuto - FRENTE_MIN ? voz.colores[1] : voz.colores[0];
        datos[p] = color[0]; datos[p + 1] = color[1]; datos[p + 2] = color[2]; datos[p + 3] = color[3];
      } else datos[p + 3] = 0;
    }
  }
  dibujo.putImageData(pixeles, 0, 0);
  pintarHumo(minuto);
  mapa.setFilter("validacion-focos", ["<=", ["get", "minutos"], minuto]);
  const yaAfectado = ["<=", ["get", "minutos"], minuto];
  mapa.setFilter("afectados", ["all", yaAfectado, ["==", ["get", "clase"], "centro"]]);
  mapa.setFilter("afectados-punto", ["all", yaAfectado, ["==", ["get", "punto"], true]]);
  // El nombre de todo lo afectado se queda hasta el final; si choca con otro, manda la prioridad
  mapa.setFilter("afectados-nombre", yaAfectado);
  // Punto de los destinos de la cascada: tenue hasta la hora previa a la llegada (el nombre y la hora van en su globo)
  // Aparece cuando entra en la vista del incendio (tanta antelación como tiempo lleva): la animación
  // arranca solo con la ignición, y la flecha de aproximación y su destino salen juntos
  const alcanzada = ["<=", ["get", "minutos"], minuto];
  mapa.setFilter("cascada-destinos-punto", ["<=", ["-", ["get", "minutos"], minuto], minuto]);
  const destacada = ["any", alcanzada, ["<=", ["-", ["get", "minutos"], minuto], antelacion(minuto, CASCADA.aproximacion_min)]];
  mapa.setPaintProperty("cascada-destinos-punto", "circle-opacity", ["case", destacada, 1, 0.6]);
  mapa.setPaintProperty("cascada-destinos-punto", "circle-stroke-opacity", ["case", destacada, 1, 0.6]);
  filtrosCascada(minuto);
  // Isocronas de las próximas 3 horas, más tenues cuanto más lejanas
  const vista = antelacion(minuto, ISOCRONAS_MIN);
  const proximas = ["all", [">", ["get", "minutos"], minuto], ["<=", ["get", "minutos"], minuto + vista]];
  const tenue = ["interpolate", ["linear"], ["get", "minutos"], minuto, 0.95, minuto + Math.max(vista, 1), 0.3];
  for (const id of ["isocronas-halo", "isocronas", "isocronas-hora"]) mapa.setFilter(id, proximas);
  mapa.setPaintProperty("isocronas", "line-opacity", tenue);
  mapa.setPaintProperty("isocronas-halo", "line-opacity", ["*", 0.7, tenue]);
  mapa.setPaintProperty("isocronas-hora", "text-opacity", tenue);
  const llamas = ["coalesce", ["get", "llamas"], NUNCA_MIN], humo = ["coalesce", ["get", "humo"], NUNCA_MIN];
  mapa.setFilter("vias-borde", ["<=", ["min", llamas, humo], minuto]);
  const tren = ["in", ["get", "tipo"], ["literal", ["ferrocarril", "metro", "tranvia"]]];
  const humoAhora = ["all", ["<=", humo, minuto], [">", llamas, minuto]], fuegoAhora = ["<=", llamas, minuto];
  mapa.setFilter("vias-humo", ["all", humoAhora, ["!", tren]]);
  mapa.setFilter("vias-fuego", ["all", fuegoAhora, ["!", tren]]);
  mapa.setFilter("vias-humo-tren", ["all", humoAhora, tren]);
  mapa.setFilter("vias-fuego-tren", ["all", fuegoAhora, tren]);
  return quemadas * celda_m * celda_m / 1e6;
}

// Personas hasta un minuto: población del Censo 2021 de las celdas de 1 km que toca el
// fuego y plazas de los centros sociales alcanzados por las llamas
function personasHasta(minuto, d = sim) {
  const r = { poblacion: 0, menores_16: 0, mayores_64: 0, plazas: 0 };
  for (const c of d.poblacion_celdas || []) if (c.minutos <= minuto) { r.poblacion += c.poblacion; r.menores_16 += c.menores_16; r.mayores_64 += c.mayores_64; }
  for (const a of d.activos_llamas) if (a.minutos <= minuto && a.familia === "atencion_social") r.plazas += a.plazas || 0;
  return r;
}

function fijarTiempo(nuevo) {
  t = Math.max(0, Math.min(sim.horizonte_min, nuevo));
  const minuto = Math.floor(t);
  $("#rep-barra").value = minuto;
  if (minuto === minutoPintado) return;
  minutoPintado = minuto;
  const km2 = pintar(minuto);
  const hora = new Date(new Date(sim.ignicion.hora).getTime() + minuto * 60000);
  const p = personasHasta(minuto);
  $("#rep-reloj").textContent = `+${duracion(minuto)} · ${hora.toLocaleString("es-ES", { weekday: "short", hour: "2-digit", minute: "2-digit" })} · ${km2.toLocaleString("es-ES", { maximumFractionDigits: 2 })} km²` +
    ` · ${numero(p.poblacion)} hab. en ${voz.celdas}` + (p.plazas ? ` · ${numero(p.plazas)} plazas sociales` : "") +
    (sim.borde_min != null && minuto >= sim.borde_min ? " · fuera de la zona de cálculo" : "");
  for (const el of $("#resultado").querySelectorAll("[data-min]")) el.classList.toggle("pendiente", +el.dataset.min > minuto);
  // Instalaciones y conducciones alcanzadas al avanzar (no en saltos de más de hora y media): animación de activación
  if (minutoCascada >= 0 && minuto > minutoCascada && minuto - minutoCascada <= 90)
    for (const o of origenesCascada) if (o.minutos > minutoCascada && o.minutos <= minuto) animarActivacion(o);
  minutoCascada = minuto;
  comunicar(minuto, hora, km2);
  actualizarAvisos(minuto);
  actualizarCronologiaMapa(minuto);
}

// ----------------------------------------------------------------------------- cascada animada
function prepararCascada(d, zonasSeveso) {
  origenesCascada = d.cascada.instalaciones_seveso.map((i) => ({ id: i.id, lon: i.lon, lat: i.lat, minutos: i.minutos, ruta: i.ruta || [],
    zonas: zonasSeveso.filter((z) => z.properties.id === i.id) }));
  const c = d.cascada.conduccion, franjas = [];
  if (c && c.franja) {
    for (const f of c.franja) for (const anillo of f.coords)
      franjas.push({ type: "Feature", geometry: { type: "Polygon", coordinates: [anillo] }, properties: { id: "conducción", minutos: f.minutos, hasta: f.hasta } });
    // Cada tramo alcanzado es un origen: flecha de aproximación y pulso; la franja que crece, solo con la primera llegada
    for (const tr of tramosConduccion(d))
      origenesCascada.push({ id: tr.id, lon: tr.lon, lat: tr.lat, minutos: tr.minutos, ruta: tr.ruta, conduccion: true,
        zonas: tr.k ? [] : franjas.filter((f) => f.properties.minutos === c.franja[0].minutos).map((f) => ({ ...f, properties: { ...f.properties, zona: "franja" } })) });
  }
  mapa.getSource("conduccion-franja").setData({ type: "FeatureCollection", features: franjas });
  // Flechas desde la instalación (o el punto alcanzado de la conducción) a los centros de alta y muy alta de sus zonas;
  // en la conducción, desde el tramo ya alcanzado más cercano al centro
  const flechas = [], puntas = [];
  const cerca = (a) => (o) => Math.hypot((o.lon - a.lon) * Math.cos((a.lat * Math.PI) / 180), o.lat - a.lat);
  for (const a of d.cascada.activos) {
    const o = a.origen === "conducción"
      ? origenesCascada.filter((x) => x.conduccion && x.minutos <= a.minutos + 0.1).sort((p, q) => cerca(a)(p) - cerca(a)(q))[0]
      : origenesCascada.find((x) => x.id === a.origen);
    if (!o || !(a.vulnerabilidad === "alta" || a.vulnerabilidad === "muy_alta")) continue;
    const linea = [[o.lon, o.lat], [a.lon, a.lat]];
    flechas.push({ type: "Feature", geometry: { type: "LineString", coordinates: linea }, properties: { minutos: a.minutos } });
    puntas.push({ type: "Feature", geometry: { type: "Point", coordinates: linea[1] }, properties: { minutos: a.minutos, rumbo: rumboEntre(...linea) } });
  }
  mapa.getSource("cascada-flechas").setData({ type: "FeatureCollection", features: flechas });
  mapa.getSource("cascada-puntas").setData({ type: "FeatureCollection", features: puntas });
  animando.clear();
  minutoCascada = -1;
}

function filtrosCascada(minuto) {
  // Las zonas fijas se ocultan solo mientras crecen; si el navegador detiene los cuadros (pestaña oculta), reaparecen
  const enCurso = [...animando].filter(([, a]) => performance.now() - a.inicio < CASCADA.duracion_ms).map(([id]) => id);
  const fuera = ["!", ["in", ["get", "id"], ["literal", enCurso]]];
  for (const id of ["seveso-zonas", "seveso-bordes"]) mapa.setFilter(id, ["all", ["<=", ["get", "minutos"], minuto], fuera]);
  for (const id of ["conduccion-franja", "conduccion-borde"])
    mapa.setFilter(id, ["all", ["<=", ["get", "minutos"], minuto], [">", ["coalesce", ["get", "hasta"], NUNCA_MIN], minuto], fuera]);
  for (const id of ["cascada-flechas", "cascada-puntas"])
    mapa.setFilter(id, ["all", ["<=", ["get", "minutos"], minuto], [">", ["get", "minutos"], minuto - CASCADA.flechas_min]]);
}

// Polígono escalado alrededor de un punto: las zonas crecen desde la instalación
function escalar(f, [x0, y0], e) {
  return { ...f, geometry: { type: "Polygon", coordinates: f.geometry.coordinates.map((anillo) => anillo.map(([x, y]) => [x0 + e * (x - x0), y0 + e * (y - y0)])) } };
}

function animarActivacion(o) {
  const vacio = !animando.size;
  animando.set(o.id, { o, inicio: performance.now() });
  if (vacio) requestAnimationFrame(cuadroCascada);
  // Seguro por si el navegador no da cuadros (pestaña oculta): al acabar el tiempo, quita lo que ya terminó
  setTimeout(() => {
    for (const [id, a] of animando) if (performance.now() - a.inicio >= CASCADA.duracion_ms) animando.delete(id);
    if (!animando.size) for (const id of ["cascada-anim", "cascada-pulso"]) mapa.getSource(id).setData(vacioFC());
    if (sim) filtrosCascada(minutoPintado);
  }, CASCADA.duracion_ms + 50);
}

function cuadroCascada(ahora) {
  const zonas = [], pulsos = [];
  for (const [id, a] of animando) {
    const f = (ahora - a.inicio) / CASCADA.duracion_ms;
    if (f >= 1) { animando.delete(id); continue; }
    const e = Math.max(1 - (1 - f) ** 3, 0.02);
    for (const z of a.o.zonas) zonas.push(escalar(z, [a.o.lon, a.o.lat], e));
    for (const k of [0, 1, 2]) {
      const g = f * 1.6 - k * 0.3;
      if (g > 0 && g < 1) pulsos.push({ type: "Feature", geometry: { type: "Point", coordinates: [a.o.lon, a.o.lat] }, properties: { r: 8 + 46 * g, o: 1 - g } });
    }
  }
  mapa.getSource("cascada-anim").setData({ type: "FeatureCollection", features: zonas });
  mapa.getSource("cascada-pulso").setData({ type: "FeatureCollection", features: pulsos });
  if (sim) filtrosCascada(minutoPintado);
  if (animando.size) requestAnimationFrame(cuadroCascada);
}

function esquemaCascada(d, horaDe) {
  const cadenas = [];
  const centros = (origen) => {
    const g = d.cascada.activos.filter((a) => a.origen === origen);
    if (!g.length) return `<span class="eslabon centros">sin centros en sus zonas</span>`;
    const n = (v) => g.filter((a) => v.includes(a.vulnerabilidad)).length;
    const partes = [[n(["muy_alta"]), "muy alta"], [n(["alta"]), "alta"], [n(["moderada", "baja"]), "moderada o baja"]].filter(([k]) => k)
      .map(([k, t]) => `${k} de vulnerabilidad ${t}`);
    return `<span class="eslabon centros"><strong>${g.length} centro${g.length > 1 ? "s" : ""}</strong> <small>${partes.join(" · ")}</small></span>`;
  };
  const flecha = `<span class="flecha-esquema" aria-hidden="true"></span>`;
  for (const i of d.cascada.instalaciones_seveso)
    cadenas.push(`<div class="cadena" data-min="${i.minutos}"><span class="eslabon fuego">Fuego a las ${horaDe(i.minutos)}</span>${flecha}` +
      `<span class="eslabon instalacion"><strong>${html(i.id)}</strong> <small>${i.amenazas.map(html).join(", ")}</small></span>${flecha}` +
      `<span class="eslabon zona">${zonasSeveso(i).map((z) => `${html(z.amenaza)}: intervención ${km(z.radio_intervencion_m)} ` +
        `<small>alerta ${km(z.radio_alerta_m)}</small>`).join("<br>")}</span>${flecha}${centros(i.id)}</div>`);
  const c = d.cascada.conduccion;
  if (c) cadenas.push(`<div class="cadena" data-min="${c.primera_llegada_min}"><span class="eslabon fuego">Fuego a las ${horaDe(c.primera_llegada_min)}</span>${flecha}` +
    `<span class="eslabon instalacion"><strong>Conducción</strong> <small>de hidrocarburos</small></span>${flecha}` +
    `<span class="eslabon zona">Franja de 750 m <small>alrededor del tramo</small></span>${flecha}${centros("conducción")}</div>`);
  return cadenas.length ? `<div class="esquema-cascada">${cadenas.join("")}</div>` : "";
}

// ----------------------------------------------------------------------------- carreteras, vías y trenes programados
const nombreVia = (r) => r.tipo === "carretera" && r.via !== "Carreteras sin código" ? `la <strong>${html(r.via)}</strong>` : `<strong>${html(r.via.toLowerCase())}</strong>`;

function seccionVias(d, horaDe) {
  if (!d.vias) return "";
  const dist = d.distancia_alcanzado_m, primero = (r) => Math.min(...[r.llamas, r.humo].filter((m) => m != null));
  const vias = d.vias.resumen.map((r) => `<li data-min="${primero(r)}" data-lon="${r.lon}" data-lat="${r.lat}"><span class="hora">${horaDe(primero(r))}</span>` +
    `<span class="nombre"><span class="linea-via" style="border-color:${r.llamas != null ? "#d1121b" : "#5f5f5f"}"></span>${html(r.via)}<br><span class="meta">` +
    [r.llamas != null ? `${voz.agente} a menos de ${dist} m a las ${horaDe(r.llamas)} (${r.km_llamas.toLocaleString("es-ES")} km en 24 h): probable corte` : "",
      r.humo != null ? `humo a las ${horaDe(r.humo)}: visibilidad reducida` : ""].filter(Boolean).join(" · ") +
    `</span></span><span class="marca ${r.llamas != null ? "llamas" : "humo"}">+${duracion(primero(r))}</span></li>`).join("");
  const tp = d.trenes_programados, fecha = (s) => `${s.slice(6, 8)}-${s.slice(4, 6)}-${s.slice(0, 4)}`;
  const equivalente = tp && tp.dia_equivalente
    ? `<p class="meta">La fecha simulada está fuera del horario de Renfe descargado (del ${fecha(tp.horario_desde)} al ${fecha(tp.horario_hasta)}): se usan los trenes del ${fecha(tp.dia_equivalente)}, el mismo día de la semana.</p>`
    : "";
  const trenes = !tp ? "" : !tp.con_horario
    ? `<p class="meta">El horario de Renfe cubre del ${fecha(tp.horario_desde)} al ${fecha(tp.horario_hasta)}: no hay trenes programados para la fecha simulada.` +
      (tp.estaciones.length ? ` Estaciones afectadas: ${tp.estaciones.map((e) => html(e.nombre)).join(", ")}.` : "") + `</p>`
    : tp.trenes.length
      ? `<ul class="activos">${tp.trenes.map((t) => `<li data-min="${t.minutos}" data-lon="${t.lon}" data-lat="${t.lat}"><span class="hora">${horaDe(t.minutos)}</span>` +
          `<span class="nombre"><span class="simbolo circulo" style="background:#2b2b2b"></span><strong>${html(t.linea)}</strong> por ${html(t.estacion)}` +
          `<br><span class="meta">${t.trenes} tren${t.trenes > 1 ? "es pasan" : " pasa"}, en los dos sentidos, con la estación bajo el humo o con ${voz.elAgente} a menos de ${dist} m; el primero, hacia ${html(t.hacia)}` +
          (t.trenes_llamas ? `; ${t.trenes_llamas} con el fuego, desde las ${horaDe(t.primero_llamas)}` : "") + `</span></span>` +
          `<span class="marca ${t.efecto}">+${duracion(t.minutos)}</span></li>`).join("")}</ul>`
      : `<p class="meta">${tp.estaciones.length ? `Estaciones afectadas (${tp.estaciones.map((e) => html(e.nombre)).join(", ")}), sin trenes programados mientras lo están.` : "El fuego y el humo no alcanzan estaciones de Cercanías."}</p>`;
  const trenesConAviso = equivalente + trenes;
  return `<h3>Carreteras y vías afectadas (${d.vias.resumen.length})</h3>
    <p class="meta">Rojo: fuego a menos de ${dist} m de algún punto del tramo (probable corte). Gris: bajo el humo (visibilidad reducida). Carreteras de la Base Topográfica Armonizada de la Comunidad.</p>
    ${vias ? `<ul class="activos">${vias}</ul>` : `<p class="meta">Ninguna en 24 h.</p>`}
    <h3>Trenes de Cercanías programados</h3>
    <p class="meta">Horario de Renfe: trenes que pasan por una estación ya afectada, por línea y estación. No se estima cuántas personas llevan.</p>
    ${trenesConAviso}`;
}

// ----------------------------------------------------------------------------- cronología de sucesos
const km = (m) => m < 1000 ? `${numero(m)} m` : `${(m / 1000).toLocaleString("es-ES", { maximumFractionDigits: 1 })} km`;
// Zonas de cada amenaza de una instalación Seveso, de mayor a menor alcance. Cada amenaza tiene sus radios: la nube
// tóxica puede llegar a kilómetros y la sobrepresión quedarse en decenas de metros. Las simulaciones guardadas sin
// «zonas» dan los radios mayores de la instalación para todas sus amenazas.
const zonasSeveso = (i) => i.zonas
  || [{ amenaza: i.amenazas.join(", "), radio_intervencion_m: i.radio_intervencion_m, radio_alerta_m: i.radio_alerta_m }];
const radiosSeveso = (i) => zonasSeveso(i).map((z) =>
  `${html(z.amenaza)} (intervención ${km(z.radio_intervencion_m)}, alerta ${km(z.radio_alerta_m)})`).join("; ");
// Nombre corto de cada amenaza Seveso, para que la cartela quepa en dos líneas
const AMENAZA_CORTA = { "nube tóxica": "nube tóxica", "sobrepresión por explosión": "explosión", "radiación térmica": "radiación" };
// Amenaza por la que un centro queda en una zona Seveso («zona de alerta por nube tóxica»); la conducción solo tiene una
const porAmenaza = (a) => a.amenaza_derivada && a.origen !== "conducción" ? ` por ${html(a.amenaza_derivada)}` : "";
const textoPlano = (s) => s.replace(/<[^>]+>/g, "");

function construirSucesos(d) {
  const dist = d.distancia_alcanzado_m, lista = [];
  const de = (a) => `<strong>${html(rotulo(a))}</strong> (${html(a.municipio)}, vulnerabilidad ${VULNERABILIDAD[a.vulnerabilidad]})`;
  const agrupar = (arr, clave) => arr.reduce((m, a) => m.set(clave(a), [...(m.get(clave(a)) || []), a]), new Map());
  lista.push({ min: 0, tipo: "inicio", texto: d.tipo === "presa" ? `Rotura de la <strong>${html(d.presa.nombre)}</strong> (${html(d.ignicion.municipio)})` : `Ignición en <strong>${html(d.ignicion.municipio)}</strong>`, lon: d.ignicion.lon, lat: d.ignicion.lat });
  for (const m of d.municipios) if (m.minutos > 0)
    lista.push({ min: m.minutos, tipo: "municipios", texto: `${voz.ElAgente} entra en <strong>${html(m.nombre)}</strong>`, lon: m.lon, lat: m.lat });
  for (const p of d.poblaciones || [])
    lista.push({ min: p.minutos, tipo: "municipios", texto: `${voz.Agente} a menos de ${dist} m del <strong>núcleo ${html(p.nombre)}</strong> (IGN)`, lon: p.lon, lat: p.lat });
  // Centros: uno a uno los de vulnerabilidad alta y muy alta; los demás, agrupados por hora
  const resto = [];
  for (const a of d.activos_llamas) {
    if (a.vulnerabilidad === "alta" || a.vulnerabilidad === "muy_alta")
      lista.push({ min: a.minutos, tipo: "centros", clave: a.vulnerabilidad === "muy_alta", texto: `${voz.Agente} a menos de ${dist} m de ${de(a)}`, lon: a.lon, lat: a.lat });
    else resto.push(a);
  }
  for (const g of agrupar(resto, (a) => Math.floor(a.minutos / 60)).values())
    lista.push({ min: g[0].minutos, tipo: "centros", lon: g[0].lon, lat: g[0].lat, texto: g.length === 1
      ? `${voz.Agente} a menos de ${dist} m de ${de(g[0])}` : `${voz.Agente} a menos de ${dist} m de <strong>${g.length} centros</strong> de vulnerabilidad moderada o baja` });
  // Efecto cascada
  for (const i of d.cascada.instalaciones_seveso)
    lista.push({ min: i.minutos, tipo: "cascada", clave: true, lon: i.lon, lat: i.lat,
      texto: `Alcanza la instalación Seveso <strong>${html(i.id)}</strong>: se activan sus zonas de ${radiosSeveso(i)}` });
  for (const [origen, g] of agrupar(d.cascada.activos, (a) => a.origen)) {
    const ins = d.cascada.instalaciones_seveso.find((i) => i.id === origen) || g[0];
    const min = Math.min(...g.map((a) => a.minutos));
    lista.push({ min, tipo: "cascada", lon: ins.lon, lat: ins.lat, texto: g.length === 1
      ? `${de(g[0])} queda en la zona de ${html(g[0].zona)}${porAmenaza(g[0])} de ${html(origen)}` : `<strong>${g.length} centros</strong> quedan en las zonas de ${html(origen)}` });
  }
  for (const tr of tramosConduccion(d))
    lista.push({ min: tr.minutos, tipo: "cascada", clave: true, lon: tr.lon, lat: tr.lat, texto: tr.k
      ? "Alcanza <strong>otro tramo de la conducción de hidrocarburos</strong>: se amplía su franja de efectos en 750 m"
      : "Alcanza una <strong>conducción de hidrocarburos</strong>: se activa su franja de efectos en 750 m alrededor del tramo" });
  // Carreteras y vías: el fuego, uno a uno; el humo, agrupado por minuto
  if (d.vias) {
    for (const r of d.vias.resumen) if (r.llamas != null)
      lista.push({ min: r.llamas, tipo: "vias", lon: r.lon, lat: r.lat, texto: `${voz.Agente} a menos de ${dist} m de ${nombreVia(r)}: probable corte` });
    for (const g of agrupar(d.vias.resumen.filter((r) => r.humo != null), (r) => r.humo).values()) {
      const nombres = g.map(nombreVia);
      lista.push({ min: g[0].humo, tipo: "vias", lon: g[0].lon, lat: g[0].lat, texto: `Humo sobre ${nombres.length > 4
        ? `${nombres.slice(0, 3).join(", ")} y ${nombres.length - 3} vías más` : nombres.join(", ").replace(/, ([^,]*)$/, " y $1")}: visibilidad reducida` });
    }
  }
  for (const t of (d.trenes_programados || {}).trenes || []) {
    lista.push({ min: t.minutos, tipo: "vias", lon: t.lon, lat: t.lat, texto: `Primer <strong>${html(t.linea)}</strong> por ${html(t.estacion)} ` +
      (t.efecto === "llamas" ? `con ${voz.elAgente} a menos de ${dist} m` : "bajo el humo") + `, hacia ${html(t.hacia)} (${t.trenes} tren${t.trenes > 1 ? "es" : ""} de la línea en 24 h)` });
    if (t.efecto === "humo" && t.primero_llamas != null)
      lista.push({ min: t.primero_llamas, tipo: "vias", lon: t.lon, lat: t.lat, texto: `Primer <strong>${html(t.linea)}</strong> por ${html(t.estacion)} con ${voz.elAgente} a menos de ${dist} m` });
  }
  // Humo sobre centros, agrupado por minuto
  for (const g of agrupar(d.humo.activos, (a) => a.minutos).values())
    lista.push({ min: g[0].minutos, tipo: "otros", lon: g[0].lon, lat: g[0].lat, texto: g.length === 1
      ? `${de(g[0])} queda bajo el humo` : `<strong>${g.length} centros</strong> quedan bajo el humo` });
  return lista.sort((a, b) => a.min - b.min);
}

// Trenes, incidencias de la DGT y tráfico de la ciudad alcanzados (movilidad.js, cuando responde la consulta)
function anadirSucesosMovilidad(d) {
  const efecto = (e) => e.minutos_llamas === e.minutos ? `${voz.agente} a menos de ${d.distancia_alcanzado_m} m` : "bajo el humo";
  for (const e of d.trenes.afectados || [])
    sucesos.push({ min: e.minutos, tipo: "otros", lon: e.lon, lat: e.lat, texto: `Tren <strong>${html(e.linea)}</strong> en su posición actual: ${efecto(e)}` });
  for (const e of d.incidencias.afectados || [])
    sucesos.push({ min: e.minutos, tipo: "otros", lon: e.lon, lat: e.lat, texto: `Incidencia de la DGT (${html(e.tipo)}): ${efecto(e)}` });
  const ciudad = d.ciudad.afectados || [];
  if (ciudad.length) {
    const primero = ciudad.reduce((a, b) => (b.minutos < a.minutos ? b : a));
    sucesos.push({ min: primero.minutos, tipo: "otros", lon: primero.lon, lat: primero.lat,
      texto: `<strong>${ciudad.length} puntos de tráfico</strong> de la ciudad de Madrid alcanzados por el fuego o el humo` });
  }
  sucesos.sort((a, b) => a.min - b.min);
  pintarCronologia();
}

const sucesosVisibles = () => sucesos.filter((s) => s.tipo === "inicio" || tiposActivos.has(s.tipo));

function pintarCronologia() {
  const caja = $("#cronologia");
  if (!caja || !sim) return;
  const hora0 = new Date(sim.ignicion.hora).getTime(), horaDe = (min) => hhmm(new Date(hora0 + min * 60000));
  const vis = sucesosVisibles();
  caja.innerHTML = `<h3>Cronología</h3>
    <p class="tipos-suceso">${Object.entries(TIPOS_SUCESO).map(([k, n]) =>
      `<label><input type="checkbox" data-tipo="${k}"${tiposActivos.has(k) ? " checked" : ""}><span class="punto-suceso ${k}"></span>${n}</label>`).join("")}</p>
    <p class="meta">La reproducción se detiene en los sucesos clave, marcados en rojo: instalaciones Seveso y conducciones alcanzadas y centros de vulnerabilidad muy alta.</p>
    <ul class="activos cronologia">${vis.map((s, i) => `<li data-min="${s.min}" data-suceso="${i}" class="${s.clave ? "clave" : ""}">` +
      `<span class="hora">${horaDe(s.min)}</span><span class="nombre"><span class="punto-suceso ${s.tipo}"></span>${s.texto}</span>` +
      `<span class="meta">+${duracion(s.min)}</span></li>`).join("")}</ul>`;
  for (const cb of caja.querySelectorAll("input[data-tipo]")) cb.onchange = () => {
    cb.checked ? tiposActivos.add(cb.dataset.tipo) : tiposActivos.delete(cb.dataset.tipo);
    pintarCronologia();
  };
  const ir = (s) => { reproducir(false); fijarTiempo(Math.ceil(s.min)); if (s.lon != null) mapa.easeTo({ center: [s.lon, s.lat], zoom: Math.max(mapa.getZoom(), 12.5) }); };
  for (const li of caja.querySelectorAll("li[data-suceso]")) li.onclick = () => ir(vis[+li.dataset.suceso]);
  $("#rep-sucesos").innerHTML = vis.filter((s) => s.min > 0).map((s, i) =>
    `<span class="tic ${s.tipo}${s.clave ? " clave" : ""}" data-i="${i}" style="left: calc(8px + (100% - 16px) * ${s.min / sim.horizonte_min})" ` +
    `title="${horaDe(s.min)} · ${html(textoPlano(s.texto))}"></span>`).join("");
  const conMarca = vis.filter((s) => s.min > 0);
  for (const tic of $("#rep-sucesos").querySelectorAll(".tic")) tic.onclick = () => ir(conMarca[+tic.dataset.i]);
  cronologiaPintada = "";
  minutoPintado = -1;
  fijarTiempo(t);
}

function actualizarCronologiaMapa(minuto) {
  // De arriba abajo: el suceso más reciente, al final
  const ultimos = sucesosVisibles().filter((s) => s.min <= minuto).slice(-SUCESOS_EN_MAPA);
  const clave = ultimos.map((s) => `${s.min}${s.texto}`).join("|");
  if (clave === cronologiaPintada) return;
  const ultimo = ultimos.at(-1), nuevo = !!ultimo && !cronologiaPintada.endsWith(`${ultimo.min}${ultimo.texto}`);
  cronologiaPintada = clave;
  const hora0 = new Date(sim.ignicion.hora).getTime();
  $("#cronologia-mapa").innerHTML = `<h4>Últimos sucesos</h4><ul>${ultimos.map((s, i) =>
    `<li class="${s.tipo}${s.clave ? " clave" : ""}${i === ultimos.length - 1 && nuevo ? " nuevo" : ""}"><span class="hora">${hhmm(new Date(hora0 + s.min * 60000))}</span>${s.texto}</li>`).join("")}</ul>`;
}

// ----------------------------------------------------------------------------- avisos anticipados
// Tramo de la ruta que el fuego aún no ha recorrido en el minuto dado, empezando en el frente
function tramoPendiente(ruta, minuto) {
  const i = ruta.findIndex((p) => p[2] > minuto);
  if (i < 1) return i === 0 ? ruta.map((p) => [p[0], p[1]]) : null;
  const a = ruta[i - 1], b = ruta[i], f = (minuto - a[2]) / (b[2] - a[2] || 1);
  return [[a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])], ...ruta.slice(i).map((p) => [p[0], p[1]])];
}

function rumboEntre([lon0, lat0], [lon1, lat1]) {
  const dx = (lon1 - lon0) * Math.cos((lat1 * Math.PI) / 180), dy = lat1 - lat0;
  return (Math.atan2(dx, dy) * 180) / Math.PI;
}

function actualizarAvisos(minuto) {
  const hora0 = new Date(sim.ignicion.hora).getTime();
  // Las instalaciones Seveso y la conducción tienen siempre su cartela, fuera del cupo de 5:
  // disparan la cascada y, en zonas densas, lo más próximo llenaba el cupo y se quedaban sin aviso hasta ser alcanzadas
  const enVentana = avisos.filter((a) => minuto >= a.minutos - antelacion(minuto, AVISO.antelacion_min) && minuto < a.minutos + AVISO.permanencia_min)
    .sort((a, b) => a.minutos - b.minutos);
  const vigentes = [...enVentana.filter((a) => a.fuera_de_cupo), ...enVentana.filter((a) => !a.fuera_de_cupo).slice(0, AVISO.simultaneos)];
  const ids = new Set(vigentes.map((a) => a.id));
  for (const [id, m] of globos) if (!ids.has(id)) { m.remove(); globos.delete(id); }
  const rutas = [], puntas = [];
  for (const a of vigentes) {
    const alcanzado = minuto >= a.minutos;
    let m = globos.get(a.id);
    if (!m) {
      // Marcador de tamaño cero en el objetivo: dentro, el conector (SVG) y la cartela, desplazada (colocarCartelas)
      const caja = document.createElement("div");
      caja.className = "cartela";
      caja.innerHTML = `<svg class="conector"><line x1="0" y1="0" x2="0" y2="0"/><circle cx="0" cy="0" r="4"/></svg>` +
        `<div class="globo-aviso"><div class="franja" style="background:${a.color}">${a.simbolo}${html(a.tipo)}</div>` +
        `<div class="cuerpo">${a.nombre ? `<span class="nombre">${html(a.nombre)}</span>` : ""}<span class="cuenta"></span></div></div>`;
      caja.querySelector(".globo-aviso").onclick = (ev) => { ev.stopPropagation(); mapa.easeTo({ center: [a.lon, a.lat], zoom: Math.max(mapa.getZoom(), 14) }); };
      m = new maplibregl.Marker({ element: caja, anchor: "center" }).setLngLat([a.lon, a.lat]).addTo(mapa);
      caja.hidden = modo !== "crisis";
      globos.set(a.id, m);
    }
    const caja = m.getElement(), el = caja.querySelector(".globo-aviso"), llega = hhmm(new Date(hora0 + a.minutos * 60000));
    // Urgencia: a más de una hora, ámbar; a menos, naranja; alcanzado, rojo
    caja.classList.toggle("alcanzado", alcanzado);
    caja.classList.toggle("cerca", !alcanzado && a.minutos - minuto <= AVISO.urgente_min);
    el.querySelector(".cuenta").textContent = alcanzado
      ? a.alcanzado(llega)
      : `Llega en ${duracion(a.minutos - minuto)} · hacia las ${llega}`;
    if (!alcanzado && a.ruta) {
      // La flecha acaba en el propio centro: la ruta llega a la celda que arde antes a menos de 250 m y
      // de ahí, en un último tramo, al centro; sin ese tramo, la punta quedaba a un lado y no apuntaba a nada
      const tramo = tramoPendiente(a.ruta, minuto);
      if (tramo && tramo.length > 1) {
        rutas.push({ type: "Feature", geometry: { type: "LineString", coordinates: tramo }, properties: {} });
        puntas.push({ type: "Feature", geometry: { type: "Point", coordinates: tramo.at(-1) },
          properties: { rumbo: rumboEntre(tramo.at(-2), tramo.at(-1)) } });
      }
    }
  }
  for (const o of origenesCascada) if (minuto >= o.minutos - antelacion(minuto, CASCADA.aproximacion_min) && minuto < o.minutos && o.ruta.length > 1) {
    const tramo = tramoPendiente(o.ruta, minuto);
    if (tramo && tramo.length > 1) {
      rutas.push({ type: "Feature", geometry: { type: "LineString", coordinates: tramo }, properties: { color: CASCADA.naranja } });
      puntas.push({ type: "Feature", geometry: { type: "Point", coordinates: tramo.at(-1) },
        properties: { rumbo: rumboEntre(tramo.at(-2), tramo.at(-1)), icono: "punta-cascada" } });
    }
  }
  mapa.getSource("aviso-rutas").setData({ type: "FeatureCollection", features: rutas });
  mapa.getSource("aviso-puntas").setData({ type: "FeatureCollection", features: puntas });
  colocarCartelas(minuto, vigentes, true);
}

// Cartelas en los espacios vacíos del mapa: nunca sobre el fuego (lo quemado, el frente y lo que arderá en la media
// hora siguiente), el humo, las zonas Seveso activadas ni los símbolos de lo alcanzado; tampoco sobre otras cartelas,
// los objetivos, sus conectores ni los paneles del mapa, y sin que su conector cruce otro. Se busca por toda la
// pantalla, lo más cerca posible del objetivo que quede vacío y preferiblemente del lado contrario al fuego; un
// conector la une al objetivo. Se mantiene donde está mientras siga en vacío, para que no salte en cada minuto; al
// mover o acercar el mapa se recolocan todas.
const CARTELA = { distancias: [30, 55, 85, 120, 170, 230, 300, 380, 470, 570, 680, 800, 950, 1100, 1300], angulos: 24,
  margen: 10, paso: 9, antelacion_min: 30,
  tapar: 1000,     // cada celda de 9 px no vacía bajo la cartela cuesta como 1.000 px de distancia: siempre se prefiere el vacío
  radial: 400,     // salir en sentido contrario al de «hacia fuera del fuego» cuesta como 800 px de distancia
  holgura_px: 150 };   // una cartela sigue en su sitio si no está más de 150 px más lejos que su hueco vacío más cercano
let cartelasVigentes = [];

// Prueba en píxeles de pantalla: ¿hay fuego (desde < llegada ≤ minuto) en este punto?
function fuegoEnPantalla(minuto, desde = -Infinity) {
  const { filas, columnas } = sim.ventana;
  const s0 = mapa.project(lonlat(0, 0)), s1 = mapa.project(lonlat(columnas, 0)), s2 = mapa.project(lonlat(0, filas));
  const ax = s1.x - s0.x, ay = s1.y - s0.y, bx = s2.x - s0.x, by = s2.y - s0.y, det = ax * by - ay * bx;
  return (x, y) => {
    const dx = x - s0.x, dy = y - s0.y;
    const col = Math.floor(((dx * by - dy * bx) / det) * columnas), fila = Math.floor(((ax * dy - ay * dx) / det) * filas);
    if (col < 0 || fila < 0 || col >= columnas || fila >= filas) return false;
    const v = llegada[fila * columnas + col];
    return v <= minuto && v > desde;
  };
}

// Prueba en píxeles de pantalla: ¿está el punto bajo la zona de humo del minuto?
function humoEnPantalla(minuto) {
  let zona = null;
  for (const z of sim.humo.zonas || []) { if (z.minutos > minuto) break; zona = z; }
  if (!zona) return () => false;
  const anillo = zona.coords.map((c) => mapa.project(c));
  const xs = anillo.map((q) => q.x), ys = anillo.map((q) => q.y);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  return (x, y) => {
    if (x < x0 || x > x1 || y < y0 || y > y1) return false;
    let dentro = false;
    for (let i = 0, j = anillo.length - 1; i < anillo.length; j = i++) {
      const a = anillo[i], b = anillo[j];
      if ((a.y > y) !== (b.y > y) && x < (b.x - a.x) * (y - a.y) / (b.y - a.y) + a.x) dentro = !dentro;
    }
    return dentro;
  };
}

// Espacio vacío de la pantalla en el minuto: rejilla de celdas de CARTELA.paso píxeles marcadas como llenas si tienen
// fuego (quemado o por arder en la media hora siguiente), humo, zona Seveso activada, franja de la conducción o el
// símbolo de algo ya alcanzado. lleno(r) cuenta en tiempo constante (tabla de sumas) las celdas llenas del recuadro r.
function espacioVacio(minuto, ancho, alto) {
  const P = CARTELA.paso, gw = Math.ceil(ancho / P), gh = Math.ceil(alto / P);
  const celdas = new Uint8Array(gw * gh);
  // El fuego, con la media hora siguiente (para que no se le eche encima enseguida); el humo, el que se ve: el cono crece
  // tan deprisa con el viento que el de media hora después ocuparía casi todo el espacio vacío
  // En la vista plana, la pantalla es una transformación afín de la ventana de cálculo y cada celda de la rejilla se
  // consulta directamente; en 3D (mapa inclinado o sobre el relieve) no, y el fuego se marca más abajo proyectando
  // sus celdas
  const plano = !mapa.getTerrain() && mapa.getPitch() < 1;
  const hayFuego = plano ? fuegoEnPantalla(minuto + CARTELA.antelacion_min) : () => false, hayHumo = humoEnPantalla(minuto);
  // Polígonos y círculos, como funciones de punto con su recuadro para descartar rápido
  const poligonos = [];
  const anillo = (coords) => {
    const a = coords.map((c) => mapa.project(c)), xs = a.map((q) => q.x), ys = a.map((q) => q.y);
    poligonos.push({ x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys), dentro: (x, y) => {
      let d = false;
      for (let i = 0, j = a.length - 1; i < a.length; j = i++)
        if ((a[i].y > y) !== (a[j].y > y) && x < (a[j].x - a[i].x) * (y - a[i].y) / (a[j].y - a[i].y) + a[i].x) d = !d;
      return d;
    } });
  };
  const circulo_ = (lon, lat, radio_m) => {
    const c = mapa.project([lon, lat]), e = mapa.project([lon + radio_m / (111320 * Math.cos((lat * Math.PI) / 180)), lat]);
    const r = Math.hypot(e.x - c.x, e.y - c.y);
    poligonos.push({ x0: c.x - r, x1: c.x + r, y0: c.y - r, y1: c.y + r, dentro: (x, y) => Math.hypot(x - c.x, y - c.y) <= r });
  };
  for (const i of sim.cascada.instalaciones_seveso) if (i.minutos <= minuto) circulo_(i.lon, i.lat, i.radio_alerta_m);
  const c = sim.cascada.conduccion;
  for (const f of (c && c.franja) || []) if (f.minutos <= minuto && (f.hasta == null || f.hasta > minuto)) for (const a of f.coords) anillo(a);
  for (let j = 0; j < gh; j++) for (let i = 0; i < gw; i++) {
    const x = i * P + P / 2, y = j * P + P / 2;
    if (hayFuego(x, y) || hayHumo(x, y) || poligonos.some((p) => x >= p.x0 && x <= p.x1 && y >= p.y0 && y <= p.y1 && p.dentro(x, y)))
      celdas[j * gw + i] = 1;
  }
  // Fuego en 3D: se proyecta una celda de cálculo cada ~9 px de pantalla (medidos en el centro de la ventana) y se
  // marcan las celdas de la rejilla de alrededor, con margen para la perspectiva, que estira lo cercano
  if (!plano) {
    const { filas, columnas } = sim.ventana, hasta = minuto + CARTELA.antelacion_min;
    const a = mapa.project(lonlat(columnas / 2, filas / 2)), b = mapa.project(lonlat(columnas / 2 + 10, filas / 2));
    const pxCelda = Math.max(Math.hypot(b.x - a.x, b.y - a.y) / 10, 0.05);
    const s = Math.max(1, Math.floor(P / pxCelda)), r = 2;
    for (let f = 0; f < filas; f += s) for (let col = 0; col < columnas; col += s) {
      if (!(llegada[f * columnas + col] <= hasta)) continue;
      const q = mapa.project(lonlat(col + 0.5, f + 0.5)), qi = Math.floor(q.x / P), qj = Math.floor(q.y / P);
      for (let j = qj - r; j <= qj + r; j++) for (let i = qi - r; i <= qi + r; i++)
        if (i >= 0 && j >= 0 && i < gw && j < gh) celdas[j * gw + i] = 1;
    }
  }
  // Símbolos de lo ya alcanzado (centros, estaciones, trenes, entradas en municipios…): unos 10 px alrededor
  for (const f of afectadosBase) if (f.properties.minutos <= minuto) {
    const q = mapa.project(f.geometry.coordinates);
    for (let j = Math.floor((q.y - 10) / P); j <= Math.floor((q.y + 10) / P); j++)
      for (let i = Math.floor((q.x - 10) / P); i <= Math.floor((q.x + 10) / P); i++)
        if (i >= 0 && j >= 0 && i < gw && j < gh) celdas[j * gw + i] = 1;
  }
  // Tabla de sumas acumuladas
  const W = gw + 1, suma = new Float64Array(W * (gh + 1));
  for (let j = 0; j < gh; j++) { let fila = 0;
    for (let i = 0; i < gw; i++) { fila += celdas[j * gw + i]; suma[(j + 1) * W + i + 1] = suma[j * W + i + 1] + fila; } }
  const lim = (v, n) => Math.min(Math.max(v, 0), n);
  return { lleno: (r) => {
    const i0 = lim(Math.floor(r.x0 / P), gw), i1 = lim(Math.ceil(r.x1 / P), gw), j0 = lim(Math.floor(r.y0 / P), gh), j1 = lim(Math.ceil(r.y1 / P), gh);
    return suma[j1 * W + i1] - suma[j0 * W + i1] - suma[j1 * W + i0] + suma[j0 * W + i0];
  } };
}

function colocarCartelas(minuto, vigentes = cartelasVigentes, mantener = false) {
  vigentes = vigentes.filter((a) => globos.has(a.id));   // solo las que tienen su cartela creada
  cartelasVigentes = vigentes;
  if (!sim || modo !== "crisis" || !vigentes.length) return;
  const lienzoMapa = mapa.getContainer(), base = lienzoMapa.getBoundingClientRect();
  const ancho = lienzoMapa.clientWidth, alto = lienzoMapa.clientHeight;
  const vacio = espacioVacio(minuto, ancho, alto);
  const solapa = (a, b) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;
  // Paneles sobre el mapa y los propios objetivos (un círculo de 12 px alrededor de cada uno)
  // (y cualquier elemento marcado con data-tapa-mapa, como un rótulo puesto encima al grabar un vídeo)
  const ocupado = [...document.querySelectorAll("#cronologia-mapa, #esalert-mapa, #reproductor, #comunicaciones, #buscador, [data-tapa-mapa], .maplibregl-ctrl-top-right, .maplibregl-ctrl-bottom-right, .maplibregl-ctrl-bottom-left")]
    .filter((e) => !e.hidden && e.getClientRects().length).map((e) => e.getBoundingClientRect())   // también los fijos
    .filter((r) => r.width && r.height)
    .map((r) => ({ x0: r.left - base.left, y0: r.top - base.top, x1: r.right - base.left, y1: r.bottom - base.top }));
  const puntos = vigentes.map((a) => mapa.project([a.lon, a.lat]));
  for (const p of puntos) ocupado.push({ x0: p.x - 12, y0: p.y - 12, x1: p.x + 12, y1: p.y + 12 });
  // Centro del fuego en pantalla, para preferir el lado contrario
  const { filas, columnas } = sim.ventana;
  let sc = 0, sf = 0, n = 0;
  for (let i = 0; i < llegada.length; i += 7) if (llegada[i] <= minuto) { sc += i % columnas; sf += Math.floor(i / columnas); n++; }
  const centro = mapa.project(n ? lonlat(sc / n + 0.5, sf / n + 0.5) : lonlat(columnas / 2, filas / 2));

  // ¿Pasa el segmento [x0, y0, x1, y1] por el recuadro? (muestreo cada 6 px, sin los 14 px junto al objetivo)
  const cruza = ([x0, y0, x1, y1], r) => {
    const l = Math.hypot(x1 - x0, y1 - y0);
    for (let s = 14; s < l; s += 6) {
      const x = x0 + (x1 - x0) * s / l, y = y0 + (y1 - y0) * s / l;
      if (x > r.x0 && x < r.x1 && y > r.y0 && y < r.y1) return true;
    }
    return false;
  };
  // ¿Se cruzan dos conectores? (sin contar los extremos, por si dos objetivos están juntos)
  const seCruzan = ([ax, ay, bx, by], [cx, cy, dx, dy]) => {
    const giro = (px, py, qx, qy, rx, ry) => (qx - px) * (ry - py) - (qy - py) * (rx - px);
    const d1 = giro(cx, cy, dx, dy, ax, ay), d2 = giro(cx, cy, dx, dy, bx, by);
    const d3 = giro(ax, ay, bx, by, cx, cy), d4 = giro(ax, ay, bx, by, dx, dy);
    return d1 * d2 < 0 && d3 * d4 < 0;
  };
  const cajas = vigentes.map((a) => {
    const caja = globos.get(a.id).getElement(), el = caja.querySelector(".globo-aviso");
    return { caja, el, w: el.offsetWidth, h: el.offsetHeight };
  });
  // Dirección hacia fuera de cada objetivo: del centro del fuego al objetivo. Si cada conector sale en su dirección,
  // los conectores son radios del mismo centro y no se cruzan
  const fuera_ = puntos.map((p) => {
    const ux = p.x - centro.x, uy = p.y - centro.y, l = Math.hypot(ux, uy);
    return l < 1 ? [0, 1] : [ux / l, uy / l];
  });
  const m = CARTELA.margen, lim = (v, a, b) => Math.min(Math.max(v, a), b);

  const indices = vigentes.map((_, k) => k);
  // Posiciones candidatas de cada cartela: anillos de distancias y ángulos alrededor del objetivo. El borde de la cartela
  // queda a unos d píxeles del objetivo y, si se sale del mapa, se corre hacia dentro (sin tapar el objetivo: los
  // objetivos están en «ocupado»)
  const candidatos = indices.map((k) => {
    const p = puntos[k], { w, h } = cajas[k], lista = [];
    for (const d of CARTELA.distancias) for (let i = 0; i < CARTELA.angulos; i++) {
      const ang = (2 * Math.PI * i) / CARTELA.angulos;
      lista.push([Math.round(lim(Math.cos(ang) * (w / 2 + d), 5 + m + w / 2 - p.x, ancho - 5 - m - w / 2 - p.x)),
        Math.round(lim(Math.sin(ang) * (h / 2 + d), 5 + m + h / 2 - p.y, alto - 5 - m - h / 2 - p.y))]);
    }
    return lista;
  });
  // Coste de poner la cartela k en (dx, dy) con otras ya puestas ({r, seg} de cada una). Por este orden: nunca fuera del
  // mapa ni encima de otra cartela, objetivo o panel, ni tapando un conector, ni con su conector cruzando otro o
  // pasando por otra cartela; después, solo espacio vacío; después, hacia fuera del fuego y cerca del objetivo
  const coste = (k, dx, dy, puestas) => {
    const p = puntos[k], { w, h } = cajas[k], [ux, uy] = fuera_[k];
    const r = { x0: p.x + dx - w / 2 - m, y0: p.y + dy - h / 2 - m, x1: p.x + dx + w / 2 + m, y1: p.y + dy + h / 2 + m };
    const seg = [p.x, p.y, p.x + dx, p.y + dy];
    const fuera = r.x0 < 4 || r.y0 < 4 || r.x1 > ancho - 4 || r.y1 > alto - 4;
    let choques = ocupado.filter((o) => solapa(o, r)).length;
    for (const o of puestas) choques += solapa(o.r, r) + cruza(o.seg, r) + cruza(seg, o.r) + seCruzan(o.seg, seg);
    const malo = (fuera ? 1000 : 0) + 100 * choques, tapado = vacio.lleno(r), l = Math.hypot(dx, dy) || 1;
    return { dx, dy, r, seg, malo, tapado, puntos: malo * 10000 + CARTELA.tapar * tapado + l + CARTELA.radial * (1 - (dx * ux + dy * uy) / l) };
  };
  const mejorSitio = (k, puestas) => {
    let e = null;
    for (const [dx, dy] of candidatos[k]) { const c = coste(k, dx, dy, puestas); if (!e || c.puntos < e.puntos) e = c; }
    return e;
  };
  // Huecos vacíos de cada cartela sin contar las demás: cuántos tiene y a qué distancia está el más cercano
  const huecos = indices.map(() => 0), cercania = indices.map(() => Infinity);
  for (const k of indices) for (const [dx, dy] of candidatos[k]) {
    const c = coste(k, dx, dy, []);
    if (!c.malo && !c.tapado) { huecos[k]++; cercania[k] = Math.min(cercania[k], Math.hypot(dx, dy)); }
  }
  const sinK = (puestas, k) => [...puestas].filter(([j]) => j !== k).map(([, e]) => e);

  // Coloca las cartelas una a una en el orden dado, sin tocar la página. Una cartela se queda donde estaba si sigue en
  // vacío, sin choques y no mucho más lejos que su hueco vacío más cercano
  const intentar = (orden) => {
    const puestas = new Map();
    let movidas = 0;
    for (const k of orden) {
      const caja = cajas[k].caja;
      let e = null;
      if (mantener && caja.dataset.dx != null) {
        const c = coste(k, +caja.dataset.dx, +caja.dataset.dy, [...puestas.values()]);
        if (!c.malo && !c.tapado && Math.hypot(c.dx, c.dy) <= cercania[k] + CARTELA.holgura_px) e = c;
      }
      if (!e) { e = mejorSitio(k, [...puestas.values()]); movidas++; }
      puestas.set(k, e);
    }
    return { puestas, movidas, ...valorar(puestas) };
  };
  // Coste de una colocación completa: cada cartela frente a todas las demás
  const valorar = (puestas) => {
    let total = 0, limpio = true;
    for (const [k, e] of puestas) {
      const c = coste(k, e.dx, e.dy, sinK(puestas, k));
      total += c.puntos; limpio = limpio && !c.malo && !c.tapado;
    }
    return { total, limpio };
  };
  // Varios órdenes; se queda el de menor coste. Primero las que menos huecos vacíos tienen, para que las otras no se
  // los quiten; después, por hora de llegada, alrededor del fuego, de dentro afuera y de fuera adentro, y unos cuantos
  // órdenes al azar, siempre los mismos (semilla fija) para que las cartelas no salten de un minuto a otro
  const angulo = (k) => Math.atan2(puntos[k].y - centro.y, puntos[k].x - centro.x);
  const alCentro = (k) => Math.hypot(puntos[k].x - centro.x, puntos[k].y - centro.y);
  let semilla = 12345;
  const azar = () => ((semilla = (semilla * 1103515245 + 12345) % 2147483648) / 2147483648);
  const barajar = (a) => { const b = [...a]; for (let i = b.length - 1; i > 0; i--) { const j = Math.floor(azar() * (i + 1)); [b[i], b[j]] = [b[j], b[i]]; } return b; };
  const ordenes = [[...indices].sort((i, j) => huecos[i] - huecos[j]), indices, [...indices].sort((i, j) => angulo(i) - angulo(j)),
    [...indices].sort((i, j) => alCentro(i) - alCentro(j)), [...indices].sort((i, j) => alCentro(j) - alCentro(i))];
  if (indices.length > 2) for (let i = 0; i < 12; i++) ordenes.push(barajar(indices));
  let mejor = null;
  for (const orden of ordenes) {
    const intento = intentar(orden);
    if (!mejor || intento.total < mejor.total) mejor = intento;
    if (mejor.limpio && !mejor.movidas) break;   // todas siguen en su sitio, en vacío y sin choques
  }
  // Repaso: si algo se ha movido, cada cartela, con todas las demás ya puestas, busca un sitio mejor
  if (mejor.movidas) {
    for (let ronda = 0; ronda < 2; ronda++) for (const k of indices) {
      const otras = sinK(mejor.puestas, k), actual = mejor.puestas.get(k), nueva = mejorSitio(k, otras);
      if (nueva.puntos < coste(k, actual.dx, actual.dy, otras).puntos - 1) mejor.puestas.set(k, nueva);
    }
  }
  mejor.posiciones = mejor.puestas;
  for (const [k, e] of mejor.posiciones) {
    const { caja, el } = cajas[k];
    caja.dataset.dx = e.dx; caja.dataset.dy = e.dy;
    el.style.left = `${e.dx}px`; el.style.top = `${e.dy}px`;
    const linea = caja.querySelector("line");
    linea.setAttribute("x2", e.dx); linea.setAttribute("y2", e.dy);
  }
}

function reproducir(si) {
  reproduciendo = si && !!sim;
  $("#rep-play").textContent = reproduciendo ? "⏸" : "▶";
  if (reproduciendo) { ultimoCuadro = performance.now(); requestAnimationFrame(cuadro); }
}

function cuadro(ahora) {
  if (!reproduciendo) return;
  const dt = (ahora - ultimoCuadro) / 1000; ultimoCuadro = ahora;
  const antes = t, despues = Math.min(t + dt * +$("#rep-velocidad").value, sim.horizonte_min);
  const cruzados = sucesosVisibles().filter((s) => s.min > antes && s.min <= despues);
  const pausa = $("#rep-pausa").checked ? cruzados.find((s) => s.clave) : undefined;
  fijarTiempo(pausa ? Math.ceil(pausa.min) : despues);   // el visor pinta minutos enteros: el suceso ya se ve
  const camara = $("#rep-camara").value;
  // Cámara fija o siguiendo los sucesos clave
  const destino = camara === "clave" ? pausa : null;
  if (destino && destino.lon != null)
    mapa.easeTo({ center: [destino.lon, destino.lat], zoom: Math.max(mapa.getZoom(), 12.5), duration: 1000 });
  if (pausa) { reproducir(false); return; }
  if (t >= sim.horizonte_min) reproducir(false); else requestAnimationFrame(cuadro);
}

$("#rep-play").onclick = () => { if (sim && t >= sim.horizonte_min) fijarTiempo(0); reproducir(!reproduciendo); };
$("#rep-inicio").onclick = () => { reproducir(false); fijarTiempo(0); };
$("#rep-barra").oninput = () => fijarTiempo(+$("#rep-barra").value);
for (const b of document.querySelectorAll("#reproductor .cortes button")) b.onclick = () => { reproducir(false); fijarTiempo(+b.dataset.h * 60); };

// ----------------------------------------------------------------------------- panel de resultados
function mostrarResultado(d) {
  const hora0 = new Date(d.ignicion.hora);
  const horaDe = (min) => hhmm(new Date(hora0.getTime() + min * 60000));
  const v = d.viento;
  const viento = d.tipo === "presa" ? "" : v.origen === "AEMET"
    ? `AEMET: observado en ${html(v.estacion.estacion)} (a ${v.estacion.distancia_km} km) y previsto para ${html(v.municipio)}` +
      (v.horas_repetidas ? ` (${v.horas_repetidas} h sin predicción, se mantiene la anterior)` : "") +
      (v.horas_con_racha ? `; racha en lugar del viento medio en ${v.horas_con_racha} h (tormenta prevista, o racha observada de ${v.umbral_racha_kmh} km/h o más)` : "")
    : v.constante === false
      ? `${html(v.fuente || "introducido a mano")}, hora a hora (${d.vientos_por_hora[0].velocidad_kmh.toLocaleString("es-ES")} km/h del ${rumbo(d.vientos_por_hora[0].desde)} en la primera hora` +
        (v.racha ? `: ${html(v.racha)}` : "") + ")"
      : `introducido a mano, constante: ${d.vientos_por_hora[0].velocidad_kmh} km/h del ${rumbo(d.vientos_por_hora[0].desde)}`;
  const finos = d.tipo === "presa" ? [0] : (d.humedades_por_hora || [d.humedades]).map((h) => Math.round(h.m_1h * 1000) / 10);
  const humedad = d.humedad_fija === false
    ? `humedad del combustible muerto fino del ${Math.min(...finos).toLocaleString("es-ES")} al ${Math.max(...finos).toLocaleString("es-ES")} %, ` +
      `de ${html(v.humedad || "la temperatura y la humedad del aire, hora a hora")}`
    : "humedad del combustible muerto fija de verano";
  const vivo = d.humedad_viva ? `; combustible vivo al ${Math.round(d.humedad_viva * 100)} %${d.humedad_viva < 0.9 ? " (de julio a septiembre)" : ""}` : "";
  const lista = (arr, tipo, extra) => arr.length
    ? `<ul class="activos">${arr.map((a) => `<li data-min="${a.minutos}" data-lon="${a.lon}" data-lat="${a.lat}"><span class="hora">${horaDe(a.minutos)}</span>` +
        `<span class="nombre"><span class="simbolo ${FAMILIAS[a.familia].subtipos[a.subtipo][1]}" style="background:${FAMILIAS[a.familia].color};color:${FAMILIAS[a.familia].color}"></span>${html(rotulo(a))}` +
        `<br><span class="meta">${html(a.municipio)} · vulnerabilidad ${VULNERABILIDAD[a.vulnerabilidad]}${extra ? " · " + extra(a) : ""}</span></span>` +
        `<span class="marca ${tipo}">+${duracion(a.minutos)}</span></li>`).join("")}</ul>`
    : `<p class="meta">Ninguno en 24 h.</p>`;
  const sens = (s) => s.centros ? `<p class="meta">Además, ${s.centros} centro${s.centros > 1 ? "s" : ""} de acogida o protección con ${numero(s.plazas)} plazas (no se muestran uno a uno).</p>` : "";
  const seveso = d.cascada.instalaciones_seveso.map((i) =>
    `<li>Instalación Seveso <strong>${i.id}</strong>, alcanzada a las <strong>${horaDe(i.minutos)}</strong> (+${duracion(i.minutos)}): amenaza derivada de ${radiosSeveso(i)}.</li>`).join("");
  const otros = tramosConduccion(d).slice(1);
  const cond = d.cascada.conduccion ? `<li>Conducción de hidrocarburos alcanzada a las <strong>${horaDe(d.cascada.conduccion.primera_llegada_min)}</strong>: se activa su franja de efectos en 750 m alrededor del tramo` +
    (otros.length ? `; otro${otros.length > 1 ? "s" : ""} tramo${otros.length > 1 ? "s" : ""} a las ${otros.map((tr) => `<strong>${horaDe(tr.minutos)}</strong>`).join(", ")}` : "") + `.</li>` : "";
  $("#resultado").hidden = false;
  requestAnimationFrame(() => $("#resultado").scrollIntoView({ block: "start", behavior: "smooth" }));
  $("#resultado").innerHTML = `
    ${d.tipo === "presa" ? cabeceraPresa(d, horaDe) : `<h2>Evolución estimada</h2>
    ${d.sin_propagacion ? `<p class="aviso">El fuego no avanza: ${html(d.sin_propagacion)}.</p>` : ""}
    ${d.borde_min != null ? `<p class="aviso">El fuego llega al borde de la zona de cálculo (${(d.ventana.columnas * d.ventana.celda_m / 1000).toLocaleString("es-ES")} km de lado) a las ${horaDe(d.borde_min)}: desde entonces, la superficie y los afectados se quedan cortos.</p>` : ""}
    <p class="meta">Ignición a las ${hhmm(hora0)} en ${html(d.ignicion.municipio)}, sobre ${html(d.ignicion.combustible_nombre).toLowerCase()} a ${numero(d.ignicion.altitud_m)} m.
      Viento ${viento}. Combustible del ${html(d.ignicion.combustible_fuente || "mapa europeo de combustibles de EFFIS (250 m)")}; ${humedad}${vivo}. Modelo de Rothermel sobre celdas de 50 m.</p>
    <p class="leyenda-crisis"><span style="background:rgb(255,96,0)"></span>frente activo <span style="background:rgba(110,18,8,.6)"></span>área quemada
      <span style="background:rgba(85,85,85,.3)"></span>humo <span style="background:rgba(255,127,0,.3)"></span>zona Seveso activada
      <span class="linea-via conduccion"></span>conducción de hidrocarburos
      <span class="linea-via" style="border-color:#d1121b"></span>carretera o vía con fuego a menos de ${d.distancia_alcanzado_m} m
      <span class="linea-via" style="border-color:#5f5f5f"></span>bajo el humo
      <span class="linea-via isocrona"></span>hasta dónde llega el fuego en las próximas horas</p>
    <p class="meta">Avisos: centros que alcanza el fuego, carreteras, vías de tren, núcleos de población del IGN, instalaciones Seveso y la conducción
      a los que llegará el fuego en las próximas 3 horas, con la cuenta atrás; los ${AVISO.simultaneos} más próximos a la vez, más las instalaciones Seveso y la conducción, que siempre tienen el suyo. Un núcleo, cuando el fuego llega a menos de ${d.distancia_alcanzado_m} m de su casco.</p>
    <p class="meta">Cada cosa alcanzada aparece en el mapa al llegarle el efecto, con su nombre, que se queda hasta el final:
      <span style="color:${COLOR_EFECTO.llamas};font-weight:600">fuego a menos de ${d.distancia_alcanzado_m} m</span>,
      <span style="color:${COLOR_EFECTO.derivada};font-weight:600">zona Seveso o de la conducción</span>,
      <span style="color:${COLOR_EFECTO.humo};font-weight:600">humo</span>.</p>`}
    <div id="cronologia"></div>
    <h3>${voz.superficie}</h3>
    <p>${Object.entries(d.superficie_km2).map(([h, k]) => `<strong>${h} h</strong>: ${k.toLocaleString("es-ES")} km²`).join(" · ")}</p>
    <h3>Habitantes en las celdas de 1 km que toca ${voz.elAgente}</h3>
    <p class="meta">Población del Censo 2021 en las celdas de 1 km que toca ${voz.elAgente} (la celda entera, aunque ${d.tipo === "presa" ? "solo se inunde" : "arda solo"} una parte) y plazas de los centros sociales alcanzados.</p>
    <table class="personas"><tr><th></th><th>Habitantes</th><th>Menores de 16</th><th>Mayores de 64</th><th>Plazas sociales</th></tr>
    ${d.horizontes_h.map((h) => { const p = personasHasta(h * 60, d); return `<tr><td><strong>${h} h</strong></td><td>${numero(p.poblacion)}</td><td>${numero(p.menores_16)}</td><td>${numero(p.mayores_64)}</td><td>${numero(p.plazas)}</td></tr>`; }).join("")}</table>
    <h3>Municipios en los que entra ${voz.elAgente} (${d.municipios.length})</h3>
    <ul class="activos">${d.municipios.map((m) => `<li data-min="${m.minutos}"><span class="hora">${horaDe(m.minutos)}</span><span class="nombre">${html(m.nombre)}</span><span class="meta">+${duracion(m.minutos)}</span></li>`).join("")}</ul>
    <h3>Activos alcanzados por ${d.tipo === "presa" ? "el agua" : "las llamas"} (${d.activos_llamas.length})</h3>
    <p class="meta">${voz.Agente} a menos de ${d.distancia_alcanzado_m} m del centro.</p>
    ${lista(d.activos_llamas, "llamas")}${sens(d.sensibles_llamas)}
    ${d.tipo === "presa" ? "" : `<h3>Efecto cascada</h3>
    ${esquemaCascada(d, horaDe)}
    ${seveso || cond ? `<ul>${seveso}${cond}</ul>` : `<p class="meta">El fuego no alcanza instalaciones Seveso ni conducciones de hidrocarburos en 24 h.</p>`}
    ${d.cascada.activos.length ? `<h4>Activos bajo amenaza derivada (${d.cascada.activos.length})</h4>${lista(d.cascada.activos, "derivada", (a) => `${html(a.origen)}, zona de ${html(a.zona)}${porAmenaza(a)}`)}` : ""}${sens(d.cascada.sensibles)}
    <h3>Activos bajo el humo (${d.humo.activos.length})</h3>
    <p class="meta">Cono viento abajo del área quemada, recalculado cada ${d.humo.parametros.paso_min} minutos (semiángulo ${d.humo.parametros.semiangulo_grados}°, hasta ${d.humo.parametros.alcance_max_km} km más allá del fuego).</p>
    ${lista(d.humo.activos, "humo")}${sens(d.humo.sensibles)}`}
    ${seccionVias(d, horaDe)}`;
  for (const li of $("#resultado").querySelectorAll("li[data-lon]")) li.onclick = () => mapa.flyTo({ center: [+li.dataset.lon, +li.dataset.lat], zoom: 14 });
}

// Cabecera del resultado de una rotura de presa: el modelo de la onda y la leyenda
function cabeceraPresa(d, horaDe) {
  const p = d.presa, m = d.modelo, km = (x) => (x / 1000).toLocaleString("es-ES", { maximumFractionDigits: 1 });
  return `<h2>Evolución estimada</h2>
    <p class="meta">Rotura de la ${html(p.nombre)} (${html(d.ignicion.municipio)}) a las ${horaDe(0)}. El agua recorre, aguas abajo, la zona
      inundable de la capa de rotura de presas del Catálogo de Riesgos Potenciales, con una onda que se frena: sale a
      ${m.velocidad_inicial_kmh.toLocaleString("es-ES")} km/h, calibrada para recorrer en 30 minutos la zona de primera inundación del
      catálogo (${km(p.longitud_30_min_m)} km), y no baja de ${m.velocidad_min_kmh} km/h. Relieve del IGN (25 m) sobre celdas de 50 m.
      ${m.fin_min < d.horizonte_min ? `Deja de avanzar a las ${horaDe(m.fin_min)}.` : ""}</p>
    <p class="leyenda-crisis"><span style="background:rgb(90,185,255)"></span>frente de la onda <span style="background:rgba(25,80,160,.65)"></span>zona inundada
      <span class="linea-via" style="border-color:#d1121b"></span>carretera o vía con agua a menos de ${d.distancia_alcanzado_m} m
      <span class="linea-via isocrona"></span>hasta dónde llega el agua en las próximas horas</p>
    <p class="meta">Avisos: centros, carreteras, vías de tren y núcleos de población del IGN a los que llegará el agua en las próximas
      3 horas, con la cuenta atrás; los ${AVISO.simultaneos} más próximos a la vez.</p>`;
}

// ----------------------------------------------------------------------------- comunicaciones ficticias
// ES-Alert: se emite al declarar la alerta y cada vez que crece el área del aviso (un municipio
// entra en la próxima hora del fuego); el área son los municipios en los que el fuego ha entrado o entra en la hora
// siguiente a la emisión. Sobre el mapa, con aspecto de aviso en un móvil, resaltado durante los primeros minutos.
let emisionesAlerta = [0];
const ALERTA_NUEVA_MIN = 20;

function comunicar(minuto, hora, km2) {
  const d = sim;
  const municipios = d.municipios.filter((m) => m.minutos <= minuto).map((m) => m.nombre);
  const alcanzados = d.activos_llamas.filter((a) => a.minutos <= minuto);
  const presa = d.tipo === "presa";
  const w = presa ? null : d.vientos_por_hora[Math.min(Math.floor(minuto / 60), d.vientos_por_hora.length - 1)];
  const haciaHumo = presa ? "" : w.velocidad_kmh > 0 ? `hacia el ${rumbo(w.desde + 180)}` : "sin viento, sobre la zona";
  const centros = alcanzados.length
    ? ` ${alcanzados.length} centro${alcanzados.length > 1 ? "s" : ""} con población vulnerable alcanzado${alcanzados.length > 1 ? "s" : ""}` +
      ` (${alcanzados.slice(0, 3).map(rotulo).join(", ")}${alcanzados.length > 3 ? "…" : ""}).`
    : "";
  $("#rrss-texto").textContent = presa
    ? `🌊 Rotura de la ${d.presa.nombre} (${d.ignicion.municipio}) a las ${hhmm(new Date(d.ignicion.hora))}. ` +
      `Situación estimada a las ${hhmm(hora)}: ${km2.toLocaleString("es-ES", { maximumFractionDigits: 1 })} km² inundados` +
      `${municipios.length ? ` en ${municipios.join(", ")}` : ""}.${centros} ` +
      `Aléjate de los cauces, sube a zonas altas y sigue las indicaciones de los servicios de emergencia. 📍 ${d.ignicion.lat.toFixed(4)}, ${d.ignicion.lon.toFixed(4)} #Cascada`
    : `🔥 Incendio forestal en ${d.ignicion.municipio}, iniciado a las ${hhmm(new Date(d.ignicion.hora))}. ` +
    `Situación estimada a las ${hhmm(hora)}: ${km2.toLocaleString("es-ES", { maximumFractionDigits: 1 })} km² afectados` +
    `${municipios.length ? ` en ${municipios.join(", ")}` : ""}. Humo ${haciaHumo}.${centros} ` +
    `Evita la zona y sigue las indicaciones de los servicios de emergencia. 📍 ${d.ignicion.lat.toFixed(4)}, ${d.ignicion.lon.toFixed(4)} #Cascada`;
  const emision = emisionesAlerta.filter((e) => e <= minuto).pop() ?? 0;
  const area = d.municipios.filter((m) => m.minutos <= emision + 60).map((m) => m.nombre);
  const horaEmision = new Date(new Date(d.ignicion.hora).getTime() + emision * 60000);
  const lista = area.join(", ") || d.ignicion.municipio;
  const cuerpo = presa
    ? `Rotura de presa: ${d.presa.nombre}. Puede inundar en la próxima hora: ${lista}.\n` +
      `Si está cerca del cauce, diríjase de inmediato a zonas altas por las vías que indiquen los servicios de emergencia. ` +
      `No cruce cauces ni zonas inundadas y no use el coche. Información: 112.`
    : `Incendio forestal en ${d.ignicion.municipio}. Puede afectar en la próxima hora a: ${lista}.\n` +
    `Si está en esta zona, aléjese del fuego por las vías que indiquen los servicios de emergencia. ` +
    `Si hay humo, cierre puertas y ventanas y permanezca en el interior. No se acerque a la zona. Información: 112.`;
  $("#esalert-texto").textContent = `ALERTA DE PROTECCIÓN CIVIL\n${cuerpo}\n` +
    `Área del aviso (celdas de telefonía): ${lista}. Emitido a las ${hhmm(horaEmision)}.`;
  $("#esalert-mapa-texto").textContent = cuerpo;
  $("#esalert-mapa-hora").textContent = `${hhmm(horaEmision)} · ${area.length || 1} municipio${area.length > 1 ? "s" : ""}`;
  $("#esalert-mapa").classList.toggle("nueva", minuto - emision < ALERTA_NUEVA_MIN);
}

// ----------------------------------------------------------------------------- validación con un caso real
// El caso de Tres Cantos (2025) no se carga desde el visor: la validación se describe en la metodología. Las capas
// del perímetro y los focos se quedan vacías.
function limpiarValidacion() {
  for (const id of ["validacion-perimetro", "validacion-focos"]) if (mapa.getSource(id)) mapa.getSource(id).setData(vacioFC());
}

