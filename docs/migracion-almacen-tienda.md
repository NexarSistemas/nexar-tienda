# Migracion Almacen -> Tienda

## Cuentas corrientes

- Clientes: la fuente de verdad sigue siendo `cc_clientes_mov`.
- Proveedores: la fuente de verdad para deuda comercial pasa a ser `facturas_proveedores`.
- `cc_proveedores_mov` queda como legado/libro auxiliar y no debe considerarse la fuente principal de deuda.

## Alcance de este refactor

- Centraliza helpers minimos de calculo.
- Mantiene compatibilidad con la base y las rutas actuales.
- No conecta todavia compras con facturas de proveedores.
