# Panel de noticias: requisitos

Oct 10, 2026 · @Enrique Troitiño

## Objetivo y decisiones

Una página web personal que muestra los titulares de última hora de medios elegidos por Enrique, ordenados por zona (Girona, Cataluña, España, Europa, Mundo), con resúmenes, etiquetas, contraste entre medios de distinta línea editorial y avisos sobre posibles bulos hechos por IA.

| Tema | Decisión |
| --- | --- |
| Contenido | Solo titulares de última hora, sin resumen diario aparte |
| Estilo | Inspirado en World Monitor (oscuro, tipo sala de control), sin copiarlo |
| Mapa | Secundario: lo principal son las columnas por zona |
| Lenguaje | Python |
| Presupuesto de IA | 0 € al mes: solo planes gratuitos |
| Alojamiento | GitHub Actions + GitHub Pages, sin servidor propio |
| Muro de pago | Si la noticia viene de un medio con muro, ofrecer la misma noticia en otros medios |
| Desarrollo | Estos requisitos se implementan después con Claude Code |

El presupuesto de 0 € es lo que más limita el resto: obliga a usar la IA solo donde aporta más (ver la sección de IA gratis).

## Fuentes

Lista inicial propuesta. Las fuentes viven en un archivo de configuración (`fuentes.yaml`) para poder añadir o quitar medios sin tocar el código. La columna de orientación la rellena Enrique: el contraste entre medios depende de ella y no debe decidirla la IA.

| Zona | Medio | Idioma | Muro de pago | Orientación |
| --- | --- | --- | --- | --- |
| Girona | Diari de Girona | ca/es | Parcial |  |
| Girona | El Punt Avui (Girona) | ca | Parcial |  |
| Girona | Girona Notícies | ca | No |  |
| Cataluña | 3Cat / 324 | ca | No |  |
| Cataluña | La Vanguardia | es/ca | Parcial |  |
| Cataluña | Ara | ca | Parcial |  |
| Cataluña | El Periódico | es/ca | Parcial |  |
| Cataluña | El Nacional | ca | No |  |
| España | El País | es | Parcial |  |
| España | El Mundo | es | Parcial |  |
| España | ABC | es | Parcial |  |
| España | elDiario.es | es | No |  |
| España | El Confidencial | es | Parcial |  |
| España | RTVE | es | No |  |
| Europa | Politico Europe | en | No |  |
| Europa | Euronews | en/es | No |  |
| Mundo | BBC News | en | No |  |
| Mundo | The Guardian | en | No |  |
| Mundo | France 24 | en/es | No |  |
| Verificadores | Maldita, Newtral, EFE Verifica, Verificat | es/ca | No | (no aplica) |

Requisitos de las fuentes:

- Cada medio se define con: nombre, zona, URL del RSS, idioma, si tiene muro de pago y orientación.
- "Muro de pago: Parcial" significa que el medio tiene artículos de pago, no que todos lo sean. El valor de esta columna es orientativo y hay que comprobarlo.
- En la fase 1 se comprueba que cada RSS existe y funciona. Si un medio no tiene RSS, se quita o se busca otra vía; no se lee la web a mano en la primera versión.
- En Cataluña conviene cubrir también el eje independentista / no independentista, no solo izquierda / derecha. Se añade un segundo campo de orientación si Enrique lo quiere.

## Funcionalidades

Ocho bloques. Los de IA (F3 a F5) trabajan sobre grupos de noticias, no sobre cada noticia suelta, para no pasarse del límite gratuito.

**F1. Recogida de titulares.** Cada 15 minutos se leen los RSS de todas las fuentes. Se guarda título, entradilla, enlace, medio, zona y hora. Las noticias repetidas (mismo enlace) se descartan.

**F2. Agrupar noticias del mismo hecho.** Las noticias que hablan de lo mismo se juntan en un grupo, aunque vengan de medios distintos y en idiomas distintos. Se hace sin IA de pago: con un modelo pequeño que convierte cada título en números comparables (se llama "embedding") y se ejecuta gratis dentro de GitHub Actions. Si dos títulos se parecen lo bastante, van al mismo grupo.

**F3. Resumen, etiquetas, lugar e importancia (IA).** Para cada grupo nuevo, la IA genera:

