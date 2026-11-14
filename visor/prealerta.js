// Prealerta (decisiones del 08-11-2026): dónde está el riesgo focal en los próximos
// 7 días según la previsión de AEMET. El servidor cruza la previsión municipal (diaria a 7 días y horaria a 3)
// con los umbrales del Plan Meteoalerta de cada zona de aviso y con los avisos oficiales, y deduce qué peligros
// del catálogo activa cada fenómeno. Aquí se pintan los municipios por nivel, las zonas de aviso y los activos
// con riesgo focal del día elegido; se consulta el detalle de un municipio y se muestran las 13 capas
// meteorológicas del catálogo (propensión climática de cada punto).
"use strict";

const PA = { color: ["#8fcf8f", "#f5d000", "#f28c00", "#d1121b"], nombre: ["verde", "amarillo", "naranja", "rojo"] };
const CAPAS_METEO = [
  ["1_1", "Temperaturas máximas"], ["1_2", "Temperaturas mínimas"], ["1_3", "Vientos fuertes"],
  ["1_4", "Lluvias persistentes (12 h)"], ["1_5", "Lluvias fuertes (1 h)"], ["1_6", "Nevadas"], ["1_7", "Tormentas"],
  ["1_8", "Niebla"], ["1_9", "Ola de calor"], ["1_10", "Ola de frío"], ["1_11", "Polvo en suspensión"],
  ["1_12", "Sequías (consumo humano)"], ["1_13", "Granizo"],
];
const CAPAS_PRE = ["municipios-relleno", "municipios-borde", "municipios-elegido", "zonas-aviso", "zonas-aviso-nombre", "focal"];
const MAX_LISTA = 40;
const pre = { datos: null, dia: 0, municipios: null, municipio: null, temporizador: null, activo: false };
const chipPA = (n) => `<span class="nivel pa${n}">${PA.nombre[n]}</span>`;
const fechaCorta = (iso) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
const fechaHora = (iso) => iso ? `${fechaCorta(iso)} a las ${iso.slice(11, 16)}` : "—";
const horaDe = (iso) => iso ? iso.slice(11, 16) : "";
const origenDe = (o) => o === "AEMET" ? `<span class="origen aemet">aviso AEMET</span>` : `<span class="origen">previsión</span>`;
const nombreSubtipo = (s) => { for (const f of Object.values(FAMILIAS)) if (f.subtipos[s]) return f.subtipos[s][0]; return s; };
const nombreFenomeno = (c) => (pre.datos && pre.datos.fenomenos[c]) ? pre.datos.fenomenos[c].nombre : c;
const volar = (li) => mapa.flyTo({ center: [+li.dataset.lon, +li.dataset.lat], zoom: Math.max(mapa.getZoom(), 14) });

