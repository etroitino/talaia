"use strict";
// Vista Semana: portada del informe, matriz sucesos × medios y detalle de cada suceso.
// Usa las utilidades de app.js (el, $, almacen, sesion, enlaceExterno, fechaHora, anunciar, pedirJSON...).

const ESTADO_INFORME = {
  provisional: "Provisional: la semana no ha terminado",
  cerrado: "Cerrado",
  parcial: "Cerrado con cobertura parcial",
  no_disponible: "No disponible",
};
const ESTADO_ANALISIS = {
  completo: "Análisis con IA completo",
  parcial: "Análisis con IA parcial",
  sin_ia: "Sin análisis de IA: solo cobertura y titulares",
};
const CELDA = {
  encontrada: ["●", "Cobertura encontrada"],
  parcial: ["◐", "Localizada; texto parcial o no disponible"],
  sin_coincidencias: ["○", "Sin coincidencias en la muestra"],
  no_evaluable: ["×", "Fuente no evaluable (error o sin cobertura del periodo)"],
};
const ACCESO = { completo: "Texto completo", parcial: "Texto parcial", solo_titular: "Solo titular", inaccesible: "Inaccesible" };
const GENERO = { noticia: "Noticia", analisis: "Análisis", opinion: "Opinión", entrevista: "Entrevista", no_verificado: "Género no verificado" };
const HABLANTE = { periodista: "Periodista (texto del medio)", entrevistado: "Persona entrevistada", comunicado: "Comunicado", fuente_citada: "Fuente citada", desconocido: "Autor de la cita no identificado" };