- Un resumen de 2-3 frases en español, escrito con sus palabras, nunca copiando el texto del medio.
- Un tema de una lista cerrada (política, economía, sucesos, sociedad, internacional, deportes, cultura, ciencia y tecnología, clima) y hasta 3 etiquetas libres.
- El lugar donde pasa (ciudad o país). Las coordenadas para el mapa se sacan después con un servicio gratuito de mapas, guardando cada lugar para no repetir la consulta.
- Una importancia de 1 a 5.

**F4. Contraste entre medios (IA).** Solo para grupos con importancia 4 o 5 y cubiertos por al menos 3 medios de orientación distinta. La IA indica en qué coinciden, en qué se diferencian (datos, enfoque, lo que cada uno omite) y qué medio dice qué. No da la razón a nadie: describe diferencias.

**F5. Avisos de posible bulo.** La IA no decide si algo es bulo, porque se equivoca y además solo ve titulares. En su lugar:

1. Se cruzan los grupos con los RSS de los verificadores (Maldita, Newtral, EFE Verifica, Verificat). Si un verificador ha publicado sobre ese tema, se muestra su enlace y su calificación tal cual la da él.
2. La IA marca "señales a vigilar" cuando las hay: solo un medio lo publica, no se cita ninguna fuente, los medios se contradicen en un dato clave, o el titular es muy alarmista. Se muestran como avisos, nunca como "es falso".

**F6. Alternativa al muro de pago.** Si una noticia viene de un medio marcado con muro de pago y su grupo tiene noticias de medios sin muro, se muestran como "Léelo también en: …". Si no hay alternativa, no se muestra nada.

**F7. Interfaz.**

- Estilo oscuro tipo sala de control, inspirado en World Monitor pero con diseño propio.
- Barra superior con los 5 grupos más importantes del momento.
- Cinco columnas: Girona, Cataluña, España, Europa, Mundo. En el móvil, pestañas en vez de columnas.
- Cada noticia muestra: hora, medio, titular, tema, insignia de muro de pago y, al abrirla, resumen, contraste, avisos y alternativas.
- Mapa secundario con un punto por grupo, coloreado por tema.
- Filtros por tema y por medio, y un buscador por palabras.
- Marca de "nuevo" para lo publicado en la última hora.
- La página se recarga sola cada pocos minutos.

**F8. Histórico.** Se guardan los últimos 7 días. Lo más antiguo se borra solo.

## IA gratis: límites y cómo encajar

Proveedor propuesto: Groq, plan gratuito. Su límite real es de tokens por día (un token es más o menos un trozo de palabra), no de peticiones.

| Proveedor | Límite gratuito | Problema |
| --- | --- | --- |
| Groq | 30 peticiones/min, 1.000 peticiones/día, 200.000 tokens/día | Ninguno grave; guarda los datos hasta 30 días para revisar abusos |
| Gemini (Google) | Límites no publicados; se ven en Google AI Studio | Sus condiciones dicen que las apps para usuarios en la UE solo pueden usar el plan de pago |
| OpenRouter | 50 peticiones/día en modelos gratuitos | Se queda corto |