// ----------------------------------------------------------------------------- capas del mapa
document.addEventListener("mapa-listo", () => {
  const debajo = "activos-grupos", oculta = { visibility: "none" };
  mapa.addSource("municipios", { type: "geojson", data: fc([]) });
  mapa.addSource("zonas-aviso", { type: "geojson", data: "/datos/zonas_aviso.geojson", attribution: "Zonas de aviso © AEMET" });
  mapa.addSource("focal", { type: "geojson", data: fc([]) });
  mapa.addLayer({ id: "municipios-relleno", type: "fill", source: "municipios", layout: oculta,
    paint: { "fill-color": ["match", ["get", "nivel"], 1, PA.color[1], 2, PA.color[2], 3, PA.color[3], "rgba(0,0,0,0)"], "fill-opacity": 0.42 } }, debajo);
  mapa.addLayer({ id: "municipios-borde", type: "line", source: "municipios", layout: oculta,
    paint: { "line-color": "#5c6670", "line-width": 0.7 } }, debajo);
  mapa.addLayer({ id: "municipios-elegido", type: "line", source: "municipios", layout: oculta, filter: ["==", ["get", "codigo"], ""],
    paint: { "line-color": "#1f2328", "line-width": 2.5 } }, debajo);
  mapa.addLayer({ id: "zonas-aviso", type: "line", source: "zonas-aviso", layout: oculta, filter: ["==", ["geometry-type"], "Polygon"],
    paint: { "line-color": "#1f2328", "line-width": 1.8, "line-dasharray": [4, 3] } }, debajo);
  mapa.addLayer({ id: "zonas-aviso-nombre", type: "symbol", source: "zonas-aviso", filter: ["==", ["geometry-type"], "Point"],
    layout: { ...oculta, "text-field": ["get", "nombre"], "text-font": ["Open Sans Semibold"], "text-size": 12,
      "text-letter-spacing": 0.06, "text-transform": "uppercase" },
    paint: { "text-color": "#1f2328", "text-halo-color": "#fff", "text-halo-width": 1.6 } });
  // Activos con riesgo focal: anillo del color del nivel, pequeño de lejos y del tamaño del símbolo de cerca
  const colorNivel = ["match", ["get", "nivel"], 3, PA.color[3], 2, PA.color[2], PA.color[1]];
  mapa.addLayer({ id: "focal", type: "circle", source: "focal", layout: oculta,
    paint: { "circle-radius": zoom(8, 4, 11, 8, 13, 11), "circle-color": colorNivel, "circle-opacity": 0.25,
      "circle-stroke-width": zoom(8, 1.5, 12, 3), "circle-stroke-color": colorNivel } });
  capasClicables.push("focal");
  construirCapasMeteo();

  mapa.on("click", "municipios-relleno", (ev) => {
    if (modo === "prealerta" && !sobreElemento(ev.point)) mostrarMunicipio(ev.features[0].properties.codigo);
  });
  mapa.on("click", "focal", (ev) => {
    if (modo !== "prealerta") return;
    const p = ev.features[0].properties;
    emergente(ev.lngLat, `<strong>${html(p.nombre)}</strong><br>${chipPA(p.nivel)} ${html(p.motivos)}`);
  });
  mapa.on("mouseenter", "focal", () => mapa.getCanvas().style.cursor = "pointer");
  mapa.on("mouseleave", "focal", () => mapa.getCanvas().style.cursor = "");
  aplicarModoPrealerta();
  if (pre.activo) cargarPrealerta();   // el modo se eligió antes de que el mapa estuviera listo
});

// El modo puede cambiar antes de que el mapa esté listo: las capas se ajustan cuando existen (también desde "mapa-listo")
function aplicarModoPrealerta() {
  pre.activo = modo === "prealerta";
  if (!mapa.getLayer("focal")) return;
  for (const id of CAPAS_PRE) visible(id, pre.activo);
  for (const caja of document.querySelectorAll("#capas-meteo input[data-capa]:checked")) mostrarCapaMeteo(caja.dataset.capa, pre.activo);
}

document.addEventListener("modo", () => {
  aplicarModoPrealerta();
  if (pre.activo) cargarPrealerta(); else clearTimeout(pre.temporizador);
});

// Las 13 capas meteorológicas del catálogo se añaden al mapa la primera vez que se piden, por debajo de las
// referencias (carreteras y nombres)
function mostrarCapaMeteo(codigo, si) {
  if (!mapa.getLayer(`capa-${codigo}`)) {
    if (!si) return;
    mapa.addSource(`capa-${codigo}`, { type: "raster", url: `pmtiles:///datos/capas/peligrosid_${codigo}.pmtiles`, tileSize: 256,
      attribution: "Catálogo de Riesgos Potenciales © Comunidad de Madrid" });
    mapa.addLayer({ id: `capa-${codigo}`, type: "raster", source: `capa-${codigo}`,
      paint: { "raster-opacity": 0.8, "raster-resampling": "nearest" } }, capasCon(mapa, "ref-")[0]);
  }
  visible(`capa-${codigo}`, si);
}

