# /// script
# requires-python = ">=3.12"
# dependencies = ["playwright", "numpy", "pyyaml", "jsonschema", "feedparser"]
# ///
"""Pruebas de navegador con datos SINTÉTICOS (Chromium sin interfaz). Ejecutar: uv run test_navegador.py [--capturas DIR]
La primera vez puede hacer falta: uv run --with playwright playwright install chromium
La auditoría automática de accesibilidad (axe-core, desde cdnjs) no sustituye a probar con un lector de pantalla."""
import functools
import itertools
import http.server
import json
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright

import demo_sintetica
import montar_sitio

AXE = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"
ANCHOS = [(375, 812), (390, 844), (768, 1024), (1440, 900)]
capturas = Path(sys.argv[sys.argv.index("--capturas") + 1]) if "--capturas" in sys.argv else None
fallos, medidas = [], {}


def comprobar(cond, msg):
    if not cond:
        fallos.append(msg)
        print("✘", msg)


def montar(base, ahora):
    arch, trabajo = base / "archivo", base / "trabajo"
    arch.mkdir(); trabajo.mkdir()
    demo_sintetica.informe_demo(arch, trabajo)
    datos = demo_sintetica.datos_directo(ahora)
    (base / "datos.json").write_text(json.dumps(datos, ensure_ascii=False))
    return montar_sitio.montar(base / "datos.json", arch, base / "_site"), datos


def nueva_version(sitio, datos, minutos=1, n=6):
    """Simula una recogida nueva: n noticias más recientes arriba de cada zona."""
    ahora = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(minutes=minutos)
    extra = []
    for zona, fid in [("espana", "abc"), ("mundo", "the-guardian"), ("girona", "el-punt-avui-girona")]:
        for i in range(n):
            extra.append({**demo_sintetica.n(f"nuevo-{minutos}-{zona}-{i}", fid, f"[SINTÉTICO] nueva {zona} {i}", f"https://example.org/nuevo/{minutos}/{zona}/{i}",
                                             (ahora - timedelta(seconds=i)).isoformat()), "muro": False})
    datos = {**datos, "actualizado": ahora.isoformat(), "noticias": extra + datos["noticias"]}
    tmp = sitio.parent / f"d{minutos}.json"
    tmp.write_text(json.dumps(datos))
    d24 = montar_sitio.directo(datos, yaml.safe_load(open("fuentes.yaml", encoding="utf-8"))["fuentes"], json.loads((sitio / "semana" / "index.json").read_text()))
    (sitio / "ultimas24h.json").write_text(json.dumps(d24, ensure_ascii=False))
    v = json.loads((sitio / "version.json").read_text())
    (sitio / "version.json").write_text(json.dumps({**v, "version": d24["version"], "actualizado": datos["actualizado"]}))
    return datos


def servir(raiz):
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(raiz))
    h.log_message = lambda *a: None
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


def axe(pg, nombre):
    try:
        pg.add_script_tag(url=AXE)
    except Exception as e:
        medidas.setdefault("axe", {})[nombre] = f"no ejecutado ({type(e).__name__})"
        return
    r = pg.evaluate("axe.run(document, {resultTypes: ['violations']}).then(r => r.violations.map(v => ({id: v.id, impact: v.impact, n: v.nodes.length, ej: v.nodes[0].target.join(' ')})))")
    medidas.setdefault("axe", {})[nombre] = r
    graves = [v for v in r if v["impact"] in ("serious", "critical")]
    comprobar(not graves, f"axe {nombre}: {graves}")


