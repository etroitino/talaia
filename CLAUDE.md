# Talaia

Panel personal de titulares de última hora por zona (Girona, Cataluña, España, Europa, Mundo), con vistas Miradas y Verificadores, y un informe semanal que compara cómo cuentan los mismos sucesos medios de distintos países. Requisitos completos en `REQUISITOS.md`; recorridos de la página en `FLOWS.md`.

## Stack
- Python (scripts con dependencias inline, se ejecutan con `uv run`). Sin framework, sin servidor, sin base de datos remota, sin cuentas.
- GitHub Actions:
  - `recoger.yml` cada 15 min: descarga el `datos.json` publicado (o lo restaura del archivo), ejecuta `recoger.py` y `agrupar.py`, guarda capturas en la rama `archivo`, monta el sitio con `montar_sitio.py` y publica Pages. **Es el único workflow que publica Pages.** Al final comprueba si toca el informe semanal y lanza `semana.yml`.
  - `semana.yml`: genera el informe, lo sube a la rama `archivo` y lanza `recoger.yml` para publicarlo. Nunca despliega Pages por su cuenta.
- El horario de GitHub no es fiable: la recogida la lanza cron-job.org cada 15 min vía API (`workflow_dispatch`) con un token fine-grained (solo repo talaia, solo Actions: write). No tocar cron-job.org ni su token. El `schedule` queda como respaldo.
- Pages sirve `index.html` + `estilo.css` + `app.js` (router, Directo, Fuentes) + `semana.js` (vista Semana). Rutas hash: `#/directo`, `#/directo/<zona|miradas|verificadores>`, `#/semana/AAAA-Www[/ev-…]`, `#/fuentes`.
- Fuentes en `fuentes.yaml`; ajustes (IA, semana, extracción) en `config.yaml`; esquema del informe en `esquema_semana.json`.

## Datos y almacenamiento
- Sin commits de datos en `main`. El archivo duradero es la rama huérfana `archivo` (`archivo.py`):
  `capturas/AAAA-Www.jsonl` (metadatos por semana ISO de Madrid, solo titular/enlace/medio/hora/muro), `capturas/AAAA-Www.ejecuciones.json` (horas con recogida y estado por fuente), `semana/` (informes), `uso/ia.json` (tokens de las últimas 48 h), `cache_ia/` (resultados validados). Capturas: 12 semanas; informes: indefinidos.
- Fusionar es una unión por id; un push rechazado se resuelve releyendo y fusionando (no hay force-push). Recuperar: `git fetch origin archivo && git worktree add .archivo archivo`, o `uv run archivo.py restaurar`.
- Públicos: `ultimas24h.json` (Directo; 24 h; sin cuerpos), `version.json` (marca de bytes), `fuentes.json`, `datos.json` (7 días, compatibilidad), `semana/index.json`, `semana/AAAA-Www.json` y `.md`.

## Reglas
- Presupuesto de IA: 0 €. Solo Groq (con q; nunca Grok/xAI), plan gratuito, sin respaldo de pago. El modelo se comprueba en `/models`; topes por petición, ejecución y 24 h en `config.yaml`. Sin cuota o sin clave, Directo sigue igual y el informe dice "sin IA".
- Nunca copiar texto de los medios en Directo: solo titular y enlace. La entradilla no se guarda.
- Excepción limitada (informe semanal): citas breves y literales, necesarias para el análisis, atribuidas y enlazadas, comprobadas contra el texto del artículo indicado (`evidencias.py`). Nada de artículos completos ni reconstrucciones a base de citas (máximo de citas y de proporción por artículo). Las traducciones se marcan como tales. No es una garantía jurídica de "derecho de cita".
- Texto completo solo si es accesible a cualquier visitante y robots.txt lo permite (`extraer.py`); no se sortean muros, CAPTCHA, 403 ni controles de acceso, no se usan cookies ni RemovePaywall. El texto vive en memoria: nunca en el repo, logs ni artifacts.
- Cada afirmación del informe referencia evidencias por id. Omisiones solo con evidencia positiva y texto completo de los comparados. Si no hay evidencia: "No evaluable".
- La clave de la IA solo en GitHub Secrets (`GROQ_API_KEY`) o en el entorno local. Nunca en el código, la config ni la página.
- Si una fuente falla, el programa sigue y la página avisa. "Sin respuesta" o "sin coincidencias" no significa que el medio no publicara.
- Etiqueta "premium" (campo `muro`) solo en artículos que el medio declara de pago, comprobados uno a uno (métodos en `fuentes.yaml`), nunca por medio.
- La orientación de cada medio la decide Enrique, no la IA. El campo `pais` es la sede del medio, no su orientación. Nada de puntuaciones ideológicas.
- Datos de demostración: solo con `demo_sintetica.py` y marcados `synthetic: true`. Nunca presentar datos inventados como reales.

## Local
- `uv run comprobar_rss.py` — estado de cada RSS (marca ANTIGUO si responde pero no se actualiza).
- `uv run recoger.py` · `uv run agrupar.py` · `uv run agrupar.py --revisar`.
- `uv run archivo.py capturar --local --dir DIR` — capturas en un directorio sin git.
- `uv run semana.py --week 2026-W43 [--as-of ISO] [--no-llm] [--dry-run --salida DIR] [--forzar] [--local --archivo DIR]`; `--auto` decide con la hora de Madrid; `--auto --solo-comprobar` solo informa.
- `uv run montar_sitio.py --archivo DIR --salida _site` y `python3 -m http.server -d _site` → http://localhost:8000 (no abrir con file://).
- Pruebas: `uv run test_recoger.py`, `test_agrupar.py`, `test_archivo.py`, `test_semana.py`, `test_navegador.py [--capturas DIR]` (Chromium de Playwright; axe-core desde cdnjs).