const Semana = {
  indice: null, versionIndice: null, informes: new Map(), rutaActual: null, error: null,

  claveRuta(h = location.hash) { return "pos:" + h.split("?")[0]; },
  guardarPosicion() {
    if (!this.rutaActual) return;
    const sc = contenedorScroll($("vista-semana"));
    sesion.set(this.claveRuta(this.rutaActual), sc.scrollTop);
  },
  restaurarPosicion() {
    const top = sesion.get(this.claveRuta(), 0);
    requestAnimationFrame(() => { contenedorScroll($("vista-semana")).scrollTop = top; });
  },

  async cargarIndice() {
    if (this.indice && this.versionIndice === estado.versionSemana) return this.indice;
    this.indice = await pedirJSON("semana/index.json?v=" + (estado.versionSemana || Date.now()));
    this.versionIndice = estado.versionSemana;
    return this.indice;
  },
  async cargarInforme(id) {
    const entrada = this.indice.informes.find(i => i.week_id === id);
    const clave = id + ":" + (entrada?.input_hash || entrada?.generated_at || "");
    if (!this.informes.has(clave)) this.informes.set(clave, await pedirJSON(`semana/${encodeURIComponent(id)}.json?v=${encodeURIComponent(entrada?.generated_at || "")}`));
    return this.informes.get(clave);
  },

  async mostrar(r, explicita) {
    if (this.rutaActual && this.rutaActual !== location.hash) this.guardarPosicion();
    const v = $("vista-semana");
    const ruta = location.hash;
    this.rutaActual = ruta;
    if (!v.childElementCount) v.replaceChildren(pagina([el("h2", { id: "titulo-semana", tabindex: -1 }, "Semana"), el("p", { className: "vacio" }, "Cargando…")]));
    try {
      const idx = await this.cargarIndice();
      if (!idx.informes.length) return this.pintarVacio();
      const semana = r.partes[0];
      if (!semana) { location.replace(`#/semana/${idx.informes[0].week_id}`); return; }
      if (!idx.informes.some(i => i.week_id === semana)) return this.pintarVacio(`No hay informe de ${semana}.`);
      const inf = await this.cargarInforme(semana);
      if (location.hash !== ruta) return;  // la persona ya navegó a otro sitio
      if (r.partes[1]) {
        const ev = inf.events.find(e => e.id === r.partes[1]);
        if (!ev) return this.pintarVacio(`El suceso ${r.partes[1]} no está en el informe ${semana}.`);
        this.pintarSuceso(inf, ev, r.params);
      } else this.pintarPortada(inf, idx);
      this.restaurarPosicion();
      if (explicita) $("titulo-semana")?.focus({ preventScroll: true });
    } catch (e) {
      v.replaceChildren(pagina([el("h2", { id: "titulo-semana", tabindex: -1 }, "Semana"),
        el("p", { className: "vacio", role: "alert" }, `No se pudo cargar el informe semanal (${e.message}). Directo sigue funcionando.`)]));
    }
  },

  pintarVacio(motivo) {
    $("vista-semana").replaceChildren(pagina([
      el("h2", { id: "titulo-semana", tabindex: -1 }, "Semana"),
      el("p", { className: "etiqueta no_disponible" }, "No disponible"),
      el("p", {}, motivo || "Todavía no hay informes semanales."),
      el("p", {}, "El informe provisional se genera los domingos a partir de las 09:00 (hora de Madrid) y la semana se cierra el lunes a partir de las 00:30, con datos hasta el lunes a las 00:00."),
      this.indice?.informes?.length ? el("p", {}, el("a", { href: `#/semana/${this.indice.informes[0].week_id}` }, "Ir al último informe")) : null,
    ]));
  },

  pintarPortada(inf, idx) {
    const fuentes = new Map(inf.sources.map(s => [s.id, s]));
    const entrada = idx.informes.find(i => i.week_id === inf.week_id);
    const ids = new Set(inf.events.flatMap(e => e.source_ids));
    const paises = new Set([...ids].map(id => fuentes.get(id)?.country).filter(Boolean));
    const [anio, sem] = inf.week_id.split("-W");
    const selector = el("select", { id: "elegir-semana", onchange: e => { location.hash = `#/semana/${e.target.value}`; } },
      idx.informes.map(i => el("option", { value: i.week_id, selected: i.week_id === inf.week_id }, `${i.week_id} · ${i.status.replace("_", " ")}`)));
    const avisos = [
      ...(inf.synthetic ? ["DEMOSTRACIÓN SINTÉTICA: datos inventados para probar la página; no son noticias reales."] : []),
      ...(entrada?.ultimo_error ? [`La última generación falló el ${fechaHora(entrada.ultimo_error.at)} (${entrada.ultimo_error.message}). Se muestra el último informe válido.`] : []),
      ...(inf.status === "provisional" ? [`Informe provisional: datos hasta ${fechaHora(inf.cutoff_at)}. La semana aún no ha terminado.`] : []),
      ...(inf.analysis_status !== "completo" ? [ESTADO_ANALISIS[inf.analysis_status] + (inf.analysis_note ? `: ${inf.analysis_note}` : ".")] : []),
      ...(inf.selection?.reason_fewer ? [inf.selection.reason_fewer] : []),
      ...inf.coverage_warnings.map(w => w.message),
    ];
    $("vista-semana").replaceChildren(pagina([
      el("h2", { id: "titulo-semana", tabindex: -1 }, `Semana ${Number(sem)} de ${anio}`),
      el("div", { className: "selector-semana" },
        el("label", { for: "elegir-semana" }, "Semana"), selector,
        el("a", { className: "boton", href: `semana/${inf.week_id}.md`, download: `talaia-${inf.week_id}.md` }, `Descargar informe ${inf.week_id} (Markdown)`)),
      el("p", {}, el("span", { className: `etiqueta ${inf.status}` }, ESTADO_INFORME[inf.status] || inf.status), " ",
        inf.synthetic ? el("span", { className: "etiqueta sintetico" }, "Sintético") : null),
      avisos.length ? el("div", { className: "tarjeta advertencias", role: "note" }, el("h3", {}, "Advertencias de cobertura"), el("ul", {}, avisos.map(a => el("li", {}, a)))) : null,
      el("dl", { className: "datos-informe" },
        par("Intervalo", `${fechaLarga(inf.period_start)} – ${fechaLarga(inf.period_end_exclusive)} (exclusivo), hora de Madrid (${inf.timezone})`),
        par("Corte de datos", fechaHora(inf.cutoff_at)),
        par("Generado", fechaHora(inf.generated_at)),
        par("Cobertura observada", inf.observed_coverage ? `${fechaHora(inf.observed_coverage.first_capture)} → ${fechaHora(inf.observed_coverage.last_capture)} · ${inf.observed_coverage.capture_hours} de ${inf.observed_coverage.expected_hours} h con recogida` : "—"),
        par("Sucesos", String(inf.events.length)),
        par("Medios en los sucesos", String(ids.size)),
        par("Países en los sucesos", String(paises.size)),
        par("Modelo", inf.model_id ? `${inf.model_id} · prompt ${inf.prompt_version} · esquema ${inf.schema_version}` : `sin IA · esquema ${inf.schema_version}`)),
      el("h3", {}, "Matriz de sucesos y medios"),
      matriz(inf, fuentes),
      el("h3", {}, "Sucesos"),
      inf.events.length ? el("ol", { className: "sucesos" }, inf.events.map(ev => tarjetaSuceso(inf, ev, fuentes))) : el("p", { className: "vacio" }, "No hay sucesos comparables en esta semana."),
      el("h3", {}, "Silencios de la semana"),
      el("p", {}, "Ausencias observadas en nuestra muestra (RSS capturados), no afirmaciones de que el medio no publicara nada."),
      inf.silences.length ? el("ul", {}, inf.silences.map(s => el("li", {}, s.description))) : el("p", { className: "vacio" }, "Ninguno destacable."),
      el("h3", {}, "Notas de fuentes"),
      tablaFuentes(inf, fuentes),
      inf.source_notes.length ? el("ul", {}, inf.source_notes.map(n => el("li", {}, el("b", {}, fuentes.get(n.source_id)?.name || n.source_id), ": ", n.text))) : null,
      el("h3", {}, "Método y límites"),
      el("ul", {}, inf.limitations.map(l => el("li", {}, l))),
    ]));
  },

  pintarSuceso(inf, ev, params) {
    const fuentes = new Map(inf.sources.map(s => [s.id, s]));
    const evid = new Map(ev.evidence.map(e => [e.id, e]));
    const arts = new Map(ev.articles.map(a => [a.id, a]));
    const medios = ev.source_ids;
    const elegidos = (params.get("medios") || "").split(",").filter(m => medios.includes(m));
    const a = params.get("a"), b = params.get("b");
    const comparando = a && b && a !== b && medios.includes(a) && medios.includes(b);
    const visibles = comparando ? [a, b] : elegidos.length ? elegidos : medios;
    const nombre = id => `${fuentes.get(id)?.name || id} (${fuentes.get(id)?.country || "?"})`;
    const cambiarParams = cambios => {
      const p = new URLSearchParams(params);
      for (const [k, v] of Object.entries(cambios)) v ? p.set(k, v) : p.delete(k);
      const h = `#/semana/${inf.week_id}/${ev.id}${p.toString() ? "?" + p : ""}`;
      history.replaceState(null, "", h);  // filtros en la URL sin añadir pasos al historial
      almacen.set("ruta", h);
      this.rutaActual = h;
      this.pintarSuceso(inf, ev, p);
      anunciar(comparandoTexto(p));
    };
    const comparandoTexto = p => p.get("a") && p.get("b") ? `Comparando ${nombre(p.get("a"))} y ${nombre(p.get("b"))}` : "Filtro de medios actualizado";
    const ref = ids => (ids || []).filter(id => evid.has(id)).map((id, i) => el("button", {
      type: "button", className: "ref boton", "aria-label": `Ver evidencia ${id}`,
      onclick: () => { const t = $("evid-" + id); t?.scrollIntoView({ block: "center" }); t?.focus({ preventScroll: true }); }
    }, `[${ev.evidence.findIndex(e => e.id === id) + 1}]`));
    const cita = id => {
      const e = evid.get(id);
      if (!e) return null;
      const art = arts.get(e.article_id);
      return el("blockquote", { className: "cita", id: "evid-" + id, tabindex: -1 },
        el("q", { lang: e.language }, e.exact_quote),
        e.translation_es ? el("p", { className: "traduccion" }, el("b", {}, "Traducción al español (no es cita literal): "), e.translation_es) : null,
        el("footer", {}, `[${ev.evidence.findIndex(x => x.id === id) + 1}] `, HABLANTE[e.speaker?.type] || "—", e.speaker?.name ? ` · ${e.speaker.name}` : "",
          " · ", nombre(art?.source_id), " · ", art ? enlaceExterno(art.url, "artículo original") : "", ` · alcance: ${e.extraction_scope}`));
    };
    const afirmaciones = (titulo, lista, texto) => lista?.length ? [el("h5", {}, titulo), el("ul", {}, lista.map(c => el("li", {}, texto(c), " ", ...ref(c.evidence_ids), ...(c.evidence_ids || []).map(cita))))] : [];
    const tarjeta = sid => {
      const comp = ev.comparisons.find(c => c.source_id === sid) || {};
      const susArts = ev.articles.filter(x => x.source_id === sid);
      return el("article", { className: "tarjeta", "aria-labelledby": `med-${sid}` },
        el("h4", { id: `med-${sid}` }, nombre(sid)),
        el("ul", {}, susArts.map(x => el("li", {}, enlaceExterno(x.url, x.title), el("div", { className: "cifras-suceso" },
          `${fechaHora(x.published_at)} · ${GENERO[x.genre] || x.genre}${x.genre_basis ? ` (${x.genre_basis})` : ""} · ${ACCESO[x.access_status] || x.access_status}${x.access_reason ? `: ${x.access_reason}` : ""}`)))),
        ...afirmaciones("Encuadre", comp.framing_claims, c => c.text),
        ...afirmaciones("Lenguaje cargado y alternativa descriptiva", comp.language_claims, c => [el("q", {}, c.term), " → ", c.descriptive_alternative]),
        ...afirmaciones("Actores señalados", comp.actor_claims, c => `${c.actor}${c.role ? ` (${c.role})` : ""}`),
        ...afirmaciones("Fuentes citadas", comp.cited_source_claims, c => c.source),
        !comp.framing_claims?.length && !comp.language_claims?.length && !comp.actor_claims?.length && !comp.cited_source_claims?.length
          ? el("p", { className: "vacio" }, ev.analysis_status === "sin_ia" ? "Sin análisis de IA para este medio." : "Sin afirmaciones con evidencia verificable para este medio.") : null);
    };
    const chips = el("fieldset", { className: "chips" }, el("legend", {}, "Filtrar por medio"),
      medios.map(m => {
        const c = el("input", { type: "checkbox", value: m, checked: elegidos.includes(m) });
        c.addEventListener("change", () => {
          const s = new Set(elegidos); c.checked ? s.add(m) : s.delete(m);
          cambiarParams({ medios: [...s].join(","), a: null, b: null });
        });
        return el("label", {}, c, nombre(m));
      }));
    const sel = (id, valor, etiqueta) => el("label", {}, etiqueta + " ", el("select", { id, onchange: e => cambiarParams({ [id === "cmp-a" ? "a" : "b"]: e.target.value, medios: null }) },
      el("option", { value: "" }, "—"), medios.map(m => el("option", { value: m, selected: m === valor }, nombre(m)))));
    const volver = `#/semana/${inf.week_id}`;
    $("vista-semana").replaceChildren(pagina([
      el("a", { className: "volver", href: volver }, `← Volver a la semana ${inf.week_id}`),
      el("h2", { id: "titulo-semana", tabindex: -1 }, ev.title),
      ev.title_is_headline ? el("p", { className: "cifras-suceso" }, `Titular de ${nombre(ev.title_source_id)} (sin título neutral de la IA).`) : null,
      el("p", {}, el("span", { className: `etiqueta ${inf.status}` }, ESTADO_INFORME[inf.status]), " ",
        el("span", { className: "etiqueta" }, ESTADO_ANALISIS[ev.analysis_status] || ev.analysis_status), " ",
        inf.synthetic ? el("span", { className: "etiqueta sintetico" }, "Demostración sintética") : null),
      el("p", { className: "cifras-suceso" }, `${ev.country_ids.length} países · ${ev.source_ids.length} medios · artículos de ${fechaHora(ev.first_published_at)} a ${fechaHora(ev.last_published_at)} · corte ${fechaHora(inf.cutoff_at)}`),
      el("h3", {}, "Resumen neutral"),
      ev.summary_claims.length ? el("ul", {}, ev.summary_claims.map(c => el("li", {}, c.text, " ", ...ref(c.evidence_ids)))) : el("p", { className: "vacio" }, "Sin resumen: no hay análisis de IA para este suceso."),
      ev.temporal_notes.length ? el("div", { className: "tarjeta advertencias", role: "note" }, el("h4", {}, "Desfases de tiempo y género"), el("ul", {}, ev.temporal_notes.map(t => el("li", {}, t)))) : null,
      el("h3", {}, "Lo más llamativo"),
      ev.highlight_claims.length ? el("ul", {}, ev.highlight_claims.map(c => el("li", {}, c.text, " ", ...ref(c.evidence_ids)))) : el("p", { className: "vacio" }, "Nada con evidencia suficiente."),
      el("h3", {}, "Comparativa por medio"),
      chips,
      el("div", { className: "selector-semana" }, el("span", {}, "Comparar dos medios:"), sel("cmp-a", a, "A"), sel("cmp-b", b, "B"),
        comparando || elegidos.length ? el("button", { type: "button", className: "boton", onclick: () => cambiarParams({ a: null, b: null, medios: null }) }, "Ver todos") : null),
      el("div", { className: "comparativa" }, visibles.map(tarjeta)),
      el("h3", {}, "Omisiones verificables"),
      ev.omissions.length ? el("ul", {}, ev.omissions.map(o => el("li", {}, o.fact, " ", ...ref(o.supporting_evidence_ids),
        el("div", { className: "cifras-suceso" }, "No encontrado en: ", o.compared_article_ids.map(id => arts.get(id)).filter(Boolean)
          .map(x => `${nombre(x.source_id)} (${fechaHora(x.published_at)})`).join(" · "), `. Alcance: ${o.scope}`),
        ...o.supporting_evidence_ids.map(cita))))
        : el("p", { className: "vacio" }, "No evaluable o ninguna: solo se señalan omisiones con evidencia positiva en un artículo y texto completo en los comparados."),
      el("h3", {}, "Diferencias de cifras"),
      ev.figure_differences.length ? el("ul", {}, ev.figure_differences.map(f => el("li", {}, el("b", {}, f.topic), ": ",
        f.values.map((x, i) => [i ? " · " : "", `${x.value} (${nombre(arts.get(x.article_id)?.source_id)}, ${fechaHora(x.published_at)}) `, ...ref([x.evidence_id])]))))
        : el("p", { className: "vacio" }, "Ninguna con evidencia."),
      el("p", {}, el("a", { className: "volver", href: volver }, `← Volver a la semana ${inf.week_id}`)),
    ]));
  },
};

