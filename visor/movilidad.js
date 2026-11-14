// Movilidad en tiempo real: trenes de viajeros (Renfe) y tráfico
// (puntos de medida de la ciudad de Madrid e incidencias de la DGT en toda la Comunidad).
// Capas opcionales en los tres modos, con una casilla cada una en «Elementos del mapa». Apagadas al empezar (el
// visor arranca con todo desmarcado); en la copia sin conexión no se encienden nunca al arrancar.
// En gestión de crisis, la evolución simulada se cruza con la situación actual (cruzarMovilidad).
"use strict";

const SEMAFORO = { 0: "#2e9d43", 1: "#f5c400", 2: "#e0301e", 3: "#8b0000" };
const NIVEL_TRAFICO = ["fluido", "lento", "retenciones", "congestión"];
const REFRESCO_MS = { trenes: 30000, trafico: 300000 };
const movil = { trenes: false, trafico: false, datos: {}, temporizador: {} };
const fc = (features) => ({ type: "FeatureCollection", features });
const punto = (lon, lat, props) => ({ type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties: props });

function senal(nombre, dibujar) {
  const t = 32, c = document.createElement("canvas"); c.width = c.height = t;
  const g = c.getContext("2d"); dibujar(g, t);
  mapa.addImage(nombre, g.getImageData(0, 0, t, t), { pixelRatio: 2 });
}

document.addEventListener("mapa-listo", () => {
  // Señales de tráfico clásicas: prohibido (corte) y peligro (resto de incidencias)
  senal("senal-corte", (g, t) => {
    g.fillStyle = "#d1121b"; g.strokeStyle = "#fff"; g.lineWidth = 2;
    g.beginPath(); g.arc(t / 2, t / 2, 13, 0, Math.PI * 2); g.fill(); g.stroke();
    g.fillStyle = "#fff"; g.fillRect(8, t / 2 - 3, t - 16, 6);
  });
  senal("senal-peligro", (g, t) => {
    g.beginPath(); g.moveTo(t / 2, 2); g.lineTo(t - 2, t - 4); g.lineTo(2, t - 4); g.closePath();
    g.fillStyle = "#fff"; g.fill(); g.strokeStyle = "#d1121b"; g.lineWidth = 4; g.lineJoin = "round"; g.stroke();
    g.fillStyle = "#111"; g.font = "bold 15px sans-serif"; g.textAlign = "center"; g.fillText("!", t / 2, t - 8);
  });

  for (const id of ["trafico-ciudad", "trafico-incidencias", "trenes"]) mapa.addSource(id, { type: "geojson", data: fc([]) });
  const debajo = "activos-grupos";   // por encima de capas y humo, por debajo de los activos
  mapa.addLayer({ id: "trafico-ciudad", type: "circle", source: "trafico-ciudad", layout: { visibility: "none" },
    filter: [">=", ["zoom"], ["match", ["get", "nivel"], 0, 11, 9]],   // lo fluido solo de cerca
    paint: { "circle-color": ["match", ["get", "nivel"], 0, SEMAFORO[0], 1, SEMAFORO[1], 2, SEMAFORO[2], SEMAFORO[3]],
      "circle-radius": zoom(9, 1.8, 12, 3.5, 15, 6), "circle-stroke-color": "#fff", "circle-stroke-width": 0.6 } }, debajo);
  mapa.addLayer({ id: "trafico-incidencias", type: "symbol", source: "trafico-incidencias", layout: { visibility: "none",
    "icon-image": ["match", ["get", "categoria"], "corte", "senal-corte", "senal-peligro"],
    "icon-size": zoom(8, 0.6, 12, 0.9), "icon-allow-overlap": true,
    "symbol-sort-key": ["match", ["get", "categoria"], "corte", 2, 1] } }, debajo);
  mapa.addLayer({ id: "trenes", type: "circle", source: "trenes", layout: { visibility: "none" },
    paint: { "circle-color": "#2b2b2b", "circle-radius": zoom(8, 4, 13, 7), "circle-stroke-color": "#fff", "circle-stroke-width": 2 } }, debajo);
  mapa.addLayer({ id: "trenes-linea", type: "symbol", source: "trenes", minzoom: 11, layout: { visibility: "none",
    "text-field": ["get", "linea"], "text-font": ["Open Sans Semibold"], "text-size": 11, "text-anchor": "left",
    "text-offset": [0.9, 0], "text-allow-overlap": true },
    paint: { "text-color": "#2b2b2b", "text-halo-color": "#fff", "text-halo-width": 1.6 } }, debajo);
  capasClicables.push("trenes", "trafico-ciudad", "trafico-incidencias");

  mapa.on("click", "trenes", (ev) => {
    const p = ev.features[0].properties;
    emergente(ev.lngLat, `<strong>Tren ${html(p.linea)}</strong><br>${html(p.estado)}${p.parada ? ` · parada ${html(p.parada)}` : ""}` +
      `<br><span class="meta">${html(p.etiqueta)} · posición de las ${(p.hora || "").slice(11, 16)}</span>`);
  });
  mapa.on("click", "trafico-ciudad", (ev) => {
    const p = ev.features[0].properties;
    emergente(ev.lngLat, `<strong>${html(p.descripcion || "Punto de medida " + p.id)}</strong><br>` +
      `<span class="semaforo" style="background:${SEMAFORO[p.nivel]}"></span>${NIVEL_TRAFICO[p.nivel]}` +
      `<br><span class="meta">${p.intensidad != null ? numero(p.intensidad) + " vehículos/h" : ""}` +
      `${p.ocupacion != null ? ` · ocupación ${numero(p.ocupacion)} %` : ""}${p.velocidad ? ` · ${numero(p.velocidad)} km/h` : ""}</span>`);
  });
  mapa.on("click", "trafico-incidencias", (ev) => emergente(ev.lngLat, textoIncidencia(ev.features[0].properties)));
  for (const id of ["trenes", "trafico-ciudad", "trafico-incidencias"]) {
    mapa.on("mouseenter", id, () => mapa.getCanvas().style.cursor = "pointer");
    mapa.on("mouseleave", id, () => mapa.getCanvas().style.cursor = "");
  }
  for (const capa of ["trenes", "trafico"]) activarMovilidad(capa, !SIN_CONEXION && $(`#ver-${capa}`).checked);
  // La ventana «Datos del visor» lleva trenes, tráfico e incidencias aunque sus capas estén apagadas: se piden una vez
  if (!SIN_CONEXION) {
    movil.datos.trenes = movil.datos.trenes || null; movil.datos.trafico = movil.datos.trafico || null;
    leyendaMovilidad();
    if (!movil.trenes) cargarTrenes();
    if (!movil.trafico) cargarTrafico();
  } else leyendaMovilidad();
});

