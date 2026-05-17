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

## 2026-05-17 — Codex — feature/filtro-proveedor-catalogo

### Tarea
Implementar Prioridad 2 del roadmap: filtro por proveedor en catálogo, combinable con búsqueda textual y categoría.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/productos.html`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- `get_productos()` ahora hace `LEFT JOIN` con `stock` para exponer `proveedor_habitual` sin cambiar la estructura de la base.
- Se agregó soporte opcional para filtrar por proveedor en `get_productos()`, manteniendo compatibilidad con llamadas existentes.
- La ruta `/productos` ahora lee `proveedor`, arma la lista de proveedores visibles y la envía al template junto al filtro seleccionado.
- El catálogo ahora muestra un selector "Todos los proveedores", incluye `proveedor_habitual` en la búsqueda textual y lo muestra de forma discreta debajo de la descripción.
- El JavaScript del catálogo ahora combina búsqueda + categoría + proveedor sobre la misma tabla.

### Qué se probó
- Verificación estática del flujo en `database.py`, `routes/main.py` y `templates/productos.html`.
- Validación sintáctica de Python con `python3 -m py_compile database.py routes/main.py`.

### Pendiente de prueba manual
- Abrir `/productos` y verificar carga sin errores.
- Probar filtro solo por categoría.
- Probar filtro solo por proveedor.
- Probar combinación de búsqueda + categoría + proveedor.
- Verificar que productos sin `proveedor_habitual` sigan visibles cuando el filtro está en "Todos los proveedores".

## 2026-05-17 — Codex — feature/filtro-proveedor-catalogo corrección

### Tarea
Corregir el filtro por proveedor del catálogo para comparar por nombre visible y sin distinguir mayúsculas/minúsculas.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/productos.html`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se normalizó el filtro opcional `proveedor` en `get_productos()` usando `LOWER(...)` para evitar comparaciones sensibles a mayúsculas/minúsculas.
- La ruta `/productos` ahora deduplica proveedores visibles por `lower()` pero conserva el nombre original para mostrarlo en el selector.
- El template guarda categoría y proveedor normalizados en `data-*` y mantiene el `option value` con el nombre visible del proveedor.
- El JavaScript ahora normaliza búsqueda, categoría y proveedor antes de comparar.

### Qué se probó
- Revisión estática del flujo entre SQL, ruta, template y filtro JavaScript.

### Pendiente de prueba manual
- Verificar que un mismo proveedor escrito con distintas mayúsculas no se duplique en el selector.
- Probar filtro por proveedor, categoría y búsqueda en combinación.
- Confirmar que productos sin proveedor solo se oculten al elegir un proveedor específico.
