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

## Después

Ver la sección «Recorridos actuales» al final de este archivo (se rellena con las pruebas de navegador).
