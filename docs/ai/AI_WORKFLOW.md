# AI_WORKFLOW.md

Todas las IA deben leer primero:

1. docs/ai/AI_CONTEXT.md
2. docs/ai/ROADMAP_NEXAR_COMERCIO.md
3. docs/ai/AI_CHANGELOG.md

## Flujo

1. Identificar tarea.
2. Revisar roadmap.
3. Buscar archivos afectados.
4. Entender flujo actual.
5. Proponer cambio mínimo.
6. Implementar.
7. Probar lo posible.
8. Actualizar AI_CHANGELOG.md.
9. Actualizar ROADMAP si cambia estado.

## Bajo consumo de tokens

- No reescribir archivos completos si no hace falta.
- No hacer refactors masivos.
- No tocar áreas sensibles fuera de la tarea.
- Preferir parches pequeños.
- No modificar builds/versionado salvo pedido explícito.

## Formato de AI_CHANGELOG

## YYYY-MM-DD — IA usada

### Tarea
Descripción corta.

### Archivos modificados
- archivo

### Qué se cambió
- cambio

### Qué se probó
- prueba

### Pendiente
- pendiente
