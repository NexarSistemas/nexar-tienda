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

## 2026-05-17 — Codex — feature/categorias-configurables

### Tarea
Implementar Prioridad 4 del roadmap: categorías configurables para productos, manteniendo compatibilidad con categorías base y productos existentes.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/config.html`
- `app.py`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se agregaron funciones para listar categorías personalizadas, categorías usadas, categorías configurables y su estado consolidado por rubro actual.
- La gestión de categorías ahora permite crear, renombrar y activar/desactivar sin borrado destructivo, con validación case-insensitive y actualización de `productos.categoria` al renombrar.
- Las categorías base hardcodeadas siguen existiendo, pero ahora pueden ocultarse mediante registros de tabla inactivos sin romper compatibilidad.
- La pantalla de Configuración ahora muestra estado, origen y cantidad de productos por categoría, con acciones de agregar, renombrar y activar/desactivar.
- Los formularios siguen usando la lista unificada de categorías visibles, manteniendo la categoría actual incluso si quedó inactiva en edición.
- Se agregaron aliases legacy para los nuevos endpoints de categorías en `app.py`.

### Qué se probó
- Validación sintáctica de Python.
- Revisión estática del flujo de configuración y de los selects de categoría en alta/edición de productos.

### Pendientes
- Caso A: crear una categoría nueva y usarla en un producto.
- Caso B: renombrar una categoría y verificar actualización en productos existentes.
- Caso C: desactivar una categoría y confirmar que no aparezca en productos nuevos pero sí siga visible en edición si ya está asignada.
- Caso D: intentar crear una categoría duplicada con distinta capitalización.
- Caso E: verificar que categorías de gastos y reportes sigan funcionando igual.

## 2026-05-17 — Codex — feature/carga-lotes-productos

### Tarea
Implementar Prioridad 5A del roadmap: carga por lotes de productos únicos reutilizando la lógica existente de alta.

### Archivos modificados
- `routes/main.py`
- `templates/productos.html`
- `templates/productos_lote.html`
- `app.py`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se agregó una pantalla de "Carga por lote" accesible desde Catálogo.
- La carga por lote permite definir datos comunes del producto y varias filas individuales con descripción, costo, precio, stock y código de barras.
- El guardado valida todas las filas antes de crear productos y usa `db.add_producto(data)` para cada fila válida, evitando duplicar lógica.
- Se ignoran filas completamente vacías y se evita guardado parcial cuando una fila cargada tiene errores.
- Se respetan categorías configurables, proveedor habitual y unidades disponibles del rubro actual.
- Se agregó alias legacy para el nuevo endpoint en `app.py`.

### Qué se probó
- Validación sintáctica de Python.
- Revisión estática del flujo de validación, creación en lote y retorno al catálogo.

### Pendiente
- Caso A: crear varios productos desde lote y verificar proveedor/categoría en catálogo.
- Caso B: dejar filas vacías y confirmar que solo se cree la fila válida.
- Caso C: provocar error en una fila y verificar que no haya guardado parcial.
- Caso D: usar una categoría configurable nueva y validar que aparezca correctamente.

## 2026-05-17 — Codex — feature/importacion-productos-plantilla

### Tarea
Implementar Prioridad 6 del roadmap: importación de productos mediante plantilla CSV descargable.

### Archivos modificados
- `routes/main.py`
- `templates/productos.html`
- `templates/productos_importar.html`
- `app.py`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se agregó una pantalla de importación CSV accesible desde Catálogo con instrucciones, columnas esperadas y carga de archivo.
- Se agregó descarga de plantilla CSV usando `csv` de la librería estándar y `Response`.
- La importación valida encabezados, tolera BOM con `utf-8-sig`, ignora filas completamente vacías y acumula errores por fila sin guardar parcialmente.
- Si no hay errores, se crean los productos usando `db.add_producto(data)` respetando proveedor habitual, categorías configurables y valores por defecto del rubro actual.
- Se agregaron aliases legacy para los nuevos endpoints en `app.py`.

### Qué se probó
- Validación sintáctica de Python.
- Revisión estática del flujo de descarga de plantilla, validación e importación completa sin guardado parcial.

### Pendiente
- Caso A: importar 2 productos válidos y verificarlos en catálogo.
- Caso B: importar CSV sin `descripcion` y verificar error.
- Caso C: importar mezcla de fila válida e inválida y confirmar que no se importe ninguna.
- Caso D: importar con categoría vacía y confirmar categoría por defecto.
- Caso E: importar con `proveedor_habitual` y validar visualización/filtro.

## 2026-05-17 — Codex — feature/importacion-productos-plantilla corrección plantilla nativa

### Tarea
Corregir la UX de descarga de plantilla CSV en ventana nativa pywebview para que el usuario sepa dónde se generó el archivo.

### Archivos modificados
- `routes/main.py`
- `templates/productos_importar.html`
- `app.py`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- El flujo principal ahora genera la plantilla CSV en una carpeta conocida: `exports/plantillas/plantilla_productos_nexar.csv`.
- La app muestra un `flash` con la ruta exacta del archivo generado.
- Se agregó un botón opcional para abrir la carpeta de plantillas reutilizando el patrón existente del proyecto.
- La pantalla de importación ahora explica por qué en ventana nativa se usa generación local en vez de depender solo de la descarga del navegador embebido.

### Qué se probó
- Validación sintáctica de Python.
- Revisión estática del flujo de generación de plantilla, apertura de carpeta y mantenimiento de la importación existente.

### Pendiente
- Generar la plantilla desde la ventana nativa y verificar que el archivo exista en la ruta informada.
- Abrir el archivo con Excel o LibreOffice.
- Confirmar que la importación CSV sigue funcionando sin cambios.

## 2026-05-17 — Codex — feature/importacion-productos-plantilla mejora destino

### Tarea
Mejorar la generación de la plantilla CSV para permitir guardarla en Descargas además de la carpeta de la aplicación.

### Archivos modificados
- `routes/main.py`
- `templates/productos_importar.html`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se agregó selector de destino para generar la plantilla en la carpeta de la aplicación o en `Downloads`.
- Si `Downloads` no existe, la app usa la carpeta personal del usuario y, como último fallback, la carpeta de la aplicación.
- La generación sigue mostrando la ruta final exacta mediante `flash`.
- Se mantuvo intacta la importación CSV actual.

### Qué se probó
- Validación sintáctica de Python.
- Revisión estática del flujo de selección de destino, fallback y mensaje final al usuario.

### Pendiente
- Generar la plantilla en carpeta de la app y verificar ruta.
- Generar la plantilla en Descargas y verificar ruta.
- Confirmar fallback correcto cuando `Downloads` no exista.

## 2026-05-17 — Codex — feature/importacion-productos-plantilla mejora detección descargas

### Tarea
Mejorar la detección de la carpeta Descargas/Downloads para generar la plantilla CSV.

### Archivos modificados
- `routes/main.py`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- La resolución de carpeta de descargas ahora revisa `XDG_DOWNLOAD_DIR` si existe.
- También prueba `~/Downloads`, `~/Descargas` y `~/descargas`.
- Si no encuentra ninguna carpeta válida, usa `Path.home()` y mantiene la carpeta de la app como fallback final.

### Qué se probó
- Validación sintáctica de Python.
- Revisión estática del flujo de selección de destino y fallbacks.

### Pendiente
- Verificar generación en Linux con carpeta `Descargas`.
- Verificar generación en entornos con `XDG_DOWNLOAD_DIR`.
