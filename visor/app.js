// Visor de Cascada: mapa, análisis basal (capas de peligrosidad, activos, celda de 1 km y ficha de activo).
// La gestión de crisis está en crisis.js.
"use strict";

// ----------------------------------------------------------------------------- fondos del IGN
// Con red, el mapa base, el relieve, la ortofoto y las tipografías se piden directamente al IGN y a MapLibre; con el
// servidor sin conexión, a su copia guardada (/externo/, procesamiento/sin_conexion.py).
// SIN_CONEXION y COPIA se definen en mapabase.js, que se carga antes.
// Ortofoto PNOA del IGN (WMTS)
const WMTS = (servicio, capa, formato) =>
  `https://www.ign.es/wmts/${servicio}?service=WMTS&request=GetTile&version=1.0.0&layer=${capa}` +
  `&style=default&tilematrixset=GoogleMapsCompatible&tilematrix={z}&tilerow={y}&tilecol={x}&format=image/${formato}`;
// El modo "Mapa" es el mapa base operativo (mapabase.js); este es el de la ortofoto. Sobre ella van los mismos
// rótulos y carreteras del mapa base (capas "ref-…"), no la capa de nombres del IGN para ortofoto (IGNBaseOrto):
// esa pinta los embalses a máximo nivel en azul y duplica los nombres
const FONDOS = {
  "ign-pnoa": SIN_CONEXION ? `${COPIA}/ign-pnoa/{z}/{x}/{y}.jpeg` : WMTS("pnoa-ma", "OI.OrthoimageCoverage", "jpeg"),
};

// ----------------------------------------------------------------------------- catálogo
const CAPAS = [
  ["3_1", "Incendios forestales", "Naturales"],
  ["2_1", "Avenidas y crecidas", "Naturales"],
  ["2_3", "Rotura de presas", "Naturales"],
  ["6_27", "Derrumbes y colapso de edificaciones", "Naturales"],
  ["5_4", "Subsidencias", "Naturales"],
  ["6_3", "Nube tóxica", "Tecnológicos"],
  ["6_4", "Sobrepresión por explosión", "Tecnológicos"],
  ["6_11", "Centrales energéticas", "Tecnológicos"],
  ["6_12", "Transporte de energía", "Tecnológicos"],
  ["6_16", "Transporte por carretera", "Tecnológicos"],
  ["6_15", "Transporte por tren", "Tecnológicos"],
  ["6_14", "Transporte por avión", "Tecnológicos"],
  ["6_6", "Actividades extractivas", "Tecnológicos"],
];
const NIVELES = ["", "muy baja", "baja", "moderada", "alta", "muy alta"];
const FAMILIAS = {
  educativos: { nombre: "Educativos", color: "#2f6fd1", subtipos: {
    infantil: ["Infantil", "circulo"], primaria_secundaria: ["Primaria y secundaria", "cuadrado"],
    educacion_especial: ["Educación especial", "triangulo"] } },
  sanitarios: { nombre: "Sanitarios", color: "#1f9d6b", subtipos: {
    hospital: ["Hospitales", "circulo"], dialisis: ["Diálisis", "cuadrado"] } },
  atencion_social: { nombre: "Atención social", color: "#7b4fc9", subtipos: {
    residencial: ["Residenciales", "circulo"], de_dia: ["De día", "cuadrado"] } },
};
const VULNERABILIDAD = { baja: "baja", moderada: "moderada", alta: "alta", muy_alta: "muy alta" };

// ----------------------------------------------------------------------------- mapa
const protocolo = new pmtiles.Protocol();
maplibregl.addProtocol("pmtiles", protocolo.tile);

const mapa = new maplibregl.Map({
  container: "mapa",
  center: [-3.7, 40.45], zoom: 8.6, minZoom: 7, maxZoom: 17,
  attributionControl: { compact: true },
  style: {
    version: 8,
    glyphs: SIN_CONEXION ? `${COPIA}/glifos/{fontstack}/{range}.pbf` : "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
    sources: Object.fromEntries(Object.entries(FONDOS).map(([id, url]) =>
      [id, { type: "raster", tiles: [url], tileSize: 256, attribution: "© Instituto Geográfico Nacional",
        maxzoom: SIN_CONEXION ? Math.min(19, window.CASCADA_ZOOM_CACHE) : 19 }])),
    layers: [
      { id: "ign-pnoa", type: "raster", source: "ign-pnoa", layout: { visibility: "none" } },
    ],
  },
});
// El panel lateral y la ventana pueden cambiar de tamaño después de crear el mapa
new ResizeObserver(() => mapa.resize()).observe(document.getElementById("mapa"));
mapa.addControl(new maplibregl.NavigationControl({ showCompass: false }));
mapa.addControl(new maplibregl.ScaleControl({ maxWidth: 120 }));

