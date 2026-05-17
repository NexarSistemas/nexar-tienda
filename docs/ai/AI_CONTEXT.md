# AI_CONTEXT.md — Contexto maestro para Nexar Comercio

## Producto

El producto visible es Nexar Comercio.

El repositorio técnico sigue siendo nexar-tienda por compatibilidad con builds, instaladores, actualizaciones, licencias y artefactos existentes.

No renombrar identificadores técnicos salvo pedido explícito.

## Stack

- Python
- Flask
- SQLite
- Jinja2
- Bootstrap
- JavaScript simple en templates
- pywebview
- PyInstaller
- GitHub Actions

## Regla principal

No romper lo que ya funciona.

Antes de modificar:
1. analizar flujo actual
2. detectar archivos afectados
3. proponer cambio mínimo viable
4. implementar solo lo necesario
5. mantener compatibilidad con datos existentes
6. actualizar AI_CHANGELOG.md

## Regla de ramas

Nunca trabajar directamente sobre main.
Cada mejora debe ir en rama propia.

## Áreas sensibles

Tener cuidado especial con:
- compras
- ventas
- stock
- facturas
- cuentas corrientes
- reportes
- licencias
- actualizaciones
- configuración de rubro
- migraciones SQLite

## Hallazgos conocidos

En templates/compras.html existe una fricción:
el botón Crear producto desde una compra exige completar producto_descripcion antes de abrir creación de producto.

El flujo ya tiene return_to=compra_nueva y borrador de compra, por lo tanto se debe mejorar sin rehacer todo.

En templates/productos.html ya existe búsqueda y filtro por categoría.
Falta filtro por proveedor.

Las categorías están mezcladas entre services/rubros.py y tabla categorias.
A futuro deben ser configurables.

Los reportes deben estar habilitados en demo para que el usuario conozca el valor del sistema.
