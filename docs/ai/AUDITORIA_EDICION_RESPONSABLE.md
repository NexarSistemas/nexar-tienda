# AUDITORIA_EDICION_RESPONSABLE.md

## Objetivo

Documentar qué entidades de Nexar Comercio hoy pueden editarse, eliminarse, desactivarse o anularse, qué riesgos reales existen con el comportamiento actual y qué camino conviene seguir para mantener consistencia en historial, stock, cuenta corriente, caja y reportes.

Esta auditoría es documental. No modifica lógica funcional.

## Resumen ejecutivo

- `productos`, `clientes`, `proveedores` y `categorías` ya tienen una base más segura porque priorizan desactivación sobre borrado físico.
- `ventas` quedó corregido parcialmente con MVP de anulación segura: ya no debería borrarse físicamente desde el flujo principal, restaura stock y conserva historial.
- `compras` quedó corregido parcialmente con MVP de anulación segura: ya no debería borrarse físicamente desde el flujo principal y solo se anula si no rompe stock ni deuda proveedor.
- `facturas de proveedor` quedó corregido parcialmente con MVP de anulación segura: ya no debería borrarse físicamente desde el flujo principal y se bloquea si tiene pagos.
- `gastos` todavía tiene puntos de borrado físico o edición destructiva que pueden afectar trazabilidad histórica.
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
| Compras | MVP corregido: anula, conserva historial y revierte stock con guardas | Medio | Completar exclusión de anuladas en vistas secundarias y definir reversión segura para compras con factura proveedor | Muy alta |
| Ventas | MVP corregido: anula, conserva historial y recompone stock | Medio | Completar exclusión de anuladas en todas las vistas/reportes secundarios y revisar compensaciones contables | Muy alta |
| Facturas proveedor | MVP corregido: anula sin borrar y bloquea si hay pagos | Medio | Completar cobertura sobre reportes secundarios y definir estrategia futura para pagos parciales con trazabilidad más fina | Alta |
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
  La confirmación visual de desactivación ya usa modal homogéneo de Nexar en lugar de `confirm()` nativo del navegador.

### Compras

- Estado actual del MVP:
  Corregido parcialmente. El flujo principal pasa por anulación segura en lugar de borrado físico.
- Edición:
  Hay un flujo “seguro” para editar solo metadatos: fecha, remito, proveedor y observaciones, sin recalcular stock ni modificar detalle.
- Eliminación:
  El MVP actual marca la compra con `anulada=1`, conserva el registro, registra fecha/usuario/motivo y descuenta stock una sola vez al anular.
- Impacto en stock:
  Mejorado parcialmente: si el stock actual no alcanza para revertir la cantidad ingresada, la anulación se bloquea.
- Impacto en facturas proveedor:
  Mejorado por bloqueo seguro: si la compra tiene factura comercial asociada, el MVP no intenta revertirla automáticamente y rechaza la anulación.
- Impacto en cuenta corriente:
  Mejorado parcialmente: la compra ya no se borra, pero queda pendiente una estrategia formal para compras ligadas a deuda proveedor.
- Impacto en reportes:
  Reducido en el historial principal porque la compra anulada sigue visible. Quedan pendientes filtros activos si más adelante aparecen totales o reportes derivados de compras.
- Identificación:
  El flujo principal ya no borra físicamente, pero todavía falta cobertura más amplia sobre facturas proveedor y métricas secundarias.
- Comportamiento seguro recomendado:
  Mantener y completar este enfoque:
  1. Editar compra: limitar a metadatos seguros.
  2. Anular compra: registrar estado anulado, revertir stock con movimiento y bloquear cuando haya deuda proveedor o stock insuficiente.
  3. Eliminar físicamente: reservar solo para limpieza técnica excepcional.

### Ventas

- Estado actual del MVP:
  Corregido parcialmente. El flujo principal pasa por anulación segura en lugar de borrado físico.
- Historial:
  Existe historial con ticket y detalle.
- Eliminación/anulación:
  El MVP actual marca la venta con `anulada=1`, conserva `ventas` y `ventas_detalle`, registra fecha/usuario/motivo de anulación, repone stock y crea movimiento de stock de anulación.
- Impacto en stock:
  Controlado en el flujo principal: la reposición ocurre una sola vez si la venta no estaba anulada.