const visible = (id, si) => mapa.setLayoutProperty(id, "visibility", si ? "visible" : "none");
const $ = (sel) => document.querySelector(sel);
const html = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const numero = (n) => n.toLocaleString("es-ES");
// Tipo corto delante del nombre de cada centro: «Colegio de primaria · MARIA AUXILIADORA».
// De los hospitales el conjunto no publica el nombre: el nombre ya es el tipo
const rotulo = (a) => a.tipo && a.tipo !== a.nombre ? `${a.tipo} · ${a.nombre}` : a.nombre;

// Plegar y desplegar el panel lateral: el mapa ocupa todo el ancho; el navegador recuerda la elección
function plegarPanel(plegado) {
  document.querySelector("main").classList.toggle("sin-panel", plegado);
  const b = $("#plegar-panel");
  b.textContent = plegado ? "‹" : "›";
  b.title = plegado ? "Mostrar el panel lateral" : "Ocultar el panel lateral";
  b.setAttribute("aria-expanded", String(!plegado));
  try { localStorage.setItem("cascada-panel-plegado", plegado ? "1" : "0"); } catch { /* sin almacenamiento: no se recuerda */ }
}
$("#plegar-panel").onclick = () => plegarPanel(!document.querySelector("main").classList.contains("sin-panel"));
try { if (localStorage.getItem("cascada-panel-plegado") === "1") plegarPanel(true); } catch { /* sin almacenamiento */ }
// Capas con elementos que se pueden pulsar: el clic sobre ellas no abre la celda ni mueve la alerta
const capasClicables = ["activos", "activos-grupos"];
const sobreElemento = (punto) => mapa.queryRenderedFeatures(punto, { layers: capasClicables.filter((id) => mapa.getLayer(id)) }).length > 0;

let orto = false, nombres = true;
function cambiarFondo(siOrto) {
  orto = siOrto;
  for (const id of capasCon(mapa, "terreno-")) visible(id, !orto);
  visible("ign-pnoa", orto);
  $("#fondo-mapa").classList.toggle("activo", !orto);
  $("#fondo-orto").classList.toggle("activo", orto);
}
$("#fondo-mapa").onclick = () => cambiarFondo(false);
$("#fondo-orto").onclick = () => cambiarFondo(true);

// ----------------------------------------------------------------------------- vista en 3D
// Relieve del MDT de 25 m del IGN (procesamiento/relieve.py, teselas Terrarium servidas en local), exagerado ×1,5 para
// que se aprecie fuera de la sierra, con un sombreado suave. Apagada al arrancar, en los tres modos; al encenderla, el
// mapa se inclina sobre el relieve y se puede girar e inclinar con el ratón (botón derecho o Ctrl + arrastrar). El
// fuego, el humo, las zonas y las cartelas se pintan sobre el relieve
const RELIEVE = { exageracion: 1.5, inclinacion: 60 };
let vista3d = false;
function prepararRelieve() {
  const fuente = { type: "raster-dem", url: "pmtiles:///datos/relieve.pmtiles", tileSize: 256, encoding: "terrarium",
    attribution: "Relieve: MDT 25 m © Instituto Geográfico Nacional" };
  mapa.addSource("relieve", fuente);
  mapa.addSource("relieve-sombra", { ...fuente });   // MapLibre recomienda una fuente aparte para el sombreado
  const encima = mapa.getStyle().layers.find((l) => l.id.startsWith("capa-"));
  mapa.addLayer({ id: "relieve-sombra", type: "hillshade", source: "relieve-sombra", layout: { visibility: "none" },
    paint: { "hillshade-exaggeration": 0.35, "hillshade-shadow-color": "#3d3326", "hillshade-highlight-color": "#ffffff" } },
    encima && encima.id);
}
function cambiarVista3d(si) {
  vista3d = si;
  mapa.setTerrain(si ? { source: "relieve", exaggeration: RELIEVE.exageracion } : null);
  visible("relieve-sombra", si);
  mapa.easeTo({ pitch: si ? RELIEVE.inclinacion : 0, bearing: si ? mapa.getBearing() : 0, duration: 1000 });
  $("#vista-3d").classList.toggle("activo", si);
  $("#vista-3d").setAttribute("aria-pressed", String(si));
}
$("#vista-3d").onclick = () => cambiarVista3d(!vista3d);

