# Talaia — Plan de implementación de V1

**Estado:** listo para iniciar la fase 0 · 10 de noviembre de 2026  
**Referencias:** [REQUIREMENTS.md](REQUIREMENTS.md) y [ARCHITECTURE.md](ARCHITECTURE.md)  
**Repositorio:** [etroitino/talaia](https://github.com/etroitino/talaia)

El objetivo es llegar a una edición diaria validada de extremo a extremo sin interrumpir la Talaia actual. Cada fase tiene una salida comprobable. Si una prueba temprana invalida una decisión técnica, se corrige esa parte del diseño antes de construir sobre ella. El alcance de V1 está cerrado.

| Fase | Entrega comprobable | Depende de |
| --- | --- | --- |
| 0 | Línea base y pruebas de viabilidad del Mac, las capturas y el despliegue | — |
| 1 | Recogida RSS independiente e importación recuperable | 0 |
| 2 | Edición editorial reproducible en el Mac | 1 |
| 3 | Web estática utilizable con datos validados | Contrato de 2 |
| 4 | Entrega, publicación y recuperación ensayadas de extremo a extremo | 1, 2, 3 |
| 5 | Validación paralela y decisión de lanzamiento | 4 |
| 6 | Sustitución del sitio y comprobación de la reversión | 5 y autorización de despliegue |

## Fase 0 · Línea base y pruebas de viabilidad

**Entrega.** Un registro de resultados que permita decidir si el diseño es viable y qué parámetros habrá que fijar. Trabajar en una rama aislada a partir de una revisión identificada de `main`. Registrar la revisión publicada y los datos que necesita la versión actual para volver a montarse.

| Prueba | Qué medir o comprobar | Decisión que habilita |
| --- | --- | --- |
| Mac e IA | Ejecutar una selección y varios análisis sobre una muestra real común. Medir tiempo total y por tarea, memoria, precisión, diversidad, contraste y trazabilidad. Incluir fuente única, reproducciones de un teletipo y cifras de momentos distintos. | Elegir modelo local y presupuesto de tiempo, memoria y concurrencia. Comparar con un modelo externo solo si el proveedor y el envío de esa muestra están autorizados. La ausencia de respaldo externo no frena el prototipo local. |
| Capturas | Probar un lote comprimido, su descarga autorizada desde el Mac y su importación. Medir tamaño y cobertura y estimar volumen con siete días de retención. Verificar los permisos y la configuración de caducidad del repositorio. | Elegir cadencia de recogida. Comprobar que la importación tolera un intervalo sin captura y que la caducidad de archivos y la ventana por entrada se distinguen. |
| Despertar y reanudar | Probar el disparador del Mac en sesión activa, suspensión e inicio de sesión. Simular cambio de zona y una ventana editorial perdida. | Fijar la frecuencia de comprobación de `launchd` y confirmar cómo se recupera la edición de hoy. |
| Entrega y recuperación | Con datos sintéticos y fuera de la publicación pública, probar el envío de un candidato, la validación por Actions, la construcción del artefacto y la reconciliación simulada tras un corte entre despliegue y confirmación. Probar el despliegue real solo en un destino de prueba expresamente habilitado o durante el corte autorizado. | Verificar permisos, trazabilidad del identificador de revisión y capacidad de repetir una entrega. Identificar qué parte queda pendiente de demostrar en Pages. |

**Piezas y pruebas.** Ejecutar desde la revisión base las pruebas existentes de recogida, agrupación, archivo, informe semanal y navegador, según sus dependencias. Registrar fallos previos y separar muestras sintéticas de las reales. Puntos de partida: `test_recoger.py`, `test_agrupar.py`, `test_archivo.py`, `test_semana.py` y `test_navegador.py`. Un ensayo con credenciales o automatizaciones nuevas depende de que estén disponibles y autorizadas.

**Salida.** Quedan registradas las medidas, las decisiones de configuración y cualquier bloqueo. La ruta local puede producir una muestra útil a tiempo o se ajusta antes de pasar a la fase 2. El sitio público y sus disparadores siguen operativos. **Requisitos:** RNF-V1-02, RNF-V1-03, RNF-V1-08, RNF-V1-09, RNF-V1-10.

## Fase 1 · Recogida RSS independiente

**Entrega.** Un workflow de recogida separado produce un artefacto con manifiesto, corte, metadatos mínimos y estado por fuente. El importador del Mac valida lotes, aplica la ventana lógica de siete días, deduplica y registra lagunas. Definir el contrato de captura con su versión de esquema e identificador de artículo.

**Piezas.** Reutilizar normalización, identificadores y reglas de `recoger.py` y `fuentes.yaml`, y las utilidades de fechas de `archivo.py`. Mantener el workflow público existente durante la validación. El nuevo recolector carece de permisos de despliegue. **Disparador:** se mantiene cron-job.org y el horario nativo de GitHub queda como respaldo, por los huecos observados en la fase 0 (4,3 ejecuciones al día en vez de 96; huecos de hasta 10,5 h). Durante la validación, la recogida de V1 se lanza con cada ejecución de `recoger.yml` (`workflow_run`), sin cambiar el disparador actual.

**Pruebas y salida.** Con el Mac desconectado, GitHub sigue produciendo capturas. Probar fuentes caídas, lotes repetidos y fuera de orden, entradas caducadas, intervalos ausentes y recuperación tras reconectar. El importador no duplica entradas ni confunde una laguna con falta de noticias. Los cuerpos de artículos quedan fuera de los lotes. **Requisitos:** RF-V1-03, RNF-V1-01, RNF-V1-04, RNF-V1-05, RNF-V1-06.

## Fase 2 · Producción editorial en el Mac

Dividir esta fase en dos entregas revisables, ambas ejecutables con las mismas capturas de prueba.

| Entrega | Trabajo y piezas | Comprobación |
| --- | --- | --- |
| 2A · Edición mínima validada | Guardar estado de trabajo en SQLite. Adaptar `agrupar.py` para proponer relaciones sin cambiar IDs ya publicados. Aplicar preselección, impacto, diversidad y una única configuración editorial. Preparar con IA local una edición de 5–7 acontecimientos con justificaciones, detalle y evidencias. Reutilizar controles pertinentes de `extraer.py`, `evidencias.py` e `ia.py`. | Con la misma entrada, el proceso reconoce el trabajo ya validado. Distingue cobertura duplicada, noticia de fuente única, acceso de pago, afirmación no corroborada y cambios de fecha. Ante un análisis fallido baja a parcial o a titulares con enlaces según la evidencia. |
| 2B · Continuidad | Añadir las ventanas de 07:00, 13:00 y 19:00 en `Europe/Madrid`, el bloqueo local y la recuperación al iniciar sesión o reanudar. Generar novedades, rectificaciones vinculadas, historias activas y enriquecimiento selectivo de Explorar. Exportar un lote incremental con versión de esquema, revisión base, corte, IDs y huellas. | Repetir una ejecución no duplica una edición ni una corrección. Las revisiones no cambian el texto, orden o selección del día. Tras una ausencia de varios días solo se prepara la edición vigente. Con carga alta, las tareas principales tienen prioridad y Explorar utiliza capacidad sobrante. |

**Salida.** Una muestra real genera un lote validado y legible para un publicador que desconozca el SQLite local. Los candidatos inválidos quedan fuera de la entrega. Los límites medidos, los estados y la degradación quedan reproducibles. El respaldo externo permanece desactivado hasta su autorización y prueba. **Requisitos:** RF-V1-01 a RF-V1-04, RF-V1-06 a RF-V1-10, RF-V1-12 a RF-V1-14, RNF-V1-02, RNF-V1-03, RNF-V1-04, RNF-V1-07, RNF-V1-08.

## Fase 3 · Web estática de V1

**Entrega.** Una vista previa local del sitio completo. Conservar las piezas útiles del HTML, CSS y JavaScript existentes y adaptar `montar_sitio.py` para construir una única revisión estática a partir del contrato editorial. Empezar con datos de prueba válidos y sustituirlos por lotes reales cuando estén disponibles.

1. **Hoy y detalle.** Portada breve, evidencias desplegables y rectificaciones junto al original. Mostrar la fecha de la edición y avisar si falta la de hoy.
2. **Novedades e historias.** Mostrar hasta tres novedades pendientes. Marcar consultado al abrir el contenido y conservar el estado solo en ese navegador. Enlazar historias, cambios relevantes y publicaciones anteriores.
3. **Explorar, archivo y diagnóstico.** Filtrar por tema y territorio. Buscar por palabras en los titulares y resúmenes del archivo de 90 días. Identificar días sin edición. Distinguir estado de RSS, IA y publicación con fechas y motivos sanitizados.

**Pruebas y salida.** Ampliar `test_navegador.py` para cubrir recorridos en móvil y escritorio, teclado, cuatro novedades, una rectificación visible con el bloque lleno, dos navegadores, archivo y búsqueda, cambio de día en Madrid y cambio de revisión durante una carga. Si falta una captura, Explorar indica cobertura parcial y excluye entradas caducadas. La vista previa se monta con un lote real sin servidor de aplicación. **Requisitos:** RF-V1-05, RF-V1-08 a RF-V1-16, RNF-V1-05, RNF-V1-06.

## Fase 4 · Entrega, publicación y recuperación

**Entrega.** El Mac conserva el lote hasta recibir confirmación, lo entrega a la rama de candidatos y activa el workflow autorizado. El publicador lee candidatos pendientes, valida la revisión base, prepara el respaldo y el sitio completo y registra el resultado por identificador. Los ensayos usan un destino aislado o generan un artefacto de vista previa sin activar producción.

| Caso de prueba | Resultado exigido |
| --- | --- |
| Candidato duplicado, corrupto u obsoleto | El duplicado es idempotente. Los demás no publican ni pisan la revisión vigente. El Mac puede recomponer un candidato obsoleto. |
| Activaciones simultáneas o aviso perdido | Un único despliegue en curso. El publicador encuentra el candidato pendiente por lectura de la rama, incluso si se perdió el aviso. |
| Fallo antes del despliegue | La revisión anterior sigue como base y continúa disponible. El candidato válido puede reintentarse. |
| Fallo después de desplegar y antes de confirmar | La reconciliación contrasta el resultado de Actions con el identificador público y el respaldo preparado. Mientras el estado sea incierto, se bloquean nuevos avances. |
| Pérdida del Mac original | Otro equipo restaura ediciones, relaciones, rectificaciones y evidencias desde el respaldo confirmado. Importa únicamente las capturas RSS que aún existen. |
| Limpieza y datos públicos | Se retiran datos caducados de la vista activa. El respaldo conserva evidencia mínima y relaciones necesarias. Ramas, artefactos, logs y Pages quedan libres de credenciales, datos de lectura y textos completos. |

**Salida.** El artefacto completo se genera desde el mismo flujo que se desplegará. Se demuestra restauración en otro equipo o entorno limpio y queda registrada cualquier prueba de Pages que requiera un destino habilitado. La prueba de reversión reconstruye un artefacto desde código y datos identificados. **Requisitos:** RF-V1-16, RNF-V1-01, RNF-V1-04 a RNF-V1-06, RNF-V1-09, RNF-V1-10.

## Fase 5 · Validación paralela

Ejecutar la V1 en paralelo con la versión pública, sin cambiar la URL pública. Usar muestras reales comunes y revisar las ediciones en la vista previa. Como punto de partida operativo, propongo **una semana de observación con al menos cinco ediciones reales revisadas**. Es una duración de validación, no una condición de producto añadida. Si faltan casos relevantes, ampliar la muestra o cubrirlos con una prueba controlada.

| Comprobación | Evidencia de salida |
| --- | --- |
| Cadencia y disponibilidad | Hora de inicio, validación y disponibilidad de cada edición. Registrar retrasos y comprobar las dos revisiones de novedades y la recuperación del día actual. |
| Calidad editorial | Revisión de relevancia, diversidad, omisiones, claridad y utilidad del contraste. Cada afirmación importante tiene evidencia comprobable. Los errores graves de atribución, invenciones y contradicciones no detectadas bloquean el corte hasta corregirse o controlarse. |
| Experiencia de lectura | Revisar portada en unos cinco minutos y una sesión con detalle de unos 15–20. Probar móvil y escritorio, archivo, seguimiento, rectificaciones y navegación con teclado. |
| Operación y recuperación | Resultados de fallos simulados de RSS, IA y publicación. Prueba de restauración del estado esencial y reconstrucción del artefacto anterior. Verificar qué diagnóstico queda visible si Pages no pudo actualizarse. |

**Salida.** Una tabla de resultados marca cada criterio como superado, pendiente o bloqueado, con enlace a su evidencia. Las diferencias editoriales razonables se documentan. Un fallo bloqueante regresa a la fase responsable y obliga a repetir las pruebas afectadas. Las capacidades aplazadas no intervienen en la decisión. **Requisitos:** RF-V1-05, RNF-V1-07, RNF-V1-08, RNF-V1-09, RNF-V1-10.

## Fase 6 · Sustitución y reversión

La ejecución del corte requiere autorización para modificar el despliegue público. Preparar antes un artefacto de V1 con su respaldo preparado y un artefacto reproducible de la versión anterior con código y datos. Registrar el estado y los disparadores de los workflows actuales, incluido el disparador externo documentado.

1. Confirmar que la revisión candidata coincide con la que superó la validación. Identificar la revisión anterior y el procedimiento de restauración. Si el despliegue real solo se puede probar en Pages de producción, registrar ese punto pendiente como comprobación del corte y preparar la reversión inmediata.
2. Desactivar o aislar la capacidad de despliegue del flujo anterior y comprobar que no queda una ejecución antigua en curso o pendiente. El disparador externo no debe poder sobrescribir Pages después del corte: cron-job.org pasa a lanzar directamente la recogida de V1, con autorización para cambiar su destino, y el horario nativo sigue como respaldo. Mantener disponibles los datos y la configuración necesarios para volver atrás.
3. Publicar por el workflow autorizado. Comprobar en la URL pública el identificador de revisión, la fecha real, la portada, un detalle con evidencias, el archivo y el diagnóstico. Confirmar que la recogida posterior no sobrescribe el sitio.
4. Si la publicación no se reconcilia, se pierde contenido o aparece un fallo grave de trazabilidad o lectura, detener nuevas promociones y restaurar la revisión anterior por un único canal de publicación. Verificar la revisión restaurada en Pages antes de reactivar cualquier disparador de la versión anterior.

**Salida.** La V1 sirve la revisión prevista, queda registrado el resultado de la comprobación pública y el procedimiento de reversión sigue disponible. **Requisitos:** RNF-V1-01, RNF-V1-04, RNF-V1-05, RNF-V1-09, RNF-V1-10.

## Pautas para ejecutar el plan

- Abrir una entrega revisable por fase o subfase, con una revisión de partida, archivos afectados, requisitos cubiertos y pruebas ejecutadas. Mantener los cambios de producción separados de las pruebas.
- Los nombres de los archivos nuevos son decisiones de implementación. Reutilizar funciones y pruebas existentes antes de duplicarlas. Conservar las interfaces que la versión activa todavía usa mientras dure la validación paralela.
- Registrar los límites de IA, tiempos de reintento, frecuencia de recogida y tamaños de muestra a partir de las medidas de fase 0. Si una medida obliga a cambiar un contrato o una decisión de arquitectura, documentar la evidencia y ajustar el plan. Una ampliación funcional requiere aprobación expresa.
- El resumen semanal, «Distintas miradas», las cronologías avanzadas, la PWA sin conexión y las sugerencias automáticas de fuentes quedan fuera de las tareas de V1.
