# Contexto completo — Migración Nexar Almacén → Nexar Tienda

Estoy trabajando en el proyecto Nexar Tienda, usando Nexar Almacén solo como referencia funcional.

## Estado actual del trabajo

Ya se hizo únicamente esto:

```bash
git checkout main
git pull origin main
git checkout -b refactor/tienda-cc-core

No se implementó nada todavía.
No se modificaron archivos.
No se hicieron commits.
No se abrió PR.
No se tocó Mercado Pago.
No se tocaron licencias.
No se tocó Nexar Finanzas.
No se migró OpenFoodFacts.

La rama actual esperada es:

refactor/tienda-cc-core

Antes de continuar, verificar:

git status
git branch --show-current

Si no estoy en refactor/tienda-cc-core, cambiar a esa rama o crearla desde main actualizado.

Objetivo general

Unificar funcionalidades útiles de Nexar Almacén dentro de Nexar Tienda, usando Nexar Tienda como base principal y moderna.

La idea NO es fusionar ambos repos completos ni reescribir Tienda.

Nexar Tienda será el núcleo principal para varios rubros:

tienda
almacén
kiosco
regalería
librería
ferretería
otros rubros futuros

Comercialmente pueden venderse como productos separados, pero técnicamente la base será Nexar Tienda.

Nexar Almacén queda solo como referencia funcional y fuente de migración parcial.

Repos involucrados

Repositorio base principal:

NexarSistemas/nexar-tienda

Repositorio de referencia:

NexarSistemas/nexar-almacen

No trabajar directamente sobre main.

Diagnóstico ya realizado

Codex ya analizó ambos repos y detectó lo siguiente:

Estado de Nexar Tienda

Nexar Tienda ya heredó bastante de Almacén, pero quedó en estado híbrido.

La cuenta corriente de clientes sí está conectada al flujo de ventas.

Proveedores quedó dividido entre dos modelos distintos:

cc_proveedores_mov
facturas_proveedores

Solo uno parece tener uso real visible actualmente.

Archivos críticos detectados en Nexar Tienda
Backend principal
routes/main.py
database.py
app.py

Puntos importantes:

routes/main.py

contiene muchas rutas y lógica de dominio.

Es archivo crítico y riesgoso para seguir creciendo sin modularizar.

database.py

contiene creación de tablas, migraciones SQLite y funciones de acceso a datos.

app.py

parece ser más liviano o punto de entrada, pero debe revisarse antes de tocar imports.

Layout / sidebar
templates/base.html

El sidebar ya está modularizado por layout/permisos, pero todavía no distingue rubro Tienda/Almacén.

No modificar sidebar agresivamente en esta etapa.

Dashboard
templates/dashboard.html

El dashboard actual es liviano.

Todavía no muestra:

deuda clientes
deuda proveedores
facturas vencidas
facturas por vencer

No migrar dashboard completo de Almacén.

Más adelante agregar solo KPIs/alertas puntuales.

Clientes
templates/clientes.html
templates/cliente_detalle.html

Tienda ya tiene mejor implementación que Almacén para clientes.

Detectado:

clientes
cc_clientes_mov
venta_id
saldo calculado al vuelo
reconciliación desde ventas

Conclusión:

NO migrar cc_clientes de Almacén encima de Tienda.

Mantener la lógica actual de Tienda.

Solo mejorar si hace falta:

UI
textos
validaciones
reportes
dashboard
vencimientos si todavía faltan

Riesgo menor detectado:

En cliente_detalle.html hay textos que dicen “Compras” cuando en realidad se refieren a ventas del cliente. Corregir después, no ahora si no es parte del refactor.

Proveedores
templates/proveedores.html
templates/proveedor_detalle.html

Tienda tiene proveedores básicos y cuenta corriente por movimientos.

También existe tabla facturas_proveedores en el esquema, pero sin flujo real activo claro.

Problema principal:

cc_proveedores_mov
vs
facturas_proveedores

Hay duplicidad conceptual.

Esta es la deuda técnica más peligrosa.

Compras
templates/compras.html
templates/compra_form.html

Compras en Tienda:

impactan stock
guardan historial
NO generan movimiento automático de cuenta corriente proveedor
NO generan deuda proveedor automáticamente

Regla importante:

No tocar impacto de stock en esta etapa.

Las compras deben seguir funcionando como hoy.

Más adelante se puede agregar:

compra contado
compra cuenta corriente

Si es compra a cuenta corriente, recién ahí generar facturas_proveedores.

Ventas / POS
templates/punto_venta.html
routes/main.py

Ventas en Tienda:

separan creación de venta
descuentan stock en paso separado
reconcilian cuenta corriente cliente si corresponde

Riesgo importante:

No tocar ventas en este refactor.

Cualquier cambio futuro debe respetar:

crear_venta()
decrementar_stock_venta()
reconciliar cc_cliente

para evitar duplicar o saltear stock.

Stock

Tienda tiene:

stock
stock_movimientos

No migrar stock desde Almacén.

Tienda gana en stock.

Comparación Tienda vs Almacén
Tienda gana en:
clientes
ventas
stock_movimientos
temporadas
blueprint/routes/main.py
layout actual
integración moderna
licencias
Mercado Pago
Almacén gana en:
facturas de proveedores
vencimientos de proveedores
pagos parciales de facturas
alertas de facturas vencidas
alertas de facturas por vencer
modelo operativo de deuda proveedor
Decisiones técnicas ya tomadas
1. Clientes

Mantener modelo actual de Tienda.

Fuente de verdad:

cc_clientes_mov

Cuando el movimiento viene de una venta, debe conservar:

venta_id

No reemplazar por modelo viejo de Almacén.

No migrar cc_clientes completo de Almacén.

Almacén solo puede usarse como referencia conceptual para:

vencimientos
pagos
ajustes
notas de crédito

Pero Tienda ya tiene mejor trazabilidad porque relaciona movimientos con ventas.

2. Proveedores

Usar:

facturas_proveedores

como fuente de verdad para deuda comercial de proveedores.

No seguir usando cc_proveedores_mov como fuente principal de deuda.

cc_proveedores_mov debe quedar como:

legado temporal
o libro auxiliar
o futura base para ajustes/pagos no asociados

pero NO debe convivir indefinidamente como segunda fuente de saldo.

La deuda proveedor debe calcularse desde facturas:

saldo_factura = importe - pagado
deuda_proveedor = suma de saldos de facturas pendientes

Estados calculados, no guardados:

PAGADA
VENCIDA
POR VENCER
VIGENTE
3. Compras

Compras siguen impactando stock como hoy.

No tocar ese flujo todavía.

Más adelante, cuando se integre deuda proveedor:

Si compra es contado:
    no generar deuda

Si compra es cuenta corriente:
    generar factura_proveedor

Evitar duplicar deuda.

Una compra no siempre equivale a una factura.

Puede haber:

una factura con varias compras
una compra sin factura
una factura manual
pago parcial
pago total

Por eso inicialmente conviene permitir facturas manuales por proveedor antes de conectar compras automáticamente.

4. Dashboard

No migrar dashboard completo de Almacén.

Agregar más adelante widgets puntuales:

total deuda proveedores
facturas vencidas
facturas por vencer
total deuda clientes
clientes con deuda
stock bajo
5. Sidebar

No modificar agresivamente.

Primero integrar acceso desde:

proveedor_detalle.html

Después, si hace falta, agregar acceso en sidebar.

6. Rubro / unidades

No implementar en esta rama.

Va después de estabilizar cuentas corrientes.

Idea futura:

NEXAR_PRODUCTO=nexar-tienda
NEXAR_RUBRO=tienda

o:

NEXAR_PRODUCTO=nexar-tienda
NEXAR_RUBRO=almacen

No crear producto separado nexar-almacen en licencias.

El rubro se maneja dentro de la app.

Producto debe seguir siendo único.

NO crear:

ProductoTienda
ProductoAlmacen

Usar un producto común con campos futuros:

tipo_unidad
permite_fraccionado
rubro

Unidades futuras:

UNIDADES_TIENDA = [
    "unidad",
    "paquete",
]

UNIDADES_ALMACEN = [
    "unidad",
    "paquete",
    "kg",
    "gramo",
    "litro",
    "ml",
    "docena",
]
Objetivo específico de la rama actual

Rama:

refactor/tienda-cc-core

Objetivo:

Preparar núcleo técnico de cuentas corrientes sin agregar funcionalidades grandes.

NO implementar todavía facturas completas si no está acordado.

Esta rama debe enfocarse en:

ordenar dominio
crear helpers/servicios mínimos
centralizar cálculos
documentar fuente de verdad
reducir riesgo antes de migrar UI
Qué se debe hacer ahora
Paso actual

Continuar desde:

refactor/tienda-cc-core

Primero ejecutar:

git status
git branch --show-current

Confirmar que no hay cambios sucios inesperados.

Tareas para Codex en esta rama
1. Confirmar uso real de tablas

Buscar en Nexar Tienda:

cc_clientes_mov
cc_proveedores_mov
facturas_proveedores

Determinar:

dónde se crean
dónde se leen
dónde se escriben
qué rutas dependen de cada una
qué templates las muestran
qué funciones en database.py las usan

No volver a analizar todo el repo desde cero.

Enfocarse solo en cuenta corriente y facturas.

2. Crear o proponer capa de servicios mínima

Preferencia inicial:

services/
├── cc_clientes_service.py
├── cc_proveedores_service.py
├── facturas_proveedores_service.py
└── rubros_service.py

Pero en esta rama probablemente conviene empezar solo con:

services/cc_clientes_service.py
services/facturas_proveedores_service.py

o incluso:

services/cuentas_corrientes.py

si el proyecto está todavía muy centralizado.

No hacer refactor gigante.

No mover todas las rutas a blueprints todavía.

No romper routes/main.py.

3. Centralizar cálculos

Crear helpers puros y seguros para:

Clientes
calcular_saldo_cliente(cliente_id)

Debe usar el modelo actual de Tienda:

cc_clientes_mov

y respetar venta_id.

Proveedores
calcular_saldo_factura(factura)
calcular_estado_factura(factura, hoy=None)
calcular_deuda_proveedor(proveedor_id)

Debe usar como fuente:

facturas_proveedores

No usar cc_proveedores_mov como fuente de deuda principal.

4. Compatibilidad

No borrar cc_proveedores_mov.

No borrar rutas existentes.

No romper templates existentes.

No hacer migración destructiva.

No eliminar columnas.

No cambiar nombres de tablas existentes.

Todo cambio de base debe ser defensivo:

CREATE TABLE IF NOT EXISTS ...
ALTER TABLE solo si columna no existe
DEFAULT seguro
5. Documentar decisión de dominio

Agregar comentarios técnicos o documentación mínima donde corresponda:

Clientes:
fuente de verdad = cc_clientes_mov

Proveedores:
fuente de verdad = facturas_proveedores

cc_proveedores_mov:
legado/libro auxiliar, no usar para deuda principal

Puede ser en:

docs/migracion-almacen-tienda.md

o comentarios en servicios.

Si se crea documentación, que sea breve y útil.

Qué NO hacer ahora

No implementar todavía:

alta completa de factura proveedor
pago parcial
pago total
dashboard de alertas
sidebar nuevo
rubro/unidades
venta fraccionada
conexión automática compra → factura
backfill masivo

No tocar:

Mercado Pago
licencias
Supabase
Netlify
nexar_licencias
Nexar Finanzas
OpenFoodFacts

No modificar:

ventas
stock
temporadas
pagos Mercado Pago
planes
upgrade de licencias

salvo que sea estrictamente necesario para importaciones, y si lo fuera, explicarlo antes.

Riesgos detectados
Riesgo 1 — Duplicidad proveedor

Actualmente Tienda parece tener dos modelos:

cc_proveedores_mov
facturas_proveedores

Si ambos calculan deuda, habrá inconsistencias.

Ejemplo peligroso:

Proveedor A:
cc_proveedores_mov dice deuda $50.000
facturas_proveedores dice deuda $80.000

Solución:

facturas_proveedores será fuente de verdad
cc_proveedores_mov queda legado/auxiliar
Riesgo 2 — Compras y deuda duplicada

Compras hoy impactan stock, pero no deuda.

Si se conecta mal:

compra genera deuda
factura manual también genera deuda

se duplica deuda proveedor.

Solución futura:

compra contado → no genera deuda
compra cuenta corriente → genera factura/deuda
factura manual → solo si no viene de compra

No implementar todavía.

Riesgo 3 — Stock

No tocar stock.

Tienda tiene:

stock_movimientos

y no se debe reemplazar por lógica de Almacén.

Riesgo 4 — Ventas

No tocar ventas.

Tienda separa:

crear venta
descontar stock
reconciliar cuenta corriente cliente

No romper ese flujo.

Riesgo 5 — Base SQLite existente

Hay que mantener compatibilidad con bases viejas.

No hacer cambios destructivos.

Riesgo 6 — routes/main.py demasiado grande

routes/main.py es crítico.

No meter toda la lógica nueva ahí.

Extraer funciones de cálculo a servicios/helpers.

Orden de implementación futuro
Etapa 1 — actual
refactor/tienda-cc-core

Objetivo:

servicios/helpers mínimos
centralización de cálculos
decisión de dominio documentada
sin grandes cambios funcionales
Etapa 2
feat/tienda-facturas-proveedor

Objetivo:

activar facturas_proveedores como flujo real

Tareas futuras:

listar facturas por proveedor
crear factura manual
editar factura
registrar pago parcial
registrar pago total
calcular saldo
calcular estado
mostrar vencidas
mostrar por vencer
integrar en proveedor_detalle
Etapa 3
feat/compras-deuda-proveedor

Objetivo:

conectar compras con deuda proveedor sin romper stock

Tareas futuras:

mantener compra actual
agregar condición contado/cuenta corriente
si cuenta corriente, generar factura_proveedor
si contado, no generar deuda
evitar duplicados
test compra contado
test compra cuenta corriente
Etapa 4
feat/tienda-dashboard-alertas

Objetivo:

agregar KPIs financieros sin cambiar lógica base

Tareas futuras:

total deuda proveedores
facturas vencidas
facturas por vencer
total deuda clientes
clientes con deuda
stock bajo
Etapa 5
feat/tienda-rubro-unidades

Objetivo:

preparar Tienda para tienda/almacen/kiosco/etc.

No implementar hasta cerrar cuentas corrientes.

Ramas recomendadas
refactor/tienda-cc-core
feat/tienda-facturas-proveedor
feat/compras-deuda-proveedor
feat/tienda-dashboard-alertas
feat/tienda-rubro-unidades
feat/venta-fraccionada
Resultado esperado para esta continuación

En esta rama actual, quiero que Codex haga lo siguiente:

Verifique estado Git.
Confirme que está en refactor/tienda-cc-core.
Revise solo usos de:
cc_clientes_mov
cc_proveedores_mov
facturas_proveedores
Proponga o implemente refactor mínimo de servicios/helpers, según corresponda.
No cambie comportamiento visible todavía.
No toque ventas, stock, licencias ni Mercado Pago.
Deje listo el núcleo para que la próxima rama pueda implementar feat/tienda-facturas-proveedor.
Pruebas esperadas si se llega a modificar algo

Ejecutar como mínimo:

python -m py_compile app.py database.py routes/main.py

Si se agregan servicios:

python -m py_compile services/*.py

Si existe forma de iniciar la app:

python iniciar.py

Validar manualmente:

abre dashboard
abre proveedores
abre detalle proveedor
abre clientes
abre detalle cliente
abre ventas/POS
abre compras

No hace falta probar Mercado Pago en esta rama.

Comandos Git sugeridos si la rama queda bien

Solo después de revisar cambios:

git status
git diff --stat
git diff

Si todo está correcto:

git add .
git commit -m "refactor: preparar nucleo de cuentas corrientes"
git push -u origin refactor/tienda-cc-core

Luego abrir PR hacia main.

No hacer tag todavía.

No versionar todavía salvo que yo lo pida.

Resumen corto para recordar

Tienda ya tiene clientes CC mejor que Almacén.

No migrar clientes desde Almacén.

El problema real está en proveedores:

cc_proveedores_mov vs facturas_proveedores

Decisión:

facturas_proveedores = fuente de verdad de deuda proveedor
cc_proveedores_mov = legado/auxiliar

La rama actual refactor/tienda-cc-core debe dejar ordenado ese núcleo, sin implementar pantallas grandes ni pagos todavía.
