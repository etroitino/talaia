# Recorridos de Talaia

Estado observado antes de esta evolución (rama `main`, commit `e52a4fe`), con la copia publicada de
`datos.json` del 25/10/2026 07:45 UTC, en Chromium sin interfaz a 390 × 844 y 1440 × 900, servida con
`python3 -m http.server`. Las cifras son de esa muestra, no objetivos.

## Antes

| Recorrido | Qué hace | Resultado observado |
| --- | --- | --- |
| Zonas (escritorio) | Cinco columnas Girona–Mundo, cada una con su scroll | Correcto. Sin scroll horizontal global. |
| Zonas (móvil) | Pestañas `button role=tab` sin `tabpanel`, sin flechas | Cambia de zona, pero la zona no está en la URL: al recargar la página vuelve a Girona. Sin `aria-controls` ni teclado de pestañas. |
| Desplegar grupo | `details.grupo` con «N medios» | Se abre. Tras la recarga automática sigue abierto. El resumen mide 18 px de alto: blanco táctil pequeño. |
| Alternativas premium | «Léelo también en:» bajo la noticia premium | 16 noticias con alternativa en la muestra. No hay forma de ocultar el premium. |
| Recarga (móvil) | `cargar()` cada 5 min reconstruye todo el DOM | **El scroll de `main` (el contenedor real en móvil) salta de 1500 a 0.** |
| Recarga (escritorio) | Intenta restaurar `scrollTop` de cada `ol` | **La columna vuelve a 0** (800 → 0). El foco se pierde (pasa a `BODY`). |
| Franja «ÚLTIMA HORA» | Todo lo de la última hora, hasta 15 | En móvil se lee solo «ÚLTIMA». Puede repetir el mismo hecho. |
| Enlaces externos | `target=_blank rel="noopener noreferrer"` | Correcto. |
| Datos | `datos.json` de 7 días con `?t=` en cada recarga | 3 431 770 bytes (879 178 en gzip) en cada recarga, aunque no cambie nada. La página solo usa 24 h. |
| Estado en móvil | Número de titulares y antigüedad | Ocultos por debajo de 1100 px; solo queda el reloj decorativo. |
| Metadatos | Hora y medio | 11,2 px. |
| DOM inicial | Todas las noticias de 24 h | 7 459 nodos, 1 211 `li`. |
| Ráfagas | Orden cronológico estricto | Hasta 62 seguidas de La Vanguardia y 52 de El País con la misma hora. |

Consola sin errores en ambos anchos.

## Después (rama `semana-y-directo`)

Comprobado con `uv run test_navegador.py` (datos sintéticos, 375/390/768/1440 px) y con la misma
muestra publicada del 25/10 07:45 UTC para las medidas.

| Recorrido | Resultado |
| --- | --- |
| Zonas (escritorio) | Vista general con las cinco columnas; «General», zonas, Miradas y Verificadores como enlaces con `aria-current`. `#/directo/espana` resalta la columna. |
| Zonas (móvil) | Barra desplazable con nombres completos y conteo; solo se pinta la zona visible. Recargar mantiene `#/directo/espana`; Atrás/Adelante funcionan. |
| Miradas / Verificadores | Vista propia de ancho completo con nota explicativa; Miradas no aparece en Mundo. |
| Desplegar grupo | «N medios» de 44 px en móvil; abierto tras la recarga; con «Comparar enfoques» solo si un artículo exacto está en un informe. |
| Premium | «Ocultar premium» quita los premium y, si el grupo tiene alternativa abierta, la muestra como representante. |
| Recarga | Solo se pide `version.json` (100 B); si cambia, `ultimas24h.json?v=…`. Si se lee abajo, aviso «N noticias nuevas · ver» sin mover nada; se incorporan al volver arriba o al pulsar. Recarga manual: misma entrada visible a la misma altura (±2 px), en `main`/columna o documento. |
| Foco | Se conserva en el mismo elemento lógico tras recargar; los cambios de ruta llevan el foco al título y se anuncian en `aria-live`. |
| Filtros | Búsqueda sin acentos, medios, ocultar premium, orden Recientes / Más contrastadas / Diversidad, «Cargar más»; conteos sobre el total filtrado; «Limpiar». |
| Más cubiertas | Hasta 5 grupos sin repetir, ordenados por medios distintos; plegada en móvil. |
| Semana | Portada con intervalo, estado, corte, cobertura, advertencias arriba, matriz con scroll propio, sucesos, silencios y notas. Detalle con filtro por medio y comparación de dos, guardados en la URL; «Volver» recupera la posición. |
| Fuentes | Estado por fuente (incluido «responde pero sin entradas recientes»), titulares excluidos y borrado del historial local. |
| Enlaces externos | `target=_blank rel="noopener noreferrer"` y solo http(s). |
| Accesibilidad | «Saltar al contenido», axe-core sin violaciones en 10 vistas (390/1440), metadatos ≥12 px y titulares 16 px en móvil, `prefers-reduced-motion`. Falta probar con un lector de pantalla real. |
| Errores | Consola sin errores ni peticiones fallidas; sin `version.json`, aviso legible y la copia anterior sigue a la vista. |

### Medidas con la misma muestra (datos.json publicado el 25/10/2026 07:45 UTC)

| | Antes | Después |
| --- | --- | --- |
| Descarga en cada recarga sin cambios | 3 431 770 B (879 178 gzip) | 100 B (`version.json`) |
| Descarga cuando hay cambios | 3 431 770 B | 271 710 B (79 449 gzip) |
| DOM inicial 1440 px | 7 459 nodos | 3 894 nodos |
| DOM inicial 390 px | 7 459 nodos | 1 230 nodos |
| Scroll móvil tras recargar | 1500 → 0 | se conserva |
| Scroll de columna tras recargar | 800 → 0 | se conserva |

Caché real de Pages: `Cache-Control: max-age=600` con ETag/Last-Modified. `no-store` solo afecta al navegador, no al CDN: por eso `version.json` lleva `?t=` y `ultimas24h.json` va versionado en la URL.