function emergente(lngLat, contenido) {
  new maplibregl.Popup({ maxWidth: "300px" }).setLngLat(lngLat).setHTML(contenido).addTo(mapa);
}

const lugarIncidencia = (p) => [p.carretera, p.km != null ? `km ${numero(p.km)}` : "", p.sentido ? `sentido ${p.sentido}` : ""].filter(Boolean).join(" · ");
const textoIncidencia = (p) => `<strong>${html(p.tipo)}</strong><br>${html(lugarIncidencia(p))}` +
  `${p.municipio ? `<br>${html(p.municipio)}` : ""}<br><span class="meta">DGT${p.desde ? ` · desde ${p.desde.slice(8, 10)}/${p.desde.slice(5, 7)} ${p.desde.slice(11, 16)}` : ""}</span>`;

// ----------------------------------------------------------------------------- carga y refresco
async function cargarTrenes() {
  try {
    const d = await consultar("/api/trenes");
    movil.datos.trenes = d;
    mapa.getSource("trenes").setData(fc(d.trenes.map((t) => punto(t.lon, t.lat, t))));
  } catch (e) { movil.datos.trenes = { error: e.message }; }
  leyendaMovilidad();
}

async function cargarTrafico() {
  try {
    const d = await consultar("/api/trafico");
    movil.datos.trafico = d;
    mapa.getSource("trafico-ciudad").setData(fc((d.ciudad.puntos || []).map((p) => punto(p.lon, p.lat, p))));
    mapa.getSource("trafico-incidencias").setData(fc((d.incidencias.incidencias || []).map((i) => punto(i.lon, i.lat, i))));
  } catch (e) { movil.datos.trafico = { ciudad: { error: e.message }, incidencias: { error: e.message } }; }
  leyendaMovilidad();
}