// Casilla de nombres: todos los rótulos del mapa de golpe, los del mapa base (poblaciones, embalses, carreteras) y los
// de los modos (lo afectado en la crisis, la conducción, las líneas de los trenes, las zonas de aviso). Estos últimos se
// apagan con la opacidad, porque cada modo decide cuándo están visibles
const NOMBRES_DE_LOS_MODOS = ["afectados-nombre", "conducciones-nombre", "trenes-linea", "zonas-aviso-nombre"];
function mostrarNombres(si) {
  nombres = si;
  for (const id of capasCon(mapa, "ref-nombre-")) visible(id, si);
  for (const id of NOMBRES_DE_LOS_MODOS) if (mapa.getLayer(id)) mapa.setPaintProperty(id, "text-opacity", si ? 1 : 0);
  $("#ver-nombres").checked = si;
}
$("#ver-nombres").onclick = () => mostrarNombres(!nombres);

// ----------------------------------------------------------------------------- modos
let modo = "basal";
function cambiarModo(nuevo) {
  modo = nuevo;
  for (const m of ["basal", "prealerta", "crisis"]) {
    $(`#modo-${m}`).classList.toggle("activo", nuevo === m);
    $(`#panel-${m}`).hidden = nuevo !== m;
  }
  if (mapa.getSource("celda")) mapa.getSource("celda").setData({ type: "FeatureCollection", features: [] });
  if (nuevo !== "basal") $("#ficha-mapa").hidden = true;   // la ficha es del análisis basal
  document.dispatchEvent(new CustomEvent("modo", { detail: nuevo }));
}
for (const m of ["basal", "prealerta", "crisis"]) $(`#modo-${m}`).onclick = () => cambiarModo(m);

// ----------------------------------------------------------------------------- capas de peligrosidad
// La casilla de un grupo no superpone sus capas (con una sola paleta, el color sería el de la capa dibujada
// encima): muestra la capa combinada con el nivel máximo del grupo en cada punto, sin el fondo de incendios y
// avión, que genera la cadena de datos. Una capa suelta y la combinada de su grupo no
// se muestran a la vez. Al empezar, todas apagadas (el visor arranca con todo desmarcado).
const COMBINADAS = { Naturales: "naturales", Tecnológicos: "tecnologicos" };

function fuenteCapa(id, fichero) {
  mapa.addSource(`capa-${id}`, { type: "raster", url: `pmtiles:///datos/capas/${fichero}.pmtiles`,
    tileSize: 256, attribution: "Catálogo de Riesgos Potenciales © Comunidad de Madrid" });
  mapa.addLayer({ id: `capa-${id}`, type: "raster", source: `capa-${id}`,
    layout: { visibility: "none" }, paint: { "raster-opacity": 0.85, "raster-resampling": "nearest" } });
}

function construirCapas() {
  const cont = $("#capas");
  for (const grupo of ["Naturales", "Tecnológicos"]) {
    const g = document.createElement("label"); g.className = "grupo";
    g.title = "Nivel máximo de las capas del grupo en cada punto, sin el fondo de incendios y avión";
    g.innerHTML = `<input type="checkbox" data-combinada="${COMBINADAS[grupo]}" data-grupo="${grupo}"> ${grupo} <span class="meta">máximo del grupo</span>`;
    cont.appendChild(g);
    fuenteCapa(COMBINADAS[grupo], `combinada_${COMBINADAS[grupo]}`);
    for (const [codigo, nombre, gr] of CAPAS.filter((c) => c[2] === grupo)) {
      const l = document.createElement("label"); l.className = "hoja";
      l.innerHTML = `<input type="checkbox" data-capa="${codigo}" data-grupo="${gr}"> ${nombre}`;
      cont.appendChild(l);
      fuenteCapa(codigo, `peligrosid_${codigo}`);
    }
  }
  const apagar = (caja, id) => { caja.checked = false; visible(`capa-${id}`, false); };
  cont.addEventListener("change", (ev) => {
    const caja = ev.target, grupo = caja.dataset.grupo;
    if (caja.dataset.capa) {
      visible(`capa-${caja.dataset.capa}`, caja.checked);
      const combinada = cont.querySelector(`input[data-combinada][data-grupo="${grupo}"]`);
      if (caja.checked && combinada.checked) apagar(combinada, combinada.dataset.combinada);
    } else if (caja.dataset.combinada) {
      visible(`capa-${caja.dataset.combinada}`, caja.checked);
      if (caja.checked) for (const h of cont.querySelectorAll(`input[data-capa][data-grupo="${grupo}"]:checked`)) apagar(h, h.dataset.capa);
    }
    leyendaCapas();
  });
  leyendaCapas();
}

