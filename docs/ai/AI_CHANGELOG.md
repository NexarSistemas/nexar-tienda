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

## 2026-05-17 — Codex — feature/codigos-barras-internos

### Tarea
Implementar generación opcional de códigos de barras internos para productos nuevos, edición, carga por lote e importación CSV.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/producto_form.html`
- `templates/productos_lote.html`
- `templates/productos_importar.html`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se agregó un correlativo interno `NXR00000001` basado en `config.siguiente_codigo_barras_interno`, con verificación de unicidad contra `productos.codigo_barras`.
- `db.add_producto()` y `db.update_producto()` ahora generan el código interno solo cuando el usuario lo pide y el campo está vacío.
- También se agregó validación centralizada para impedir códigos de barras manuales duplicados.
- En alta y edición de producto se sumó el checkbox para generar código interno cuando no hay código de fábrica.
- La carga por lote ahora permite generar códigos internos para filas sin código y valida duplicados manuales antes de crear productos.
- La importación CSV agregó la misma opción y valida duplicados manuales por fila antes de importar, evitando guardados parciales.

### Qué se probó
- Validación sintáctica de Python.
- Revisión estática del flujo de creación, edición, lote e importación con códigos manuales y autogenerados.

### Pendiente
- Crear producto nuevo sin código y confirmar generación `NXR...`.
- Editar producto sin código y confirmar generación.
- Probar carga por lote con varios productos sin código.
- Probar importación CSV con generación interna activada.
- Verificar rechazo de códigos manuales duplicados sin guardado parcial.
## 2026-05-18 â€” Codex â€” feature/reportes-demo

### Tarea
Implementar Prioridad 8 del roadmap: habilitar reportes en versiÃ³n demo.

### Archivos modificados
- `licensing/planes.py`
- `docs/ai/AI_CHANGELOG.md`

### QuÃ© se cambiÃ³
- Se agregÃ³ el mÃ³dulo `reportes` al plan `DEMO` en el mapping central de planes.
- Con ese cambio, la UI deja de ocultar "Resumen Mensual" y "EstadÃ­sticas Anuales" en demo, porque ambas pantallas ya dependen de `modulo_activo("reportes")`.
- No se habilitaron exportaciones ni otros mÃ³dulos premium: `export`, `multiusuario`, `temporadas` y demÃ¡s siguen igual.
- No fue necesario agregar un mÃ³dulo separado `estadisticas`, porque la ruta `/estadisticas` ya usa `require_modulo("reportes")`.

### QuÃ© se probÃ³
- RevisiÃ³n estÃ¡tica de `routes/main.py`: `/reportes`, `/estadisticas` y `rentabilidad_detallada` siguen protegidos por `require_modulo("reportes")`.
- RevisiÃ³n estÃ¡tica de `templates/base.html`: la navegaciÃ³n de reportes ya depende de `modulo_activo("reportes")`, por lo que se habilita correctamente en demo.
- ValidaciÃ³n local del mapping para confirmar que `DEMO` ahora resuelve `core` + `reportes`.

### Pendiente de prueba manual
- Abrir `/reportes` con licencia demo y confirmar carga correcta.
- Abrir `/estadisticas` con licencia demo y confirmar carga correcta.
- Verificar que "Mi plan" muestre `reportes` como mÃ³dulo habilitado en demo.
- Confirmar que exportaciones sigan bloqueadas en demo.

## 2026-05-18 â€” Codex â€” feature/onboarding-inicial

### Tarea
Implementar Prioridad 9A del roadmap: onboarding inicial liviano en dashboard.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/dashboard.html`
- `docs/ai/AI_CHANGELOG.md`

### QuÃ© se cambiÃ³
- Se agregÃ³ `get_onboarding_context()` para resumir estado inicial de la instalaciÃ³n usando cantidad de productos activos, proveedores activos, ventas, rubro confirmado y preferencia `onboarding_oculto`.
- La ruta `dashboard()` ahora envÃ­a `onboarding_context` al template.
- Se agregÃ³ una ruta POST para ocultar la guÃ­a y persistir `onboarding_oculto=1` en config.
- El dashboard ahora muestra una card "Primeros pasos" solo cuando falta al menos uno de estos puntos: rubro, proveedor, producto o primera venta.
- La card incluye accesos directos a configurar negocio, crear proveedor, crear producto, registrar compra/venta y ver reportes.
- Si el plan no tiene reportes activos, la card evita mandar a una pantalla bloqueada y deriva a `Mi plan`.
- La guÃ­a no bloquea la app ni obliga a completar ningÃºn paso.