function activarMovilidad(capa, si) {
  if (!mapa.getLayer("trenes")) { $(`#ver-${capa}`).checked = movil[capa]; return; }   // el mapa aún no ha cargado
  movil[capa] = si;
  $(`#ver-${capa}`).checked = si;
  const capas = capa === "trenes" ? ["trenes", "trenes-linea"] : ["trafico-ciudad", "trafico-incidencias"];
  for (const id of capas) visible(id, si);
  clearInterval(movil.temporizador[capa]);
  const cargar = capa === "trenes" ? cargarTrenes : cargarTrafico;
  if (si) { cargar(); movil.temporizador[capa] = setInterval(cargar, REFRESCO_MS[capa]); }
  leyendaMovilidad();
}
$("#ver-trenes").onclick = () => activarMovilidad("trenes", !movil.trenes);
$("#ver-trafico").onclick = () => activarMovilidad("trafico", !movil.trafico);

const horaDeIso = (iso) => (iso || "").slice(11, 16);

function leyendaMovilidad() {
  const caja = $("#movilidad-leyenda"), partes = [];
  if (!caja) return;   // va en el resumen del arranque; cerrado, ya no se muestra
  if (SIN_CONEXION && !movil.trenes && !movil.trafico) {
    caja.hidden = false;
    caja.innerHTML = `<h3>En tiempo real</h3><p class="meta">Copia sin conexión: sin trenes, tráfico ni incidencias de la DGT.</p>`;
    return;
  }
  if (movil.trenes || "trenes" in movil.datos) {
    const d = movil.datos.trenes;
    partes.push(`<div><span class="tren"></span><strong>Trenes de viajeros</strong> · ` + (!d ? "consultando…"
      : d.error ? `<span class="error">${html(d.error)}</span>` : `${d.trenes.length} a las ${horaDeIso(d.marca || d.consultado)}`) +
      `<br><span class="meta">Renfe, GTFS-Realtime (CC BY 4.0). Cada 30 s. Sin estimar personas.</span></div>`);
  }
  if (movil.trafico || "trafico" in movil.datos) {
    const d = movil.datos.trafico;
    const ciudad = !d ? "consultando…" : d.ciudad.error ? `<span class="error">${html(d.ciudad.error)}</span>`
      : `${numero(d.ciudad.puntos.length)} puntos, datos de las ${(d.ciudad.marca || "").slice(11, 16)}`;
    const inc = !d ? "consultando…" : d.incidencias.error ? `<span class="error">${html(d.incidencias.error)}</span>`
      : `${d.incidencias.incidencias.length}, consultadas a las ${horaDeIso(d.incidencias.consultado)}`;
    partes.push(`<div><strong>Tráfico de la ciudad de Madrid</strong> · ${ciudad}<br>` +
      NIVEL_TRAFICO.map((n, i) => `<span class="semaforo" style="background:${SEMAFORO[i]}"></span>${n}`).join(" ") +
      `<br><span class="meta">Ayuntamiento de Madrid. Lo fluido, solo de cerca. Cada 5 min.</span></div>` +
      `<div><strong>Incidencias de la DGT</strong> · ${inc}<br><span class="senal corte"></span>corte de carretera o calzada ` +
      `<span class="senal peligro"></span>otras<br><span class="meta">Toda la Comunidad. Cada 5 min.</span></div>`);
  }
  caja.hidden = !partes.length;
  caja.innerHTML = partes.length ? `<h3>En tiempo real</h3>${partes.join("")}` : "";
}