function pagina(hijos) { return el("div", { className: "pagina" }, hijos); }
function par(dt, dd) { return el("div", {}, el("dt", {}, dt), el("dd", {}, dd)); }
const fechaLarga = iso => new Date(iso).toLocaleString("es-ES", { timeZone: TZ, weekday: "long", day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" });

function matriz(inf, fuentes) {
  const sids = inf.sources.map(s => s.id);
  const leyenda = el("ul", { className: "leyenda", "aria-label": "Leyenda de la matriz" },
    Object.entries(CELDA).map(([k, [s, t]]) => el("li", { className: "celda " + k }, el("span", { "aria-hidden": "true" }, s + " "), t)));
  const tabla = el("table", {},
    el("caption", { className: "solo-lector" }, "Cobertura de cada suceso por medio"),
    el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "Suceso"),
      sids.map(id => el("th", { scope: "col", title: `${fuentes.get(id).name} · ${fuentes.get(id).country}` }, fuentes.get(id).name, el("br"), el("small", {}, fuentes.get(id).country))))),
    el("tbody", {}, inf.events.map(ev => el("tr", {},
      el("th", { scope: "row" }, el("a", { href: `#/semana/${inf.week_id}/${ev.id}` }, ev.title)),
      sids.map(id => {
        const k = ev.matrix[id] || "no_evaluable";
        const [s, t] = CELDA[k];
        return el("td", { className: "celda " + k, title: t }, el("span", { "aria-hidden": "true" }, s), el("span", { className: "solo-lector" }, t));
      })))));
  return [leyenda, el("div", { className: "tabla-scroll", tabindex: 0, role: "region", "aria-label": "Matriz de sucesos y medios (desplazable)" }, tabla),
    el("p", { className: "cifras-suceso" }, "«Sin coincidencias» significa que no hay ningún artículo de ese medio en nuestra muestra para el suceso, no que el medio no publicara nada.")];
}

