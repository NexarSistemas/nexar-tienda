# Product Variants Phase 1

> El contrato normativo vigente del dominio se encuentra en
> [`../architecture/CATALOGO_UNIVERSAL_V1.md`](../architecture/CATALOGO_UNIVERSAL_V1.md).
> Este documento conserva el alcance histórico de la primera implementación.

## Objetivo

Agregar una base genérica de productos con variantes compatible con rubros
distintos y preparada conceptualmente para futuras integraciones como
Tiendanube, sin romper el flujo actual de Nexar Comercio.

## Modelo incorporado

- `producto_atributos`: definiciones reutilizables como `Color`, `Talle`,
  `Medida` o `Material`.
- `producto_atributo_valores`: opciones reutilizables por atributo.
- `producto_variantes`: variantes explícitas por producto con combinación,
  SKU, código de barras, costo, precio, precio promocional opcional, estado e
  identificador externo.
- `producto_variante_valores`: composición atributo/valor de cada variante.
- `stock_variantes`: stock propio por variante.

La unicidad de la combinación dentro de un producto se resuelve con
`combination_key`, calculada desde los pares atributo/valor ordenados.

## Compatibilidad retroactiva

- `productos` y `stock` siguen siendo la fuente legacy para productos comunes.
- No se migran masivamente productos existentes a variantes.
- El POS, compras, lector de códigos, reportes y exportaciones conservan en
  esta fase el comportamiento actual basado en producto simple.
- Las bases existentes pueden abrirse y migrar con `init_db()` sin perder datos.

## Alcance real de esta fase

- Persistencia SQLite y migración idempotente.
- Servicio pequeño para alta y consulta de variantes.
- UI mínima para gestionar variantes desde producto.
- Tests de compatibilidad, migración e idempotencia.

## Preparación para Tiendanube

El dominio usa nombres internos genéricos y agrega `external_id` opcional en
las entidades nuevas, pero no acopla el modelo al formato JSON de ningún
proveedor externo.

## Gestión incorporada en el Issue #144

- Edición atómica de atributos, valores, SKU, código de barras, costo, precios
  y stock configurado de una variante.
- Activación y desactivación explícitas desde la ficha del producto.
- Eliminación física cuando solo existen las dependencias propias de la
  variante.
- Desactivación segura cuando una relación externa conserva referencias a la
  variante.
- Validaciones de servidor, permisos, CSRF y auditoría con las convenciones
  existentes.

Estas acciones no cambian la fuente de verdad legacy ni habilitan todavía
variantes en POS, compras, movimientos o reportes.

## Integracion de stock del Issue #145

- `productos.stock_modo` define de forma persistente si el producto opera con
  stock legacy (`stock`) o por variantes (`stock_variantes`). La existencia de
  variantes creadas no cambia el modo por si sola.
- `services/inventory.py` centraliza la resolucion del item vendible, altas,
  bajas, ajustes, listado operativo, alertas y transicion a variantes.
- En modo legacy, los movimientos rechazan `variante_id` y escriben solo en
  `stock`. En modo variantes, la variante es obligatoria y se escribe solo en
  `stock_variantes`.
- `stock_movimientos` conserva registros legacy y suma `variante_id` y
  `stock_fuente` para identificar producto, variante opcional y tabla afectada.
- La activacion de stock por variantes es una accion explicita y transaccional:
  valida que la suma asignada a variantes coincida con el stock legacy, no borra
  la fila legacy, registra movimientos/auditoria y revierte todo ante error.
- Los totales de productos con variantes son proyecciones calculadas desde sus
  variantes activas, no una segunda fuente editable.

## Pendientes para una fase siguiente

- Resolver variante efectiva en POS, compras, reportes e importación.
- Definir sincronización controlada entre producto base legacy y variantes.
- Implementar adaptadores externos hacia Tiendanube u otras plataformas.