function construirCapasMeteo() {
  const cont = $("#capas-meteo");
  cont.innerHTML = CAPAS_METEO.map(([c, n]) => `<label class="hoja"><input type="checkbox" data-capa="${c}"> ${n}</label>`).join("");
  cont.addEventListener("change", (ev) => { if (ev.target.dataset.capa) mostrarCapaMeteo(ev.target.dataset.capa, ev.target.checked && pre.activo); });
  $("#leyenda-meteo").innerHTML = "Peligrosidad: " + [1, 2, 3, 4, 5].map((n) => `<span class="n${n}"></span>${NIVELES[n]}`).join("");
}

// ----------------------------------------------------------------------------- carga
async function cargarPrealerta() {
  clearTimeout(pre.temporizador);
  try {
    if (!pre.municipios) pre.municipios = await fetch("/datos/municipios.geojson").then((r) => r.json());
    const d = await consultar("/api/prealerta");
    // Mientras AEMET se actualiza solo cambia el estado: no se repinta el mapa si la previsión y los avisos son los mismos
    const igual = pre.datos && !pre.datos.sin_prevision && !d.sin_prevision && pre.datos.consultado === d.consultado &&
      pre.datos.avisos_consultados === d.avisos_consultados && pre.datos.fuente_avisos === d.fuente_avisos;
    pre.datos = d;
    pintarEstado(d);
    if (d.sin_prevision) {
      $("#prealerta-dias").innerHTML = ""; $("#prealerta-dia").innerHTML = ""; $("#prealerta-activos").innerHTML = "";
      pintarMunicipios(null);
    } else if (!igual) {
      pre.dia = Math.min(pre.dia, d.fechas.length - 1);
      construirDias(d);
      await elegirDia(pre.dia);
    }
    if (d.estado && d.estado.actualizando && pre.activo) pre.temporizador = setTimeout(cargarPrealerta, 4000);
  } catch (e) {
    $("#prealerta-estado").innerHTML = `<p class="error">No se ha podido cargar la prealerta: ${html(e.message)}</p>`;
  }
}

function pintarEstado(d) {
  const e = d.estado || {}, partes = [];
  if (d.sin_prevision) partes.push(`<p>Todavía no hay ninguna previsión de AEMET guardada.</p>`);
  else partes.push(`<p class="meta">Previsión de AEMET OpenData elaborada el ${fechaHora(d.elaborado)} y pedida el ${fechaHora(d.consultado)}` +
    `${d.municipios_sin_dato.length ? ` (${d.municipios_sin_dato.length} municipios sin previsión)` : ""}.` +
    (d.fuente_avisos ? ` Avisos: ${html(d.fuente_avisos)}, consultados a las ${horaDe(d.avisos_consultados)}.`
      : d.avisos_error ? ` Avisos no disponibles: ${html(d.avisos_error)}.` : "") + `</p>`);
  if (e.actualizando) {
    const p = e.progreso || {};
    partes.push(`<p class="meta actualizando">Pidiendo la previsión a AEMET: ${p.hechos || 0} de ${p.total || 179} municipios` +
      `${p.municipio ? ` (${html(p.municipio)})` : ""}…</p>`);
  } else {
    if (e.error) partes.push(`<p class="error">${html(e.error)}</p>`);
    partes.push(`<p><button id="prealerta-actualizar" type="button">Actualizar la previsión</button></p>`);
  }
  $("#prealerta-estado").innerHTML = partes.join("");
  const b = $("#prealerta-actualizar");
  if (b) b.onclick = async () => { b.disabled = true; await fetch("/api/prealerta/actualizar", { method: "POST" }); cargarPrealerta(); };
}

