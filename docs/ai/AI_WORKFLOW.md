# AI_WORKFLOW.md

Todas las IA deben leer primero:

1. AGENTS.md
2. docs/ai/AI_CONTEXT.md
3. docs/ai/ROADMAP_NEXAR_COMERCIO.md
4. docs/ai/AI_CHANGELOG.md

## Flujo

1. Verificar rama actual.
2. Si está en main, crear rama propia.
3. Identificar tarea.
4. Revisar roadmap.
5. Buscar archivos afectados.
6. Entender flujo actual.
7. Proponer cambio mínimo.
8. Implementar.
9. Probar lo posible.
10. Actualizar AI_CHANGELOG.md.
11. Actualizar ROADMAP si cambia estado.

## Bajo consumo de tokens

- No reescribir archivos completos si no hace falta.
- No hacer refactors masivos.
- No tocar áreas sensibles fuera de la tarea.
- Preferir parches pequeños.
- No modificar builds/versionado salvo pedido explícito.
