# Talaia V1 · Fase 1 · Resultados (10-nov-2026)

Rama `v1-fase1`, creada desde `main` en `9226416`. Sin cambios en `recoger.yml`, cron-job.org ni Pages.
- `capturar_rss.py` + `.github/workflows/capturas.yml`: se lanza por `workflow_run` con cada ejecución de `recoger.yml` y con un `schedule` de respaldo; permisos `contents: read`; artefacto `captura-rss` con 7 días de retención. **No fusionado:** `workflow_run` y `schedule` solo funcionan desde `main`.
- `importar_capturas.py`: importador SQLite en `~/.talaia/talaia.db`. `test_capturas.py`: OK (`test_recoger.py`: OK).
- Decisión del disparador (cron-job.org y horario nativo de respaldo) registrada en `ARCHITECTURE.md` e `IMPLEMENTATION_PLAN.md`.

| Prueba | Resultado |
| --- | --- |
| Lotes reales en Actions sin el Mac (rama `prueba-capturas`) | P1 `42812026642`, P2 `42812254055`, P3 `42812897333`: ~22 s, ~1.690 artículos, 31/31 fuentes, ~169 KB gzip |
| Volumen a 7 días | ~169 KB × ~100 lotes/día × 7 ≈ 118 MB de artefactos |
| Recuperación tras reconectar | 3 lotes importados en 5 s; una segunda descarga no trae nada |
| Fuera de orden y repetidos | 6 órdenes y 1 secuencia con repeticiones sobre los lotes reales: estado idéntico (1.496 artículos en la ventana, de 1.700 únicos) |
| Ventana de 7 días | entradas de más de 7 días descartadas y purgadas por su propia hora (pruebas sintéticas) |
| Lagunas frente a falta de noticias | Sin lagunas entre P1 y P3 (RSS mínimo: ABC, 2,7 h). Pruebas sintéticas: RSS corto, fuente caída, intervalo sin lotes y sin capturas recientes |
| Lote inválido o con cuerpo | Lote real con `resumen` añadido: rechazado, 0 artículos importados |

Pendiente: fusionar `capturas.yml` en `main` (requiere autorización) para ejecutarlo en paralelo de forma continua. Ramas de prueba conservadas: `prueba-capturas`, `prueba-recoger-separar`, `archivo-prueba`, `liberar-pages` y `v1-prueba-candidatos`.
