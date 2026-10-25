"use strict";
// Talaia: router por hash, Directo y Fuentes. La vista Semana está en semana.js.

const TZ = "Europe/Madrid";
const ZONAS = [["girona", "Girona"], ["cataluna", "Cataluña"], ["espana", "España"], ["europa", "Europa"], ["mundo", "Mundo"]];
const EXTRA = [["miradas", "Miradas"], ["verificadores", "Verificadores"]];
const NOMBRE_ZONA = Object.fromEntries([...ZONAS, ...EXTRA]);
const COMPROBAR_MIN = 3;   // version.json pesa unos bytes; ultimas24h.json solo se pide si cambia
const VIEJO_MIN = 45;      // más de esto sin actualizar = aviso
const NUEVO_MIN = 60;      // marca "nuevo"
const PAGINA = 40;         // entradas por columna antes de "Cargar más"
const MAX_SEGUIDAS = 2;    // modo Diversidad: como mucho estas entradas seguidas del mismo medio
const MAX_DESTACADAS = 5;
const LEIDOS_DIAS = 7, LEIDOS_MAX = 3000;
const PREMIUM_TXT = "Artículo para suscriptores según el propio medio. Puede que puedas leer algunos gratis al mes.";
const CANDADO = '<svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" aria-hidden="true"><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>';

// --- Utilidades compartidas con semana.js ---