function construirDias(d) {
  const cont = $("#prealerta-dias");
  cont.innerHTML = d.dias.map((dia, i) => {
    const n = Object.values(d.municipios).filter((m) => (m.niveles[i] || 0) >= 1).length;
    return `<button type="button" class="dia${i === pre.dia ? " activo" : ""}" data-dia="${i}" style="--c:${PA.color[dia.nivel_max]}" ` +
      `title="${PA.nombre[dia.nivel_max]}${n ? `: ${n} municipios en amarillo o más` : ""}">` +
      `<span class="nombre">${html(dia.nombre)}</span><span class="fecha">${fechaCorta(dia.fecha)}</span>` +
      `<span class="punto"></span><span class="cuenta">${n ? `${n} mun.` : "—"}</span></button>`;
  }).join("");
  for (const b of cont.querySelectorAll("button")) b.onclick = () => elegirDia(+b.dataset.dia);
}

async function elegirDia(i) {
  pre.dia = i;
  for (const b of document.querySelectorAll("#prealerta-dias button")) b.classList.toggle("activo", +b.dataset.dia === i);
  pintarMunicipios(i);
  pintarResumenDia(i);
  if (pre.municipio) mostrarMunicipio(pre.municipio);
  try {
    const a = await consultar(`/api/prealerta/activos?dia=${i}`);
    if (a.dia === pre.dia) pintarActivos(a);
  } catch (e) { $("#prealerta-activos").innerHTML = `<p class="error">${html(e.message)}</p>`; }
}

// ----------------------------------------------------------------------------- mapa
function pintarMunicipios(i) {
  const d = pre.datos, fuente = mapa.getSource("municipios");
  if (!fuente) return;   // el mapa aún no está listo: se pintará desde "mapa-listo"
  const features = pre.municipios.features.map((f) => {
    const m = i !== null && d.municipios[f.properties.codigo];
    return { ...f, properties: { ...f.properties, nivel: m ? (m.niveles[i] || 0) : 0, fenomeno: m ? m.fenomeno_max[i] : null } };
  });
  fuente.setData({ type: "FeatureCollection", features });
}

// ----------------------------------------------------------------------------- panel: día
function pintarResumenDia(i) {
  const d = pre.datos, dia = d.dias[i];
  const fen = Object.entries(dia.fenomenos).filter(([, v]) => v.nivel >= 1)
    .sort((a, b) => b[1].nivel - a[1].nivel || b[1].municipios - a[1].municipios);
  const tabla = fen.length
    ? `<table><tr><th>Fenómeno</th><th>Nivel</th><th class="num">Municipios</th><th>Origen</th></tr>` + fen.map(([c, v]) =>
        `<tr><td>${html(nombreFenomeno(c))}</td><td>${chipPA(v.nivel)}</td><td class="num">${v.municipios}</td><td>${origenDe(v.origen)}</td></tr>`).join("") + `</table>`
    : `<p class="nota">Ningún fenómeno adverso previsto: toda la Comunidad en verde.</p>`;
  const avisos = dia.avisos.length
    ? `<h4>Avisos oficiales (${dia.avisos.length})</h4><ul class="avisos">` + dia.avisos.map((a) =>
        `<li>${chipPA(a.nivel)} <strong>${html(a.fenomeno_nombre)}</strong> en ${html(a.zona_nombre)}${a.umbral ? `: ${html(a.umbral)}` : ""}` +
        `<br><span class="meta">de ${horaDe(a.inicio)} a ${horaDe(a.fin)}${a.fin.slice(0, 10) !== a.inicio.slice(0, 10) ? ` del ${fechaCorta(a.fin)}` : ""} · ${html(a.fuente)}</span></li>`).join("") + `</ul>`
    : "";
  const act = Object.values(dia.activaciones);
  const activaciones = act.length
    ? `<h4>Peligros del catálogo que se activan</h4><p>${act.map((v) => `${chipPA(v.nivel)} ${html(v.nombre)}`).join(" · ")}</p>` : "";
  $("#prealerta-dia").innerHTML = `<h3>${html(dia.nombre)} ${fechaCorta(dia.fecha)} · ${chipPA(dia.nivel_max)}</h3>${tabla}${avisos}${activaciones}`;
}