function leyendaCapas() {
  const combinadas = document.querySelectorAll("#capas input[data-combinada]:checked").length;
  const sueltas = document.querySelectorAll("#capas input[data-capa]:checked").length;
  const niveles = [1, 2, 3, 4, 5].map((n) => `<span class="n${n}"></span>${NIVELES[n]}`).join("");
  $("#leyenda").innerHTML = (combinadas ? "Nivel máximo del grupo (sin el fondo de incendios y avión): " : "Peligrosidad: ") + niveles +
    (sueltas > 1 ? `<span class="aviso-capas meta">Con varias capas sueltas a la vez, en cada punto se ve la dibujada encima.</span>` : "");
}

// ----------------------------------------------------------------------------- activos
let activosTodos = { type: "FeatureCollection", features: [] };

function icono(nombre, color, forma) {
  const t = 28, c = document.createElement("canvas"); c.width = c.height = t;
  const g = c.getContext("2d"); g.fillStyle = color; g.strokeStyle = "#ffffff"; g.lineWidth = 3;
  g.beginPath();
  if (forma === "circulo") g.arc(t / 2, t / 2, 9, 0, Math.PI * 2);
  else if (forma === "cuadrado") g.rect(5, 5, t - 10, t - 10);
  else { g.moveTo(t / 2, 3); g.lineTo(t - 3, t - 4); g.lineTo(3, t - 4); g.closePath(); }
  g.fill(); g.stroke();
  mapa.addImage(nombre, g.getImageData(0, 0, t, t), { pixelRatio: 2 });
}

function construirActivos() {
  const cont = $("#familias");
  for (const [familia, f] of Object.entries(FAMILIAS)) {
    const g = document.createElement("label"); g.className = "grupo";
    g.innerHTML = `<input type="checkbox" data-familia="${familia}"> <span class="simbolo circulo" style="background:${f.color}"></span>${f.nombre}`;
    cont.appendChild(g);
    for (const [subtipo, [nombre, forma]] of Object.entries(f.subtipos)) {
      const l = document.createElement("label"); l.className = "hoja";
      l.innerHTML = `<input type="checkbox" data-subtipo="${subtipo}" data-familia="${familia}"> ` +   // todo desmarcado al empezar
        `<span class="simbolo ${forma}" style="background:${f.color};color:${f.color}"></span>${nombre}`;
      cont.appendChild(l);
      icono(`activo-${subtipo}`, f.color, forma);
    }
  }
  cont.addEventListener("change", (ev) => {
    const caja = ev.target;
    if (caja.dataset.subtipo) {
      const hermanas = [...cont.querySelectorAll(`input[data-subtipo][data-familia="${caja.dataset.familia}"]`)];
      const padre = cont.querySelector(`input[data-familia="${caja.dataset.familia}"]:not([data-subtipo])`);
      padre.checked = hermanas.every((h) => h.checked);
      padre.indeterminate = !padre.checked && hermanas.some((h) => h.checked);
    } else {
      for (const h of cont.querySelectorAll(`input[data-subtipo][data-familia="${caja.dataset.familia}"]`)) h.checked = caja.checked;
    }
    filtrarActivos();
  });

  mapa.addSource("activos", { type: "geojson", data: activosTodos, cluster: true, clusterRadius: 42, clusterMaxZoom: 12 });
  mapa.addLayer({ id: "activos-grupos", type: "circle", source: "activos", filter: ["has", "point_count"],
    paint: { "circle-color": "#5c6670", "circle-opacity": 0.85, "circle-stroke-color": "#fff", "circle-stroke-width": 2,
      "circle-radius": ["step", ["get", "point_count"], 12, 20, 16, 100, 20, 500, 24] } });
  mapa.addLayer({ id: "activos-grupos-n", type: "symbol", source: "activos", filter: ["has", "point_count"],
    layout: { "text-field": ["get", "point_count_abbreviated"], "text-size": 12, "text-font": ["Open Sans Semibold"] },
    paint: { "text-color": "#fff" } });
  mapa.addLayer({ id: "activos", type: "symbol", source: "activos", filter: ["!", ["has", "point_count"]],
    layout: { "icon-image": ["concat", "activo-", ["get", "subtipo"]], "icon-size": 1, "icon-allow-overlap": true } });

  mapa.on("click", "activos-grupos", (ev) => {
    const f = ev.features[0];
    mapa.getSource("activos").getClusterExpansionZoom(f.properties.cluster_id)
      .then((z) => mapa.easeTo({ center: f.geometry.coordinates, zoom: z }));
  });
  mapa.on("click", "activos", (ev) => { if (modo === "basal") mostrarActivo(ev.features[0].properties.id); });
  for (const id of ["activos", "activos-grupos"]) {
    mapa.on("mouseenter", id, () => mapa.getCanvas().style.cursor = "pointer");
    mapa.on("mouseleave", id, () => mapa.getCanvas().style.cursor = "");
  }
  fetch("/datos/activos.geojson").then((r) => r.json()).then((d) => { activosTodos = d; filtrarActivos(); resumenActivos(); });
}