with tempfile.TemporaryDirectory() as t, sync_playwright() as p:
    base = Path(t)
    sitio, datos = montar(base, datetime.now(timezone.utc).replace(microsecond=0))
    srv = servir(sitio)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    nav = p.chromium.launch()
    ev_id = json.loads((sitio / "semana" / "2026-W43.json").read_text())["events"][0]["id"]

    def pagina(ancho, alto, ruta="", **kw):
        ctx = nav.new_context(viewport={"width": ancho, "height": alto}, **kw)
        pg = ctx.new_page()
        pg.errores, pg.fallidas = [], []
        pg.on("console", lambda m: m.type == "error" and pg.errores.append(m.text))
        pg.on("pageerror", lambda e: pg.errores.append(str(e)))
        pg.on("requestfailed", lambda r: "127.0.0.1" in r.url and pg.fallidas.append(r.url))
        pg.on("response", lambda r: "127.0.0.1" in r.url and r.status >= 400 and pg.fallidas.append(f"{r.status} {r.url}"))
        pg.goto(url + ruta)
        pg.wait_for_timeout(700)
        return pg

    sin_scroll = "document.documentElement.scrollWidth <= innerWidth"
    # --- Todas las vistas, en los cuatro anchos: sin scroll horizontal global, sin errores ---
    for ancho, alto in ANCHOS:
        for ruta in ["#/directo", "#/directo/miradas", "#/directo/verificadores", "#/semana/2026-W43", f"#/semana/2026-W43/{ev_id}?a=tass&b=el-pais", "#/fuentes"]:
            pg = pagina(ancho, alto, ruta)
            comprobar(pg.evaluate(sin_scroll), f"{ancho}px {ruta}: scroll horizontal global")
            comprobar(not pg.errores and not pg.fallidas, f"{ancho}px {ruta}: errores {pg.errores} {pg.fallidas}")
            if capturas:
                pg.screenshot(path=str(capturas / f"{ancho}_{ruta.strip('#/').split('?')[0].replace('/', '_')}.png"), full_page=False)
            if ancho in (390, 1440) and "?" not in ruta:
                axe(pg, f"{ancho} {ruta}")
            pg.context.close()

    # --- Datos ligeros y DOM inicial ---
    pg = pagina(1440, 900)
    pedidas = []
    pg.on("request", lambda r: pedidas.append(r.url.split("?")[0].rsplit("/", 1)[-1]))
    medidas["dom_inicial_1440"] = pg.evaluate("document.getElementsByTagName('*').length")
    medidas["bytes_ultimas24h"] = (sitio / "ultimas24h.json").stat().st_size
    medidas["bytes_datos7d"] = (sitio / "datos.json").stat().st_size
    pg.evaluate("comprobar()"); pg.wait_for_timeout(500)
    comprobar(pedidas == ["version.json"], f"sin cambios solo se pide version.json: {pedidas}")
    comprobar("datos.json" not in pedidas, "Directo no descarga el archivo de 7 días")

    # --- Escritorio: columna Mundo leída abajo; recarga sin moverla y aviso de nuevas ---
    pg.goto(url + "#/directo/mundo"); pg.wait_for_timeout(400)
    col = "#col-mundo ol"
    pg.evaluate(f"document.querySelector('{col}').scrollTop = 900")
    antes = pg.evaluate(f"(() => {{ const ol = document.querySelector('{col}'), top = ol.getBoundingClientRect().top; const li = [...ol.children].find(l => l.getBoundingClientRect().bottom > top); return [li.dataset.clave, li.getBoundingClientRect().top - top]; }})()")
    datos = nueva_version(sitio, datos, 1)
    pg.evaluate("comprobar()"); pg.wait_for_timeout(500)
    despues = pg.evaluate(f"(() => {{ const ol = document.querySelector('{col}'); const li = ol.querySelector('[data-clave=\"{antes[0]}\"]'); return li.getBoundingClientRect().top - ol.getBoundingClientRect().top; }})()")
    comprobar(abs(despues - antes[1]) < 2, f"escritorio: el artículo visible se movió ({antes[1]} -> {despues})")
    comprobar(pg.is_visible("#nuevas") and "nuevas" in pg.inner_text("#nuevas"), "escritorio: falta el aviso «N noticias nuevas»")
    # Foco de teclado y grupo abierto se conservan al aplicar (recarga manual con ancla)
    pg.evaluate("document.querySelector('#col-mundo ol').scrollTop = 0"); pg.wait_for_timeout(300)  # al volver arriba se incorporan
    comprobar(pg.is_hidden("#nuevas"), "al volver arriba se incorporan las nuevas")
    pg.goto(url + "#/directo/espana"); pg.wait_for_timeout(300)
    pg.click("#col-espana details.grupo summary")
    pg.focus("#col-espana details.grupo summary")
    clave = pg.evaluate("document.activeElement.closest('li').dataset.clave")
    datos = nueva_version(sitio, datos, 2)
    pg.evaluate("comprobar(true)"); pg.wait_for_timeout(500)
    comprobar(pg.evaluate(f"!!document.querySelector('#col-espana details.grupo[open][data-clave=\"{clave}\"]')"), "el grupo abierto se cerró en la recarga")
    comprobar(pg.evaluate(f"document.activeElement.matches('summary') && document.activeElement.closest('li').dataset.clave === '{clave}'"), "el foco de teclado se perdió en la recarga")
    pg.context.close()

    # --- Móvil: el contenedor real es el documento; España leída abajo ---
    pg = pagina(390, 844, "#/directo/espana")
    pg.evaluate("document.scrollingElement.scrollTop = 1500"); pg.wait_for_timeout(200)
    antes = pg.evaluate("(() => { const li = [...document.querySelectorAll('#col-espana ol > li')].find(l => l.getBoundingClientRect().bottom > 0); return [li.dataset.clave, li.getBoundingClientRect().top]; })()")
    datos = nueva_version(sitio, datos, 3)
    pg.evaluate("comprobar()"); pg.wait_for_timeout(500)
    despues = pg.evaluate(f"document.querySelector('#col-espana [data-clave=\"{antes[0]}\"]').getBoundingClientRect().top")
    comprobar(abs(despues - antes[1]) < 2 and pg.evaluate("scrollY") > 1000, f"móvil: salto de scroll en la recarga ({antes[1]} -> {despues})")
    comprobar(pg.is_visible("#nuevas"), "móvil: falta el aviso de nuevas")
    pg.click("#nuevas"); pg.wait_for_timeout(300)
    comprobar(pg.evaluate("scrollY") < 50 and "nueva espana" in pg.inner_text("#col-espana ol > li:first-child"), "móvil: «ver» no muestra las nuevas arriba")
    # Recargar la página mantiene la zona; datos visibles de resultados y antigüedad
    pg.reload(); pg.wait_for_timeout(500)
    comprobar(pg.evaluate("location.hash") == "#/directo/espana" and pg.is_visible("#col-espana"), "móvil: la zona no sobrevive a la recarga")
    comprobar(pg.is_visible("#total") and pg.is_visible("#hace") and pg.is_visible("#resumen-filtros"), "móvil: titulares/antigüedad/resultados no visibles")
    comprobar(pg.inner_text("#total").isdigit(), "el número de titulares no se rellena")
    # Tamaños táctiles y de letra
    pequenos = pg.evaluate("""[...document.querySelectorAll('.secciones a, .zonas a, #refrescar, #q, .medios summary, .casilla, #orden, details.grupo summary, .mas, #plegar-destacadas')]
        .filter(e => e.offsetParent).map(e => [e.id || e.className || e.tagName, e.getBoundingClientRect().height, e.getBoundingClientRect().width]).filter(([, h, w]) => h < 44 || w < 44)""")
    comprobar(not pequenos, f"móvil: controles de menos de 44 px: {pequenos[:5]}")
    meta = pg.evaluate("parseFloat(getComputedStyle(document.querySelector('#col-espana .meta')).fontSize)")
    tit = pg.evaluate("parseFloat(getComputedStyle(document.querySelector('#col-espana a.titular')).fontSize)")
    comprobar(meta >= 12 and tit >= 16, f"móvil: letra pequeña (meta {meta}, titular {tit})")
    # Más cubiertas: plegada en móvil, se despliega; sin sucesos repetidos
    comprobar(pg.get_attribute("#plegar-destacadas", "aria-expanded") == "false", "móvil: Más cubiertas no empieza plegada")
    pg.click("#plegar-destacadas"); pg.wait_for_timeout(200)
    claves = pg.evaluate("[...document.querySelectorAll('#lista-destacadas > li')].map(l => l.dataset.clave)")
    comprobar(claves and len(claves) == len(set(claves)) and len(claves) <= 5, f"Más cubiertas repite o se pasa: {claves}")
    pg.context.close()

    # --- Miradas: navegación, recarga, atrás y adelante ---
    pg = pagina(1440, 900, "#/directo/girona")
    pg.click(".zonas a[href='#/directo/miradas']"); pg.wait_for_timeout(300)
    comprobar(pg.get_attribute(".zonas a[href='#/directo/miradas']", "aria-current") == "page" and pg.is_visible("#col-miradas"), "Miradas no se abre")
    comprobar(pg.evaluate("[...document.querySelectorAll('#col-mundo li .medio')].length") == 0, "Miradas no debe mostrar la columna Mundo")
    pg.reload(); pg.wait_for_timeout(500)
    comprobar(pg.is_visible("#col-miradas"), "Miradas no sobrevive a recargar")
    pg.go_back(); pg.wait_for_timeout(300)
    comprobar(pg.evaluate("location.hash") == "#/directo/girona", "Atrás no vuelve a Girona")
    pg.go_forward(); pg.wait_for_timeout(300)
    comprobar(pg.evaluate("location.hash") == "#/directo/miradas" and pg.is_visible("#col-miradas"), "Adelante no vuelve a Miradas")
    # La columna Mundo no incluye medios de Miradas
    pg.goto(url + "#/directo"); pg.wait_for_timeout(300)
    medios_mundo = set(pg.evaluate("[...document.querySelectorAll('#col-mundo ol > li > .meta .medio')].map(e => e.textContent)"))
    comprobar(not medios_mundo & {"TASS", "Al Jazeera", "DW"}, f"Miradas mezclada en Mundo: {medios_mundo}")

    # --- Buscar + filtrar + ocultar premium + ordenar + cargar más, combinados ---
    total = lambda: pg.evaluate("document.getElementById('resumen-filtros').textContent")
    pg.fill("#q", "SINTETICO NUMERO"); pg.wait_for_timeout(400)  # sin acentos ni mayúsculas
    comprobar("entradas" in total() and "búsqueda" in total(), f"la búsqueda no se refleja: {total()}")
    pg.fill("#q", ""); pg.wait_for_timeout(300)
    pg.click("#filtro-medios summary")
    pg.check("#lista-medios input[value='el-pais']"); pg.check("#lista-medios input[value='eldiario-es']"); pg.wait_for_timeout(300)
    n_esp = pg.evaluate("document.querySelectorAll('#col-espana ol > li.noticia').length")
    rep_premium = pg.evaluate("[...document.querySelectorAll('#col-espana ol > li.noticia')].some(l => l.querySelector(':scope > .meta .premium'))")
    pg.check("#sin-premium"); pg.wait_for_timeout(300)
    comprobar(not pg.evaluate("[...document.querySelectorAll('#col-espana ol > li.noticia')].some(l => l.querySelector(':scope > .meta .premium'))") and rep_premium,
              "ocultar premium no quita los premium")
    comprobar(pg.evaluate("[...document.querySelectorAll('#col-espana a.titular')].some(a => a.textContent.includes('Hecho compartido contado por eldiario-es'))"),
              "el grupo con representante premium debe mostrarse con su alternativa abierta")
    cuenta_txt = pg.inner_text("#col-espana .cuenta")
    pg.select_option("#orden", "contrastadas"); pg.wait_for_timeout(300)
    primero = pg.inner_text("#col-espana ol > li.noticia:first-child")
    comprobar("medios" in primero, "«Más contrastadas» no pone primero el grupo con más medios")
    comprobar(pg.is_visible("#limpiar"), "falta «Limpiar» con filtros activos")
    pg.click("#limpiar"); pg.wait_for_timeout(300)
    comprobar(not pg.is_checked("#sin-premium") and pg.is_hidden("#limpiar"), "«Limpiar» no borra los filtros")
    li_antes = pg.evaluate("document.querySelectorAll('#col-espana ol > li.noticia').length")
    cuenta = int(pg.inner_text("#col-espana .cuenta").split()[0])
    pg.click("#col-espana .mas"); pg.wait_for_timeout(300)
    li_despues = pg.evaluate("document.querySelectorAll('#col-espana ol > li.noticia').length")
    comprobar(li_despues > li_antes and cuenta > li_antes, f"«Cargar más» o conteo mal ({li_antes} -> {li_despues}, cuenta {cuenta})")
    comprobar(pg.evaluate("document.activeElement.dataset.foco") in ("mas-espana", None), "foco tras cargar más")
    # Diversidad: como mucho 2 seguidas del mismo medio (la ráfaga inicial de Girona tiene 15)
    pg.select_option("#orden", "diversidad"); pg.wait_for_timeout(300)
    medios = pg.evaluate("[...document.querySelectorAll('#col-girona ol > li > .meta .medio')].map(e => e.textContent)")
    racha = max(len(list(g)) for _, g in itertools.groupby(medios))
    comprobar(racha <= 2 or len(set(medios)) == 1, f"Diversidad deja rachas de {racha}")
    pg.select_option("#orden", "recientes")
    # «Comparar enfoques» solo por artículo exacto
    href = pg.evaluate("[...document.querySelectorAll('a.comparar')].map(a => a.getAttribute('href'))")
    comprobar(href and all(h == f"#/semana/2026-W43/{ev_id}" for h in href), f"Comparar enfoques mal enlazado: {href}")
    # Enlaces externos protegidos
    malos = pg.evaluate("[...document.querySelectorAll('a[target=_blank]')].filter(a => !/noopener/.test(a.rel) || !/noreferrer/.test(a.rel) || !/^https?:/.test(a.href)).length")
    comprobar(malos == 0, f"{malos} enlaces externos sin protección")
    # Leído: se atenúa y se puede borrar
    with pg.context.expect_page() as nueva:
        pg.click("#col-mundo a.titular >> nth=0")
    nueva.value.close()
    comprobar(pg.evaluate("document.querySelector('#col-mundo a.titular').classList.contains('leido')"), "el enlace leído no se marca")
    pg.goto(url + "#/fuentes"); pg.wait_for_timeout(400)
    pg.click("text=Borrar historial de lectura"); pg.wait_for_timeout(200)
    comprobar(pg.evaluate("Object.keys(JSON.parse(localStorage.getItem('talaia.leidos') || '{}')).length") == 0, "no se borra el historial")
    pg.context.close()

    # --- Semana: portada, suceso, filtrar, comparar dos, volver sin perder contexto ---
    pg = pagina(390, 844, "#/semana")
    comprobar(pg.evaluate("location.hash") == "#/semana/2026-W43", "Semana no abre el último informe")
    txt = pg.inner_text("#vista-semana")
    comprobar("DEMOSTRACIÓN SINTÉTICA" in txt and "Europe/Madrid" in txt and "2026" in txt, "faltan rótulo sintético / intervalo / zona horaria")
    matriz = "document.querySelector('[aria-label^=\"Matriz de sucesos\"]')"
    comprobar(pg.evaluate(f"(() => {{ const t = {matriz}; return !!t && t.scrollWidth > t.clientWidth && document.documentElement.scrollWidth <= innerWidth; }})()"),
              "la matriz debe desplazarse dentro de su caja en móvil")
    cab = pg.evaluate(f"[...{matriz}.querySelectorAll('thead th')].map(th => th.textContent)")
    comprobar("TASSRU" in cab and "RTRU" in cab and len(cab) == 1 + len(demo_sintetica.fuentes), f"la matriz no nombra cada medio: {cab[:5]}")
    comprobar("[object" not in txt and pg.evaluate(f"{matriz}.querySelectorAll('tbody tr').length") == 2, "matriz mal pintada")
    comprobar(pg.evaluate(f"[...{matriz}.querySelectorAll('td')].every(td => td.querySelector('.solo-lector').textContent && td.title)"), "celdas de la matriz sin nombre accesible")
    md = pg.get_attribute("a[download]", "href")
    comprobar(md == "semana/2026-W43.md" and (sitio / md).read_text().startswith("# Talaia · Semana 2026-W43"), f"Markdown: {md}")
    pg.evaluate("document.scrollingElement.scrollTop = 600"); pg.wait_for_timeout(100)
    pos = pg.evaluate("scrollY")
    pg.evaluate(f"document.querySelector(\"a[href='#/semana/2026-W43/{ev_id}']\").click()"); pg.wait_for_timeout(500)  # sin desplazar la página
    comprobar(pg.evaluate("document.activeElement.id") == "titulo-semana", "el cambio de ruta no lleva el foco al título")
    pg.check(".chips input[value='tass']"); pg.wait_for_timeout(200)
    comprobar("medios=tass" in pg.evaluate("location.hash") and pg.evaluate("document.querySelectorAll('.comparativa > article').length") == 1, "filtro por medio")
    pg.select_option("#cmp-a", "tass"); pg.wait_for_timeout(200); pg.select_option("#cmp-b", "el-pais"); pg.wait_for_timeout(300)
    comprobar(pg.evaluate("document.querySelectorAll('.comparativa > article').length") == 2, "comparar dos medios")
    comprobar(pg.evaluate("[...document.querySelectorAll('.cita q')].every(q => q.lang)") and "Traducción al español (no es cita literal)" in pg.text_content("#vista-semana"),
              "citas sin idioma o traducción sin marcar")
    comprobar(pg.evaluate("[...document.querySelectorAll('.cita footer a')].every(a => a.target === '_blank' && /noopener/.test(a.rel))"), "enlace al artículo original")
    pg.reload(); pg.wait_for_timeout(600)
    comprobar("a=tass" in pg.evaluate("location.hash") and pg.evaluate("document.querySelectorAll('.comparativa > article').length") == 2, "la comparación no sobrevive a recargar")
    pg.click("a.volver >> nth=0"); pg.wait_for_timeout(600)
    comprobar(pg.evaluate("location.hash") == "#/semana/2026-W43" and abs(pg.evaluate("scrollY") - pos) < 5, f"volver no conserva la posición ({pos} -> {pg.evaluate('scrollY')})")
    pg.go_back(); pg.wait_for_timeout(500)
    comprobar("a=tass" in pg.evaluate("location.hash"), "Atrás no vuelve a la comparación")
    pg.context.close()
    # Enlace profundo directo y semana inexistente
    pg = pagina(1440, 900, f"#/semana/2026-W43/{ev_id}")
    comprobar(pg.is_visible("text=Comparativa por medio"), "el enlace profundo al suceso no carga")
    pg.goto(url + "#/semana/2020-W01"); pg.wait_for_timeout(400)
    comprobar("No hay informe de 2020-W01" in pg.inner_text("#vista-semana"), "semana inexistente sin estado vacío")
    pg.context.close()

    # --- Teclado y ARIA ---
    pg = pagina(1440, 900, "#/directo")
    pg.keyboard.press("Tab")
    comprobar(pg.evaluate("document.activeElement.id") == "saltar", "el primer Tab no llega a «Saltar al contenido»")
    pg.keyboard.press("Enter")
    comprobar(pg.evaluate("document.activeElement.id") == "contenido", "«Saltar al contenido» no mueve el foco")
    for _ in range(12):
        pg.keyboard.press("Tab")
    comprobar(pg.evaluate("getComputedStyle(document.activeElement).outlineStyle") != "none", "foco no visible")
    comprobar(pg.evaluate("document.querySelectorAll('[role=tab]').length") == 0, "pestañas ARIA a medias")
    comprobar(pg.evaluate("[...document.querySelectorAll('[aria-labelledby]')].every(e => e.getAttribute('aria-labelledby').split(' ').every(id => document.getElementById(id)))"), "aria-labelledby roto")
    comprobar(pg.evaluate("document.getElementById('anuncio').getAttribute('aria-live')") == "polite", "falta región aria-live")
    pg.context.close()

    # --- Movimiento reducido y almacenamiento bloqueado ---
    pg = pagina(390, 844, "#/directo", reduced_motion="reduce")
    comprobar(pg.evaluate("getComputedStyle(document.querySelector('.directo'), '::before').animationName") == "none", "no respeta prefers-reduced-motion")
    pg.context.close()
    ctx = nav.new_context(viewport={"width": 390, "height": 844})
    ctx.add_init_script("Object.defineProperty(window, 'localStorage', { get() { throw new Error('bloqueado'); } }); Object.defineProperty(window, 'sessionStorage', { get() { throw new Error('bloqueado'); } });")
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(url + "#/directo/mundo"); pg.wait_for_timeout(600)
    comprobar(not errs and pg.evaluate("document.querySelectorAll('#col-mundo li.noticia').length") > 0, f"con almacenamiento bloqueado falla: {errs}")
    ctx.close()

    # --- Datos que no cargan: aviso legible, sin romper ---
    (sitio / "version.json").rename(sitio / "version.json.bak")
    pg = pagina(390, 844, "#/directo")
    comprobar("No se pudieron actualizar" in pg.inner_text("#avisos"), "sin datos no hay aviso de error")
    pg.context.close()
    nav.close()
    srv.shutdown()

print(json.dumps(medidas, ensure_ascii=False, indent=1))
print("FALLOS:" if fallos else "OK", *fallos, sep="\n")
sys.exit(1 if fallos else 0)
