# AUDITORIA_EDICION_RESPONSABLE.md

## Objetivo

Documentar qué entidades de Nexar Comercio hoy pueden editarse, eliminarse, desactivarse o anularse, qué riesgos reales existen con el comportamiento actual y qué camino conviene seguir para mantener consistencia en historial, stock, cuenta corriente, caja y reportes.

Esta auditoría es documental. No modifica lógica funcional.

## Resumen ejecutivo

- `productos`, `clientes`, `proveedores` y `categorías` ya tienen una base más segura porque priorizan desactivación sobre borrado físico.
- `ventas`, `compras`, `facturas de proveedor` y `gastos` todavía tienen puntos de borrado físico o edición destructiva que pueden afectar trazabilidad histórica.
- `stock` permite ajuste manual con movimiento registrado, lo cual es bueno, pero sigue existiendo riesgo si en el futuro se habilita edición directa fuera de ese flujo.
- `caja` permite apertura, movimientos y cierre, pero no tiene todavía bloqueo explícito de edición posterior ni reglas fuertes de inmutabilidad histórica.
- `reportes` dependen de tablas operativas; por eso cualquier borrado físico en ventas, compras, gastos o stock impacta directo en resultados históricos.
- Prioridades recomendadas:
  1. Reemplazar borrado físico de ventas por anulación segura.
  2. Endurecer compras para evitar eliminación con impacto silencioso en stock e historial.
  3. Formalizar ajustes responsables de stock.
  4. Endurecer facturas de proveedor y deuda comercial.
  5. Agregar confirmaciones y copy de riesgo en UI para acciones destructivas.

## Matriz global

| Área | Acción actual | Riesgo | Recomendación | Prioridad |
| --- | --- | --- | --- | --- |
| Productos | Desactiva con `activo=0`; edición amplia | Bajo a medio | Mantener soft delete y limitar cambios sensibles a stock/códigos con validación | Alta |
| Stock | Ajuste manual cambia stock y registra movimiento | Medio | Mantener ajustes con movimiento y desalentar edición directa sin motivo | Alta |
| Proveedores | Desactiva con `activo=0`; mantiene detalle y facturas | Bajo a medio | Mantener desactivación y revisar vínculo con deuda/facturas antes de cambios estructurales | Media |
| Clientes | Desactiva con `activo=0`; CC se reconstruye desde ventas faltantes | Bajo a medio | Mantener desactivación y evitar borrado físico con saldo o historial | Media |
| Compras | Puede editar metadatos seguros; eliminar revierte stock y borra compra | Alto | Cambiar a anulación o soft delete con reversión explícita y trazabilidad | Muy alta |
| Ventas | Eliminar borra venta, detalle, CC asociada y revierte stock | Muy alto | Implementar anulación segura; evitar borrado físico operativo | Muy alta |
| Facturas proveedor | Edita importes con guardas; elimina si no hay pagos | Alto | Preferir anulación/estado; no borrar físicamente facturas comerciales | Alta |
| Caja diaria | Movimientos manuales y cierre sin bloqueo fuerte posterior | Medio a alto | Congelar cajas cerradas y registrar ajustes posteriores como asientos compensatorios | Alta |
| Gastos | Edita y elimina físicamente; sincroniza con caja | Alto | Pasar a anulación o soft delete, sobre todo si afectó caja/reportes | Alta |
| Reportes | Lectura derivada de datos vivos | Alto indirecto | Proteger orígenes; no “corregir reportes” tocando historia sin trazabilidad | Alta |
| Categorías | Renombra y activa/desactiva; no borra productos | Bajo | Mantener desactivación y evitar borrado que deje datos huérfanos | Media |
| Importaciones | Alta masiva de productos nuevos | Medio | Validar duplicados y dejar rastro de origen/importación si más adelante se edita masivamente | Media |
| Carga por lote | Alta masiva con validaciones básicas | Medio | Igual que importación: evitar reescrituras masivas sin trazabilidad | Media |
| Códigos de barras internos | Generación secuencial y validación de unicidad | Bajo a medio | Tratar cambios posteriores como sensibles para no romper búsqueda/etiquetas | Media |
| Imágenes de catálogo | Ruta editable y reemplazable | Bajo | Editable libre; no impacta historial contable | Baja |

## Revisión por módulo

### Productos

- Alta:
  Se crean en `productos` y a la vez se inicializa fila en `stock`. También puede generarse código de barras interno si falta.
- Edición:
  Hoy permite cambiar descripción, marca, imagen, categoría, unidad, fraccionamiento, costo, precio, IVA, código de barras y estado activo.
- Desactivación/eliminación:
  El “eliminar” actual es soft delete mediante `activo=0`.