// ----------------------------------------------------------------------------- resumen al arrancar
// Ventana centrada con los datos del visor: activos por familia y subtipo, capas de
// peligrosidad, población y, debajo, trenes y tráfico en tiempo real (movilidad.js). Se cierra con su botón y no vuelve.
// Al cerrarla vuelven la cabecera, el panel, el buscador, los controles y el color del mapa, que cambia de tamaño
function cerrarPortada() {
  $("#datos-inicio").remove();
  document.body.classList.remove("con-portada");
  mapa.resize();
}
$("#datos-inicio-cerrar").onclick = cerrarPortada;

// Entradas de la portada: cierran la portada y abren el modo con el panel derecho a la vista. Las de la crisis eligen la
// amenaza y dejan la alerta sin poner (el punto o la presa los elige quien la usa)
function entrar(modoNuevo, amenaza) {
  plegarPanel(false);
  cerrarPortada();
  if (modoNuevo === "crisis") { $("#modo-crisis").click(); $(`#crisis-${amenaza}`).click(); }
  else $("#modo-basal").click();
}
$("#entrada-incendio").onclick = () => entrar("crisis", "incendio");
$("#entrada-presa").onclick = () => entrar("crisis", "presa");
$("#entrada-basal").onclick = () => entrar("basal");

// Cifras de la portada: centros con ubicación, habitantes del censo, capas de peligrosidad, presas y trenes en tiempo real
function cifra(id, texto) { const c = $(`#${id}`); if (c) c.textContent = texto; }
cifra("cifra-capas", String(CAPAS.length));
consultar("/api/presas").then((l) => cifra("cifra-presas", String(l.length))).catch(() => cifra("cifra-presas", "–"));
// Trenes de viajeros de Renfe en este momento (GTFS-Realtime); sin conexión, no hay dato
if (SIN_CONEXION) cifra("cifra-trenes", "–");
else consultar("/api/trenes").then((d) => cifra("cifra-trenes", d.error ? "–" : numero(d.trenes.length))).catch(() => cifra("cifra-trenes", "–"));

function resumenActivos() {
  cifra("cifra-centros", numero(activosTodos.features.length));
  const caja = $("#datos-activos");
  if (!caja) return;
  const n = {};
  for (const f of activosTodos.features) n[f.properties.subtipo] = (n[f.properties.subtipo] || 0) + 1;
  const filas = Object.values(FAMILIAS).map((f) => {
    const subtipos = Object.entries(f.subtipos);
    const total = subtipos.reduce((s, [k]) => s + (n[k] || 0), 0);
    return `<tr class="familia"><td><span class="simbolo circulo" style="background:${f.color}"></span>${f.nombre}</td><td class="num">${numero(total)}</td></tr>` +
      subtipos.map(([k, [nombre, forma]]) => `<tr class="subtipo"><td><span class="simbolo ${forma}" style="background:${f.color};color:${f.color}"></span>` +
        `${nombre}</td><td class="num">${numero(n[k] || 0)}</td></tr>`).join("");
  }).join("");
  caja.innerHTML = `<h3>Activos</h3><table>${filas}<tr class="total"><td>Total en el mapa</td><td class="num">${numero(activosTodos.features.length)}</td></tr></table>` +
    `<p class="meta">Centros educativos, sanitarios y de atención social de la Comunidad de Madrid (datos.comunidad.madrid).</p>`;
}