// ----------------------------------------------------------------------------- panel: activos con riesgo focal
const itemActivo = (x, extra) => {
  const f = FAMILIAS[x.familia];
  return `<li data-lon="${x.lon}" data-lat="${x.lat}"><span class="simbolo ${f.subtipos[x.subtipo][1]}" style="background:${f.color};color:${f.color}"></span>` +
    `<span class="nombre">${html(rotulo(x))}<br><span class="meta">${html(x.municipio)} · vulnerabilidad ${VULNERABILIDAD[x.vulnerabilidad]}${extra ? " · " + extra : ""}</span></span>${chipPA(x.nivel)}</li>`;
};
const sensiblesTexto = (s) => s.centros
  ? `<p class="nota">Además, ${s.centros} centro${s.centros > 1 ? "s" : ""} de acogida o protección con ${numero(s.plazas)} plazas (no se muestran uno a uno).</p>` : "";

function grupoActivos(titulo, lista, extra) {
  if (!lista.length) return "";
  const porSubtipo = {};
  for (const x of lista) porSubtipo[x.subtipo] = (porSubtipo[x.subtipo] || 0) + 1;
  const desglose = Object.entries(porSubtipo).map(([s, n]) => `${numero(n)} ${nombreSubtipo(s).toLowerCase()}`).join(", ");
  return `<h4>${titulo} (${numero(lista.length)})</h4><p class="meta">${desglose}.</p>` +
    `<ul class="activos">${lista.slice(0, MAX_LISTA).map((x) => itemActivo(x, extra(x))).join("")}</ul>` +
    (lista.length > MAX_LISTA ? `<p class="meta">… y ${numero(lista.length - MAX_LISTA)} más, todos marcados en el mapa.</p>` : "");
}

function listasActivos(a) {
  const directos = {}, activados = {};
  for (const x of a.directos) (directos[x.fenomeno] ||= []).push(x);
  for (const x of a.activados) (activados[x.capa] ||= []).push(x);
  return Object.values(directos).map((l) => grupoActivos(`Efecto directo: ${l[0].fenomeno_nombre.toLowerCase()}`, l, () => "")).join("") +
    Object.values(activados).map((l) => grupoActivos(`Peligro activado: ${l[0].capa_nombre.toLowerCase()}`, l,
      (x) => `peligrosidad ${x.peligrosidad_nombre}, riesgo ${chip(x.riesgo, x.riesgo_nombre)}`)).join("") + sensiblesTexto(a.sensibles);
}

function pintarActivos(a) {
  const marcas = new Map();
  const marcar = (x, motivo) => {
    const m = marcas.get(x.id) || { lon: x.lon, lat: x.lat, nombre: rotulo(x), nivel: 0, motivos: [] };
    m.nivel = Math.max(m.nivel, x.nivel); m.motivos.push(motivo); marcas.set(x.id, m);
  };
  for (const x of a.directos) marcar(x, `${x.fenomeno_nombre} (${PA.nombre[x.nivel]})`);
  for (const x of a.activados) marcar(x, `${x.capa_nombre}: peligrosidad ${x.peligrosidad_nombre}, riesgo ${x.riesgo_nombre}`);
  const fuente = mapa.getSource("focal");
  if (fuente) fuente.setData(fc([...marcas].map(([id, m]) => punto(m.lon, m.lat, { id, nombre: m.nombre, nivel: m.nivel, motivos: m.motivos.join(" · ") }))));
  $("#prealerta-activos").innerHTML = `<h3>Activos con riesgo focal (${numero(marcas.size)})</h3>` +
    (marcas.size ? listasActivos(a) : `<p class="nota">Ningún activo con riesgo focal este día.</p>${sensiblesTexto(a.sensibles)}`);
  for (const li of $("#prealerta-activos").querySelectorAll("li[data-lon]")) li.onclick = () => volar(li);
}

