# Estado operativo — 21 de julio de 2026

## Rol del repositorio

Producto comercial de escritorio visible como **Nexar Comercio**. El identificador técnico compatible continúa siendo `nexar-tienda`.

## Estado confirmado

- Repositorio activo y release estable documentada: `v1.36.7`.
- La DEMO para instalaciones nuevas dura 14 días; las DEMO históricas conservan el período ya otorgado.
- La protección anti-reinstalación consulta identidad remota y no concede una DEMO nueva sin verificación.
- Los planes pagos pueden contratarse directamente sin activar previamente DEMO o BASICA.
- `Mi Plan` reutiliza una única resolución de precios por render y conserva la alineación entre producto, acciones y checkout.
- Las licencias vencidas o administrativamente bloqueadas no conceden permisos de negocio.
- El SDK `nexar_licencias` es la capa compartida de validación; el checkout se delega a `nexar-pagos`.

## Decisiones vigentes

- BASICA es permanente mientras la licencia sea válida.
- PRO y FULL son temporales y requieren renovación.
- Seleccionar un plan, abrir Mercado Pago o pulsar “Ya pagué” no habilita permisos hasta confirmar una licencia oficial.
- Los repos `nexar-comercio` y `nexar-almacen`, si aparecen separados, se consideran legacy y no sustituyen este repositorio.

## Próximos trabajos

Los siguientes avances deben partir de Issues abiertos y no reabrir los correctivos ya fusionados sobre licencias, DEMO y precios. ARCA, Mercado Pago y cambios estructurales requieren PR pequeños y validación específica.

## Integraciones

- `nexar_licencias`: validación y cache de licencias.
- `nexar-pagos`: creación de preferencias y confirmación de pagos.
- `nexar-admin`: operación administrativa de licencias, demos, clientes y precios.
- `nexar-ai-context`: contexto transversal del ecosistema.