function resumenCapas() {
  const caja = $("#datos-capas");
  if (!caja) return;
  const grupos = [["Naturales", "naturales"], ["Tecnológicos", "tecnológicas"]].map(([g, adj]) => `${CAPAS.filter((c) => c[2] === g).length} ${adj}`);
  caja.innerHTML = `<h3>Capas de peligrosidad</h3><p><strong>${CAPAS.length}</strong> capas: ${grupos.join(" y ")}, ` +
    `de 1 (muy baja) a 5 (muy alta), a 5 m.</p><p class="meta">Catálogo de Riesgos Potenciales de la Comunidad de Madrid (IDEM).</p>`;
}

async function resumenPoblacion() {
  const caja = $("#datos-poblacion");
  let d;
  try { d = await consultar("/api/resumen"); }
  catch (e) { if (caja) caja.innerHTML = `<h3>Población</h3><p class="error">${html(e.message)}</p>`; cifra("cifra-habitantes", "–"); return; }
  if (!$("#datos-poblacion")) return;   // ya se ha cerrado
  const p = d.poblacion;
  cifra("cifra-habitantes", `${(p.total / 1e6).toLocaleString("es-ES", { maximumFractionDigits: 2 })}`);
  caja.innerHTML = `<h3>Población</h3><p><strong>${numero(p.total)}</strong> habitantes, ${numero(p.menores_16)} menores de 16 y ` +
    `${numero(p.mayores_64)} mayores de 64, en las ${numero(d.celdas)} celdas de 1 km que cubren la Comunidad.</p><p class="meta">INE, Censo 2021 en la rejilla europea de 1 km.</p>`;
}
resumenCapas();
resumenPoblacion();

// ----------------------------------------------------------------------------- buscador de municipios
// Arriba en el centro del mapa, en los tres modos. Sin tildes ni mayúsculas; primero los
// que empiezan por lo escrito. Al elegir, el mapa encuadra el término; en el análisis basal, además, se abre la celda
// de 1 km de su capital. En la crisis solo se encuadra (un clic en el mapa movería la alerta)
const buscador = { municipios: null, resultados: [], activo: -1 };
const sinTildes = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

// Se piden una sola vez, al arrancar, para que las sugerencias salgan al teclear
function municipiosBuscador() {
  if (!buscador.municipios) {
    buscador.municipios = consultar("/api/municipios").then((l) => l.map((m) => ({ ...m, clave: sinTildes(m.nombre) })));
    buscador.municipios.catch(() => { buscador.municipios = null; });   // si falla, se reintenta en la siguiente búsqueda
  }
  return buscador.municipios;
}
municipiosBuscador();

function listaBuscador(abierta) {
  $("#buscador-lista").hidden = !abierta;
  $("#buscador-texto").setAttribute("aria-expanded", String(abierta));
}

function pintarBuscador() {
  const lista = $("#buscador-lista");
  lista.innerHTML = buscador.resultados.length
    ? buscador.resultados.map((m, i) => `<li role="option" data-i="${i}" class="${i === buscador.activo ? "activo" : ""}"` +
        ` aria-selected="${i === buscador.activo}">${html(m.nombre)}</li>`).join("")
    : `<li class="vacio">Ningún municipio con ese nombre</li>`;
  listaBuscador(true);
}

$("#buscador-texto").addEventListener("input", async (ev) => {
  const q = sinTildes(ev.target.value.trim());
  if (!q) { buscador.resultados = []; return listaBuscador(false); }
  let todos;
  try { todos = await municipiosBuscador(); } catch (e) { return; }
  if (sinTildes($("#buscador-texto").value.trim()) !== q) return;   // ya se ha escrito otra cosa
  const empiezan = todos.filter((m) => m.clave.startsWith(q));
  const contienen = todos.filter((m) => !m.clave.startsWith(q) && m.clave.includes(q));
  buscador.resultados = [...empiezan, ...contienen].slice(0, 8);
  buscador.activo = buscador.resultados.length ? 0 : -1;
  pintarBuscador();
});

