# AI_CHANGELOG.md

Registro de avances hechos por Codex, Copilot, Gemini o ChatGPT.

## 2026-05-17 — ChatGPT — documentación inicial

### Tarea
Definir documentación viva para IA y roadmap de mejoras de Nexar Comercio.

### Hallazgos
- Producto visible: Nexar Comercio.
- Repo técnico: nexar-tienda.
- Regla agregada: nunca trabajar directo sobre main.
- Cada mejora debe ir en rama propia.
- Hay fricción al crear producto desde compra porque exige descripción previa.
- Ya existe flujo return_to=compra_nueva.
- Catálogo tiene búsqueda y filtro por categoría.
- Falta filtro por proveedor.
- Categorías deben volverse configurables.
- Reportes deben estar habilitados en demo.

### Pendiente inmediato recomendado
Implementar prioridad 1:
flujo ágil de compra con producto nuevo sin exigir descripción previa.

## 2026-05-17 — ChatGPT — feature/flujo-compra-producto-nuevo

### Tarea
Implementar Prioridad 1 del roadmap: permitir crear producto desde una compra sin exigir descripción previa.

### Archivos modificados
- `templates/compras.html`

### Qué se cambió
- Se eliminó el bloqueo JavaScript que impedía abrir “Crear producto” si `producto_descripcion` estaba vacío.
- Se mantuvo el flujo existente `return_to=compra_nueva`.
- Se conservó el borrador de compra al avanzar hacia la creación del producto.
- No se modificó la creación de proveedor desde compra.

### Qué se probó
- Revisión estática del flujo en template.
- Verificación de que `buildProductoUrl()` sigue enviando los parámetros del borrador.

### Pendiente
- Probar manualmente en la app:
  1. abrir Nueva Compra
  2. presionar Crear producto sin descripción
  3. crear producto
  4. verificar regreso a compra con producto seleccionado
- Luego de validar y mergear esta rama, continuar con Prioridad 2: filtro por proveedor en catálogo.