const $ = id => document.getElementById(id);
function el(tag, props = {}, ...hijos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "dataset") Object.assign(e.dataset, v);
    else if (k.startsWith("aria-") || ["role", "for", "tabindex", "scope", "lang"].includes(k)) e.setAttribute(k, v);
    else e[k] = v;
  }
  e.append(...hijos.flat(Infinity).filter(h => h != null && h !== false));
  return e;
}
const almacen = {  // localStorage puede estar bloqueado: nunca debe romper la página
  get(k, d) { try { const v = localStorage.getItem("talaia." + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("talaia." + k, JSON.stringify(v)); } catch { } },
  borrar(k) { try { localStorage.removeItem("talaia." + k); } catch { } },
};
const sesion = {
  get(k, d) { try { const v = sessionStorage.getItem("talaia." + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { sessionStorage.setItem("talaia." + k, JSON.stringify(v)); } catch { } },
};
const normalizar = s => (s || "").normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
const urlSegura = u => { try { const x = new URL(u); return ["http:", "https:"].includes(x.protocol) ? x.href : null; } catch { return null; } };
function enlaceExterno(url, texto, props = {}) {
  const href = urlSegura(url);
  if (!href) return el("span", props, texto);
  return el("a", { href, target: "_blank", rel: "noopener noreferrer", ...props }, texto);
}
const fechaCorta = d => d.toLocaleDateString("es-ES", { timeZone: TZ });
function hora(iso) {
  const d = new Date(iso);
  const hm = d.toLocaleTimeString("es-ES", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
  return fechaCorta(d) === fechaCorta(new Date()) ? hm : d.toLocaleDateString("es-ES", { timeZone: TZ, day: "2-digit", month: "2-digit" }) + " " + hm;
}
const fechaHora = iso => iso ? new Date(iso).toLocaleString("es-ES", { timeZone: TZ, dateStyle: "medium", timeStyle: "short" }) : "—";
function hace(iso) {
  const min = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
  return min < 1 ? "ahora" : min < 60 ? `hace ${min} min` : min < 2880 ? `hace ${Math.floor(min / 60)} h` : `hace ${Math.floor(min / 1440)} días`;
}
function anunciar(texto) {  // región aria-live discreta: un resumen, nunca la lista de titulares
  const a = $("anuncio");
  a.textContent = "";
  setTimeout(() => { a.textContent = texto; }, 50);
}
async function pedirJSON(url, opciones) {
  const r = await fetch(url, opciones);
  if (!r.ok) throw new Error(`HTTP ${r.status} en ${url.split("?")[0]}`);
  return r.json();
}

// --- Estado ---

const estado = {
  D: null,            // datos que se muestran (ya preparados)
  pendiente: null,    // datos nuevos que esperan a que la persona vuelva arriba o lo pida
  version: null,
  comprobado: 0,
  error: null,
  zona: null,         // zona de Directo de la ruta actual (null = vista general)
  seccion: null,
  mostrar: {},        // entradas visibles por lista ("Cargar más")
  abiertos: new Set(sesion.get("abiertos", [])),
  filtros: Object.assign({ q: "", medios: [], sinPremium: false, orden: "recientes" }, almacen.get("filtros", {})),
  leidos: almacen.get("leidos", {}),
  plegada: almacen.get("destacadas_plegada", null),
};

const esMovil = () => matchMedia("(max-width: 700px)").matches;

// --- Leídos: historial local limitado, sin sincronizar con nada ---

function purgarLeidos() {
  const limite = Date.now() - LEIDOS_DIAS * 86400000;
  const e = Object.entries(estado.leidos).filter(([, t]) => t > limite).sort((a, b) => b[1] - a[1]).slice(0, LEIDOS_MAX);
  estado.leidos = Object.fromEntries(e);
  almacen.set("leidos", estado.leidos);
}
function marcarLeido(id) {
  estado.leidos[id] = Date.now();
  almacen.set("leidos", estado.leidos);
  document.querySelectorAll(`a.titular[data-id="${CSS.escape(id)}"]`).forEach(a => a.classList.add("leido"));
}

// --- Datos ---

function preparar(d) {
  const fuentes = new Map(d.fuentes.map(f => [f.id, f]));
  const grupos = new Map();
  const ahora = Date.now();
  const noticias = d.noticias
    .filter(n => urlSegura(n.enlace))
    .map(n => {
      const f = fuentes.get(n.fuente) || {};
      const medio = f.nombre || n.fuente || "¿?";
      return { ...n, medio, pais: f.pais, t: Date.parse(n.hora), busca: normalizar(n.titulo + " " + medio) };
    })
    .filter(n => n.t <= ahora + 5 * 60000)   // fechas futuras: fuera de Directo
    .sort((a, b) => b.t - a.t);
  for (const n of noticias) if (n.grupo) (grupos.get(n.grupo) || grupos.set(n.grupo, []).get(n.grupo)).push(n);
  return { ...d, noticias, fuentesMap: fuentes, grupos, comparar: d.comparar || {} };
}

function palabras(q) { return normalizar(q).split(/\s+/).filter(Boolean); }
function pasa(n, f, ps) {
  if (f.sinPremium && n.muro === true) return false;
  if (f.medios.length && !f.medios.includes(n.fuente)) return false;
  for (const w of ps) if (!n.busca.includes(w)) return false;
  return true;
}

// Entradas de una zona: una por grupo, representada por su noticia más reciente que cumpla los filtros
// (si se oculta el premium y hay una alternativa abierta, la alternativa pasa a representar el grupo).
function entradas(D, zona, f = estado.filtros) {
  const ps = palabras(f.q), vistos = new Set(), salida = [];
  let titulares = 0;
  for (const n of D.noticias) {
    if (n.zona !== zona || !pasa(n, f, ps)) continue;
    titulares++;
    const clave = n.grupo || n.id;
    if (vistos.has(clave)) continue;
    vistos.add(clave);
    const otras = n.grupo ? D.grupos.get(n.grupo).filter(o => o !== n && o.zona !== "verificadores" && !(f.sinPremium && o.muro === true)) : [];
    salida.push({ clave, n, otras, medios: new Set([n.fuente, ...otras.map(o => o.fuente)]).size });
  }
  return { lista: ordenar(salida, f.orden), titulares };
}

function ordenar(lista, orden) {
  if (orden === "contrastadas") return [...lista].sort((a, b) => b.medios - a.medios || b.n.t - a.n.t);
  if (orden === "diversidad") return diversificar(lista, MAX_SEGUIDAS);
  return lista;
}

// Como mucho `k` entradas seguidas del mismo medio; dentro de cada medio se conserva el orden cronológico.
function diversificar(lista, k) {
  const pendientes = [...lista], salida = [];
  while (pendientes.length) {
    const ult = salida.slice(-k);
    const bloqueado = ult.length === k && ult.every(e => e.n.fuente === ult[0].n.fuente) ? ult[0].n.fuente : null;
    let i = bloqueado ? pendientes.findIndex(e => e.n.fuente !== bloqueado) : 0;
    if (i < 0) i = 0;
    salida.push(pendientes.splice(i, 1)[0]);
  }
  return salida;
}

function destacadas(D, f = estado.filtros) {
  const todas = new Map();
  for (const [z] of ZONAS) for (const e of entradas(D, z, f).lista) {
    if (e.medios < 2) continue;
    const previa = todas.get(e.clave);
    if (!previa || e.n.t > previa.n.t) todas.set(e.clave, e);
  }
  return [...todas.values()].sort((a, b) => b.medios - a.medios || b.n.t - a.n.t).slice(0, MAX_DESTACADAS);
}

// --- Pintar Directo ---

function meta(n, ahora, conPais) {
  const m = el("div", { className: "meta" },
    el("time", { dateTime: n.hora }, hora(n.hora)),
    ahora - n.t < NUEVO_MIN * 60000 ? el("span", { className: "nuevo" }, "nuevo") : null,
    el("span", { className: "medio" }, n.medio),
    conPais && n.pais ? el("span", { className: "pais", title: "País de la redacción del medio" }, n.pais) : null);
  if (n.muro === true) {
    const p = el("span", { className: "premium", title: PREMIUM_TXT });
    p.innerHTML = CANDADO;
    p.append("premium");
    m.append(p);
  }
  return m;
}

function titular(n) {
  const a = enlaceExterno(n.enlace, n.titulo, { className: "titular" + (estado.leidos[n.id] ? " leido" : ""), dataset: { id: n.id } });
  return a;
}

function entradaLi(e, D, ahora, conPais) {
  const { n, otras } = e;
  const li = el("li", { className: "noticia", dataset: { clave: e.clave } }, meta(n, ahora, conPais), titular(n));
  li.style.setProperty("--zona", `var(--${n.zona})`);
  if (n.muro === true) {  // F6: alternativas abiertas, una por medio
    const libres = [...new Map(otras.filter(o => o.muro !== true && o.fuente !== n.fuente).map(o => [o.fuente, o])).values()];
    if (libres.length) {
      const p = el("div", { className: "tambien" }, "Léelo también en: ");
      libres.forEach((o, i) => p.append(i ? " · " : "", enlaceExterno(o.enlace, o.medio)));
      li.append(p);
    }
  }
  const acciones = el("div", { className: "acciones" });
  if (otras.length) {
    const texto = e.medios > 1 ? `${e.medios} medios` : `${otras.length + 1} noticias del mismo medio`;
    const d = el("details", { className: "grupo", open: estado.abiertos.has(e.clave), dataset: { clave: e.clave } },
      el("summary", { "aria-label": `${texto}: ver otras coberturas de este hecho` }, texto),
      el("ul", {}, otras.map(o => el("li", {}, meta(o, ahora, true), titular(o)))));
    d.addEventListener("toggle", () => {
      d.open ? estado.abiertos.add(e.clave) : estado.abiertos.delete(e.clave);
      sesion.set("abiertos", [...estado.abiertos].slice(-200));
    });
    acciones.append(d);
  }
  const ruta = [n, ...otras].map(o => D.comparar[o.id]).find(Boolean);
  if (ruta) acciones.prepend(el("a", { className: "comparar", href: `#/semana/${ruta}` }, "Comparar enfoques"));
  if (acciones.childElementCount) li.append(acciones);
  return li;
}

function listaEntradas(id, lista, D, ahora, conPais) {
  const ol = el("ol", { dataset: { lista: id } });
  const n = estado.mostrar[id] || PAGINA;
  for (const e of lista.slice(0, n)) ol.append(entradaLi(e, D, ahora, conPais));
  if (!lista.length) ol.append(el("li", { className: "vacio" }, hayFiltros() ? "Nada coincide con los filtros." : `Sin titulares en las últimas ${D.ventana_horas || 24} h.`));
  return ol;
}

function columna(zona, nombre, D, ahora, opciones = {}) {
  const { lista, titulares } = entradas(D, zona);
  const id = `col-${zona}`;
  const ol = listaEntradas(zona, lista, D, ahora, opciones.conPais);
  const cuenta = `${lista.length} ${hayFiltros() ? "con filtros" : ""}`.trim();
  const col = el("section", { className: "col", id, "aria-labelledby": `${id}-t`, dataset: { zona } },
    el("h3", { id: `${id}-t`, tabindex: -1 }, nombre,
      el("span", { className: "cuenta", title: `${lista.length} entradas (${titulares} titulares)${hayFiltros() ? " con los filtros actuales" : ""}` }, cuenta)),
    opciones.nota ? el("p", { className: "nota-vista" }, opciones.nota) : null,
    ol);
  col.style.setProperty("--zona", `var(--${zona})`);
  const visibles = estado.mostrar[zona] || PAGINA;
  if (lista.length > visibles) {
    col.append(el("button", {
      type: "button", className: "mas", dataset: { foco: `mas-${zona}` },
      onclick: () => { estado.mostrar[zona] = visibles + PAGINA; pintarDirecto(); }
    }, `Cargar más (${lista.length - visibles} restantes)`));
  }
  return { col, lista, titulares };
}

const hayFiltros = (f = estado.filtros) => !!(f.q.trim() || f.medios.length || f.sinPremium);

function pintarZonas(conteos) {
  const ul = $("zonas");
  const item = ([z, nombre], extra) => {
    const general = !esMovil() && !estado.zona && !extra;
    const actual = estado.zona === z || (esMovil() && !estado.zona && z === zonaMovil());
    const a = el("a", { href: `#/directo/${z}`, className: extra ? "extra" : "", "aria-label": `${nombre}: ${conteos[z] ?? 0} entradas${hayFiltros() ? " con filtros" : ""}` },
      nombre, el("span", { className: "n", "aria-hidden": "true" }, String(conteos[z] ?? "")));
    a.style.setProperty("--zona", `var(--${z})`);
    if (actual) a.setAttribute("aria-current", "page");
    else if (general) a.title = "Ir a la columna";
    return el("li", {}, a);
  };
  const general = el("a", { href: "#/directo", title: "Las cinco zonas en columnas" }, "General");
  if (!estado.zona) general.setAttribute("aria-current", "page");
  ul.replaceChildren(
    ...(esMovil() ? [] : [el("li", {}, general)]),
    ...ZONAS.map(z => item(z, false)),
    el("li", { className: "separador", "aria-hidden": "true" }),
    ...EXTRA.map(z => item(z, true)));
}

const zonaMovil = () => almacen.get("zona_movil", "girona");

function pintarFiltrosResumen(conteos, titulares) {
  const f = estado.filtros;
  const activos = [f.q.trim() && "búsqueda", f.medios.length && `${f.medios.length} medios`, f.sinPremium && "sin premium"].filter(Boolean);
  const zona = estado.zona || (esMovil() ? zonaMovil() : null);
  const ambito = zona ? NOMBRE_ZONA[zona] : "las cinco zonas";
  const total = zona ? conteos[zona] : ZONAS.reduce((s, [z]) => s + conteos[z], 0);
  const tit = zona ? titulares[zona] : ZONAS.reduce((s, [z]) => s + titulares[z], 0);
  $("resumen-filtros").replaceChildren(
    activos.length ? el("span", { className: "activos" }, `Filtros: ${activos.join(", ")} · `) : "",
    `${total} entradas (${tit} titulares) en ${ambito}`);
  $("limpiar").hidden = !activos.length;
  $("n-medios").textContent = f.medios.length ? `(${f.medios.length})` : "";
}

function pintarDirecto() {
  const D = estado.D;
  if (!D) return;
  const ahora = Date.now();
  const anclas = capturarPosicion();
  const conteos = {}, titulares = {};
  const columnas = $("columnas");
  const zona = estado.zona;
  const una = zona === "miradas" || zona === "verificadores";
  const zonaVisible = zona || (esMovil() ? zonaMovil() : null);
  const cols = [];
  for (const [z, nombre] of [...ZONAS, ...EXTRA]) {
    const extra = z === "miradas" || z === "verificadores";
    const pintar = una ? z === zona : !extra && (!esMovil() || z === zonaVisible);  // en móvil solo la zona visible
    if (!pintar) { const r = entradas(D, z); conteos[z] = r.lista.length; titulares[z] = r.titulares; continue; }
    const nota = z === "miradas" ? "Medios de otros países para comparar enfoques. No forman parte de la columna Mundo. El país indica la sede del medio, no su orientación."
      : z === "verificadores" ? "Titulares de los verificadores tal como los publican. No se vinculan automáticamente con otras noticias ni se usan para calificar ninguna."
      : null;
    const { col, lista, titulares: t } = columna(z, nombre, D, ahora, { conPais: extra, nota });
    conteos[z] = lista.length; titulares[z] = t;
    col.classList.toggle("activa", z === zonaVisible || una);
    col.classList.toggle("resaltada", !esMovil() && z === zona);
    cols.push(col);
  }
  columnas.classList.toggle("una", una);
  columnas.replaceChildren(...cols);
  pintarZonas(conteos);
  pintarFiltrosResumen(conteos, titulares);

  const dest = destacadas(D);
  $("destacadas").hidden = una || !dest.length;
  $("lista-destacadas").replaceChildren(...dest.map(e => entradaLi(e, D, ahora, false)));
  const plegada = estado.plegada ?? esMovil();
  $("lista-destacadas").hidden = plegada;
  $("plegar-destacadas").setAttribute("aria-expanded", String(!plegada));
  $("plegar-destacadas").textContent = plegada ? `Mostrar (${dest.length})` : "Plegar";

  restaurarPosicion(anclas);
}

// --- Posición: ancla estable (entrada visible + desplazamiento) en el contenedor que de verdad se desplaza ---

function contenedorScroll(e) {
  for (let p = e; p && p !== document.body; p = p.parentElement) {
    const o = getComputedStyle(p).overflowY;
    if ((o === "auto" || o === "scroll") && p.scrollHeight > p.clientHeight) return p;
  }
  return document.scrollingElement;
}
function capturarPosicion() {
  const listas = [...document.querySelectorAll("#vista-directo [data-lista]")].filter(l => l.offsetParent);
  const pos = listas.map(lista => {
    const sc = contenedorScroll(lista);
    const arriba = sc === document.scrollingElement ? 0 : sc.getBoundingClientRect().top;
    let ancla = null;
    for (const li of lista.querySelectorAll(":scope > li[data-clave]")) {
      const r = li.getBoundingClientRect();
      if (r.bottom > arriba + 1) { ancla = { clave: li.dataset.clave, off: r.top - arriba }; break; }
    }
    return { id: lista.dataset.lista, global: sc === document.scrollingElement, top: sc.scrollTop, ancla };
  });
  const a = document.activeElement;
  const li = a?.closest?.("li[data-clave]");
  let foco = null;
  if (li && a.closest("[data-lista]")) {
    foco = { lista: a.closest("[data-lista]").dataset.lista, clave: li.dataset.clave,
      sel: a.matches("summary") ? "summary" : a.matches("a.comparar") ? "a.comparar" : a.dataset.id ? `a.titular[data-id="${CSS.escape(a.dataset.id)}"]` : null };
  } else if (a?.dataset?.foco) foco = { dataFoco: a.dataset.foco };
  return { pos, foco };
}
function restaurarPosicion({ pos, foco }) {
  for (const p of pos) {
    const lista = document.querySelector(`#vista-directo [data-lista="${CSS.escape(p.id)}"]`);
    if (!lista || !lista.offsetParent) continue;
    const sc = contenedorScroll(lista);
    if (p.global !== (sc === document.scrollingElement)) continue;
    const arriba = sc === document.scrollingElement ? 0 : sc.getBoundingClientRect().top;
    const li = p.ancla && lista.querySelector(`:scope > li[data-clave="${CSS.escape(p.ancla.clave)}"]`);
    if (li) sc.scrollTop += li.getBoundingClientRect().top - arriba - p.ancla.off;
    else sc.scrollTop = p.top;
  }
  if (foco) {  // devolver el foco al mismo elemento lógico (el nodo es nuevo), sin desplazar
    let e = null;
    if (foco.dataFoco) e = document.querySelector(`[data-foco="${CSS.escape(foco.dataFoco)}"]`);
    else {
      const li = document.querySelector(`[data-lista="${CSS.escape(foco.lista)}"] li[data-clave="${CSS.escape(foco.clave)}"]`);
      e = li && (foco.sel && li.querySelector(foco.sel) || li.querySelector("a"));
    }
    e?.focus({ preventScroll: true });
  }
}
function leyendoAbajo() {
  if (estado.seccion !== "directo") return false;
  return [...document.querySelectorAll("#vista-directo [data-lista]")].filter(l => l.offsetParent)
    .some(l => contenedorScroll(l).scrollTop > 60);
}

// --- Carga y refresco no disruptivo ---

async function comprobar(manual = false) {
  estado.comprobado = Date.now();
  const boton = $("refrescar");
  boton.classList.add("girando");
  try {
    // version.json sin caché (unos bytes); ultimas24h.json con su versión en la URL, así la caché sí sirve
    const v = await pedirJSON("version.json?t=" + Date.now(), { cache: "no-store" });
    estado.versionSemana = v.semana;
    if (v.version !== estado.version) {
      const d = await pedirJSON(`ultimas24h.json?v=${encodeURIComponent(v.version)}`);
      estado.version = v.version;
      recibir(preparar(d), manual);
    } else if (manual && estado.pendiente) aplicarPendiente();
    estado.error = null;
  } catch (e) {
    estado.error = e.message;
  } finally {
    boton.classList.remove("girando");
    pintarAvisos();
    reloj();
  }
}

function recibir(D, manual) {
  if (!estado.D || manual || !leyendoAbajo()) {
    const nuevas = estado.D ? contarNuevas(estado.D, D) : 0;
    aplicar(D);
    if (nuevas && estado.D) anunciar(`${nuevas} ${nuevas === 1 ? "noticia nueva" : "noticias nuevas"}`);
  } else {
    estado.pendiente = D;
    const n = contarNuevas(estado.D, D);
    const b = $("nuevas");
    b.hidden = !n;
    b.textContent = `${n} ${n === 1 ? "noticia nueva" : "noticias nuevas"} · ver`;
    if (n) anunciar(`Hay ${n} ${n === 1 ? "noticia nueva" : "noticias nuevas"}. Se mostrarán al volver arriba.`);
    pintarCabeceraDatos(D);
  }
}
function contarNuevas(viejo, nuevo) {
  const ids = new Set(viejo.noticias.map(n => n.id));
  const f = estado.filtros, ps = palabras(f.q);
  return nuevo.noticias.filter(n => !ids.has(n.id) && pasa(n, f, ps) && n.zona !== "verificadores").length;
}
function aplicar(D) {
  const antes = estado.D && new Set(estado.D.noticias.map(n => n.id));
  estado.D = D;
  estado.pendiente = null;
  $("nuevas").hidden = true;
  pintarCabeceraDatos(D);
  if (estado.seccion === "directo") pintarDirecto();
  if (antes) for (const li of document.querySelectorAll("#columnas li[data-clave]")) {
    const a = li.querySelector("a.titular");
    if (a && !antes.has(a.dataset.id)) li.classList.add("llega");
  }
  if (estado.seccion === "fuentes") Fuentes.pintar();
}
function aplicarPendiente(arriba = false) {
  if (!estado.pendiente) return;
  aplicar(estado.pendiente);
  if (arriba) for (const l of document.querySelectorAll("#vista-directo [data-lista]")) contenedorScroll(l).scrollTop = 0;
}
function pintarCabeceraDatos(D) {
  estado.actualizado = new Date(D.actualizado);
  $("total").textContent = D.noticias.filter(n => NOMBRE_ZONA[n.zona] && n.zona !== "verificadores").length;
  reloj();
  pintarAvisos(D);
}

function pintarAvisos(D = estado.pendiente || estado.D) {
  const avisos = [];
  if (estado.error) avisos.push(el("p", { className: "error", role: "alert" },
    `⚠ No se pudieron actualizar los datos (${estado.error}). ` + (D ? `Se muestra la copia de ${fechaHora(D.actualizado)} (${hace(D.actualizado)}).` : "Se reintentará.")));
  if (D?.fuentes_caidas?.length) avisos.push(el("p", {}, "⚠ Sin respuesta en la última recogida: " + D.fuentes_caidas.map(c => c.medio).join(" · ") + ". ",
    el("a", { href: "#/fuentes" }, "Ver estado de las fuentes")));
  $("avisos").replaceChildren(...avisos);
}

function reloj() {
  $("reloj").textContent = new Date().toLocaleTimeString("es-ES", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
  if (!estado.actualizado) return;
  const min = Math.max(0, Math.round((Date.now() - estado.actualizado) / 60000));
  $("hace").textContent = min < 1 ? "ahora" : min < 60 ? `hace ${min} min` : `hace ${Math.floor(min / 60)} h`;
  $("hace").title = `Datos generados el ${fechaHora(estado.actualizado.toISOString())}`;
  const viejo = min > VIEJO_MIN;
  $("directo").classList.toggle("viejo", viejo);
  $("directo").textContent = viejo ? "DATOS ANTIGUOS" : "EN DIRECTO";
}

// --- Filtros ---

function guardarFiltros() { almacen.set("filtros", estado.filtros); estado.mostrar = {}; pintarDirecto(); }
function pintarListaMedios() {
  const D = estado.D;
  if (!D) return;
  const zonaDe = new Map(D.fuentes.map(f => [f.id, f.zona]));
  const orden = [...ZONAS, ...EXTRA].map(z => z[0]);
  const fuentes = D.fuentes.filter(f => NOMBRE_ZONA[f.zona]).sort((a, b) => orden.indexOf(zonaDe.get(a.id)) - orden.indexOf(zonaDe.get(b.id)) || a.nombre.localeCompare(b.nombre, "es"));
  $("lista-medios").replaceChildren(...fuentes.map(f => {
    const c = el("input", { type: "checkbox", value: f.id, checked: estado.filtros.medios.includes(f.id) });
    c.addEventListener("change", () => {
      const m = new Set(estado.filtros.medios);
      c.checked ? m.add(f.id) : m.delete(f.id);
      estado.filtros.medios = [...m];
      guardarFiltros();
    });
    return el("label", {}, c, f.nombre, el("small", {}, NOMBRE_ZONA[f.zona]));
  }));
}
function iniciarFiltros() {
  const f = estado.filtros;
  $("q").value = f.q; $("sin-premium").checked = f.sinPremium; $("orden").value = f.orden;
  let t;
  $("q").addEventListener("input", () => { clearTimeout(t); t = setTimeout(() => { f.q = $("q").value; guardarFiltros(); }, 150); });
  $("sin-premium").addEventListener("change", () => { f.sinPremium = $("sin-premium").checked; guardarFiltros(); });
  $("orden").addEventListener("change", () => { f.orden = $("orden").value; guardarFiltros(); });
  $("limpiar").addEventListener("click", () => {
    Object.assign(f, { q: "", medios: [], sinPremium: false });
    $("q").value = ""; $("sin-premium").checked = false;
    pintarListaMedios();
    guardarFiltros();
    anunciar("Filtros borrados");
    $("q").focus();
  });
  $("plegar-destacadas").addEventListener("click", () => {
    estado.plegada = !($("lista-destacadas").hidden);
    almacen.set("destacadas_plegada", estado.plegada);
    pintarDirecto();
  });
}

// --- Fuentes ---

const Fuentes = {
  datos: null,
  async cargar() {
    try { this.datos = await pedirJSON("fuentes.json?v=" + (estado.version || Date.now())); this.error = null; }
    catch (e) { this.error = e.message; }
    this.pintar();
  },
  pintar() {
    const v = $("vista-fuentes");
    const cab = [el("h2", { id: "titulo-fuentes", tabindex: -1 }, "Fuentes")];
    if (this.error) { v.replaceChildren(el("div", { className: "pagina" }, cab, el("p", { className: "vacio", role: "alert" }, `No se pudo cargar el estado de las fuentes (${this.error}).`))); return; }
    if (!this.datos) { v.replaceChildren(el("div", { className: "pagina" }, cab, el("p", { className: "vacio" }, "Cargando…"))); return; }
    const filas = this.datos.fuentes.map(f => {
      const e = f.estado || {};
      const ok = e.exito && (!e.error || e.exito > e.error_hora);
      const antiguo = ok && e.entrada_mas_reciente && Date.now() - Date.parse(e.entrada_mas_reciente) > 7 * 86400000;
      return el("tr", {},
        el("th", { scope: "row" }, f.nombre, f.sustituye ? el("div", { className: "cifras-suceso" }, `Sustituye a ${f.sustituye}`) : null),
        el("td", {}, NOMBRE_ZONA[f.zona] || f.zona),
        el("td", {}, f.pais || "—"), el("td", {}, f.idioma || "—"),
        el("td", { className: "celda " + (antiguo ? "parcial" : ok ? "encontrada" : "no_evaluable") },
          antiguo ? `⚠ responde, pero sin entradas recientes (última: ${fechaHora(e.entrada_mas_reciente)})` : ok ? "✔ responde" : "✘ " + (e.error || "sin datos")),
        el("td", {}, fechaHora(e.comprobado)), el("td", {}, fechaHora(e.exito)),
        el("td", {}, e.entradas != null ? `${e.entradas} entradas · ${fechaHora(e.entrada_mas_antigua)} → ${fechaHora(e.entrada_mas_reciente)}` : "—"),
        el("td", {}, f.muro === "no" ? "no se comprueba" : `por artículo (${f.muro})`),
        el("td", {}, f.nota || ""));
    });
    const tabla = el("div", { className: "tabla-scroll", tabindex: 0, role: "region", "aria-label": "Estado de las fuentes (desplazable)" },
      el("table", {}, el("caption", { className: "solo-lector" }, "Estado de cada fuente"),
        el("thead", {}, el("tr", {}, ...["Medio", "Zona", "País", "Idioma", "Estado", "Comprobado", "Último éxito", "Ventana del RSS", "Premium", "Notas"].map(t => el("th", { scope: "col" }, t)))),
        el("tbody", {}, filas)));
    const excl = this.datos.excluidas || [];
    v.replaceChildren(el("div", { className: "pagina" }, cab,
      el("p", {}, `Estado al ${fechaHora(this.datos.actualizado)}. El país es el de la sede del medio, no su orientación. «Ventana del RSS» es lo que el feed ofrece en cada lectura; la captura cada 15 minutos acumula la semana.`),
      tabla,
      el("h3", {}, "Titulares excluidos"),
      el("p", {}, "Boletines y títulos de sección sin contenido que se quitan con reglas por fuente (fuentes.yaml). Últimos ejemplos para revisarlas:"),
      excl.length ? el("ul", {}, excl.slice(0, 40).map(x => el("li", {}, el("b", {}, x.fuente), ` · ${x.titulo} `, el("code", {}, x.regla)))) : el("p", { className: "vacio" }, "Ninguno."),
      el("h3", {}, "Límites conocidos"),
      el("ul", {},
        el("li", {}, "Premium: solo se marca cuando el propio artículo lo declara (comprobado uno a uno). Muchos medios tienen muro medido."),
        el("li", {}, "«Sin respuesta» significa que el RSS falló en la última lectura, no que el medio no haya publicado."),
        el("li", {}, "Los grupos de Directo se recalculan sobre las últimas 48 h; la semana se reagrupa desde cero.")),
      el("h3", {}, "Datos guardados en este navegador"),
      el("p", {}, `Historial de lectura local: ${Object.keys(estado.leidos).length} enlaces (se borran solos a los ${LEIDOS_DIAS} días). No se envía a ningún sitio.`),
      el("button", { type: "button", className: "boton", onclick: () => {
        estado.leidos = {}; almacen.borrar("leidos");
        document.querySelectorAll("a.titular.leido").forEach(a => a.classList.remove("leido"));
        anunciar("Historial de lectura borrado"); this.pintar();
      } }, "Borrar historial de lectura")));
  },
};

// --- Router ---

function leerRuta() {
  const h = location.hash.startsWith("#/") ? location.hash.slice(2) : "";
  const [camino, query = ""] = h.split("?");
  const partes = camino.split("/").filter(Boolean).map(decodeURIComponent);
  return { seccion: partes[0] || "", partes: partes.slice(1), params: new URLSearchParams(query) };
}

function irA(ruta, explicita) {
  const r = leerRuta();
  if (!["directo", "semana", "fuentes"].includes(r.seccion)) {
    const g = almacen.get("ruta", "#/directo");
    location.replace(typeof g === "string" && g.startsWith("#/") ? g : "#/directo");
    return;
  }
  const cambiaSeccion = estado.seccion !== r.seccion;
  if (estado.seccion === "semana" && window.Semana) Semana.guardarPosicion();
  estado.seccion = r.seccion;
  for (const s of ["directo", "semana", "fuentes"]) $("vista-" + s).hidden = s !== r.seccion;
  document.querySelectorAll(".secciones a").forEach(a => a.dataset.seccion === r.seccion ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
  almacen.set("ruta", location.hash);
  let foco = null, titulo = "Talaia";
  if (r.seccion === "directo") {
    const z = NOMBRE_ZONA[r.partes[0]] ? r.partes[0] : null;
    estado.zona = z;
    if (z && ZONAS.some(x => x[0] === z)) almacen.set("zona_movil", z);
    titulo = `Talaia · ${z ? NOMBRE_ZONA[z] : "Directo"}`;
    pintarListaMedios();
    pintarDirecto();
    if (estado.pendiente && !leyendoAbajo()) aplicarPendiente();
    foco = z ? document.querySelector(`#col-${z} h3`) : $("titulo-directo");
    if (explicita && z && !esMovil()) $(`col-${z}`)?.scrollIntoView({ block: "nearest", inline: "nearest" });
    if (explicita && esMovil()) document.scrollingElement.scrollTop = 0;
  } else if (r.seccion === "fuentes") {
    titulo = "Talaia · Fuentes";
    if (cambiaSeccion || !Fuentes.datos) Fuentes.cargar(); else Fuentes.pintar();
    foco = () => $("titulo-fuentes");
  } else {
    titulo = "Talaia · Semana";
    foco = () => $("titulo-semana");
    window.Semana?.mostrar(r, explicita);
  }
  document.title = titulo;
  if (explicita) {  // cambio de ruta pedido: se anuncia y se lleva el foco al título del contenido
    setTimeout(() => { const e = typeof foco === "function" ? foco() : foco; e?.focus({ preventScroll: true }); }, 0);
    anunciar(titulo.replace("Talaia · ", ""));
  }
}

function iniciar() {
  purgarLeidos();
  iniciarFiltros();
  $("saltar").addEventListener("click", e => { e.preventDefault(); $("contenido").focus(); });
  $("refrescar").addEventListener("click", () => comprobar(true));
  $("nuevas").addEventListener("click", () => { aplicarPendiente(true); anunciar("Noticias nuevas mostradas"); });
  document.addEventListener("click", e => {
    const a = e.target.closest?.("a.titular[data-id]");
    if (a) marcarLeido(a.dataset.id);
  });
  // Al volver arriba se incorporan las noticias pendientes
  document.addEventListener("scroll", () => { if (estado.pendiente && !leyendoAbajo()) aplicarPendiente(); }, { capture: true, passive: true });
  addEventListener("hashchange", () => irA(location.hash, true));
  let ancho = esMovil();
  addEventListener("resize", () => { if (esMovil() !== ancho) { ancho = esMovil(); if (estado.seccion === "directo") pintarDirecto(); } });
  addEventListener("pagehide", () => window.Semana?.guardarPosicion());
  irA(location.hash, false);
  comprobar().then(() => { if (estado.seccion === "directo") pintarListaMedios(); });
  setInterval(() => comprobar(), COMPROBAR_MIN * 60000);
  setInterval(reloj, 15000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden && Date.now() - estado.comprobado > 60000) comprobar(); });
}

document.addEventListener("DOMContentLoaded", iniciar);