$("#buscador-texto").addEventListener("keydown", (ev) => {
  const n = buscador.resultados.length;
  if (ev.key === "ArrowDown" && n) { buscador.activo = (buscador.activo + 1) % n; pintarBuscador(); ev.preventDefault(); }
  else if (ev.key === "ArrowUp" && n) { buscador.activo = (buscador.activo - 1 + n) % n; pintarBuscador(); ev.preventDefault(); }
  else if (ev.key === "Enter" && buscador.activo >= 0) { elegirMunicipio(buscador.resultados[buscador.activo]); ev.preventDefault(); }
  else if (ev.key === "Escape") listaBuscador(false);
});

// mousedown y no click: así se elige antes de que el campo pierda el foco y cierre la lista
$("#buscador-lista").addEventListener("mousedown", (ev) => {
  const li = ev.target.closest("li[data-i]");
  if (li) { ev.preventDefault(); elegirMunicipio(buscador.resultados[+li.dataset.i]); }
});
$("#buscador-texto").addEventListener("blur", () => listaBuscador(false));
$("#buscador-texto").addEventListener("focus", () => { if (buscador.resultados.length && $("#buscador-texto").value.trim()) pintarBuscador(); });

function elegirMunicipio(m) {
  $("#buscador-texto").value = m.nombre;
  listaBuscador(false);
  $("#buscador-texto").blur();
  const [oeste, sur, este, norte] = m.caja;
  mapa.fitBounds([[oeste, sur], [este, norte]], { padding: 60, maxZoom: 13, duration: 1200 });
  if (modo === "basal") mostrarCelda({ lng: m.lon, lat: m.lat });
}

function filtrarActivos() {
  const elegidos = new Set([...document.querySelectorAll("#familias input[data-subtipo]:checked")].map((i) => i.dataset.subtipo));
  mapa.getSource("activos").setData({ type: "FeatureCollection",
    features: activosTodos.features.filter((f) => elegidos.has(f.properties.subtipo)) });
  const total = document.querySelectorAll("#familias input[data-subtipo]").length;
  $("#ver-activos").checked = elegidos.size === total;
  $("#ver-activos").indeterminate = elegidos.size > 0 && elegidos.size < total;
}

// Casilla general de activos (Todos): enciende o apaga todas las familias y subtipos
$("#ver-activos").onchange = (ev) => {
  for (const caja of document.querySelectorAll("#familias input")) { caja.checked = ev.target.checked; caja.indeterminate = false; }
  filtrarActivos();
};

// ----------------------------------------------------------------------------- celda y fichas
const chip = (n, texto) => `<span class="nivel n${n}">${texto}</span>`;

// Ficha en una ventana arriba a la izquierda del mapa; al cerrarla se quita la celda marcada
function mostrarFicha(contenido) {
  $("#ficha").innerHTML = contenido;
  $("#ficha-mapa").hidden = false;
  $("#ficha-mapa").scrollTop = 0;
}

function cerrarFicha() {
  $("#ficha-mapa").hidden = true;
  if (mapa.getSource("celda")) mapa.getSource("celda").setData({ type: "FeatureCollection", features: [] });
}
$("#ficha-cerrar").onclick = cerrarFicha;

async function consultar(url) {
  const r = await fetch(url);
  const d = await r.json();
  if (!r.ok) throw new Error(d.error || r.statusText);
  return d;
}