// ----------------------------------------------------------------------------- panel: municipio
const resaltarMunicipio = (codigo) => { if (mapa.getLayer("municipios-elegido")) mapa.setFilter("municipios-elegido", ["==", ["get", "codigo"], codigo]); };

async function mostrarMunicipio(codigo) {
  pre.municipio = codigo;
  resaltarMunicipio(codigo);
  const sec = $("#prealerta-municipio"); sec.hidden = false;
  let m;
  try { m = await consultar(`/api/prealerta/municipio?codigo=${encodeURIComponent(codigo)}&dia=${pre.dia}`); }
  catch (e) { sec.innerHTML = `<p class="error">${html(e.message)}</p>`; return; }
  if (m.dia !== pre.dia || pre.municipio !== codigo) return;
  const dia = m.dias[m.dia], p = dia.prevision;
  const semana = m.dias.map((x, i) => `<button type="button" class="dia-mini${i === m.dia ? " activo" : ""}" data-dia="${i}" ` +
    `style="--c:${PA.color[x.nivel_max]}" title="${fechaCorta(x.fecha)}: ${PA.nombre[x.nivel_max]}"><span class="punto"></span>${x.fecha.slice(8, 10)}</button>`).join("");
  const filas = Object.entries(dia.fenomenos).sort((a, b) => b[1].nivel - a[1].nivel).map(([c, f]) =>
    `<tr${f.nivel ? "" : ' class="verde"'}><td>${html(nombreFenomeno(c))}</td><td>${chipPA(f.nivel)}${f.origen === "AEMET" ? " " + origenDe("AEMET") : ""}</td>` +
    `<td class="meta">${html(f.texto)}</td></tr>`).join("");
  const tiempo = [p.tmin != null && p.tmax != null ? `${p.tmin} / ${p.tmax} °C` : "", p.hr_min != null ? `humedad ${p.hr_min}–${p.hr_max} %` : "",
    p.viento_max != null ? `viento ${p.viento_max} km/h${p.racha_max != null ? ` (rachas ${p.racha_max})` : ""}` : "",
    p.prob_precip != null ? `precipitación ${p.prob_precip} %` : "", p.cielo_texto ? html(p.cielo_texto) : ""].filter(Boolean).join(" · ");
  const act = Object.values(dia.activaciones), a = m.activos;
  const nFocal = new Set([...a.directos, ...a.activados].map((x) => x.id)).size;
  sec.innerHTML = `<div class="cabecera-municipio"><h3>${html(m.nombre)}</h3><button type="button" class="enlace" id="cerrar-municipio">cerrar</button></div>
    <p class="meta">Zona de aviso ${html(m.zona_nombre)} (${m.zona})</p>
    <div class="semana">${semana}</div>
    <p class="meta">${fechaCorta(m.fecha)}: ${tiempo}</p>
    <table><tr><th>Fenómeno</th><th>Nivel</th><th>Previsión</th></tr>${filas}</table>
    ${act.length ? `<p>Activa: ${act.map((v) => `${chipPA(v.nivel)} ${html(v.nombre)}`).join(" · ")}</p>` : ""}
    <h4>Activos del municipio con riesgo focal (${numero(nFocal)})</h4>${nFocal ? listasActivos(a) : `<p class="nota">Ninguno este día.</p>${sensiblesTexto(a.sensibles)}`}`;
  $("#cerrar-municipio").onclick = () => { pre.municipio = null; sec.hidden = true; resaltarMunicipio(""); };
  for (const b of sec.querySelectorAll(".dia-mini")) b.onclick = () => elegirDia(+b.dataset.dia);
  for (const li of sec.querySelectorAll("li[data-lon]")) li.onclick = () => volar(li);
}