- Impacto en ventas históricas:
  Bajo si solo se desactiva. Las ventas históricas guardan detalle propio, pero cambios de descripción, unidad o precio del maestro pueden desalinear lectura operativa versus contexto histórico.
- Impacto en stock:
  El producto conserva su stock aunque esté inactivo, por lo que conviene no reutilizar registros viejos para otro artículo.
- Impacto en reportes:
  Desactivar no rompe reportes. Editar categoría o costo sí puede alterar lecturas presentes si algunos reportes consultan maestro actual en lugar de snapshot histórico.
- Imagen:
  Es segura de editar o reemplazar. No afecta caja, stock ni historial.
- Código de barras:
  Tiene validación de unicidad. Cambiarlo después de imprimir etiquetas o usarlo en mostrador puede generar fricción operativa, aunque no rompe historial contable.
- Qué debería pasar:
  Mantener soft delete. Permitir edición libre en campos comerciales, pero tratar como “sensibles” unidad, fraccionamiento, código de barras y costo si ya hay historial.

### Stock

- Edición directa:
  Existe ajuste manual desde stock que actualiza `stock_actual` y además registra movimiento tipo `AJUSTE` con motivo.
- Ajustes:
  El flujo actual es correcto para MVP porque deja rastro mínimo del cambio.
- Movimientos:
  Compras generan `COMPRA`, ventas descuentan stock y el ajuste manual genera `AJUSTE`.
- Impacto en compras/ventas:
  Alto. El stock es derivado de movimientos operativos y cualquier cambio sin trazabilidad rompe conciliación.
- Historial:
  Hay historial en `stock_movimientos`, pero no parece existir todavía una conciliación fuerte que impida inconsistencias si se toca stock por SQL o futuros atajos.
- ¿Conviene permitir edición directa?
  No como edición “silenciosa”. Sí como ajuste explícito con motivo obligatorio.
- ¿Conviene registrar movimiento de ajuste?
  Sí. Es el camino correcto y ya está parcialmente implementado.
- Dónde hay riesgo:
  En futuras pantallas o helpers que usen `update_stock_item` sin acompañar `stock_movimientos`, o en eliminación de compras/ventas que recompone stock por diferencia sin estado de anulación.

### Proveedores

- Edición:
  Permite actualizar datos maestros y conservar historial.
- Desactivación:
  Usa `activo=0`, lo cual es adecuado.
- Compras asociadas:
  Las compras guardan `proveedor_id` y `proveedor_nombre`, por lo que la trazabilidad mínima persiste aunque el proveedor se inhabilite.
- Facturas:
  El proveedor está vinculado a deuda comercial mediante `facturas_proveedores`.
- Cuenta corriente proveedor:
  La deuda se apoya en facturas y pagos. Cambios de proveedor en compras con pagos ya están restringidos en edición básica.
- Productos con proveedor habitual:
  Existe referencia en stock/producto para proveedor habitual; desactivar proveedor no limpia automáticamente esa relación.
- Qué debería pasar:
  Mantener soft delete. No borrar físicamente proveedores con compras, facturas o productos asociados. Si está inactivo, que siga visible en histórico.

### Compras

- Edición:
  Hay un flujo “seguro” para editar solo metadatos: fecha, remito, proveedor y observaciones, sin recalcular stock ni modificar detalle.
- Eliminación:
  Elimina físicamente la compra. Si hay factura asociada sin pagos, la elimina también. Además descuenta stock restando la cantidad comprada.
- Impacto en stock:
  Alto. Revertir stock por borrado físico puede dejar diferencias si hubo ventas posteriores o si el stock ya fue ajustado manualmente.
- Impacto en facturas proveedor:
  Alto. La compra puede arrastrar eliminación de la factura asociada.
- Impacto en cuenta corriente:
  Alto indirecto. Aunque la deuda se maneja por facturas, borrar compra vinculada cambia la trazabilidad del origen.
- Impacto en reportes:
  Alto. Se pierde historial de abastecimiento, costos y márgenes.
- Identificación:
  Hoy eliminar compra revierte stock y borra registro, no anula.
- Comportamiento seguro recomendado:
  No borrar físicamente compras operativas. Implementar “anulada” o soft delete con reversión controlada, dejando rastro de usuario, fecha y motivo.

### Ventas

- Historial:
  Existe historial con ticket y detalle.
- Eliminación/anulación:
  Hoy `delete_venta` hace borrado físico: repone stock, borra `stock_movimientos`, borra movimientos de cuenta corriente asociados, borra detalle y luego borra la venta.
- Impacto en stock:
  Muy alto. Recompone stock directamente.
- Impacto en caja:
  Alto. La venta es un hecho económico; si la caja del día ya fue usada para control, el borrado deja desalineado el negocio aunque la tabla caja no se toque explícitamente.