async function mostrarCelda(lngLat) {
  let d;
  try { d = await consultar(`/api/celda?lon=${lngLat.lng.toFixed(6)}&lat=${lngLat.lat.toFixed(6)}`); }
  catch (e) { return mostrarFicha(`<p class="error">${html(e.message)}</p>`); }
  mapa.getSource("celda").setData({ type: "Feature", geometry: { type: "Polygon", coordinates: [d.contorno] } });
  const p = d.poblacion;
  const riesgos = d.riesgos.length
    ? `<table><tr><th>Riesgo</th><th>Nivel máximo</th><th class="num">% celda</th></tr>` +
      d.riesgos.map((r) => `<tr><td>${html(r.nombre)}</td><td>${chip(r.nivel, r.nivel_nombre)}</td><td class="num">${r.porcentaje.toLocaleString("es-ES")} %</td></tr>`).join("") +
      `</table>`
    : `<p class="nota">Sin peligrosidad en esta celda (aparte del fondo de incendios y avión).</p>`;
  const activos = d.activos.length
    ? `<ul class="activos">` + d.activos.map((a) => {
        const f = FAMILIAS[a.familia];
        return `<li data-id="${a.id}"><span class="simbolo ${f.subtipos[a.subtipo][1]}" style="background:${f.color};color:${f.color}"></span>` +
          `<span class="nombre">${html(rotulo(a))}</span>${chip(a.riesgo_max, a.riesgo_max_nombre)}</li>`;
      }).join("") + `</ul>`
    : `<p class="nota">Ningún activo ubicado en la celda.</p>`;
  const sensibles = d.sensibles.centros
    ? `<p class="nota">Además, ${d.sensibles.centros} centro${d.sensibles.centros > 1 ? "s" : ""} de acogida o protección` +
      (d.sensibles.plazas ? ` con ${numero(d.sensibles.plazas)} plazas` : "") + `.</p>` : "";
  mostrarFicha(`
    <h2>Celda de 1 km</h2>
    <p class="nota">${d.grd_id}${d.fraccion_comunidad < 0.99 ? ` · ${Math.round(d.fraccion_comunidad * 100)} % dentro de la Comunidad` : ""}</p>
    <div class="cifras"><div><strong>${numero(p.total)}</strong>habitantes</div>
      <div><strong>${numero(p.menores_16)}</strong>menores de 16</div><div><strong>${numero(p.mayores_64)}</strong>mayores de 64</div></div>
    <h3>Peligrosidad</h3>${riesgos}
    <h3>Activos (${d.activos.length})</h3>${activos}${sensibles}`);
  for (const li of $("#ficha").querySelectorAll("li[data-id]")) li.onclick = () => mostrarActivo(li.dataset.id);
}

async function mostrarActivo(id) {
  let d;
  try { d = await consultar(`/api/activo?id=${encodeURIComponent(id)}`); }
  catch (e) { return mostrarFicha(`<p class="error">${html(e.message)}</p>`); }
  const f = FAMILIAS[d.familia];
  const riesgos = d.riesgos.length
    ? `<table><tr><th>Amenaza</th><th>Peligrosidad</th><th>Riesgo</th></tr>` +
      d.riesgos.map((r) => `<tr><td>${html(r.nombre)}${r.fondo ? ' <span class="nota">(fondo)</span>' : ""}</td>` +
        `<td>${chip(r.peligrosidad, r.peligrosidad_nombre)}</td><td>${chip(r.riesgo, r.riesgo_nombre)}</td></tr>`).join("") + `</table>`
    : `<p class="nota">Sin peligrosidad en su ubicación.</p>`;
  mapa.getSource("celda").setData({ type: "FeatureCollection", features: [] });
  mostrarFicha(`
    <h2>${html(rotulo(d))}</h2>
    <p class="nota"><span class="simbolo ${f.subtipos[d.subtipo][1]}" style="background:${f.color};color:${f.color}"></span>` +
    `${f.nombre} · ${f.subtipos[d.subtipo][0]} · ${html(d.municipio)}${d.plazas ? ` · ${numero(d.plazas)} plazas` : ""}</p>
    <p>Vulnerabilidad <strong>${VULNERABILIDAD[d.vulnerabilidad]}</strong> · riesgo máximo ${chip(d.riesgo_max, d.riesgo_max_nombre)}</p>
    <h3>Riesgos potenciales</h3>${riesgos}
    <p><button class="enlace" id="ver-celda">Ver su celda de 1 km</button></p>`);
  $("#ver-celda").onclick = () => mostrarCelda({ lng: d.lon, lat: d.lat });
  mapa.flyTo({ center: [d.lon, d.lat], zoom: Math.max(mapa.getZoom(), 13) });
}

// ----------------------------------------------------------------------------- arranque
mapa.on("load", () => {
  mapa.addSource("celda", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  mapa.addLayer({ id: "celda-relleno", type: "fill", source: "celda", paint: { "fill-color": "#1f2328", "fill-opacity": 0.08 } });
  mapa.addLayer({ id: "celda-borde", type: "line", source: "celda", paint: { "line-color": "#1f2328", "line-width": 2 } });
  construirTerreno(mapa, "ign-pnoa");   // por debajo de todo
  construirCapas();
  prepararRelieve();                    // sombreado del relieve, entre el mapa base y las capas
  construirReferencias(mapa);           // carreteras, tren y nombres, encima de las capas
  construirActivos();
  mapa.on("click", (ev) => {
    if (!sobreElemento(ev.point) && modo === "basal") mostrarCelda(ev.lngLat);
  });
  document.dispatchEvent(new CustomEvent("mapa-listo"));
  mostrarNombres($("#ver-nombres").checked);   // con todas las capas de nombres ya creadas, también las de los modos
});