- Impacto en caja:
  Mejorado para métricas principales porque caja y dashboard dejan de sumar ventas anuladas en los totales visibles, pero no hay todavía asiento compensatorio persistente de caja.
- Impacto en cuenta corriente cliente:
  Mejorado parcialmente: no se borran movimientos y, si existía el cargo de cuenta corriente, se agrega una compensación simple por anulación.
- Impacto en reportes:
  Reducido en reportes principales: dashboard, historial, reportes y rentabilidad principal ya filtran anuladas en el MVP. Quedan pendientes revisiones de vistas secundarias o futuras consultas nuevas.
- Recomendación:
  Mantener y completar este enfoque:
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

- Estado actual del MVP:
  Corregido parcialmente. El flujo principal pasa por anulación segura en lugar de borrado físico.
- Edición:
  Se puede editar número, fechas, importe y observaciones solo si la factura sigue activa. Ya existe la guarda de que el importe no puede quedar por debajo de lo ya pagado.
- Eliminación:
  El MVP actual marca la factura con `anulada=1`, conserva historial, registra fecha/usuario/motivo y deja de contarla como deuda activa.
- Pagos asociados:
  Mejorado por bloqueo seguro: si `pagado > 0`, la factura no se anula y no se toca el importe ya aplicado.
- Deuda comercial:
  Mejorado parcialmente: una factura anulada deja de computar como deuda comercial activa.
- Cuenta corriente:
  La fuente principal sigue siendo `facturas_proveedores`; `cc_proveedores_mov` permanece como auxiliar legado y no se recalcula en este MVP.
- Qué quedó protegido:
  1. Ya no se borra físicamente la factura desde el flujo principal.
  2. No se permite doble anulación.
  3. No se permite editar ni registrar pagos sobre facturas anuladas.
  4. No se permite anular facturas con pagos ya aplicados.
- Qué sigue permitido:
  1. Editar facturas activas sin pagos inconsistentes.
  2. Registrar pagos sobre facturas activas.
- Qué queda bloqueado o pendiente:
  1. La anulación automática de facturas con pagos parciales o totales queda bloqueada en este MVP.
  2. `cc_proveedores_mov` sigue como apoyo legado y puede requerir una estrategia futura más explícita si se profundiza la trazabilidad.
- Qué debería pasar:
  Mantener y completar este enfoque:
  1. Editar factura: solo mientras siga activa.
  2. Anular factura: registrar estado anulado con motivo obligatorio y bloquear si ya tiene pagos.
  3. Eliminar físicamente: reservar solo para limpieza técnica excepcional.

### Caja

- Movimientos:
  Permite ingresos/egresos manuales y además gastos en efectivo pueden sincronizarse como movimientos de caja. Desde Caja Segura Fase 2, los movimientos ya no deben editarse ni borrarse físicamente: se anulan con motivo y el historial queda visible.
- Apertura operativa:
  Desde Caja Operativa Fase 1, el sistema exige caja abierta antes de confirmar ventas y avisa cuando detecta una caja ya abierta al entrar.
- Arqueos:
  El cierre guarda `saldo_final_real`, pero no aparece una conciliación fuerte ni bloqueo posterior.
- Cierre de caja:
  Marca `estado=0`, pero no se observan protecciones documentadas para impedir alteraciones indirectas posteriores. Al salir de la app con una caja abierta ahora existe salida protegida: permite cerrar caja y salir, salir sin cerrar o cancelar, sin forzar cierres parciales. Ademas, la fase 2 bloquea anulaciones de movimientos y resincronizaciones de gastos cuando la caja ya esta cerrada.
- Edición posterior:
  Riesgo medio a alto, pero ahora mas contenido: si un gasto impactó una caja cerrada, sus cambios sensibles o su eliminación quedan bloqueados para no reescribir movimientos históricos en silencio.
- Qué debería pasar:
  Una caja cerrada debería considerarse congelada. Las correcciones posteriores deberían entrar como ajustes compensatorios, no reescritura silenciosa del pasado.

### Gastos

- Edición:
  Permite cambiar fecha, categoría, clasificación, descripción, monto, medio de pago y otros datos, pero ya no puede mutar en silencio un movimiento de caja cerrada ni convertirse en gasto en efectivo fuera de una caja abierta válida.
- Eliminación:
  Hoy hace borrado físico.