// ----------------------------------------------------------------------------- cruce con la crisis
// Llamada desde crisis.js al cargar una simulación: añade al panel de resultados los trenes, las
// incidencias y los puntos de tráfico actuales dentro de la zona afectada, y los marca en el mapa.
async function cruzarMovilidad(sim) {
  const seccion = document.createElement("div");
  seccion.id = "movilidad-crisis";
  seccion.innerHTML = `<h3>Trenes y tráfico ahora en la zona afectada</h3><p class="meta">Consultando Renfe, la DGT y el Ayuntamiento de Madrid…</p>`;
  $("#resultado").appendChild(seccion);
  let d;
  try { d = await consultar(`/api/incendio/movilidad?id=${encodeURIComponent(sim.id)}`); }
  catch (e) { seccion.innerHTML = `<h3>Trenes y tráfico ahora en la zona afectada</h3><p class="error">${html(e.message)}</p>`; return; }
  if (!sim || d.id !== sim.id || !document.contains(seccion)) return;   // ya hay otra simulación
  const hora0 = new Date(sim.ignicion.hora);
  const horaDe = (min) => hhmm(new Date(hora0.getTime() + min * 60000));
  const efecto = (e) => [e.minutos_llamas != null ? `fuego a menos de ${d.distancia_alcanzado_m} m a las ${horaDe(e.minutos_llamas)}` : "",
    e.minutos_humo != null ? `humo a las ${horaDe(e.minutos_humo)}` : ""].filter(Boolean).join(" · ");
  const marca = (e) => `<span class="marca ${e.minutos_llamas === e.minutos ? "llamas" : "humo"}">+${duracion(e.minutos)}</span>`;
  const bloque = (titulo, fuente, nombre, simbolo) => {
    if (fuente.error) return `<h4>${titulo}</h4><p class="error">${html(fuente.error)}</p>`;
    const lista = fuente.afectados;
    return `<h4>${titulo} (${lista.length})</h4>` + (lista.length
      ? `<ul class="activos">${lista.map((e) => `<li data-min="${e.minutos}" data-lon="${e.lon}" data-lat="${e.lat}">` +
          `<span class="hora">${horaDe(e.minutos)}</span><span class="nombre">${simbolo(e)}${nombre(e)}<br><span class="meta">${efecto(e)}</span></span>${marca(e)}</li>`).join("")}</ul>`
      : `<p class="meta">Ninguno de ${numero(fuente.total)}.</p>`);
  };
  seccion.innerHTML = `<h3>Trenes y tráfico ahora en la zona afectada</h3>
    <p class="meta">Situación actual (trenes a las ${horaDeIso(d.trenes.marca || d.trenes.consultado)}) frente a la evolución simulada: elementos que el fuego
      o el humo alcanzarían en 24 h. Los trenes se mueven: es una foto, no su recorrido.</p>` +
    bloque("Trenes de viajeros", d.trenes, (e) => `Tren ${html(e.linea)} · ${html(e.estado)}`, () => `<span class="simbolo circulo" style="background:#2b2b2b"></span>`) +
    bloque("Incidencias de la DGT", d.incidencias, (e) => `${html(e.tipo)} · ${html(lugarIncidencia(e))}`,
      (e) => `<span class="senal ${e.categoria === "corte" ? "corte" : "peligro"}"></span>`) +
    bloque("Tráfico de la ciudad", d.ciudad, (e) => `${html(e.descripcion)} · ${NIVEL_TRAFICO[e.nivel]}`,
      (e) => `<span class="semaforo" style="background:${SEMAFORO[e.nivel]}"></span>`);
  for (const li of seccion.querySelectorAll("li[data-lon]")) li.onclick = () => mapa.flyTo({ center: [+li.dataset.lon, +li.dataset.lat], zoom: 14 });
  // En la animación, cada uno con un punto del color del efecto y su nombre
  const nombres = { trenes: (e) => `Tren de Cercanías · ${e.linea}`, incidencias: (e) => `${e.tipo} · ${lugarIncidencia(e)}`,
    ciudad: (e) => `Punto de tráfico · ${e.descripcion}` };
  anadirAfectados(["trenes", "incidencias", "ciudad"].flatMap((k) => (d[k].afectados || []).map((e) => afectado(e.lon, e.lat,
    { id: e.id, clase: k, punto: true, tipo: e.minutos_llamas === e.minutos ? "llamas" : "humo", minutos: e.minutos, nombre: nombres[k](e) }))));
  anadirSucesosMovilidad(d);   // a la cronología (crisis.js)
}
