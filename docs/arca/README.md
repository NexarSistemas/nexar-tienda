# ARCA Fase 5

## Modo simulación para desarrollo

Esta fase agrega emisión simulada de comprobantes ARCA para poder seguir desarrollando el flujo sin depender de un punto de venta habilitado en ARCA/AFIP.

### Variable de entorno

- `ARCA_MODO_SIMULACION=true`
  Activa emisión simulada.
- `ARCA_MODO_SIMULACION=false`
  Deja la app preparada para WSFE real, pero en esta fase todavía no emite CAE real.

Si la variable no está definida, en desarrollo el valor por defecto es simulación activa.

### Qué hace en simulación

- Busca la venta existente.
- Genera número de comprobante incremental por punto de venta y tipo.
- Genera CAE simulado y vencimiento simulado.
- Guarda el comprobante en `arca_comprobantes` con `modo=simulacion` y estado `MODO_TEST`.
- No llama WSFE real.

### Qué hace fuera de simulación

- Valida si la configuración ARCA mínima está completa.
- Si falta configuración, guarda el resultado con estado `ERROR_CONFIG`.
- Si la configuración existe, deja registrado `SIN_CONEXION` porque la emisión real sigue pendiente de fases posteriores.

### Integración actual

- Ruta `POST /arca/ventas/<venta_id>/emitir`
- Botón en el detalle de venta (`ticket`) para administradores cuando la venta todavía no tiene comprobante ARCA.
- Vista `ARCA / Estado` mostrando si el sistema está trabajando en simulación o preparado para WSFE real.

## Ajustes generales de venta

ARCA solo emite ventas cuyos importes fiscales pueden reconstruirse desde el
snapshot de `ventas` y `ventas_detalle`. El contrato actual guarda descuento
adicional e interés de financiación como importes generales, pero no conserva su
imputación por alícuota ni su tratamiento tributario. Por lo tanto, una venta
con cualquiera de esos ajustes no se envía a ARCA: distribuirlos entre
alícuotas sería inventar semántica fiscal. La venta, caja e inventario no se
modifican; debe definirse esa imputación en una evolución fiscal posterior.