function tarjetaSuceso(inf, ev, fuentes) {
  return el("li", { className: "tarjeta suceso" },
    el("h4", {}, el("a", { href: `#/semana/${inf.week_id}/${ev.id}` }, ev.title)),
    el("p", { className: "cifras-suceso" }, `${ev.country_ids.length} países · ${ev.source_ids.length} medios: ${ev.source_ids.map(id => fuentes.get(id)?.name || id).join(", ")}`),
    ev.summary_claims.length ? el("p", {}, ev.summary_claims.map(c => c.text).join(" "))
      : el("p", { className: "vacio" }, ev.analysis_status === "sin_ia" ? ESTADO_ANALISIS.sin_ia : "Sin resumen: ninguna frase tenía evidencia suficiente."),
    ev.highlight_claims.length ? el("p", {}, el("b", {}, "Lo más llamativo: "), ev.highlight_claims[0].text) : null);
}

function tablaFuentes(inf, fuentes) {
  const filas = inf.source_coverage.map(c => el("tr", {},
    el("th", { scope: "row" }, fuentes.get(c.source_id)?.name || c.source_id),
    el("td", {}, fuentes.get(c.source_id)?.country || "—"),
    el("td", { className: "celda " + (c.status === "evaluable" ? "encontrada" : "no_evaluable") }, c.status.replace("_", " ")),
    el("td", {}, c.window_start ? `${fechaHora(c.window_start)} → ${fechaHora(c.window_end)}` : "—"),
    el("td", {}, `${c.articles_in_period} en el periodo · ${c.articles_evaluated} evaluados`),
    el("td", {}, Object.entries(c.access_counts || {}).map(([k, v]) => `${ACCESO[k] || k}: ${v}`).join(" · ") || "—"),
    el("td", {}, c.errors.length ? `${c.errors.length} errores (último: ${c.errors[c.errors.length - 1]})` : "—"),
    el("td", {}, [c.substitutes ? `Sustituye a ${c.substitutes}` : "", c.substituted_by ? `Sustituida por ${c.substituted_by}` : "", c.paywall_method && c.paywall_method !== "no" ? `Premium: ${c.paywall_method}` : ""].filter(Boolean).join(" · ") || "—")));
  return el("div", { className: "tabla-scroll", tabindex: 0, role: "region", "aria-label": "Cobertura de cada fuente (desplazable)" },
    el("table", {}, el("caption", { className: "solo-lector" }, "Ventana temporal y estado de cada fuente"),
      el("thead", {}, el("tr", {}, ...["Medio", "País", "Estado", "Ventana real", "Artículos", "Acceso al texto", "Errores", "Sustituciones y muro"].map(t => el("th", { scope: "col" }, t)))),
      el("tbody", {}, filas)));
}

window.Semana = Semana;