### QuÃ© se probÃ³
- ValidaciÃ³n sintÃ¡ctica de Python con `python -m py_compile database.py routes/main.py`.
- RevisiÃ³n estÃ¡tica del flujo de dashboard, ocultado de onboarding y render condicional del template.

### Pendiente de prueba manual
- Abrir dashboard en una instalaciÃ³n nueva y confirmar que aparece la card.
- Ocultar la guÃ­a y verificar que no vuelva a mostrarse.
- Probar un caso con proveedor/producto/ventas ya cargados y confirmar que la card solo aparezca si todavÃ­a falta algo.
- Confirmar que el dashboard sigue cargando normal cuando no corresponde mostrar onboarding.
## 2026-05-18 â€” Codex â€” feature/imagenes-catalogo

### Tarea
Implementar Prioridad 10A del roadmap: imÃ¡genes en catÃ¡logo MVP.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/producto_form.html`
- `templates/productos.html`
- `static/uploads/productos/.gitkeep`
- `.gitignore`
- `docs/ai/AI_CHANGELOG.md`

### QuÃ© se cambiÃ³
- Se agregÃ³ la columna segura `productos.imagen` en la creaciÃ³n inicial de la tabla y en la migraciÃ³n con `PRAGMA table_info(productos)` + `ALTER TABLE` para bases existentes.
- Se agregÃ³ guardado local de imÃ¡genes bajo `static/uploads/productos/`, usando nombre Ãºnico con `uuid`, extensiones permitidas (`.jpg`, `.jpeg`, `.png`, `.webp`) y `secure_filename`.
- Alta de producto ahora acepta archivo de imagen y guarda la ruta relativa `uploads/productos/...` en `productos.imagen`.
- EdiciÃ³n de producto ahora muestra la imagen actual, permite reemplazarla y conserva la anterior si no se sube una nueva.
- El catÃ¡logo ahora muestra una miniatura de 48x48 por producto y un placeholder simple cuando no hay imagen.
- Se versionÃ³ la carpeta de uploads con `.gitkeep` y se ignoraron las imÃ¡genes reales subidas por usuario en `.gitignore`.
- No se implementÃ³ borrado automÃ¡tico de archivos anteriores ni integraciÃ³n con cÃ¡mara/telÃ©fono en este MVP.

### QuÃ© se probÃ³
- ValidaciÃ³n sintÃ¡ctica de Python con `python -m py_compile database.py routes/main.py`.
- RevisiÃ³n estÃ¡tica del flujo de alta, ediciÃ³n, validaciÃ³n de extensiones, persistencia de ruta relativa y render de miniaturas en catÃ¡logo.

### Pendiente de prueba manual
- Caso A: crear producto con imagen, guardarlo, ver miniatura en catÃ¡logo y ver imagen actual al editar.
- Caso B: crear producto sin imagen y verificar placeholder en catÃ¡logo.
- Caso C: editar producto con imagen sin subir nueva y confirmar que conserva la anterior.
- Caso D: editar producto con imagen, subir una nueva y confirmar que cambia la miniatura.
- Caso E: intentar subir un `.txt` y verificar mensaje claro sin guardar imagen invÃ¡lida.
## 2026-05-18 â€” Codex â€” feature/imagenes-catalogo mejora visual

### Tarea
Mejorar Prioridad 10A: normalizaciÃ³n visual y preview de imÃ¡genes en catÃ¡logo.

### Archivos modificados
- `routes/main.py`
- `templates/producto_form.html`
- `templates/productos.html`
- `docs/ai/AI_CHANGELOG.md`

### QuÃ© se cambiÃ³
- Se agregÃ³ texto de ayuda mÃ¡s claro en el formulario con tamaÃ±o recomendado `800 x 800 px`, formatos admitidos y aclaraciÃ³n de que la app ordena la vista del catÃ¡logo.
- La imagen actual en ediciÃ³n ahora se muestra con lÃ­mite visual razonable y `object-fit: contain`, evitando previews gigantes o deformadas.
- Las miniaturas del catÃ¡logo se normalizaron a `56 x 56 px`, con borde y placeholder uniforme cuando el producto no tiene imagen.
- Se agregÃ³ preview ampliado al pasar el mouse sobre una miniatura, con popover acotado y vista mÃ¡xima aproximada de `360 x 360 px`.
- En pantallas chicas el popover ampliado se oculta para no tapar la interfaz.
- En backend se agregÃ³ validaciÃ³n simple de tamaÃ±o para rechazar archivos mayores a `3 MB`.
- No se agregÃ³ Pillow ni redimensionado automÃ¡tico porque `requirements.txt` no lo incluye hoy.

### QuÃ© se probÃ³
- ValidaciÃ³n sintÃ¡ctica de Python con `python -m py_compile database.py routes/main.py`.
- RevisiÃ³n estÃ¡tica del render del formulario, miniaturas uniformes, popover ampliado y lÃ­mite de 3 MB.

### Pendiente de prueba manual
- Verificar que la miniatura uniforme no rompa el ancho de la tabla del catÃ¡logo.
- Confirmar que el popover ampliado aparece al pasar el mouse y no supera visualmente el tamaÃ±o esperado.
- Confirmar que en mÃ³vil o ventana angosta el popover no molesta.
- Intentar subir una imagen mayor a 3 MB y validar el mensaje de error.
## 2026-05-18 â€” Codex â€” feature/imagenes-catalogo correccion preview modal

### Tarea
Corregir el preview de imÃ¡genes en catÃ¡logo para evitar recorte dentro de la tabla responsive.

### Archivos modificados
- `templates/productos.html`
- `docs/ai/AI_CHANGELOG.md`

### QuÃ© se cambiÃ³
- Se reemplazÃ³ el preview ampliado por hover dentro de la tabla por apertura mediante modal Bootstrap al hacer click en la miniatura.
- La miniatura se mantuvo uniforme en `56 x 56 px` con `object-fit: cover`, borde redondeado y cursor `zoom-in`.
- Cada imagen real ahora carga sus datos en un Ãºnico modal reutilizable con tÃ­tulo por producto.
- Se eliminÃ³ la dependencia visual del popover hover que se cortaba por `table-responsive` o contenedores de la card.
- Los productos sin imagen siguen mostrando placeholder y no disparan modal.

### QuÃ© se probÃ³
- RevisiÃ³n estÃ¡tica del template y del JavaScript que abre/cierra el modal Bootstrap.

### Pendiente de prueba manual
- Confirmar que al hacer click en la miniatura se abre el modal con la imagen correcta.
- Confirmar que el modal cierra bien desde botÃ³n cerrar y backdrop.
- Verificar que la imagen ampliada no se corta y no ocupa toda la ventana.

## 2026-05-18 — Codex — audit/edicion-responsable

### Tarea
Auditoría de edición responsable global.

### Archivos modificados
- `docs/ai/AUDITORIA_EDICION_RESPONSABLE.md`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se documentaron riesgos de edición, eliminación, desactivación y anulación.
- No se modificó lógica funcional.

### Pendiente
- Implementar correcciones en ramas pequeñas según prioridades detectadas.

## 2026-05-18 � Codex � fix/ventas-anulacion-segura

### Tarea
Implementar correcci�n de auditor�a: ventas con anulaci�n segura.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/historial.html`
- `templates/ticket.html`
- `templates/cliente_detalle.html`
- `docs/ai/AUDITORIA_EDICION_RESPONSABLE.md`
- `docs/ai/AI_CHANGELOG.md`

