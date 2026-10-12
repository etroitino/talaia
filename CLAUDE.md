# Talaia

Panel personal de titulares de última hora por zona (Girona, Cataluña, España, Europa, Mundo). Requisitos completos en `REQUISITOS.md`.

## Stack
- Python (scripts con dependencias inline, se ejecutan con `uv run`).
- GitHub Actions (`.github/workflows/recoger.yml`) cada 15 min: descarga el `datos.json` publicado, ejecuta `recoger.py` y publica en Pages. Sin commits de datos, sin servidor ni base de datos.
- GitHub Pages sirve `index.html` (un solo archivo HTML+CSS+JS) que lee `datos.json`.
- Fuentes en `fuentes.yaml`; ajustes en `config.yaml` (desde la fase 3).

## Reglas
- Presupuesto de IA: 0 €. Solo planes gratuitos (Groq). Contar tokens y parar antes del límite.
- Nunca copiar texto de los medios: solo titular, resumen propio y enlace al original. La entradilla no se guarda en `datos.json` (es público); la IA la lee del RSS al vuelo.
- La clave de la IA solo en GitHub Secrets. Nunca en el código, la config ni la página.
- Si una fuente falla, el programa sigue y la página avisa.
- Etiqueta "muro" solo en artículos con muro comprobado uno a uno (métodos en `fuentes.yaml`), nunca por medio.
- La orientación de cada medio la decide Enrique, no la IA.

## Fases (no empezar una sin cerrar la anterior)
1. Titulares: F1 + página con cinco columnas. Comprobar todos los RSS.
2. Grupos y muro de pago: F2 + F6.
3. IA básica: F3 + mapa + filtros. Medir tokens por grupo.
4. Contraste y avisos: F4 + F5 con verificadores.
5. Estética: estilo sala de control, móvil, detalles.

## Local
- `uv run comprobar_rss.py` — estado de cada RSS de `fuentes.yaml`.
- `uv run recoger.py` — actualiza `datos.json`.
- `uv run test_recoger.py` — prueba de repetidas, borrado a 7 días y horas.
- `python3 -m http.server` y abrir http://localhost:8000 — la página (abrir el archivo directamente no carga `datos.json`).
