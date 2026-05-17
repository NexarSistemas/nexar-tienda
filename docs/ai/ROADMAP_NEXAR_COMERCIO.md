# ROADMAP_NEXAR_COMERCIO.md

## Objetivo

Mejorar Nexar Comercio priorizando usabilidad, productividad y estabilidad.

Regla:
primero mejoras operativas, después mejoras visuales.

## Prioridad 0 — Auditoría de edición responsable

Revisar qué se puede editar, eliminar o desactivar en:
- stock
- catálogo
- productos
- proveedores
- clientes
- compras
- ventas
- facturas
- gastos
- caja
- reportes

Criterio:
permitir edición responsable sin romper historial, stock ni reportes.

Preferir soft delete cuando haya historial.

## Prioridad 1 — Flujo ágil de compra con producto/proveedor nuevo

Problema:
desde Nueva Compra, Crear producto exige descripción previa.

Objetivo:
permitir Crear producto aunque descripción esté vacía.

Requisitos:
- mantener borrador de compra
- usar return_to=compra_nueva
- volver a compra con producto creado seleccionado
- no romper creación de proveedor
- hacer cambio mínimo viable

Archivos probables:
- templates/compras.html
- routes/main.py
- templates/producto_form.html
- database.py

## Prioridad 2 — Filtro por proveedor en catálogo

Objetivo:
filtrar productos por proveedor, combinable con búsqueda y categoría.

Caso real:
ver todos los productos que vende un proveedor específico, por ejemplo mates de Marroquinería Full, sin mezclarlos con otros proveedores.

Archivos probables:
- routes/main.py
- templates/productos.html
- database.py

## Prioridad 3 — Aumento masivo de precios por proveedor/categoría

Objetivo:
aplicar aumento porcentual a productos de:
- proveedor completo
- proveedor + categoría

Ejemplo:
proveedor X aumenta 2% todo.
proveedor X aumenta 5% solo termos.

Actualizar:
- costo
- precio venta

Debe mostrar cantidad de productos afectados y pedir confirmación.

## Prioridad 4 — Categorías configurables

Objetivo:
permitir crear, editar, activar/desactivar y eliminar categorías.

No romper categorías hardcodeadas existentes.
Migrar gradualmente.

## Prioridad 5 — Carga por lotes de productos únicos

Objetivo:
cargar varios productos únicos en una tabla rápida.

Caso:
10 mates distintos, cada uno con precio diferente y stock 1.

## Prioridad 6 — Importación Excel/CSV con plantilla

Objetivo:
descargar plantilla, completarla offline e importar productos.

Columnas sugeridas:
- descripcion
- marca
- categoria
- proveedor
- codigo_barras
- costo
- precio_venta
- stock_actual
- stock_minimo
- stock_maximo
- unidad

## Prioridad 7 — Código de barras automático interno

Objetivo:
generar código interno imprimible cuando el producto no trae código de barras.

## Prioridad 8 — Reportes habilitados en demo

Objetivo:
en versión demo, los reportes deben estar disponibles para que el usuario conozca el sistema.

## Prioridad 9 — Onboarding inicial

Objetivo:
asistente inicial para elegir rubro, cargar primer proveedor, primer producto y explicar reportes.

## Prioridad 10 — Imágenes en catálogo

Última prioridad.

Objetivo:
permitir foto por producto desde PC o teléfono.

## Futuro — OCR/IA para remitos

No priorizar ahora.
Primero resolver carga por lote, importación y flujo manual rápido.