- Impacto en cuenta corriente cliente:
  Alto. El borrado elimina movimientos de `cc_clientes_mov` asociados.
- Impacto en reportes:
  Muy alto. Desaparece facturación histórica.
- Recomendación:
  Diferenciar claramente:
  1. Editar venta: evitar en MVP salvo metadatos inocuos.
  2. Anular venta: registrar estado anulado, reponer stock con movimiento específico y compensar CC/caja.
  3. Eliminar físicamente: reservar solo para limpieza técnica excepcional.

### Clientes

- Edición:
  Permite cambiar datos maestros, límite de crédito y estado activo.
- Eliminación/desactivación:
  Usa `activo=0`, lo que es correcto.
- Cuenta corriente:
  Se alimenta por movimientos y además hay reconciliación automática de ventas a cuenta corriente faltantes.
- Ventas asociadas:
  Las ventas guardan `cliente_id` y nombre; desactivar cliente no debería romper el historial.
- Qué debería pasar:
  No borrar físicamente clientes con historial o saldo. Mantener desactivación y bloquear cambios peligrosos si existieran futuras fusiones o reasignaciones.

### Facturas proveedor

- Edición:
  Se puede editar número, fechas, importe y observaciones. Ya hay una guarda útil: el importe no puede quedar por debajo de lo ya pagado.
- Eliminación:
  Solo se permite si no tiene pagos registrados.
- Pagos asociados:
  El campo `pagado` protege parcialmente, pero todavía no hay un estado de anulación o un libro de eventos completo.
- Deuda comercial:
  Alto impacto. La factura es el soporte de deuda con proveedor.
- Cuenta corriente:
  Aunque no exista una tabla separada tipo `cc_proveedores`, la factura hace de base para deuda.
- Qué debería pasar:
  No eliminar físicamente facturas comerciales una vez emitidas o vinculadas a compra real. Preferir anulación con motivo, especialmente si ya impactaron gestión o reportes.

### Caja

- Movimientos:
  Permite ingresos/egresos manuales y además gastos en efectivo pueden sincronizarse como movimientos de caja.
- Arqueos:
  El cierre guarda `saldo_final_real`, pero no aparece una conciliación fuerte ni bloqueo posterior.
- Cierre de caja:
  Marca `estado=0`, pero no se observan protecciones documentadas para impedir alteraciones indirectas posteriores.
- Edición posterior:
  Riesgo medio a alto. Si se borra o edita un gasto que originó un movimiento de caja, la sincronización puede borrar o alterar ese movimiento aunque la caja histórica ya sea referencia cerrada.
- Qué debería pasar:
  Una caja cerrada debería considerarse congelada. Las correcciones posteriores deberían entrar como ajustes compensatorios, no reescritura silenciosa del pasado.

### Gastos

- Edición:
  Permite cambiar fecha, categoría, clasificación, descripción, monto, medio de pago y otros datos.
- Eliminación:
  Hoy hace borrado físico.
- Caja:
  Existe sincronización con `caja_movimientos`. Si el gasto desaparece o cambia de condiciones, el movimiento de caja puede actualizarse o borrarse.
- Reportes:
  Alto impacto. Borrar un gasto modifica resultados históricos.
- Qué debería pasar:
  Para gastos ya usados en caja o reportes conviene anular o desactivar, no borrar. Si se mantiene edición, debería quedar rastro mínimo de cambios sensibles.

### Categorías

- Crear:
  Seguro.
- Renombrar:
  Riesgo bajo a medio. Puede cambiar clasificación visible de productos o gastos existentes.
- Activar/desactivar:
  Correcto para catálogo futuro.
- Impacto en productos/reportes:
  Bajo si la categoría es solo descriptiva, pero el renombre puede alterar agrupaciones históricas en reportes si estos leen el valor actual.
- Qué debería pasar:
  Mantener activación/desactivación y evitar “borrado real”. Para categorías con uso histórico, el renombre conviene tratarlo con cuidado.

### Importaciones, lote, códigos e imágenes

- Importaciones CSV:
  Crean productos nuevos con validaciones básicas y pueden generar códigos internos si falta código de barras.
- Carga por lote:
  También crea productos nuevos en cantidad, con validaciones mínimas por fila.
- Consistencia:
  En altas nuevas la consistencia es razonable, pero si más adelante se agregan ediciones masivas habrá riesgo alto sin vista previa, diff o bitácora.
- Códigos de barras internos:
  Se generan con secuencia `NXR...` y validación de unicidad. Son seguros en alta, pero cambiarlos luego puede romper operación de mostrador, etiquetas y búsqueda.
- Imágenes de catálogo:
  Son de bajo riesgo funcional. Reemplazarlas no afecta stock ni historia comercial.