### Qu� se cambi�
- Se agregaron columnas seguras en `ventas` para estado y trazabilidad de anulaci�n: `anulada`, `anulada_at`, `anulada_por` y `motivo_anulacion`.
- El flujo principal del historial dej� de borrar ventas f�sicamente y ahora usa `db.anular_venta(...)`.
- La anulaci�n restaura stock una sola vez, conserva `ventas` y `ventas_detalle`, y registra movimiento de stock de anulaci�n.
- Si la venta ten�a impacto en cuenta corriente y exist�a el movimiento original, se agrega una compensaci�n simple sin borrar historial.
- Se filtraron ventas anuladas en dashboard, caja resumida y reportes/rentabilidad principales del MVP.
- La UI ahora muestra estado `Anulada`, impide reanular desde el listado y actualiza el modal de confirmaci�n para hablar de anulaci�n y no de borrado.
- La auditor�a qued� actualizada para marcar ventas como corregido parcialmente con este MVP.

### Qu� se prob�
- Validaci�n sint�ctica con `python -m py_compile database.py routes/main.py`.
- Revisi�n est�tica de historial, ticket, detalle de cliente y consultas principales de ventas/reportes.

### Pendientes
- Confirmar manualmente que una venta anulada no siga sumando en todas las vistas secundarias fuera del recorte MVP.
- Definir una estrategia m�s formal para compensaci�n de caja hist�rica si luego se requiere trazabilidad contable m�s estricta.