- Caja:
  Existe sincronización con `caja_movimientos`. Desde Caja Segura Fase 2B, un gasto en efectivo exige caja abierta y fecha compatible con la caja actual; si no, el guardado se bloquea. Además, si el gasto ya impactó una caja cerrada, no puede reescribir ese movimiento histórico.
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
  MVP implementado parcialmente. Pendiente: revisar cobertura total de reportes secundarios y definir estrategia formal de compensación de caja.
- `fix/compras-anulacion-segura`
  MVP implementado parcialmente. Pendiente: definir reversión segura cuando la compra ya generó factura proveedor o deuda comercial.
- `fix/stock-ajustes-responsables`
  Reforzar que todo cambio de stock pase por ajuste con motivo y dejar mejor trazabilidad.
- `fix/facturas-proveedor-seguras`
  MVP implementado parcialmente. Pendiente: evaluar si a futuro hace falta una bitácora explícita de pagos o ajustes compensatorios más detallados.
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

- Editar una compra activa por flujo seguro y confirmar que no cambia stock.
- Crear compra, anularla y verificar que el stock baja exactamente la cantidad ingresada.
- Intentar anular una compra ya anulada y confirmar bloqueo.
- Crear compra, vender parte del stock e intentar anularla con stock insuficiente; debe bloquear.
- Crear compra con factura proveedor y confirmar que la anulación se bloquea sin borrar historial.

### Ventas

- Registrar venta, verificar descuento de stock y movimiento de CC si corresponde.
- Eliminar venta y comprobar impacto en stock, historial y cuenta corriente.

### Clientes

- Desactivar cliente con ventas y saldo.
- Revisar que el detalle y la cuenta corriente sigan accesibles.

### Facturas proveedor

- Editar importe antes y después de registrar pagos parciales.
- Anular factura sin pagos y verificar que siga visible como historial.
- Intentar anular factura ya anulada y confirmar bloqueo.
- Intentar anular factura con pagos y confirmar bloqueo sin borrar historial ni tocar `pagado`.

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

## 2026-05-19 - feature/cc-clientes-segura

### Cuenta corriente clientes
- Estado: corregido parcialmente con MVP de anulacion segura.
- El libro `cc_clientes_mov` ahora conserva historial, calcula deuda solo con movimientos activos y deja trazabilidad minima de anulacion.
- Los pagos de clientes ya no deben corregirse borrando ni reescribiendo deuda: se anulan con motivo obligatorio, se bloquea la doble anulacion y se impide anular desde clientes movimientos que nacieron de una venta fiada.
- Si un pago genero ingreso en caja, la anulacion tambien anula su `caja_movimientos` vinculado para mantener caja y cuenta corriente alineadas.
- La venta fiada sigue compensando deuda al anularse desde Historial de ventas, sin borrar asientos previos.
- Riesgo que queda abierto: el formulario heredado de movimientos sigue permitiendo ajustes manuales y notas de credito; el MVP endurece especialmente pagos y ventas relacionadas, pero no agrega todavia una bitacora avanzada de cambios manuales.
- UI: el detalle del cliente ahora debe advertir `El movimiento no se borrara. Quedara anulado para conservar historial.` y usar modal Nexar en lugar de confirmaciones nativas.

## 2026-05-19 - feature/gastos-seguros

### Gastos
- Estado: corregido parcialmente con MVP de anulacion segura.
- `gastos` ahora conserva historial con `anulado`, `anulada_at`, `anulada_por` y `motivo_anulacion`.
- Los gastos ya no deben corregirse borrando ni editando en forma destructiva: se anulan con motivo obligatorio y luego se vuelven a cargar si hace falta.
- Si un gasto en efectivo genero un `EGRESO` en caja abierta, la anulacion tambien anula ese movimiento vinculado para mantener caja y gasto alineados.
- Los reportes y resumenes de rentabilidad pasan a ignorar gastos anulados, pero el listado de gastos los mantiene visibles como historial.
- UI: `gastos.html` debe usar modal Nexar para anular y mostrar antes de confirmar fecha, categoria, medio de pago, importe y descripcion reales del gasto.
- Riesgo que queda abierto: el endpoint conserva el nombre `gasto_eliminar` por compatibilidad interna, aunque operativamente ahora anula en lugar de borrar.