- Qué pasa si luego se editan:
  1. Importación/lote: si se usa para sobreescribir productos existentes, debería haber modo “simulación” y confirmación por campo.
  2. Códigos: tratarlos como dato sensible.
  3. Imágenes: edición libre aceptable.

## Clasificación de acciones

### Editable sin riesgo alto

- Descripción de producto.
- Marca.
- Imagen de catálogo.
- Proveedor habitual de referencia.
- Stock mínimo y máximo.
- Datos de contacto de clientes y proveedores.
- Observaciones no contables.
- Activar/desactivar categorías.

### Editable con recalculo o movimiento

- Stock actual: solo mediante ajuste con movimiento y motivo.
- Costo y precio de venta: editable, pero idealmente con criterio temporal si luego impacta reportes de margen.
- Compra histórica: solo metadatos seguros; cambiar cantidades o producto exige recalcular stock y revisar factura.
- Factura proveedor: importe y fechas requieren validación contra pagos y deuda.
- Gasto en efectivo: si ya sincronizó caja, cualquier cambio debería recalcular o compensar movimiento.

### No eliminar físicamente

- Ventas.
- Compras con impacto en stock.
- Facturas de proveedor emitidas.
- Gastos que ya impactaron caja o reportes.
- Clientes con cuenta corriente o ventas.
- Proveedores con compras o facturas.
- Productos usados en ventas/compras.

### Mejor anular/desactivar

- Ventas históricas.
- Compras históricas.
- Facturas proveedor sin borrado real.
- Gastos cargados por error.
- Productos fuera de catálogo.
- Proveedores y clientes que ya no operan.
- Categorías obsoletas.

## Recomendaciones de implementación por ramas

- `fix/ventas-anulacion-segura`
  Reemplazar borrado físico por estado anulado, reposición de stock con movimiento específico y compensación de CC.
- `fix/compras-edicion-responsable`
  Limitar edición a metadatos seguros y migrar eliminación a anulación/soft delete con control de stock.
- `fix/stock-ajustes-responsables`
  Reforzar que todo cambio de stock pase por ajuste con motivo y dejar mejor trazabilidad.
- `fix/facturas-proveedor-seguras`
  Incorporar estado anulado y reglas de edición más claras según pagos/deuda.
- `fix/gastos-anulacion-caja`
  Evitar borrado físico de gastos que impactaron caja; usar anulación o asiento compensatorio.
- `fix/caja-cierres-inmutables`
  Congelar cajas cerradas y canalizar correcciones por movimientos posteriores.
- `fix/ui-confirmaciones-peligrosas`
  Mejorar copy y advertencias en UI para explicar impacto de eliminar/anular.

## Checklist de pruebas manuales

### Productos

- Crear, editar y desactivar un producto con historial de stock.
- Confirmar que desactivar no borra ventas ni compras asociadas.
- Cambiar imagen y código de barras de un producto ya usado y revisar operación básica.

### Stock

- Realizar ajuste manual con motivo y verificar movimiento `AJUSTE`.
- Intentar conciliar stock después de una compra y una venta.

### Proveedores

- Desactivar proveedor con compras y facturas existentes.
- Verificar que siga visible en histórico y detalle.

### Compras

- Editar una compra por flujo seguro y confirmar que no cambia stock.
- Eliminar una compra sin pagos asociados y verificar cómo revierte stock.
- Intentar eliminar compra con factura pagada y confirmar bloqueo.

### Ventas

- Registrar venta, verificar descuento de stock y movimiento de CC si corresponde.
- Eliminar venta y comprobar impacto en stock, historial y cuenta corriente.

### Clientes

- Desactivar cliente con ventas y saldo.
- Revisar que el detalle y la cuenta corriente sigan accesibles.

### Facturas proveedor

- Editar importe antes y después de registrar pagos parciales.
- Intentar eliminar factura con pagos y confirmar bloqueo.
- Eliminar factura sin pagos y revisar pérdida de trazabilidad.

### Caja

- Abrir caja, registrar movimientos, cerrar caja.
- Editar o borrar un gasto en efectivo vinculado y revisar si afecta caja cerrada.

### Gastos

- Crear gasto en efectivo con caja abierta y verificar movimiento en caja.
- Editar gasto para cambiar medio de pago y revisar sincronización.
- Eliminar gasto y revisar efecto en reportes y caja.

### Categorías

- Renombrar categoría usada por productos/gastos.
- Desactivar categoría y confirmar que no desaparecen registros históricos.

### Importaciones, lote, códigos e imágenes

- Importar productos con y sin código de barras.
- Crear productos por lote y verificar validaciones por fila.
- Revisar unicidad de código de barras interno.
- Reemplazar imagen de producto y confirmar que no afecta operaciones.