## 2026-05-18 � Codex � fix/compras-anulacion-segura

### Tarea
Implementar correcci�n de auditor�a: compras con anulaci�n segura.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/compras.html`
- `templates/compra_detalle.html`
- `templates/proveedor_detalle.html`
- `docs/ai/AUDITORIA_EDICION_RESPONSABLE.md`
- `docs/ai/AI_CHANGELOG.md`

### Qu� se cambi�
- Se agregaron columnas seguras en `compras` para estado y trazabilidad de anulaci�n: `anulada`, `anulada_at`, `anulada_por` y `motivo_anulacion`.
- El flujo principal de compras dej� de borrar registros f�sicamente y ahora usa `db.anular_compra(...)`.
- La anulaci�n revierte stock una sola vez y registra movimiento `ANULACION_COMPRA`.
- Si el stock actual no alcanza para revertir la cantidad ingresada, la anulaci�n se bloquea con mensaje claro.
- Si la compra tiene factura proveedor asociada, el MVP bloquea la anulaci�n para no romper deuda comercial ni historial de proveedor.
- La UI ahora muestra estado `Anulada`, deshabilita acciones sobre compras anuladas y cambia el copy de eliminaci�n por anulaci�n.
- La auditor�a qued� actualizada para marcar compras como corregido parcialmente con este MVP.

### Qu� se prob�
- Validaci�n sint�ctica con `python -m py_compile database.py routes/main.py`.
- Revisi�n est�tica del flujo de compras, detalle de compra, historial en proveedor y validaciones de stock/factura asociada.

### Pendientes
- Confirmar manualmente los casos de anulaci�n con stock suficiente, bloqueo por stock insuficiente y bloqueo por factura proveedor asociada.
- Revisar futuras m�tricas o reportes derivados de compras si se agregan totales activos fuera del historial/listado actual.

## 2026-05-18 � Codex � fix/compras-anulacion-segura UX responsable

### Tarea
Mejorar UX de anulaci�n de compras para igualarla a ventas.

### Archivos modificados
- `routes/main.py`
- `templates/compras.html`
- `docs/ai/AI_CHANGELOG.md`

### Qu� se cambi�
- Se reemplaz� el `confirm()` nativo del navegador por un modal Bootstrap integrado con el estilo de Nexar Comercio.
- El modal ahora muestra datos de la compra seleccionada, permite cargar motivo opcional y exige checkbox de confirmaci�n.
- La ruta de anulaci�n de compras ahora valida credenciales y confirmaci�n con el mismo est�ndar responsable que ventas.
- No se modific� la l�gica backend de reversi�n de stock ni las guardas de anulaci�n segura ya implementadas, salvo la validaci�n m�nima del POST.

### Qu� se prob�
- Validaci�n sint�ctica con `python -m py_compile routes/main.py`.
- Revisi�n est�tica del modal, carga de data attributes y validaci�n del POST.

### Pendientes
- Confirmar manualmente apertura/cierre del modal, cancelaci�n sin efectos y anulaci�n correcta con contrase�a y checkbox.
## 2026-05-18 � Codex � feature/proveedores-anulacion-segura

### Tarea
Implementar anulaci�n segura para facturas de proveedor y endurecer su manejo contable b�sico.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `services/cuentas_corrientes.py`
- `templates/proveedor_facturas.html`
- `templates/proveedor_detalle.html`
- `tests/test_proveedor_facturas_anulacion.py`
- `docs/ai/AUDITORIA_EDICION_RESPONSABLE.md`
- `docs/ai/AI_CHANGELOG.md`

### Qu� se cambi�
- Se agregaron columnas seguras en `facturas_proveedores` para trazabilidad de anulaci�n: `anulada`, `anulada_at`, `anulada_por` y `motivo_anulacion`.
- El flujo principal dej� de borrar facturas f�sicamente y ahora usa `db.anular_factura_proveedor(...)`, conservando historial visible.
- La anulaci�n exige motivo obligatorio, impide doble anulaci�n y bloquea facturas con pagos ya registrados para no romper deuda comercial.
- Las facturas anuladas dejan de computar como deuda activa, vencidas o pendientes en los res�menes principales del MVP.
- Ya no se puede editar ni registrar pagos sobre facturas anuladas.
- La UI ahora usa un modal Bootstrap responsable, muestra advertencias claras, conserva la factura en historial y deshabilita acciones peligrosas cuando corresponde.
- Se agregaron tests m�nimos para anulaci�n sin pagos, bloqueo de doble anulaci�n, conservaci�n de historial y protecci�n de facturas con pagos.
- La auditor�a qued� actualizada para reflejar qu� qued� protegido y qu� pendientes siguen abiertos en cuenta corriente proveedor.

### Qu� se prob�
- Validaci�n sint�ctica con `python -m py_compile database.py routes/main.py services/cuentas_corrientes.py`.
- Tests unitarios con `python -m unittest tests.test_proveedor_facturas_anulacion`.

### Pendientes
- Confirmar manualmente el flujo visual del modal de anulaci�n desde la ficha de proveedor.
- Evaluar en una rama futura una trazabilidad m�s fina para pagos parciales y para `cc_proveedores_mov` legado si se profundiza la cuenta corriente proveedor.
## 2026-05-18 � Codex � feature/proveedores-anulacion-segura UX proveedores

### Tarea
Reemplazar confirmaciones nativas del navegador por confirmaci�n visual homog�nea en Gesti�n de Proveedores.

### Archivos modificados
- `templates/proveedores.html`
- `docs/ai/AUDITORIA_EDICION_RESPONSABLE.md`
- `docs/ai/AI_CHANGELOG.md`

### Qu� se cambi�
- Se reemplaz� el `confirm()` nativo usado al desactivar proveedores desde el listado por un modal Bootstrap reutilizable.
- El modal ahora muestra el nombre del proveedor, la advertencia de que no se borra f�sicamente y botones claros de cancelar o confirmar.
- Se mantuvo intacta la l�gica backend: el formulario sigue enviando el mismo POST a `proveedor_eliminar`.
- Se revis� el detalle de proveedor y no hab�a all� confirmaciones nativas equivalentes para ajustar en este paso.
- La auditor�a qued� actualizada para reflejar que la desactivaci�n de proveedores ya usa confirmaci�n homog�nea de Nexar.

### Qu� se prob�
- Revisi�n est�tica del template y del JavaScript del modal reutilizable.
- B�squeda local de `confirm(` y `alert(` en las vistas de proveedores para verificar que no queden popups nativos en este alcance.

### Pendientes
- Confirmar manualmente el flujo de desactivar proveedor desde el listado y la cancelaci�n sin efectos visibles.
## 2026-05-18 � Codex � feature/mejorar-config-ui-categorias correcci�n renombrado

### Tarea
Corregir el bug cr�tico de renombrado de categor�as y limpiar duplicados de forma segura en configuraci�n.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/config.html`
- `docs/ai/AI_CHANGELOG.md`

### Qu� se cambi�
- Se corrigi� `update_categoria(...)` para que renombre la categor�a existente en lugar de crear una nueva y desactivar la anterior.
- El renombrado ahora usa el `id` de la categor�a cuando est� disponible y conserva el estado activo/inactivo del registro original.
- Se simplific� el submit del formulario inline en `config.html` para que Guardar y Enter env�en solo el form de renombre, sin mezclar acciones con activar/desactivar ni agregar categor�a.
- Se agreg� limpieza segura de duplicados por nombre normalizado en categor�as de productos, con migraci�n de referencias de productos al nombre can�nico y consolidaci�n de filas sobrantes.
- Se evit� que categor�as base aparezcan tambi�n como `personalizada` en la configuraci�n cuando en realidad corresponden al seed/base del rubro.
- Se reforz� la validaci�n para impedir nuevas categor�as duplicadas en productos y en categor�as de gasto, incluyendo variantes por may�sculas, espacios y nombres normalizados.
- Tambi�n se consolidan duplicados existentes en categor�as de gasto y se muestran mensajes claros cuando un nombre ya existe.

### Qu� se prob�
- Validaci�n sint�ctica con `python -B -m py_compile database.py routes/main.py`.
- Prueba local con base temporal para verificar:
  - deduplicaci�n de categor�as existentes
  - renombrado por `id` sin crear una fila nueva
  - conservaci�n del estado activo
  - migraci�n de productos al nombre renombrado
  - bloqueo de altas duplicadas en categor�as de producto y gasto

### Pendientes
- Confirmar manualmente en UI el flujo completo de agregar, renombrar con Enter, renombrar con bot�n Guardar y activar/desactivar desde `config.html`.