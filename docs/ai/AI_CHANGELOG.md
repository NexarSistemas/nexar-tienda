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

## 2026-05-17 — Codex — feature/filtro-proveedor-catalogo circuito completo

### Tarea
Cerrar el circuito completo de `proveedor_habitual` para alta, edición y filtrado del catálogo.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/producto_form.html`
- `templates/compras.html`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- `add_producto()` ahora guarda `proveedor_habitual` en la fila de `stock` cuando viene informado en el formulario.
- La ruta `/productos` ahora arma `proveedores_visibles` desde un listado sin aplicar el filtro actual de proveedor, evitando que el selector se achique mal.
- Crear producto desde catálogo ahora permite elegir proveedor habitual.
- Crear producto desde compra ahora hereda el proveedor seleccionado mediante `prefill_proveedor_id` y lo guarda en el producto si no se eligió otro manualmente.
- Editar producto mantiene disponible el selector de proveedor habitual usando el valor actual de `stock`.
- El catálogo sigue mostrando y filtrando por proveedor usando nombre visible y comparación case-insensitive.

### Qué se probó
- Validación estática del flujo entre catálogo, alta/edición de producto y creación desde compras.

### Pendiente de prueba manual
- Caso A: crear producto desde catálogo con proveedor y verificar visualización y filtro.
- Caso B: crear producto desde compra con proveedor preseleccionado y verificar herencia en catálogo.
- Caso C: probar variantes de mayúsculas/minúsculas del mismo proveedor en el filtro.

## 2026-05-17 — Codex — feature/aumento-precios-proveedor

### Tarea
Implementar Prioridad 3 del roadmap: aumento masivo de precios por proveedor y categoría con previsualización y confirmación.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/proveedores.html`
- `templates/proveedor_detalle.html`
- `templates/precios_proveedor.html`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se agregaron funciones de base de datos para obtener productos activos por `proveedor_habitual` y categoría opcional, y para aplicar aumentos porcentuales redondeados a 2 decimales sobre `costo` y `precio_venta`.
- Se agregaron rutas para abrir la herramienta, previsualizar productos afectados y confirmar el aumento recalculando siempre del lado servidor.
- Se agregó acceso discreto desde la lista de proveedores y desde el detalle del proveedor con nombre preseleccionado.
- La previsualización muestra costo/venta actual y nuevo antes de aplicar cambios.

### Qué se probó
- Validación sintáctica de Python.
- Revisión estática del flujo GET/POST, previsualización y confirmación.

### Pendiente de prueba manual
- Caso A: aumento por proveedor sin categoría.
- Caso B: aumento por proveedor + categoría.
- Caso C: proveedor sin productos.
- Caso D: porcentaje vacío, cero o negativo.

## 2026-05-17 — Codex — feature/aumento-precios-proveedor corrección acceso

### Tarea
Corregir el acceso a "% Actualizar Precios" para que abra la pantalla sin `Not Found`.

### Archivos modificados
- `app.py`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se agregaron aliases legacy para `precios_proveedor`, `precios_proveedor_previsualizar` y `precios_proveedor_aplicar`, siguiendo el patrón ya usado por el proyecto para endpoints de `main_bp` sin prefijo.
- Con esto, los enlaces y formularios existentes con `url_for('precios_proveedor')` vuelven a resolver contra `/precios/proveedor`.

### Qué se probó
- Verificación del `url_map` para confirmar que `/precios/proveedor` queda accesible tanto por `main.precios_proveedor` como por `precios_proveedor`.

### Pendiente de prueba manual
- Hacer click en "% Actualizar Precios" desde listado de proveedores.
- Hacer click en "Actualizar precios" desde detalle de proveedor.
- Confirmar que la pantalla abre correctamente sin aplicar cambios todavía.

## 2026-05-17 — Codex — feature/aumento-precios-proveedor mejora confirmación

### Tarea
Reemplazar la confirmación nativa del navegador por un modal SweetAlert2 en la aplicación de aumentos masivos.

### Archivos modificados
- `templates/precios_proveedor.html`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se eliminó el `confirm()` nativo del botón "Confirmar aumento".
- Se agregó un formulario identificado con `data-*` para porcentaje, proveedor, categoría y cantidad afectada.
- Se incorporó confirmación visual con SweetAlert2, manteniendo la lógica actual de aplicación por POST.
- El texto del modal ahora corrige el plural entre `1 producto` y `N productos`.

### Qué se probó
- Revisión estática del flujo de previsualización y confirmación en el template.

### Pendiente de prueba manual
- Confirmar que al presionar "Confirmar aumento" aparece el modal SweetAlert2.
- Verificar que "Cancelar" no aplique cambios.
- Verificar que "Sí, aplicar aumento" ejecute el POST correctamente.