Fuente: [agentdeals.dev, cambios de precios de Gemini y alternativas](https://agentdeals.dev/gemini-api-pricing-changes), consultado el 10/10/2026. Los límites cambian; hay que revisarlos al empezar.

Reglas para no pasarse de 200.000 tokens al día:

- La IA solo procesa grupos nuevos (F2), nunca noticias sueltas ni grupos ya procesados.
- La recogida va cada 15 minutos, pero la IA va en lotes cada hora, varios grupos por petición.
- A la IA solo se le envía título y entradilla del RSS, no el artículo entero.
- El contraste (F4) solo para los grupos más importantes, con un tope diario configurable.
- El programa lleva la cuenta de los tokens gastados en el día. Si se acerca al límite, para y lo pendiente espera a la siguiente hora o al día siguiente. La página sigue mostrando titulares sin resumen.
- El proveedor y el modelo se cambian desde la configuración, para poder pasar a otro sin reescribir código.

En la fase 3 se mide cuántos grupos nuevos salen al día y cuántos tokens gasta cada uno. Con esa cifra se ajustan los topes.

## Arquitectura

&#91;embedded content: arquitectura · 6 piezas, todo en GitHub\]

Un programa en Python, guardado en un repositorio de GitHub, hace todo el trabajo. GitHub lo ejecuta cada 15 minutos y publica en GitHub Pages los archivos que lee la página; sin commits de datos en `main` (el archivo duradero vive en la rama `archivo`, ver «Evolución»).

- **Programa:** Python, con un archivo por paso (recoger, agrupar, IA, guardar). Configuración en `fuentes.yaml` y `config.yaml`.
- **Página:** un solo HTML con su CSS y JavaScript, sin servidor. Lee `datos.json` y pinta columnas, mapa y filtros.
- **Datos:** `datos.json` con los grupos de los últimos 7 días. Sin base de datos.
- **Clave de la IA:** en los secretos de GitHub ("GitHub Secrets"), que solo ve el programa al ejecutarse.
- **Mapa:** una librería gratuita de mapas web (por ejemplo Leaflet) con mapa oscuro.

## Fases

Cada fase deja algo que funciona. No se empieza la siguiente sin cerrar la anterior.

1. **Titulares.** F1 + página sencilla con las cinco columnas. Comprobar todos los RSS.
2. **Grupos y muro de pago.** F2 + F6. Ajustar a mano el umbral de parecido mirando grupos reales.
3. **IA básica.** F3 + mapa + filtros. Medir tokens por grupo.
4. **Contraste y avisos.** F4 + F5 con los verificadores.
5. **Estética.** Pulir el estilo tipo sala de control, versión móvil y detalles.

## Fuera de esta versión

- Notificaciones al móvil.
- Usuarios, contraseñas o cuentas.
- Leer el artículo entero de cada noticia en Directo. (El informe semanal sí lee el texto accesible de unos pocos artículos, con las reglas de «Evolución».)
- App móvil propia (la web en el móvil basta).
- Evitar muros de pago: solo se ofrecen otras fuentes, nunca se salta el muro.

## Criterios de aceptación

- [ ] Una noticia publicada en un RSS aparece en la página en menos de 30 minutos.
- [ ] La misma noticia contada por 3 medios aparece como un solo grupo con los 3 enlaces.
- [ ] Una noticia de un medio con muro muestra alternativas cuando las hay.
- [ ] Ningún día se supera el límite gratuito de la IA; si se acerca, el programa para solo.
- [ ] Ningún aviso dice "es falso" salvo que lo diga un verificador, enlazado.
- [ ] La página se lee bien en un móvil de 400 px de ancho.
- [ ] La clave de la IA no aparece en el código ni en la página.

## Riesgos y preguntas abiertas

- **Repositorio público.** GitHub Pages gratis exige que el repositorio sea público, así que cualquiera con el enlace verá la página y los datos. Para noticias no es grave. La clave de la IA va en los secretos de GitHub, nunca en el código.
- **Horario de GitHub Actions.** Las tareas programadas pueden ejecutarse con retraso en horas de mucho uso; "cada 15 minutos" es aproximado. Comprobar también si GitHub desactiva tareas programadas en repositorios sin actividad.
- **RSS que fallan o desaparecen.** El programa debe seguir funcionando aunque un medio falle, y avisar en la página de qué fuente no responde.
- **Errores de la IA.** Resúmenes o lugares equivocados. Cada resumen lleva siempre los enlaces a los medios originales.
- **Derechos de autor.** Directo: solo titular y enlace. Informe semanal: además, citas breves, literales, atribuidas y enlazadas (excepción limitada; no es una garantía jurídica).
- **Pendiente de Enrique:** rellenar la orientación de cada medio y confirmar la lista de fuentes.

## Evolución (25/10/2026): vista semanal y mejoras de Directo

Esta sección actualiza las fases y la regla de citas. Lo anterior sigue vigente donde no se contradiga.

### Decisiones

| Tema | Decisión |
| --- | --- |
| Navegación | Dos niveles: Directo / Semana / Fuentes; dentro de Directo, cinco zonas + Miradas + Verificadores. Enlaces con `aria-current`, no pestañas ARIA. Rutas hash; la URL manda sobre lo guardado. |
| Datos de Directo | `ultimas24h.json` (sin cuerpos) + `version.json`; `datos.json` (7 días) solo por compatibilidad. |
| Miradas | TASS y RT (RU), Al Jazeera (QA), Tehran Times (IR), Global Times → CGTN (CN), Haaretz (IL), NPR (US), DW (DE). No entran en Mundo. |
| IA | Groq, modelo configurable y comprobado en `/models`. 0 €: topes propios por petición, ejecución y 24 h; sin respaldo de pago. |
| Citas | Excepción limitada: breves, literales, atribuidas, enlazadas; comprobadas contra el texto; máx. 4 por artículo y 15 % del texto. |
| Texto completo | Solo el accesible a cualquier visitante y permitido por robots.txt. Sin sortear muros, CAPTCHA ni 403. Sin RemovePaywall. El texto no se guarda. |
| Orientación | La decide Enrique. El informe compara evidencias de cada artículo; no puntúa ideologías. |
| Archivo | Rama huérfana `archivo`: capturas por semana ISO (12 semanas), informes, uso de IA y caché. |

### Calendario del informe (hora de Madrid)

- Domingo desde las 09:00: informe **provisional** de la semana en curso, con corte visible.
- Lunes desde las 00:30: **cierre** con datos hasta el lunes 00:00 (exclusivo). Si faltan capturas, **parcial**.
- Hasta 3 días después: se regenera si llegan datos tardíos o el análisis quedó incompleto (cada 6 h como mucho). Mismos datos = no se regenera ni se gasta.
- Actions solo admite cron en UTC: `semana.yml` se programa en las dos horas posibles y `semana.py --auto` decide con `Europe/Madrid`. La recogida (cron-job.org) también lo comprueba cada 15 min.

### Selección

Reagrupación semanal desde cero (no se fía de los ids de Directo), con un hueco máximo de 36 h entre noticias de un grupo. Un suceso necesita al menos 2 países. Orden: países distintos, luego medios distintos (cada medio cuenta una vez), luego recencia. De 5 a 8 sucesos; si hay menos, se dice por qué. Solo artículos del periodo.

### Esquema (`esquema_semana.json`, `schema_version` 1.0)

`week_id`, `timezone`, `period_start`, `period_end_exclusive`, `cutoff_at`, `generated_at`, `status` (provisional/cerrado/parcial/no_disponible), `analysis_status` (completo/parcial/sin_ia), `coverage_warnings`, `observed_coverage`, `model_id`, `prompt_version`, `input_hash`, `synthetic`, `sources`, `source_coverage[]`, `selection`, `events[]` (`articles`, `evidence` con `exact_quote`/`translation_es`/`speaker`/`text_hash`/`extraction_scope`, `comparisons`, `omissions`, `figure_differences`, `temporal_notes`, `highlight_claims`, `matrix`), `silences`, `source_notes`, `limitations`. `semana.py:validar_informe` comprueba además la coherencia (periodo ISO, provisional/cerrado, ids, medios y países calculados, evidencias del artículo correcto y omisiones solo con texto completo).

### Configuración y despliegue

1. Crear el secreto `GROQ_API_KEY` en *Settings → Secrets and variables → Actions* (clave del plan gratuito de Groq). Sin él, el informe sale «sin IA».
2. Revisar en https://console.groq.com/settings/limits los límites reales de la cuenta y ajustar `ia.limites` y `ia.modelo` en `config.yaml` por debajo de ellos.
3. Settings → Actions → General → Workflow permissions: «Read and write» (para subir a la rama `archivo` y lanzar workflows). El entorno `github-pages` debe permitir desplegar desde `main`.
4. La rama `archivo` se crea sola en la primera recogida.
5. Generación manual: Actions → «Informe semanal» → Run workflow (semana, fecha de corte, sin IA, prueba, forzar).

### Recuperación ante fallos

- Recogida sin `datos.json` publicado: se reconstruye desde las capturas (`archivo.py restaurar`).
- Rama `archivo` inaccesible: Directo se publica igual y `semana/` se copia de lo publicado. Nunca se publica un sitio sin los informes que ya había.
- Informe que falla: se conserva el último válido y el error aparece aparte en la página (`ultimo_error` en `semana/index.json`).
- Escritura atómica (temporal → validar → sustituir) en datos, capturas, informes y sitio.

### Pendiente de Enrique

- RTVE: sus RSS oficiales responden, pero sus entradas son de 2022. Decidir un sustituto.
- RT: la conexión se rechaza desde la UE. Comprobar en la primera ejecución de Actions; si falla, queda «no evaluable».
- Global Times: sin RSS oficial al día; se usa CGTN. Confirmar.
- Euronews: `pais: FR` (Lyon); confirmar sede. Orientaciones: siguen vacías.
