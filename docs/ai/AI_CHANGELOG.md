# AI_CHANGELOG.md

Registro de avances hechos por Codex, Copilot, Gemini o ChatGPT.

## 2026-07-20 - Codex - fix/mi-plan-price-lookups

### Tarea
Implementar el Issue #127 para evitar consultas remotas repetidas al
renderizar `Mi Plan` y cerrar el hallazgo pendiente del PR #123.

### Diagnostico
- `_build_mi_plan_view()` llamaba `_format_price_label()` dentro de loops para
  acciones de checkout y otra vez para el listado de planes comerciales.
- `_format_price_label()` usaba `get_price_for_plan()`, que podia entrar al
  resolvedor central y consultar Supabase por cada plan antes de aplicar cache
  o fallback.
- Una sola carga de `/mi-plan` podia encadenar multiples timeouts seriales si
  Supabase estaba lento o sin respuesta.

### Que se cambio
- `services/pricing_resolver.py` ahora expone `resolve_plan_prices(...)` para
  resolver un conjunto de planes en una sola obtencion y devolver un mapa
  reutilizable por plan.
- La resolucion en lote mantiene precios centralizados, aliases actuales,
  cache runtime y fallback local. Para evitar inconsistencias visuales, el
  render usa una sola fuente por lote: Supabase si cubre todos los planes
  pedidos, luego cache runtime si tambien los cubre, y finalmente fallback
  local para todo el conjunto.
- `routes/main.py` arma un mapa de etiquetas de precio una sola vez por render
  de `/mi-plan` y lo reutiliza en `checkout_actions`, renovacion y
  `commercial_plans`, sin consultas ocultas dentro de loops.
- El checkout real sigue resolviendo el precio autorizado con
  `get_price_for_plan()` al crear el contexto real de compra; la optimizacion
  solo aplica a la visualizacion.
- `tests/test_license_integration.py` y `tests/test_pricing_resolver.py`
  agregan regresiones para una sola resolucion por render, consistencia visual,
  fallback y separacion respecto del checkout real.

### Archivos modificados
- `services/pricing_resolver.py`
- `routes/main.py`
- `tests/test_license_integration.py`
- `tests/test_pricing_resolver.py`
- `docs/ai/AI_CHANGELOG.md`

### Que se probo
- `.venv\\Scripts\\python.exe -m pytest tests/test_license_integration.py tests/test_pricing_resolver.py tests/test_mercadopago_checkout.py` -> 182 passed.

### Alcance
- No se cambiaron importes comerciales, Supabase remoto, Mercado Pago, Nexar
  Pagos ni `nexar_licencias`.
- El cartel naranja de acciones del plan sigue fuera de alcance y no se corrige
  en este cambio.

## 2026-07-20 - Codex - fix/license-background-refresh-context

### Tarea
Implementar el Issue #126 para hacer seguro el refresco automatico de
licencias fuera de request y cerrar el hallazgo pendiente del PR #121.

### Diagnostico
- `_license_auto_refresh_loop()` ejecutaba `_refresh_license_response()` con
  solo `app_context`.
- Cuando existia un checkout pendiente, `_resolve_license_from_pending_checkout()`
  terminaba llamando `_get_license_holder_profile()` y
  `_get_current_user_contact_profile()`.
- `_get_current_user_contact_profile()` leia `session` sin verificar si habia
  request activa, por lo que el refresh de fondo podia fallar con
  `RuntimeError: Working outside of request context` y dejar sin confirmar una
  licencia ya emitida.

### Que se cambio
- `routes/main.py` ahora separa un perfil persistido reutilizable en
  `_get_persisted_activation_customer_profile()`, construido desde configuracion
  local y datos de licencia ya guardados.
- `_get_current_user_contact_profile()` usa `has_request_context()` como
  defensa y solo consulta `session` durante una peticion web real.
- `_get_activation_customer_profile()` compone prioridades sin duplicar logica:
  primero datos del formulario cuando existen, luego datos persistidos, y usa
  datos del usuario autenticado solo como complemento dentro de request.
- El refresh en background mantiene el flujo de checkout pendiente con solo
  contexto de aplicacion y sin depender de `session`, `request` ni `flash`.
- `tests/test_license_integration.py` suma regresiones para helpers sin request,
  refresh con solo `app_context`, persistencia de email/codigo de vendedor y
  el loop de auto-refresh sin sleeps reales.

### Archivos modificados
- `routes/main.py`
- `tests/test_license_integration.py`
- `docs/ai/AI_CHANGELOG.md`

### Que se probo
- `.venv\\Scripts\\python.exe -m pytest tests/test_license_integration.py tests/test_license_tiers.py` -> 183 passed.

### Alcance
- No se cambiaron reglas comerciales, Mercado Pago, Supabase remoto ni el SDK
  `nexar_licencias`.
- El fix solo separa correctamente las fuentes de datos entre request y
  background para que la confirmacion automatica siga usando la licencia oficial
  como unica autoridad.

## 2026-07-20 - Codex - fix/demo-admin-state-scan

### Tarea
Corregir el hallazgo de revisión del PR #129 para que la detección de estados
administrativos DEMO siga revisando todos los campos compatibles antes de
descartar un bloqueo.

### Diagnostico
- `_get_row_admin_state()` devolvía el primer estado no vacío entre
  `row.estado`, `mensaje.estado`, `mensaje.license_status` y
  `mensaje.demo_admin_status`.
- Si `row.estado` contenía un estado comercial o de seguimiento como
  `pendiente` o `contactado`, el escaneo terminaba antes de llegar a un bloqueo
  administrativo guardado en metadata.
- Eso podía hacer que `blocked_matches` ignorara una DEMO bloqueada y que el
  resolvedor la tratara como activa, vencida o usada.

### Que se cambio
- `services/demo_eligibility.py` ahora normaliza todos los candidatos de estado
  una sola vez, recorre el conjunto completo y devuelve inmediatamente cualquier
  alias incluido en `ADMIN_BLOCKED_STATES`.
- Si no existe bloqueo administrativo, conserva como fallback el primer estado
  informativo no vacío, sin cambiar la política determinista ya implementada en
  PR #129 para DEMO activa, vencida o usada.
- `tests/test_license_integration.py` agrega regresiones para bloqueos en
  `demo_admin_status`, `license_status`, `mensaje.estado`, estado vacío,
  aliases administrativos y prevalencia global del bloqueo frente a otra fila
  activa o pendiente.

### Archivos modificados
- `services/demo_eligibility.py`
- `tests/test_license_integration.py`
- `docs/ai/AI_CHANGELOG.md`

### Que se probo
- `.venv\\Scripts\\python.exe -m pytest tests/test_license_integration.py tests/test_license_tiers.py` -> 176 passed.
- `.venv\\Scripts\\python.exe -m pytest` -> 296 passed.
- `.venv\\Scripts\\python.exe -m compileall -q app.py database.py iniciar.py run.py routes services licensing modules config tests` -> OK.
- `git diff --check` -> OK.

### Alcance
- No se modificó la política de selección determinista de DEMO activa/vencida.
- No se tocaron precios, Mercado Pago, permisos BASICA/PRO/FULL, Supabase
  remoto, Nexar Admin ni `nexar_licencias`.

## 2026-07-20 - Codex - fix/demo-eligibility-review-findings

### Tarea
Implementar el Issue #125 para cerrar vulnerabilidades de elegibilidad y
concurrencia DEMO detectadas en el refuerzo anti-reinstalacion.

### Diagnostico
- `services/supabase_license_api.py` reintentaba cualquier rechazo HTTP de
  `solicitudes_demo` con un payload legacy que podia omitir hashes de identidad
  fuerte aun ante conflictos de unicidad o carreras concurrentes.
- `services/demo_eligibility.py` tomaba `matches[0]` y podia ignorar bloqueos
  administrativos presentes en otra coincidencia fuerte del mismo equipo.
- `routes/main.py` reconsultaba tras una falla de alta DEMO, pero solo
  recuperaba una DEMO activa; si la reconsulta devolvia `expired` o `blocked`,
  terminaba mostrando un error generico de verificacion.

### Que se cambio
- `services/supabase_license_api.py` ahora clasifica el error remoto y solo
  hace fallback compatible cuando la respuesta demuestra incompatibilidad de
  esquema por columnas nuevas o schema cache desactualizada. Conflictos `409`,
  `duplicate key`, errores de autenticacion/RLS, validacion o `5xx` ya no se
  reintentan con un payload sin identidad fuerte.
- El fallback DEMO quita unicamente las columnas incompatibles detectadas de
  forma explicita, preservando el mayor nivel posible de identidad fuerte en
  esquemas legacy.
- `services/demo_eligibility.py` revisa todas las coincidencias fuertes antes de
  decidir: cualquier estado administrativo bloqueado prevalece globalmente y la
  seleccion no bloqueada pasa a ser determinista, priorizando DEMO activa con
  vencimiento valido mas conservador, luego DEMO vencida/usada y por ultimo
  registros ambiguos.
- `routes/main.py` ahora aplica la politica central tambien despues de una
  reconsulta tras falla de alta DEMO: si encuentra DEMO vigente la recupera sin
  extender fechas; si encuentra `expired`, `already_used` o `blocked`, niega una
  nueva DEMO con ese resultado y no muestra un error generico de red.
- `tests/test_license_integration.py` agrega regresiones para conflictos `409`,
  `duplicate key`, errores de autorizacion y `500`, fallback solo por esquema,
  bloqueos administrativos en multiples coincidencias, seleccion determinista y
  reconsulta posterior al alta fallida.

### Archivos modificados
- `services/supabase_license_api.py`
- `services/demo_eligibility.py`
- `routes/main.py`
- `tests/test_license_integration.py`
- `docs/ai/AI_CHANGELOG.md`

### Que se probo
- `.venv\\Scripts\\python.exe -m pytest tests/test_license_integration.py tests/test_license_tiers.py` -> 166 passed.
- `.venv\\Scripts\\python.exe -m pytest` -> 286 passed.
- `.venv\\Scripts\\python.exe -m compileall -q app.py database.py iniciar.py run.py routes services licensing modules config tests` -> OK.
- `git diff --check` -> OK.

### Dependencias / alcance
- La proteccion fuerte ante carreras simultaneas sigue dependiendo de que la
  migracion `supabase/migrations/2026-07-18_harden_solicitudes_demo_identity.sql`
  este aplicada en Supabase/Admin o exista una restriccion equivalente.
- No se tocaron precios, Mercado Pago, permisos de BASICA/PRO/FULL, Nexar
  Admin, Nexar Pagos ni el SDK `nexar_licencias`.

## 2026-07-20 - Codex - fix/license-enforcement-review-findings

### Tarea
Implementar el Issue #124 para corregir enforcement de licencias bloqueadas y
casos `SIN_PLAN` que todavia podian recuperar acceso por permanencia BASICA,
flags legacy o clasificacion comercial inconsistente.

### Diagnostico
- `database._resolve_license_snapshot()` seguia exponiendo
  `plan_base_permanente=True` para una BASICA con estado administrativo
  bloqueado, suspendido, revocado o anulado si existian flags legacy.
- `sync_license_from_remote()` podia persistir `basica_activada=1` y
  `license_plan_base_permanente=1` aunque la licencia ya resolviera
  `plan_efectivo=SIN_PLAN`.
- El middleware de `app.py` restauraba BASICA por fallback local cuando fallaba
  la validacion guardada, sin exigir que la licencia siguiera siendo utilizable.
- `licensing/planes.py` evaluaba PRO/FULL por `plan_original` antes de cortar
  por `plan_efectivo=SIN_PLAN`, dejando una ventana donde podia caer en
  `mensual_activo`.

### Que se cambio
- `database.py` ahora invalida `plan_base_permanente` y desactiva
  `basica_activada` cuando el estado administrativo bloquea la licencia o el
  plan efectivo ya es `SIN_PLAN`.
- `app.py` solo restaura BASICA desde fallback legacy si el estado resuelto
  sigue siendo BASICA utilizable; una licencia bloqueada ya no recupera acceso.
- `licensing/planes.py` trata `plan_efectivo=SIN_PLAN` como no utilizable antes
  de clasificar PRO/FULL como activos y hace explicito que
  `licencia_utilizable` exige un plan efectivo distinto de `SIN_PLAN`.
- `tests/test_license_integration.py` suma regresiones para BASICA bloqueada,
  anulada, fallback legacy bloqueado, PRO/FULL con `SIN_PLAN` y redireccion de
  rutas de negocio a `/mi-plan`.

### Archivos modificados
- `database.py`
- `app.py`
- `licensing/planes.py`
- `tests/test_license_integration.py`
- `docs/ai/AI_CHANGELOG.md`

### Que se probo
- `.venv\\Scripts\\python.exe -m pytest tests/test_license_integration.py tests/test_license_tiers.py` -> 156 passed.
- `.venv\\Scripts\\python.exe -m pytest` -> 276 passed.
- `.venv\\Scripts\\python.exe -m compileall -q app.py database.py iniciar.py run.py routes services licensing modules config tests` -> OK.
- `git diff --check` -> OK.

### Fuera de alcance
- No se tocaron Mercado Pago, Supabase, SDK externo, versiones, tags ni
  releases.
- No se modifico documentacion comercial adicional porque el comportamiento
  publico ya estaba documentado; solo se actualizo el changelog tecnico.

## 2026-07-18 - Codex - feature/mi-plan-license-ux

### Tarea
Implementar el Issue #106 para mejorar `Mi Plan` tomando Nexar Finanzas solo
como referencia funcional/UX y adaptandolo al flujo real de Nexar Comercio.

### Diagnostico
- `/mi-plan` ya refrescaba licencia, calculaba acciones, mostraba modulos,
  datos del titular, codigo de vendedor, checkout y seguimiento post-pago.
- El template mezclaba reglas de presentacion con decisiones de negocio:
  estado original/efectivo, vencimiento, renovacion, upgrades, revalidacion y
  post-pago.
- La fuente real de estado ya estaba en `get_license_status_context()` y las
  acciones en `get_plan_actions()`, ambos alineados con los Issues #109, #110,
  #111, #112, #113 y #114.
- Nexar Finanzas agrupa plan, estado, vencimiento, refresco y checkout en una
  pantalla de licencia, pero Comercio requiere DEMO/BASICA/PRO/FULL, upgrades,
  codigo de vendedor y activacion inicial directa; no se copio codigo.

### Que se cambio
- Se agrego un modelo centralizado `_build_mi_plan_view()` que prepara resumen
  visible, avisos, limites, modulos, acciones de checkout/manuales, renovacion,
  post-pago y datos comerciales.
- `templates/mi_plan.html` ahora renderiza el modelo y deja de mostrar detalles
  tecnicos como fallback SDK en el resumen principal.
- La pantalla muestra BASICA como permanente, PRO/FULL con vencimiento y dias,
  DEMO activa/vencida con acciones pagas, y bloqueos administrativos sin
  presentarlos como planes activos.
- Los precios de botones comerciales se resuelven con `get_price_for_plan()`; no
  se hardcodearon precios ni se modificaron Nexar Pagos/Mercado Pago.

### Archivos modificados
- `routes/main.py`
- `templates/mi_plan.html`
- `tests/test_license_integration.py`
- `README.md`
- `docs/MODULOS_Y_PLANES.md`
- `docs/ai/AI_CHANGELOG.md`

### Que se probo
- `.venv/bin/python -m pytest tests/test_license_integration.py tests/test_license_tiers.py` -> 150 passed.

### Fuera de alcance
- No se cambio Supabase, Nexar Pagos, Mercado Pago, precios centrales, tags ni
  Releases.

## 2026-07-18 - Codex - security/demo-anti-reinstall

### Tarea
Implementar el Issue #113 para reforzar la proteccion contra multiples DEMO por
reinstalacion, borrado local, cambio de carpeta, restauracion o manipulacion
simple de flags.

### Diagnostico
- `activation_id` se genera en `services/supabase_license_api.generate_activation_id()`
  con usuario, host, `/etc/machine-id`/DBus, UUID DMI y pista de disco; en el
  flujo inicial se prefiere `get_current_hwid()` del SDK cuando esta disponible.
- El identificador se persistia en solicitudes o checkout, pero la DEMO nueva se
  activaba localmente aunque `create_demo_request()` fallara.
- `demo_mode`, `demo_install_date` y flags de activacion viven en SQLite; borrar
  o restaurar la base podia dejar una instalacion aparentemente nueva.
- `solicitudes_demo` recibia producto, email y un JSON en `mensaje` con
  `activation_id` y fechas DEMO, pero no habia consulta previa centralizada ni
  restriccion unica versionada para concurrencia.
- Sin conexion, una instalacion sin evidencia podia obtener DEMO local; eso
  confiaba en datos locales editables.
- El email era util para contacto, pero no suficientemente fuerte como unica
  identidad del equipo.

### Que se cambio
- Se agrego `services/demo_eligibility.py` con identidad DEMO, normalizacion,
  hashes SHA-256 por producto, matching legacy y estados `eligible`, `active`,
  `expired`, `already_used`, `blocked`, `offline_unverified` y `error`.
- `/activacion-inicial` consulta `solicitudes_demo` antes de crear una DEMO; solo
  persiste permisos locales despues de una respuesta remota valida o recupera
  una DEMO remota vigente sin extender fechas.
- Si la verificacion o el registro remoto fallan en una instalacion sin DEMO
  confirmada, se conserva la activacion inicial pendiente, se marca estado sin
  permisos y se ofrecen reintento o planes pagos.
- `create_demo_request()` envia columnas nuevas de identidad/hash cuando existen
  y mantiene fallback a payload legacy para tablas aun no migradas.
- La UI oculta/deshabilita la accion DEMO cuando ya fue usada o esta bloqueada,
  sin exponer HWID, `activation_id` completo ni errores raw.
- Se agrego migracion versionada no ejecutada para endurecer idempotencia remota
  con indice unico parcial por producto e `identity_hash`.

### Archivos modificados
- `routes/main.py`
- `services/demo_eligibility.py`
- `services/supabase_license_api.py`
- `templates/activacion_inicial.html`
- `tests/test_license_integration.py`
- `README.md`
- `docs/MODULOS_Y_PLANES.md`
- `docs/ai/AI_CHANGELOG.md`
- `supabase/migrations/2026-07-18_harden_solicitudes_demo_identity.sql`

### Que se probo
- `.venv/bin/python -m pytest tests/test_license_integration.py tests/test_license_tiers.py` -> 143 passed.

### Limitaciones
- La defensa no intenta resistir a un usuario con control total del equipo.
- La concurrencia fuerte entre altas simultaneas requiere aplicar la migracion
  Supabase incluida o una RPC/constraint equivalente en el servicio remoto.
- Si el SDK no entrega HWID y el sistema no expone senales estables compartidas
  entre usuarios del SO, el segundo usuario queda limitado por los datos legacy
  disponibles.

## 2026-07-18 - Codex - feature/direct-plan-activation

### Tarea
Implementar el Issue #112 para permitir compra y activacion directa inicial de
BASICA, PRO y FULL sin DEMO ni planes intermedios obligatorios.

### Diagnostico
- Una instalacion nueva completa primero `/registro-inicial`, luego queda con
  `activation_initial_completed=0` y el middleware la lleva a
  `/activacion-inicial`.
- La pantalla inicial ya listaba DEMO, BASICA, PRO y FULL, pero el seguimiento
  post-pago dependia principalmente de una licencia local guardada; sin
  `license_key`, `/api/licencia/estado` devolvia `sin_licencia` sin consultar
  una licencia emitida por `activation_id`.
- DEMO se activaba solo si el usuario elegia DEMO; no habia activacion automatica
  para planes pagos, pero faltaba estado explicito de checkout pendiente.
- El checkout existente se arma con producto, plan destino, precio centralizado,
  `external_reference`, email y `activation_id`; para alta usa
  `ALTA|activation_id|producto|plan`.
- El flujo "Ya pague" refrescaba licencias guardadas y hacia polling desde
  `Mi plan`, pero no podia completar una compra inicial sin clave local aunque
  Licencias ya hubiera emitido una licencia asociada al equipo.
- La fuente de verdad para permisos sigue siendo la licencia efectiva resuelta
  por SDK/Supabase y sincronizada localmente; existe riesgo si se concedieran
  modulos solo por seleccion, checkout o declaracion manual, por eso no se hizo.
- Dependencia externa detectada: Nexar Pagos, Licencias o Admin deben emitir la
  licencia oficial vinculada al mismo `activation_id`/HWID enviado en checkout.
  Si no existe esa licencia, la app mantiene estado pendiente.

### Que se cambio
- Se agrego estado local de seguimiento de checkout inicial:
  `activation_checkout_status`, `activation_checkout_plan`,
  `activation_checkout_activation_id`, `activation_checkout_started_at` y
  `activation_checkout_checked_at`.
- BASICA, PRO y FULL desde instalacion inicial quedan como `alta_licencia`,
  conservan el mismo `activation_id` estable y no completan la activacion
  inicial hasta confirmar licencia oficial.
- "Ya pague" ahora, cuando no hay clave local pero existe checkout pendiente,
  consulta Supabase por producto, plan esperado y `activation_id`/HWID mediante
  la integracion existente; solo sincroniza si encuentra licencia activa con
  `license_key`.
- `/api/licencia/estado` y el refresh de `Mi plan` devuelven mensajes claros de
  pendiente, confirmado o error temporal, sin activar permisos ante errores de
  red.
- La pantalla inicial comunica que DEMO, BASICA, PRO y FULL son caminos
  independientes y muestra acciones especificas por plan.
- `Mi plan` muestra el panel post-pago cuando hay una compra inicial pendiente.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `services/supabase_license_api.py`
- `templates/activacion_inicial.html`
- `templates/mi_plan.html`
- `tests/test_license_integration.py`
- `README.md`
- `docs/MODULOS_Y_PLANES.md`
- `docs/ai/AI_CHANGELOG.md`

### Que se probo
- `.venv/bin/python -m pytest tests/test_license_integration.py tests/test_license_tiers.py` -> 139 passed.
- `.venv/bin/python -m pytest` -> 259 passed.
- `.venv/bin/python -m compileall -q app.py database.py iniciar.py run.py routes services licensing modules config tests` -> OK.

### Fuera de alcance
- No se implementa la proteccion avanzada contra reinstalaciones del Issue #113.
- No se modifican precios, Mercado Pago interno, Nexar Pagos, GitHub Actions,
  builds, instaladores, tags ni Releases.

## 2026-07-18 - Codex - fix/expired-license-behavior

### Tarea
Implementar el Issue #110 para definir y aplicar el comportamiento de licencias vencidas DEMO, PRO y FULL.

### Diagnostico
- El vencimiento local se calculaba en `database._resolve_license_snapshot()` y `get_demo_status()`.
- El estado efectivo se consumia desde `database.get_license_info()`, pero PRO/FULL vencidas podian degradar a DEMO o BASICA segun flags legacy.
- La UI de `Mi plan` y `Licencia` mezclaba estado raw, plan original y plan efectivo, pudiendo mostrar fallback o estados tecnicos.
- Las rutas de negocio dependian de modulos efectivos, pero una DEMO vencida seguia resolviendo modulos DEMO si no se bloqueaba antes.

### Archivos modificados
- `app.py`
- `database.py`
- `licensing/planes.py`
- `licensing/permisos.py`
- `services/license_sdk.py`
- `routes/main.py`
- `templates/base.html`
- `templates/mi_plan.html`
- `templates/licencia.html`
- `tests/test_license_integration.py`
- `README.md`
- `docs/MODULOS_Y_PLANES.md`
- `docs/ai/AI_CHANGELOG.md`

### Que se cambio
- Estados administrativos explicitos y aliases (`revocada`, `suspendida`, `bloqueada`, `anulada`, cancelada y variantes masculinas) resuelven `SIN_PLAN` antes que cualquier fecha.
- DEMO vencida queda sin modulos efectivos, no reinicia ni extiende el periodo y solo permite recuperar/comprar licencia o salir.
- PRO y FULL vencidas conservan `plan_original`, pero el plan efectivo pasa a `SIN_PLAN`; no degradan a BASICA ni DEMO y no conceden permisos PRO/FULL.
- BÁSICA valida sigue permanente y sin vencimiento por fechas legacy; si esta bloqueada administrativamente, tambien queda `SIN_PLAN`.
- El middleware bloquea rutas de negocio con licencia no utilizable y mantiene accesibles `Mi plan`, `Licencia`, `/api/licencia/estado`, revalidacion/checkout y salida.
- `Mi plan` y `Licencia` muestran estado normalizado, plan original, plan efectivo y mensajes especificos para DEMO/PRO/FULL vencidas.
- La activacion inicial ya no permite iniciar otra DEMO desde el flujo normal cuando la DEMO local esta vencida.

### Consulta, exportacion y backup
- No se habilito modo completo de solo lectura, exportacion ni backup con licencia vencida.
- Motivo: las rutas actuales mezclan vistas de consulta con acciones de escritura; habilitarlas parcialmente podria mantener uso normal de la app o introducir regresiones.
- Politica aplicada en este issue: bloqueo minimo consistente y acceso solo a recuperacion comercial/estado/salida.

### Que se probo
- `python -m pytest tests/test_license_integration.py tests/test_license_tiers.py` no se pudo ejecutar porque `python` no existe en el entorno.
- `.venv/bin/python -m pytest tests/test_license_integration.py tests/test_license_tiers.py` -> 131 passed.
- `.venv/bin/python -m pytest` -> 251 passed.
- `.venv/bin/python -m compileall -q app.py database.py iniciar.py run.py routes services licensing modules config tests` -> OK.

### Fuera de alcance
- No se implementa proteccion avanzada contra reinstalaciones del Issue #113.
- No se implementa compra directa nueva del Issue #112 mas alla de conservar los flujos existentes.
- No se toca Mercado Pago, Supabase, Nexar Pagos, Nexar Licencias, Nexar Admin, builds, instaladores, tags ni Releases.

## 2026-07-15 - Codex - fix/basica-permanente

### Tarea
Implementar el Issue #111 para confirmar que la licencia BASICA es permanente, sin vencimiento temporal ni renovaciones.

### Archivos modificados
- `database.py`
- `services/license_sdk.py`
- `licensing/planes.py`
- `routes/main.py`
- `tests/test_license_integration.py`
- `README.md`
- `docs/ai/AI_CHANGELOG.md`

### Que se cambio
- La fuente local efectiva ignora `license_expires_at` para BASICA y no calcula expiracion ni dias restantes aunque existan fechas legacy pasadas o futuras.
- La sincronizacion/activacion local conserva BASICA sin vencimiento y no depende de una fecha futura para mantenerla activa.
- Estados administrativos explicitos (`revocada`, `suspendida`, `bloqueada`, `anulada`) ahora bloquean BASICA en lugar de tratarla como permanente activa.
- El contexto de UI muestra BASICA valida como permanente y evita renovaciones/cuentas regresivas; si esta bloqueada, muestra estado bloqueado sin ofrecer renovacion.
- Se agregaron pruebas para fechas legacy, cambio grande de fecha evaluada, permisos BASICA, ausencia de permisos PRO/FULL y bloqueo administrativo.

### Que se probo
- `python -m pytest tests/test_license_tiers.py tests/test_license_integration.py tests/test_license_upgrade_request_fallback.py` -> 127 passed.
- `python -m compileall -q app.py database.py iniciar.py run.py routes services licensing modules config tests` -> OK.
- `python -m pytest` -> 245 passed.
- `python -m compileall .` intento recorrer `.venv` y artefactos locales de build, por lo que se reemplazo por la validacion acotada al codigo versionado.

### Fuera de alcance
- No se modifica el ciclo DEMO de 14 dias.
- No se implementa el comportamiento general de vencimientos de #110.
- No se implementa compra directa de #112 ni proteccion de reinstalacion de #113.
- No se toca Mercado Pago, checkout, precios, VERSION, CHANGELOG.md, Tag ni Release.

## 2026-07-14 - Codex - chore/sdk-build-dependency

### Tarea
Implementar el Issue #116 para que los builds empaquetados instalen `nexar_licencias v1.2.0` desde `requirements-build.txt`, siguiendo el patron validado en Nexar Finanzas.

### Archivos modificados
- `.github/workflows/build.yml`
- `requirements-build.txt`
- `README.md`
- `docs/ai/AI_CHANGELOG.md`

### Mecanismo anterior
- El workflow de Windows y Linux validaba un PAT `NEXAR_SDK_TOKEN` contra GitHub API.
- Luego hacia checkout separado de `rolojnb/nexar_licencias` en `nexar_licencias_src`.
- Finalmente instalaba `requirements.txt` y despues `pip install ./nexar_licencias_src`, dejando dos mecanismos paralelos para dependencias de build.

### Mecanismo nuevo
- `requirements.txt` queda reservado para desarrollo local, ejecucion desde codigo fuente y tests.
- `requirements-build.txt` incluye `requirements.txt` y fija `nexar-licencias` a `git+ssh://git@github.com/rolojnb/nexar_licencias.git@v1.2.0`.
- Los jobs Windows y Linux configuran acceso SSH con `webfactory/ssh-agent@v0.9.0`, agregan `github.com` a `known_hosts` con `ssh-keyscan` y ejecutan `pip install -r requirements-build.txt`.
- Se elimina el checkout separado del SDK y la instalacion manual `pip install ./nexar_licencias_src`.

### Secret SSH requerido
- `NEXAR_LICENCIAS_DEPLOY_KEY`: clave privada de una Deploy Key de solo lectura configurada en `rolojnb/nexar_licencias`.

### Validaciones
- `python -m pip install -r requirements.txt`
- `python -m pytest tests/test_license_integration.py tests/test_license_tiers.py tests/test_license_upgrade_request_fallback.py` -> 121 passed.
- `python -m pip install -r requirements-build.txt` -> instala `nexar-licencias-1.2.0` desde `v1.2.0` por Git SSH. El primer intento en sandbox fallo por DNS local; el reintento con red habilitada paso.
- `python -c "import nexar_licencias, importlib.metadata as m; print(nexar_licencias.__file__); print(m.version('nexar-licencias'))"` -> SDK instalado desde `.venv/site-packages`, version `1.2.0`.
- Import explicito de `nexar_licencias`, `cache`, `config`, `device`, `plans`, `validator`, `verifier_local` y `verifier_online`.
- `python -m pytest` -> 239 passed.
- `PYINSTALLER_CONFIG_DIR=/tmp/pyinstaller-cache pyinstaller build/nexar_tienda_linux.spec --distpath dist --workpath build/work --noconfirm` -> build Linux OK, `dist/NexarTienda` generado. El primer intento sin `PYINSTALLER_CONFIG_DIR` fallo porque el entorno local no podia escribir en `/home/.../.cache/pyinstaller`.
- Windows no se compilo localmente por estar en runner Linux; queda cubierto por el workflow Windows con el mismo `requirements-build.txt`, `webfactory/ssh-agent` y secret `NEXAR_LICENCIAS_DEPLOY_KEY`.

### Riesgos o limitaciones
- La instalacion local de `requirements-build.txt` requiere acceso SSH al repositorio privado.
- Los specs de PyInstaller ya incluyen los hidden imports requeridos de `nexar_licencias`; no se modifican reglas funcionales de DEMO, BASICA, PRO ni FULL.

## 2026-07-14 - Codex - fix/demo-lifecycle-14-days

### Tarea
Auditar y asegurar el ciclo de vida de la licencia DEMO para que las nuevas instalaciones duren exactamente 14 dias, sin recortar ni reactivar DEMO historicas.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `licensing/planes.py`
- `tests/test_license_integration.py`
- `README.md`
- `docs/ai/AI_CHANGELOG.md`

### Que se cambio
- Se centralizo el calculo deterministico de DEMO en `calculate_demo_lifecycle()`, con soporte para fecha fija en tests y vencimiento exclusivo persistido en `demo_expires_at`.
- Se definio la convencion: el dia de activacion cuenta como dia valido; una DEMO de 14 dias iniciada el `2026-01-01` vence al comenzar el `2026-01-15`.
- `get_demo_status()` ahora migra datos legacy de forma idempotente, completa `demo_expires_at` cuando falta, conserva vencimientos validos ya otorgados y no muestra dias negativos.
- El onboarding y el reintento remoto de solicitud DEMO usan las fechas persistidas para no extender la prueba al completar el flujo nuevamente.
- Los mensajes de estado diferencian DEMO nuevas de 14 dias y DEMO historicas, evitando afirmar que una DEMO antigua fue originalmente de 14 dias.

### Que se probo
- `python -m pytest tests/test_license_integration.py -k "activacion_inicial_demo_guarda_datos_y_habilita_ingreso"`
- `python -m pytest tests/test_license_integration.py`
- `python -m pytest tests/test_license_tiers.py tests/test_license_upgrade_request_fallback.py`
- `python -m pytest`

## 2026-07-14 - Codex - feature/integrar-sdk-licencias-centralizado

### Tarea
Integrar Nexar Comercio con el contrato publico actual del SDK `nexar_licencias` para centralizar configuracion, mantener compatibilidad legacy y reforzar tests de licencias.

### Archivos modificados
- `services/license_sdk.py`
- `services/supabase_license_api.py`
- `tests/test_license_integration.py`
- `.env.example`
- `README.md`
- `docs/ai/AI_CHANGELOG.md`

### Que se cambio
- `services/license_sdk.py` ahora carga `SDKConfig`/`DEFAULT_CONFIG` desde el SDK cuando estan disponibles, pasa `config=` a `validar_licencia_detalle`, `validar_licencia` y cache si el contrato lo soporta, y usa `normalize_plan`/`resolve_effective_license` del SDK como fuente preferente.
- Se conservaron defensas locales para estados suspendida/bloqueada/anulada/revocada, evitando mantener FULL/PRO activo cuando el remoto indica bloqueo.
- El fallback online de `services/supabase_license_api.py` ahora prefiere `NEXAR_LICENSES_VALIDATION_URL` y `NEXAR_LICENSES_SUPABASE_KEY`, conserva `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_KEY`, `NEXAR_CACHE_FILE` y `NEXAR_CACHE_DAYS`, y respeta timeouts `NEXAR_LICENSES_*`.
- Se documentaron las variables recomendadas del SDK en `.env.example` y `README.md`.
- Se agregaron tests para configuracion central/aliases legacy, fallback online con cache, licencias suspendidas, timeouts Supabase y no exposicion de secretos en logs/debug.

### Que se probo
- `python -m pytest tests/test_license_integration.py`
- `python -m pytest`

## 2026-07-02 - Codex - docs/issue-107-context-alignment

### Tarea
Validar la documentacion local de Nexar Comercio contra el contexto central actualizado, sin tocar logica funcional ni areas protegidas.

### Archivos modificados
- `AGENTS.md`
- `README.md`
- `docs/ai/AI_CHANGELOG.md`

### Que se cambio
- Se aclaro que `nexar-ai-context` es un repo externo usado como contexto transversal del ecosistema.
- Se confirmo en la documentacion local que el producto visible sigue siendo `Nexar Comercio` y que el repo tecnico se mantiene como `nexar-tienda`.
- Se corrigio la referencia a `nexar-comercio` y `nexar-almacen` para tratarlos como repos legacy/no activos, evitando confusiones con el producto vigente.

### Que se probo
- Relevamiento documental de `AGENTS.md`, `README.md`, `CHANGELOG.md` y `docs/ai/AI_CONTEXT.md` contra `nexar-ai-context`.

## 2026-06-24 - Codex - release/v1.36.6

### Tarea
Cerrar el fix de solicitudes manuales de upgrade con versionado patch, validacion completa y documentacion minima de release, manteniendo el alcance en Nexar Comercio.

### Archivos modificados
- `VERSION`
- `README.md`
- `CHANGELOG.md`
- `build/nexar_tienda.iss`
- `docs/ai/AI_CHANGELOG.md`

### Que se cambio
- Se confirmo la version actual `1.36.5` y se preparo el siguiente patch `1.36.6`.
- Se sincronizo la metadata de version en app, README, changelog e instalador Windows.
- El resumen comercial del release quedo enfocado en la validacion obligatoria de email para upgrades manuales y en la migracion SQL de `codigo_vendedor` para `solicitudes_upgrade`.

### Que se probo
- `.\.venv\Scripts\python.exe -m pytest`

## 2026-06-24 - Codex - fix/manual-upgrade-email-required

### Tarea
Corregir el flujo de solicitud manual de upgrade desde `Mi Plan` para no registrar filas en `solicitudes_upgrade` con `email=""`, mantener `codigo_vendedor` cuando exista y dejar lista la migracion SQL de Supabase, sin tocar Mercado Pago ni Nexar Admin.

### Archivos modificados
- `app.py`
- `routes/main.py`
- `templates/acuerdo_licencia.html`
- `tests/test_license_integration.py`
- `tests/test_license_upgrade_request_fallback.py`
- `supabase/migrations/2026-06-24_add_codigo_vendedor_to_solicitudes_upgrade.sql`
- `docs/ai/AI_CHANGELOG.md`

### Que se cambio
- Se agrego una validacion previa a `create_upgrade_request()` en `mi_plan_solicitar_upgrade()` para frenar la solicitud manual cuando el email resuelto del titular queda vacio.
- En ese caso la app vuelve a `Mi Plan`, muestra un mensaje claro para completar el email del titular y evita cualquier insercion en `public.solicitudes_upgrade`.
- Se reviso la persistencia del formulario `Datos del titular`: ya guarda `license_owner_email` en configuracion local, por lo que no hizo falta tocar ese flujo.
- Se confirmo y cubrio con tests que `create_upgrade_request()` conserva `codigo_vendedor` en el payload y tambien en el reintento compatible cuando el campo existe.
- Se agrego la migracion SQL `supabase/migrations/2026-06-24_add_codigo_vendedor_to_solicitudes_upgrade.sql` para incorporar `codigo_vendedor` en `public.solicitudes_upgrade` sin ocultar el dato desde la app.
- Se reforzo la robustez del area de licencias con un `logger` explicito en `app.py` y una lectura defensiva del perfil actual para evitar errores 500 en tests y rutas permitidas.
- Se agrego una linea informativa minima en la vista publica del acuerdo de licencia para mantener coherencia con el texto visible esperado.
- Se ajustaron tests de integracion y fallback para cubrir envio manual con email valido, con y sin `codigo_vendedor`, y el bloqueo cuando falta email.

### Que se probo
- `python -m unittest tests.test_license_integration.LicenseIntegrationTests.test_solicitud_manual_desde_demo_envia_alta_licencia tests.test_license_integration.LicenseIntegrationTests.test_solicitud_manual_sin_email_no_envia_a_supabase_y_muestra_mensaje tests.test_license_integration.LicenseIntegrationTests.test_solicitud_manual_upgrade_conserva_codigo_vendedor tests.test_license_integration.LicenseIntegrationTests.test_solicitud_manual_con_email_valido_y_sin_codigo_vendedor_envia_solicitud_igual tests.test_license_integration.LicenseIntegrationTests.test_build_checkout_context_permite_alta_licencia_desde_demo tests.test_license_integration.LicenseIntegrationTests.test_build_checkout_context_con_license_key_sigue_usando_cambio_plan tests.test_license_upgrade_request_fallback`
- `.\.venv\Scripts\python.exe -m pytest tests/test_license_integration.py -k "activacion_inicial_demo_guarda_datos_y_habilita_ingreso or activacion_inicial_demo_no_guarda_dedupe_si_falla_envio_remoto or acuerdo_licencia_es_publico_y_muestra_license_txt or create_demo_request_reintenta_con_payload_compatible or full_se_muestra_como_full_y_debug_expone_resolucion or licencia_y_mi_plan_son_accesibles_con_recuperacion_pendiente"`
- `.\.venv\Scripts\python.exe -m pytest`

## 2026-06-24 - Codex - fix/solicitud-manual-licencias

### Tarea
Cerrar el fix de solicitudes manuales de licencia con versionado patch y release minimo, manteniendo el alcance acotado al error `PGRST204` por `origen` en `solicitudes_upgrade`.

### Archivos modificados
- `services/supabase_license_api.py`
- `tests/test_license_upgrade_request_fallback.py`
- `supabase/migrations/2026-06-24_add_origen_to_solicitudes_upgrade.sql`
- `VERSION`
- `README.md`
- `CHANGELOG.md`
- `build/nexar_tienda.iss`
- `docs/ai/AI_CHANGELOG.md`

### Que se cambio
- `create_upgrade_request` ahora reintenta con un payload compatible cuando Supabase rechaza campos nuevos como `origen`, cubriendo tambien la solicitud manual `alta_licencia` desde `Mi Plan`.
- Se agrego un test puntual para el fallback de `solicitudes_upgrade` y una migracion SQL minima para incorporar `origen` sin romper datos existentes.
- Se cerro el release patch `v1.36.5` sincronizando version en app, README, changelog e instalador Windows.

### Que se probo
- `python -m py_compile services/supabase_license_api.py tests/test_license_upgrade_request_fallback.py`
- `python -m unittest tests.test_license_upgrade_request_fallback tests.test_license_integration.LicenseIntegrationTests.test_solicitud_manual_desde_demo_envia_alta_licencia tests.test_license_integration.LicenseIntegrationTests.test_solicitud_manual_upgrade_conserva_codigo_vendedor`
- `python -m pytest` fallo porque el entorno actual no tiene instalado `pytest` (`No module named pytest`).
- `python -m unittest` se ejecuto como suite global y expuso fallas ajenas a este fix en areas preexistentes del repo, por lo que no se uso como senal limpia de regresion de esta correccion.

## 2026-06-18 - Codex - release/v1.36.4

### Tarea
Cerrar el release de Nexar Comercio para la Fase 1B de activacion inicial obligatoria, limitando los cambios finales a versionado y documentacion de release.

### Archivos modificados
- `VERSION`
- `README.md`
- `CHANGELOG.md`
- `build/nexar_tienda.iss`
- `docs/ai/AI_CHANGELOG.md`

### Que se cambio
- Se detecto la version actual `1.36.3` y se preparo el siguiente patch `1.36.4`.
- Se alineo la metadata de version en app, README, changelog e instalador Windows.
- El resumen comercial del release quedo enfocado en activacion inicial obligatoria, seleccion de plan, DEMO automatica de 14 dias y registro del lead DEMO en Supabase.

### Que se probo
- `python -m compileall routes services tests`
- `.\.venv\Scripts\python.exe -m pytest tests\test_license_integration.py -k "activacion_inicial or create_demo_request_reintenta"` no se pudo usar como senal confiable por `PermissionError` del entorno al crear/limpiar temporales de Windows y escribir `.pytest_cache`.

## 2026-06-18 - Codex - docs/legal-packaging-license-inventory

### Tarea
Actualizar el inventario legal local para responder el comentario del PR #100 incorporando las referencias de empaquetado que usan o copian `LICENSE.txt`.

### Archivos modificados
- `docs/ai/LEGAL_LICENSE_SYNC_INVENTORY.md`
- `docs/ai/AI_CHANGELOG.md`

### Que se cambio
- Se agregaron al inventario las referencias de `build/nexar_tienda.iss` que usan `LICENSE.txt` como licencia del instalador Windows y lo incluyen dentro del instalador.
- Se agrego la referencia de `build_deb.sh` que copia `LICENSE.txt` dentro del paquete Debian cuando existe.
- No se modifico la logica de la app, `LICENSE.txt`, templates, rutas, licencia comercial ni validaciones.

### Que se probo
- `git diff --check`

## 2026-06-18 - Codex - chore/legal-license-sync

### Tarea
Iniciar la sincronizacion legal solicitada para Nexar Sistemas con inventario local de `nexar-tienda` y trazabilidad de las limitaciones para completar el inventario remoto.

### Archivos modificados
- `docs/ai/LEGAL_LICENSE_SYNC_INVENTORY.md`
- `docs/ai/AI_CHANGELOG.md`

### Que se cambio
- Se documento el inventario legal local del repositorio disponible, incluyendo presencia de `LICENSE.txt`, ausencia de `LICENSE`/`LICENSE.md`, referencias legales y flujos de aceptacion existentes.
- Se dejo registrado que no se pudo comparar contra `rolojnb/nexar-legal/LICENSE.txt` ni inventariar todos los repositorios activos de `rolojnb` y `NexarSistemas` porque el entorno no puede acceder a GitHub por bloqueo de proxy/API.
- No se modifico contenido legal ni logica funcional de licencias, planes, pagos, Supabase, workflows, builds o deploys.

### Que se probo
- `python3 -m py_compile routes/main.py`
- `git diff --check`

## 2026-06-16 - Codex - release/v1.36.3

### Tarea
Cerrar la feature de DEMO 14 dias y codigo de vendedor como release patch, actualizando solo versionado y documentacion minima sin agregar funcionalidad nueva.

### Archivos modificados
- `VERSION`
- `README.md`
- `CHANGELOG.md`
- `build/nexar_tienda.iss`
- `docs/ai/AI_CHANGELOG.md`

### Que se cambio
- Se detecto la version actual `1.36.2` y se preparo el siguiente patch `1.36.3`.
- Se alineo la metadata de version en app, README, changelog e instalador Windows.
- El resumen comercial de release quedo enfocado en DEMO de 14 dias, compatibilidad con DEMO existentes y asociacion opcional de codigo de vendedor.

### Que se probo
- `python -m pytest` no pudo ejecutarse porque el entorno actual no tiene instalado el modulo `pytest` (`No module named pytest`).
- `python -m unittest tests.test_license_integration.LicenseIntegrationTests.test_demo_vencido_no_se_convierte_en_basica_gratis tests.test_license_integration.LicenseIntegrationTests.test_demo_nuevo_arranca_con_14_dias tests.test_license_integration.LicenseIntegrationTests.test_licencia_solicitar_guarda_y_envia_codigo_vendedor_normalizado tests.test_license_integration.LicenseIntegrationTests.test_mi_plan_guardar_codigo_vendedor_demo_sin_license_key_guarda_local tests.test_license_integration.LicenseIntegrationTests.test_mi_plan_guardar_codigo_vendedor_licencia_activa_sincroniza_supabase tests.test_license_integration.LicenseIntegrationTests.test_solicitud_manual_upgrade_conserva_codigo_vendedor tests.test_license_integration.LicenseIntegrationTests.test_validate_license_key_sincroniza_codigo_vendedor_si_existe tests.test_license_integration.LicenseIntegrationTests.test_sync_license_from_remote_no_borra_codigo_vendedor_local`

## 2026-06-16 - Codex - fix/demo-14-dias

### Tarea
Reducir la duracion de la DEMO de Nexar Comercio de 30 dias a 14 dias con diff minimo, manteniendo intacta la logica comercial existente de BASICA, PRO y FULL.

### Archivos modificados
- `database.py`
- `licensing/planes.py`
- `tests/test_license_integration.py`
- `docs/ai/AI_CHANGELOG.md`

### Que se cambio
- Se ajusto la definicion central de DEMO en `database.py` para que el periodo de prueba pase de 30 a 14 dias, tanto en `TIER_LIMITS` como en el default persistido `config.demo_dias` y en el fallback de `get_demo_status()`.
- Se mantuvo compatibilidad con demos ya creadas: el calculo sigue leyendo `demo_install_date` y el valor persistido en `config`, por lo que no se alteran fechas ya registradas fuera del nuevo default para instalaciones nuevas.
- Se hizo un ajuste visual minimo en `licensing/planes.py` para que, cuando la DEMO ya vencio, el usuario vea el mensaje claro `Tu demo de 14 dias vencio` y el aviso quede visible en la pantalla existente de licencia.
- No se duplico logica de compra ni activacion: la app sigue usando los flujos comerciales ya existentes para BASICA, PRO y FULL.

### Que se probo
- `python -m unittest tests.test_license_integration.LicenseIntegrationTests.test_demo_vencido_no_se_convierte_en_basica_gratis tests.test_license_integration.LicenseIntegrationTests.test_demo_nuevo_arranca_con_14_dias tests.test_license_integration.LicenseIntegrationTests.test_demo_muestra_basica_pro_y_full tests.test_license_integration.LicenseIntegrationTests.test_checkout_disponible_en_demo_sin_license_key tests.test_license_integration.LicenseIntegrationTests.test_build_checkout_context_permite_alta_licencia_desde_demo`

## 2026-06-16 - Codex - fix/codigo-vendedor-licencia

### Tarea
Agregar un codigo de vendedor opcional al flujo de licencia para capturarlo localmente y enviarlo a Supabase al solicitar, activar o pedir upgrade de licencia, con diff minimo y sin tocar ARCA ni la logica comercial de planes.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/licencia.html`
- `services/supabase_license_api.py`
- `services/license_sdk.py`
- `tests/test_license_integration.py`
- `docs/ai/AI_CHANGELOG.md`

### Que se cambio
- Se agrego `license_vendor_code` a la configuracion local y se expone en `get_license_info()` como `vendor_code`.
- La pantalla `licencia.html` ahora muestra el campo opcional `Codigo de vendedor` tanto para solicitar licencia como para activarla, reutilizando el valor guardado localmente.
- El codigo se normaliza con `trim + uppercase`, se guarda localmente y se envia a Supabase solo cuando tiene valor en `create_license_request`, `create_upgrade_request` y `activate_license`.
- La sincronizacion local de licencia preserva el codigo_vendedor ya guardado si el payload remoto no lo informa, para que un refresh no lo borre.
- No se modifico `external_reference` ni el contrato actual del checkout Mercado Pago; el codigo_vendedor queda asociado en Supabase por los flujos de solicitud/activacion/upgrade ya existentes.

### Que se probo
- `python -m unittest tests.test_license_integration.LicenseIntegrationTests.test_solicitud_manual_desde_demo_envia_alta_licencia tests.test_license_integration.LicenseIntegrationTests.test_solicitud_manual_upgrade_conserva_codigo_vendedor tests.test_license_integration.LicenseIntegrationTests.test_validate_license_key_sincroniza_codigo_vendedor_si_existe tests.test_license_integration.LicenseIntegrationTests.test_sync_license_from_remote_no_borra_codigo_vendedor_local`

## 2026-06-12 - Codex - release/v1.36.1

### Tarea
Cerrar la correccion de sincronizacion de licencias como release patch, sin tocar funcionalidad y actualizando solo versionado/documentacion minima.

### Archivos modificados
- `VERSION`
- `README.md`
- `CHANGELOG.md`
- `build/nexar_tienda.iss`
- `docs/ai/AI_CHANGELOG.md`

### Que se cambio
- Se detecto la version actual `1.36.0` y se preparo el release patch `1.36.1`.
- Se actualizo la version visible en `VERSION`, `README.md` e instalador Inno Setup.
- Se agrego una entrada breve en `CHANGELOG.md` orientada a usuario final para el ajuste de sincronizacion de licencias.

### Que se probo
- `python -m unittest tests.test_license_integration.LicenseIntegrationTests.test_refresh_licencia_no_encontrada_mantiene_full_local_vigente tests.test_license_integration.LicenseIntegrationTests.test_refresh_licencia_suspendida_no_mantiene_full tests.test_license_integration.LicenseIntegrationTests.test_refresh_licencia_vencida_degrada_a_demo_si_no_hay_basica tests.test_license_integration.LicenseIntegrationTests.test_refresh_licencia_error_conexion_mantiene_cache_local_vigente tests.test_license_integration.LicenseIntegrationTests.test_pro_vencida_sin_base_permanente_no_regala_basica tests.test_license_integration.LicenseIntegrationTests.test_full_vencida_sin_base_permanente_no_regala_basica`

## 2026-06-12 - Codex - fix/licencia-refresh-cache-vigente

### Tarea
Corregir solo el flujo de refresco/sincronizacion de licencia desde `Mi plan`, manteniendo diff minimo y sin tocar Mercado Pago, ARCA ni logica comercial fuera de licencias.

### Archivos modificados
- `services/license_sdk.py`
- `database.py`
- `routes/main.py`
- `templates/mi_plan.html`
- `tests/test_license_integration.py`
- `docs/ai/AI_CHANGELOG.md`

### Que se cambio
- El refresh de licencia ahora distingue entre licencia remota no encontrada, licencia suspendida/bloqueada/anulada, licencia remota vencida y errores temporales de conexion.
- Si la licencia remota no aparece pero hay cache premium local vigente, la app mantiene PRO/FULL hasta `expires_at` local y muestra una advertencia clara en vez de dejar un mensaje ambiguo.
- Si la licencia remota esta suspendida/bloqueada/anulada, o si la mensual remota ya vencio sin BASICA permanente, la app deja de mantener premium local y degrada a BASICA o DEMO segun corresponda.
- La UI de `Mi plan` actualiza el estado visual aunque el refresh devuelva advertencia, y el texto auxiliar del boton se reemplazo por uno orientado a usuario final.

### Que se probo
- `python -m unittest tests.test_license_integration.LicenseIntegrationTests.test_refresh_licencia_no_encontrada_mantiene_full_local_vigente tests.test_license_integration.LicenseIntegrationTests.test_refresh_licencia_suspendida_no_mantiene_full tests.test_license_integration.LicenseIntegrationTests.test_refresh_licencia_vencida_degrada_a_demo_si_no_hay_basica tests.test_license_integration.LicenseIntegrationTests.test_refresh_licencia_error_conexion_mantiene_cache_local_vigente tests.test_license_integration.LicenseIntegrationTests.test_pro_vencida_sin_base_permanente_no_regala_basica tests.test_license_integration.LicenseIntegrationTests.test_full_vencida_sin_base_permanente_no_regala_basica`

## 2026-06-08 - Codex - release/v1.36.0

### Tarea
Preparar la release `v1.36.0` para dejar el repositorio listo para PR contra `main`, sin hacer merge ni crear tag todavia.

### Archivos modificados
- `VERSION`
- `README.md`
- `CHANGELOG.md`
- `build/nexar_tienda.iss`
- `docs/ai/AI_CHANGELOG.md`

### Que se cambio
- Se actualizo la version estable visible del proyecto a `v1.36.0` en archivos de release y documentacion principal.
- Se agrego la entrada de release en `CHANGELOG.md` con el resumen de ARCA Fase 1 a 8, reimpresion PDF, persistencia fiscal, facturacion desde venta existente, fix de productos y fix de `venta_finalizar`.
- Se dejo trazabilidad interna del proceso de preparacion de release en `docs/ai/AI_CHANGELOG.md`.
- Se mantuvo sin cambios la logica funcional del sistema fuera de los fixes ya integrados previamente.

### Que se probo
- `python -m pytest`

## 2026-06-08 - Codex - fix/venta-finalizar-temporada-row

### Tarea
Corregir el error 500 al confirmar una venta cuando existe una temporada activa y `db.get_temporada_actual()` devuelve `sqlite3.Row`.

### Archivos modificados
- `routes/main.py`
- `tests/test_venta_finalizar_temporada.py`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- En `venta_finalizar` se separó la lectura de la temporada activa en `temporada_actual` y `temporada_nombre`, accediendo por clave (`temporada_actual["nombre"]`) para compatibilidad con `sqlite3.Row`.
- `db.crear_venta` ahora recibe `temporada=temporada_nombre`, sin cambiar la lógica de ventas, stock, caja ni ARCA.
- Se revisó el patrón de `.get()` sobre resultados `sqlite3.Row` en `routes/main.py`; además se ajustó una lectura defensiva en edición de productos para reutilizar el diccionario `producto_validacion`.
- Se agregó un test que finaliza una venta con temporada activa y verifica que el nombre quede persistido en `ventas.temporada`.

### Qué se probó
- `python3 -m py_compile tests/test_venta_finalizar_temporada.py routes/main.py`
- `pytest tests/test_venta_finalizar_temporada.py -q`
- `pytest -q`

## 2026-05-24 - Codex - fix/diagnostico-arranque-servidor

### Tarea
Instrumentar el arranque de `iniciar.py` para diagnosticar por qué aparece `❌ No se pudo iniciar el servidor` antes del bloque de `webview`.

### Archivos modificados
- `iniciar.py`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se envolvió `iniciar_flask(port)` con logs de inicio/fin y `traceback.print_exc()` para distinguir fallo en `create_app`/import de `app` versus fallo en `app.run()`.
- Se agregó trazabilidad en `esperar_servidor(url)` para registrar cada intento, estado del hilo Flask, `status_code` o excepción HTTP/URL y agotamiento del timeout.
- Se dejó explícito en logs que no existe una ruta `/health` dedicada en este arranque y que la alternativa pública candidata para readiness sería `/login`.

### Qué se diagnosticó
- La falla real ocurre antes de `app.run()`: el hilo Flask muere al ejecutar `from app import app` porque el entorno actual no tiene instalado `flask`.
- `requirements.txt` sí declara `Flask>=3.0.3,<4`, pero `venv/bin/python3 -m pip show flask` devuelve `Package(s) not found`.
- `esperar_servidor(url)` no estaba apuntando a una ruta incorrecta en este caso; recibe `Connection refused` porque el hilo ya murió antes de abrir el socket.

## 2026-05-24 - Codex - fix/diagnostico-reimpresion-arca

### Tarea
Instrumentar el flujo de reimpresión ARCA para identificar ruta exacta, servicio real, origen de datos fiscales visibles y si en desktop se abre URL web o archivo local.

### Archivos modificados
- `modules/arca/routes.py`
- `modules/arca/services/reimpresion_pdf_service.py`
- `services/file_open_service.py`
- `templates/ticket.html`
- `templates/historial.html`
- `templates/arca/comprobante_detalle.html`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se agregaron logs temporales `[ARCA REIMPRESION]` en las rutas Flask `/arca/comprobante/<venta_id>/pdf` y `/arca/comprobante/<venta_id>/abrir`.
- Se instrumentó el servicio de reimpresión PDF para registrar `venta_id`, servicio ejecutado, ausencia de template HTML, `nombre_fantasia`, `razon_social`, tipo y número de comprobante, cliente fiscal resuelto y `pdf_path`.
- Se reforzó el servicio de apertura de archivos para distinguir explícitamente entre apertura de URL y apertura de archivo local.
- Se agregaron logs temporales de frontend en `ticket`, `historial` y detalle de comprobante para dejar visible si el click usa `POST /abrir` en desktop o `GET /pdf` en navegador.
- Se agregó una marca visual temporal grande `DEBUG REIMPRESION ARCA` dentro del PDF generado para validar que el archivo abierto corresponde a la reimpresión instrumentada.

### Qué se diagnosticó
- La reimpresión ARCA no usa template HTML para generar PDF; el archivo se construye directamente con `reportlab` en `modules/arca/services/reimpresion_pdf_service.py`.
- En la base activa, `arca_configuracion.nombre_fantasia` contiene `Nexar Demo`, por eso ese texto aparece en el encabezado del comprobante reimpreso.
- En la base activa, `arca_comprobantes.tipo_comprobante` está persistido como `Factura B` para los comprobantes consultados; además la lógica fiscal actual resuelve `Factura B` para `responsable_inscripto`, `exento` y `consumidor_final`, y `Factura C` solo para `monotributo`.

## 2026-05-24 - Codex - feature/arca-fase8-reimpresion-pdf

### Tarea
Implementar la Fase 8 del módulo ARCA para permitir la reimpresión en PDF de comprobantes fiscales ya emitidos, sin volver a solicitar CAE ni alterar ventas existentes.

### Archivos modificados
- `modules/arca/services/comprobantes_service.py`
- `modules/arca/services/reimpresion_pdf_service.py`
- `modules/arca/routes.py`
- `templates/ticket.html`
- `templates/historial.html`
- `templates/arca/comprobante_detalle.html`
- `tests/test_arca_fase8_reimpresion_pdf.py`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se agregó un servicio desacoplado de reimpresión PDF ARCA que arma el comprobante desde la venta, su detalle, la configuración fiscal y el comprobante ya persistido, sin invocar emisión ni WSFE.
- La generación usa `reportlab`, guarda el archivo en `pdf_path`, reutiliza el PDF si ya existe y deja una estructura segura preparada para QR fiscal futuro con placeholder visible.
- Se incorporó la ruta protegida `GET /arca/comprobante/<venta_id>/pdf` para ver o descargar el PDF fiscal desde una venta ya facturada.
- El ticket, el historial de ventas y el detalle del comprobante ARCA ahora muestran la acción `Reimprimir comprobante ARCA` cuando corresponde.
- Si la venta no tiene comprobante fiscal ARCA autorizado, la ruta responde con un mensaje claro y no afecta ventas, stock ni caja.

### Qué se probó
- `python3 -m unittest tests.test_arca_fase8_reimpresion_pdf`

### Ajuste posterior
- Se corrigió la tarjeta superior del PDF para mostrar el número completo del comprobante sin recortes, separando tipo y numeración.
- La lógica fiscal de emisión ARCA ahora resuelve `Factura C` para emisor monotributista y mantiene `Factura B` para las demás condiciones soportadas.
- La reimpresión PDF ahora toma cliente fiscal real desde `cliente_id` cuando existe, muestra nombre + documento y reemplaza `Mostrador` por `CONSUMIDOR FINAL` en el comprobante.
- La configuración ARCA ahora persiste `nombre_fantasia`, y el encabezado del PDF usa ese valor o cae al `nombre_negocio` general del comercio antes de recurrir a cualquier fallback.
- En desktop/PyWebView la acción de reimpresión ahora genera el PDF local y lo abre con el visor predeterminado del sistema, evitando sacar al usuario a una ruta protegida en navegador.
- El diseño del PDF ARCA se normalizó hacia una estructura fiscal más estándar: encabezado comercial, bloque grande de letra/tipo, datos del cliente, detalle, totales, CAE, vencimiento y área reservada para QR.
- El comprobante interno de venta se rediseñó para compartir jerarquía visual con la factura, marcando explícitamente `COMPROBANTE INTERNO DE VENTA` y `No válido como factura`, sin CAE ni QR.
- Se agregaron tests para regeneración del PDF cuando falta el archivo físico, respeto del tipo persistido en facturas viejas, presencia de CAE/vencimiento, integridad de stock/venta y leyendas del comprobante interno.

## 2026-05-24 - Codex - feature/arca-fase7-datos-fiscales

### Tarea
Implementar la Fase 7 del módulo ARCA para consolidar el guardado y la visualización de datos fiscales generados desde ventas existentes.

### Archivos modificados
- `modules/arca/services/comprobantes_service.py`
- `modules/arca/services/facturacion_desde_venta_service.py`
- `modules/arca/routes.py`
- `routes/main.py`
- `templates/ticket.html`
- `templates/historial.html`
- `templates/arca/comprobantes.html`
- `templates/arca/comprobante_detalle.html`
- `tests/test_arca_fase7_datos_fiscales.py`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se consolidó la lectura de `arca_comprobantes` con helpers para detectar comprobantes finales, formatear `tipo + punto de venta + número` y exponer estado del PDF local como `generado` o `pendiente`.
- La persistencia de facturación desde venta ahora guarda un resumen técnico seguro en `respuesta_raw`, evitando depender de payloads completos para consulta histórica.
- El ticket de venta y el historial ahora muestran datos fiscales ARCA más completos: comprobante formateado, CAE, vencimiento, estado, fecha de emisión y estado del PDF.
- Cuando una venta ya tiene comprobante ARCA, la acción de facturar queda reemplazada visualmente por el estado `Factura ARCA generada`.
- Se convirtió `/arca/comprobantes` en un listado operativo con acceso al detalle individual y se agregó la vista `/arca/comprobantes/<id>` para consulta local del comprobante guardado.

### Qué se probó
- `python3 -m unittest tests.test_arca_fase6_factura_desde_venta tests.test_arca_fase7_datos_fiscales`

## 2026-05-24 - Codex - fix/activacion-directa-pro-full-release

### Tarea
Versionar el release patch enfocado en la corrección de activación directa de licencias PRO/FULL para `Nexar Comercio`.

### Archivos modificados
- `VERSION`
- `CHANGELOG.md`
- `README.md`
- `build/nexar_tienda.iss`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se detectó la versión actual `1.35.1` y se preparó el release `1.35.2`.
- Se agregó una entrada limpia en `CHANGELOG.md` enfocada solo en la corrección de activación directa de licencias PRO/FULL y compatibilidad con BASICA, PRO y FULL.
- Se actualizó la versión visible en `README.md` y en el instalador Windows `build/nexar_tienda.iss`.
- Se mantuvo el release sin referencias nuevas a otros módulos ajenos al fix de licencias.

### Qué se probó
- `python3 -m unittest -v tests.test_license_integration.LicenseIntegrationTests.test_validate_license_key_permite_activar_basica_desde_demo tests.test_license_integration.LicenseIntegrationTests.test_validate_license_key_permite_activar_pro_desde_demo tests.test_license_integration.LicenseIntegrationTests.test_validate_license_key_permite_activar_full_desde_demo_sin_basica_previa tests.test_license_integration.LicenseIntegrationTests.test_licensing_payload_acepta_full_y_alias_mensual_full tests.test_license_integration.LicenseIntegrationTests.test_activar_licencia_legacy_permite_full_sin_basica_previa tests.test_license_integration.LicenseIntegrationTests.test_build_checkout_context_permite_alta_licencia_basica_desde_demo tests.test_license_integration.LicenseIntegrationTests.test_build_checkout_context_permite_alta_licencia_desde_demo tests.test_license_integration.LicenseIntegrationTests.test_build_checkout_context_permite_alta_licencia_full_desde_demo tests.test_license_integration.LicenseIntegrationTests.test_build_checkout_context_con_license_key_sigue_usando_cambio_plan`
- `python3 -m unittest -v tests.test_license_tiers.LicenseTierNormalizationTests`
- `python3 -m py_compile database.py services/license_sdk.py services/licensing.py`

## 2026-05-24 - Codex - fix/activacion-directa-pro-full

### Tarea
Corregir la activación de licencias para permitir altas iniciales BASICA, PRO y FULL desde DEMO/SIN_PLAN, sin exigir BASICA previa para PRO o FULL.

### Archivos modificados
- `services/license_sdk.py`
- `database.py`
- `services/licensing.py`
- `tests/test_license_integration.py`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se eliminó la validación hardcodeada que bloqueaba activaciones iniciales `FULL` cuando `basica_activada` no estaba marcada, tanto en el flujo SDK/Supabase como en el helper legacy RSA.
- La normalización de planes sigue resolviendo `FULL` y `MENSUAL_FULL` al mismo plan comercial, mientras `PRO` y `BASICA` conservan su identidad.
- `basica_activada` quedó reservada para fallback permanente de licencias vencidas, y ya no funciona como requisito técnico previo para activar planes superiores.
- Se amplió la validación auxiliar de payloads de licencia para aceptar también `FULL` y `MENSUAL_FULL`.
- Se agregaron tests para altas iniciales BASICA, PRO y FULL desde DEMO, alias `MENSUAL_FULL`, y se confirmó que el cambio de plan existente con `license_key` sigue usando el flujo `cambio_plan`.

### Qué se probó
- `python3 -m unittest -v tests.test_license_integration.LicenseIntegrationTests.test_validate_license_key_permite_activar_basica_desde_demo tests.test_license_integration.LicenseIntegrationTests.test_validate_license_key_permite_activar_pro_desde_demo tests.test_license_integration.LicenseIntegrationTests.test_validate_license_key_permite_activar_full_desde_demo_sin_basica_previa tests.test_license_integration.LicenseIntegrationTests.test_build_checkout_context_con_license_key_sigue_usando_cambio_plan tests.test_license_integration.LicenseIntegrationTests.test_licensing_payload_acepta_full_y_alias_mensual_full tests.test_license_integration.LicenseIntegrationTests.test_activar_licencia_legacy_permite_full_sin_basica_previa tests.test_license_integration.LicenseIntegrationTests.test_build_checkout_context_permite_alta_licencia_basica_desde_demo tests.test_license_integration.LicenseIntegrationTests.test_build_checkout_context_permite_alta_licencia_desde_demo tests.test_license_integration.LicenseIntegrationTests.test_build_checkout_context_permite_alta_licencia_full_desde_demo`
- `python3 -m unittest -v tests.test_license_tiers.LicenseTierNormalizationTests`
- `python3 -m py_compile routes/main.py licensing/planes.py services/license_storage.py services/license_sdk.py services/licensing.py database.py`

## 2026-05-24 - Codex - fix/linux-ticket-print-cups

### Tarea
Implementar impresión de tickets en Linux desktop desde backend/Python usando CUPS, sin depender de `window.print()` dentro de PyWebView.

### Archivos modificados
- `services/print_service.py`
- `routes/main.py`
- `templates/ticket.html`
- `tests/test_print_service.py`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se creó `services/print_service.py` para centralizar detección de plataforma Linux, detección de `lp`/`lpr`, lectura de impresora por defecto con `lpstat -d`, generación de PDF temporal del ticket con `reportlab` y envío a CUPS con logs completos.
- En Linux desktop/PyWebView el botón `Imprimir` del ticket ahora hace `POST` al endpoint interno `POST /api/ticket/<id>/print`, usando CSRF y sesión actual, en vez de depender de `window.print()`.
- El PDF temporal se arma desde Python a partir de la venta y su detalle, ahora con ancho angosto y alto dinámico para evitar hojas finales en blanco, y se loguea cantidad de páginas junto con dimensiones generadas.
- Después de `lp` se parsea el `job_id`, se consulta `lpstat` sobre cola y detalle del trabajo, y se devuelve un mensaje claro cuando CUPS deja el job demorado, retenido o detenido.
- Se agregó soporte interno de opciones CUPS `fit-to-page` y `raw` mediante `NEXAR_CUPS_PRINT_MODE`, manteniendo `auto` como default.
- Se ajustó el CSS `@media print` del ticket para quitar `min-height`/`overflow` problemáticos y evitar una página extra en el flujo de navegador.
- Windows y navegador normal conservan el flujo previo con `window.print()`.

### Qué se probó
- Tests unitarios del servicio nuevo para archivo inexistente, ausencia de `lp/lpr`, impresión exitosa simulada, impresión con error simulado y detección de job CUPS demorado con `fit-to-page`.
- Verificación sintáctica con `py_compile` de `services/print_service.py`, `routes/main.py` e `iniciar.py`.

## 2026-05-24 - Codex - fix/linux-native-ticket-print

### Tarea
Recuperar la impresión nativa de tickets en Linux dentro de PyWebView, dejando la apertura externa solo como recurso técnico secundario y no como UX principal.

### Archivos modificados
- `iniciar.py`
- `templates/ticket.html`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se investigó la instalación local de `pywebview` y se confirmó que en `qtwebengine` no existe un handler nativo para `window.print()` como sí ocurre en Cocoa, por lo que Linux no estaba mostrando diálogo de impresión por defecto.
- Se agregó en `iniciar.py` un hook nativo para Linux/Qt que intercepta `printRequested` del `QWebEnginePage`, abre `QPrintDialog` y ejecuta la impresión con `QPrinter` desde la ventana nativa.
- En `templates/ticket.html` se volvió a un flujo principal simple con botón `Imprimir`, llamado directo a `window.print()`, `window.focus()` previo y logs JS de plataforma/backend.
- Se retiraron el aviso visible para Linux y el botón principal `Abrir en navegador para imprimir`, para no degradar la UX del ticket.
- Se reforzó el ciclo de vida del `QPrinter` manteniéndolo vivo hasta el callback de QtWebEngine y se agregaron logs de `printerName`, `isValid`, `outputFormat`, `printerState`, resultado del diálogo y señales `printFinished`.
- Se agregó un fallback interno exclusivo para Linux: si la impresión Qt falla, el ticket se renderiza a PDF temporal y se envía a CUPS con `lp`/`lpr`, mostrando error claro solo si también falla ese camino.
- Se corrigió el uso del objeto Qt real: el hook ya no llama `print(printer, callback)` sobre `BrowserView.WebView`, sino que inspecciona `QWebEnginePage` y usa `page.print(...)` solo si existe; en el entorno actual, como `page.print` no está disponible, cae a `page.printToPdf(...)` y luego envía el PDF a CUPS.

### Qué se probó
- Revisión local del código instalado de `pywebview` para `qtwebengine`, validando la ausencia de override nativo de `window.print()` y la disponibilidad de `printRequested`, `QPrintDialog` y `QPrinter` en `PySide6`.
- Verificación sintáctica con `py_compile` de los archivos tocados.

## 2026-05-24 - Codex - fix/linux-ticket-print-fallback

### Tarea
Corregir el flujo de impresión de tickets/comprobantes en Linux dentro de PyWebView, manteniendo la impresión actual en Windows y navegador normal.

### Archivos modificados
- `iniciar.py`
- `services/file_open_service.py`
- `templates/ticket.html`
- `tests/test_file_open_service.py`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se amplió `services/file_open_service.py` para abrir también URLs externas con el manejador nativo de cada plataforma y dejar logs simples de plataforma y método usado.
- Se agregó al bridge `pywebview` el método `openExternalUrl(url)` para que la ventana nativa pueda abrir el ticket actual en navegador externo sin depender de `window.print()`.
- En `templates/ticket.html` se mantuvo el botón `Imprimir`, se sumó `Abrir en navegador para imprimir`, y se agregó un aviso visible para Linux dentro de PyWebView cuando conviene usar el navegador externo.
- El flujo nuevo evita el fallo silencioso: si la apertura externa falla, deja mensaje visible con la URL manual del ticket.

### Qué se probó
- Tests unitarios del servicio de apertura para archivo inexistente, apertura Linux con `xdg-open`, apertura de URL HTTP y error controlado con target vacío.

## 2026-05-24 - Codex - fix/linux-ticket-open

### Tarea
Corregir visualización/apertura de tickets y aperturas externas en Linux sin romper Windows.

### Archivos modificados
- `services/file_open_service.py`
- `routes/main.py`
- `templates/cliente_detalle.html`
- `tests/test_file_open_service.py`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se creó `services/file_open_service.py` con `open_file_cross_platform(path)` para centralizar aperturas en Windows (`os.startfile`), Linux (`xdg-open`) y macOS (`open`), validando existencia y devolviendo mensaje claro cuando falla.
- Se reemplazaron aperturas manuales dispersas de carpetas por el servicio nuevo para evitar lógica duplicada y mejorar logs/feedback.
- El flujo de venta ahora deja un mensaje visible con la ruta del ticket para reapertura manual si no se muestra automáticamente.
- En `templates/cliente_detalle.html` se corrigió el enlace al ticket para entorno `pywebview`: en desktop remueve `target="_blank"` y navega en la misma ventana, evitando el fallo típico de Linux/Qt donde el ticket existe pero no se ve.

### Qué se probó
- Tests unitarios para archivo inexistente, apertura Linux con `xdg-open` y fallback con ruta manual si `xdg-open` falla.

## 2026-05-23 - Codex - feature/arca-fase5-simulacion

### Tarea
Implementar Fase 5 del módulo ARCA con modo simulación profesional para desarrollo, desacoplado de la emisión real en ARCA/AFIP.

### Archivos modificados
- `database.py`
- `services/arca_config_service.py`
- `modules/arca/services/comprobantes_service.py`
- `modules/arca/services/arca_client.py`
- `modules/arca/routes.py`
- `routes/main.py`
- `templates/arca/estado.html`
- `templates/arca/comprobantes.html`
- `templates/ticket.html`
- `tests/test_arca_fase1.py`
- `tests/test_arca_fase5_simulacion.py`
- `docs/arca/README.md`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- `ARCA_MODO_SIMULACION` ahora permite trabajar en simulación o dejar preparado el flujo WSFE real; en desarrollo el default queda en simulación activa.
- `arca_comprobantes` se adaptó sin romper instalaciones existentes para guardar `numero_comprobante` y `modo`, manteniendo compatibilidad con datos previos.
- Se amplió `modules/arca/services/comprobantes_service.py` con `emitir_comprobante_desde_venta(venta_id)`, generación incremental de comprobantes simulados, CAE/vencimiento simulados y control de duplicados por venta.
- La ruta `POST /arca/ventas/<venta_id>/emitir` quedó integrada al módulo ARCA y el detalle de venta (`ticket`) ahora muestra estado ARCA y botón de emisión para administradores cuando todavía no existe comprobante.
- La pantalla `ARCA / Estado` ahora informa explícitamente si la app está en simulación o preparada para WSFE real.
- Se agregó documentación mínima en `docs/arca/README.md` para dejar claro el alcance de esta fase.

### Qué se probó
- Tests unitarios para emisión simulada, control de duplicados, error controlado sin `venta_id` y garantía de no invocar WSFE real en simulación.
- Ajuste de compatibilidad en test previo del wrapper `arca_client`.

## 2026-05-23 - Codex - feature/arca-wsfe-fase4

### Tarea
Implementar Fase 4 del módulo ARCA con conexión mínima a WSFE homologación para consultas, reutilizando ticket WSAA y sin emitir comprobantes.

### Archivos modificados
- `services/arca/wsfe_client.py`
- `services/arca/wsfe_service.py`
- `services/arca/__init__.py`
- `modules/arca/services/arca_client.py`
- `modules/arca/routes.py`
- `templates/arca/estado.html`
- `tests/test_arca_fase4_wsfe.py`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se agregó un cliente SOAP mínimo para WSFE homologación con `FEDummy`, `FEParamGetTiposCbte`, `FEParamGetTiposDoc`, `FEParamGetPtosVenta` y `FECompUltimoAutorizado`, manteniendo el armado de `FEAuthRequest` fuera de las rutas.
- Se creó un servicio desacoplado que valida configuración, reutiliza ticket WSAA vigente o renueva uno vía `auth_service`, ejecuta la prueba WSFE y guarda un resumen seguro en `arca_eventos`.
- La pantalla Estado ARCA ahora incorpora el botón `Probar WSFE` y un bloque con el último resultado visible: estado de conexión, `FEDummy`, cantidades y previews de parámetros consultados, y último comprobante para PV configurado con Factura B.
- Se mantuvieron logs seguros sin exponer token ni sign completos y sin habilitar emisión, CAE, POS ni integración con ventas.

### Qué se probó
- Tests unitarios para `FEAuthRequest`, error sin configuración, reutilización de ticket vigente y parseo de último comprobante.

### Ajuste posterior
- Se corrigió la serialización SOAP de WSFE para que `Auth`, `Token`, `Sign` y `Cuit` viajen dentro del namespace `http://ar.gov.afip.dif.FEV1/`, que AFIP exige para interpretar correctamente `FEAuthRequest`.
- También se mejoró el manejo de `HTTP 500` para leer el `SOAP Fault` real antes de responder con error genérico, y se agregaron logs seguros con longitudes de `token`/`sign`, `cuit` y método WSFE invocado.

## 2026-05-23 - Codex - feature/arca-wsaa-fase31

### Tarea
Mejorar el diagnóstico técnico de certificados ARCA antes de intentar autenticación WSAA, con validación de X509, private key, passphrase y correspondencia del par.

### Archivos modificados
- `services/arca/certificate_diagnostics.py`
- `services/arca/__init__.py`
- `services/arca/auth_service.py`
- `modules/arca/services/certificados_service.py`
- `templates/arca/certificados.html`
- `tests/test_arca_fase3_wsaa.py`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se agregó un servicio desacoplado de diagnóstico técnico para certificado y key, con detección de formato PEM/DER, validez X509, key encriptada y coincidencia del par.
- `Probar conexión` ahora falla antes con mensajes claros si el certificado es inválido, si la key requiere contraseña o si el par no corresponde.
- La pantalla de Certificados ahora muestra un bloque de diagnóstico por fila con existencia, validez, formato, vencimiento leído del certificado y consistencia del par.
- Se mantuvieron logs seguros sin exponer contenido sensible de certificado, key, token ni sign.

### Qué se probó
- Tests con certificado y key válidos generados en runtime.
- Detección de key con password.
- Detección de certificado y key no coincidentes.
- Exposición del diagnóstico en `certificados_service`.

## 2026-05-23 - Codex - feature/arca-wsaa-fase3

### Tarea
Implementar Fase 3 del módulo ARCA con autenticación real WSAA en homologación, almacenamiento local de tickets y prueba de conexión desacoplada, sin emitir comprobantes.

### Archivos modificados
- `database.py`
- `modules/arca/routes.py`
- `modules/arca/services/arca_client.py`
- `services/arca_config_service.py`
- `templates/arca/config.html`
- `templates/arca/estado.html`
- `tests/test_arca_base.py`
- `tests/test_arca_fase1.py`
- `tests/test_arca_fase3_wsaa.py`
- `services/arca/__init__.py`
- `services/arca/auth_service.py`
- `services/arca/ticket_storage.py`
- `services/arca/wsaa_client.py`
- `services/arca/xml_signer.py`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se agregó persistencia dedicada para tickets WSAA por ambiente y servicio en SQLite.
- Se creó un paquete `services/arca` para separar generación de TRA, firmado CMS, cliente WSAA y orquestación de autenticación.
- El botón `Probar conexión` ahora intenta autenticación real en homologación, reutiliza ticket vigente si existe y devuelve errores claros cuando falta configuración, firma o la respuesta WSAA es inválida.
- El panel Estado ARCA ahora muestra estado de conexión WSAA, ticket vigente/vencido y mantiene el aviso de que aún no se emiten comprobantes.
- Se agregaron logs y eventos seguros sin exponer token, sign ni contenido de la clave privada.

### Qué se probó
- Tests de creación de TRA, vigencia/vencimiento de tickets y configuración incompleta.
- Ajustes de tests base para la nueva tabla de tickets y el nuevo flujo de `probar_conexion`.

## 2026-05-23 - Codex - fix/release-gh-token

### Tarea
Corregir el job `release` del workflow `Build & Release Nexar Tienda` para que `gh` autentique correctamente y no oculte errores reales al consultar releases.

### Archivos modificados
- `.github/workflows/build.yml`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se agregó `permissions: contents: write` y `env: GH_TOKEN: ${{ github.token }}` a nivel job en `release`.
- Se eliminaron los `env` repetidos con `GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}` de los steps que usan `gh`.
- Se mantuvo `--repo "${{ github.repository }}"` en los comandos `gh` que ya lo utilizaban.
- La verificación de existencia del release ahora distingue `404` como “no existe” y falla con mensaje claro ante `401`, `403` u otros errores de la API/CLI.

### Qué se probó
- Revisión estática del YAML del workflow y del flujo de autenticación del job `release`.

## 2026-05-23 - Codex - feature/arca-config-fase2

### Tarea
Implementar Fase 2 del módulo ARCA con configuración fiscal completa y persistente, manteniendo el módulo opcional, desacoplado y sin emisión real.

### Archivos modificados
- `database.py`
- `services/arca_config_service.py`
- `modules/arca/services/config_service.py`
- `modules/arca/routes.py`
- `templates/arca/config.html`
- `tests/test_arca_fase1.py`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- La tabla `arca_configuracion` ahora garantiza las columnas persistentes de Fase 2: `cuit`, `razon_social`, `condicion_fiscal`, `punto_venta`, `ambiente`, `certificado_path`, `key_path`, `certificado_vencimiento`, `activo`, `created_at` y `updated_at`, sin romper instalaciones existentes.
- Se creó `services/arca_config_service.py` como servicio desacoplado para la configuración fiscal, con `get_config()`, `save_config()`, `validate_config()`, `validar_cuit()` y `validar_rutas_certificados()`.
- Las rutas ARCA de configuración ahora delegan la validación y persistencia al servicio nuevo, dejando la lógica pesada fuera de `modules/arca/routes.py`.
- La pantalla `templates/arca/config.html` se rehizo para mostrar todos los campos de Fase 2 y aclarar que todavía no existe conexión real ni emisión de comprobantes.
- Se mantuvo un wrapper de compatibilidad en `modules/arca/services/config_service.py` para no romper imports previos del módulo.
- Se ajustaron pruebas ARCA para cubrir migración, guardado persistente, validaciones de CUIT, punto de venta, ambiente y rutas de certificados.

### Qué se probó
- Tests unitarios del módulo ARCA enfocados en persistencia, validaciones y placeholders.
- Validación sintáctica de los archivos tocados.

## 2026-05-19 - Codex - fix/licencias-flujo-comercial loop licencia y checkout demo

### Tarea
Corregir el loop entre recuperacion y licencia post-login, y destrabar el checkout comercial desde DEMO/sin licencia valida con diff minimo.

### Archivos modificados
- `routes/main.py`
- `services/mercadopago_checkout.py`
- `tests/test_license_integration.py`
- `docs/ai/AI_CHANGELOG.md`

### Que se cambio
- Se consolido la resolucion comercial del checkout para usar `cambio_plan` solo cuando la licencia local efectiva tiene `key`; DEMO/SIN_PLAN siguen por `alta_licencia`.
- Se habilito el precio por defecto de `BASICA` para que instalaciones nuevas sin env especifica no queden bloqueadas al iniciar checkout directo.
- Se ajustaron mensajes visibles con texto roto en las secciones tocadas para mantener UTF-8 correcto.
- Se ampliaron los tests de integracion para cubrir acceso sin loop a `configurar-recuperacion`/`licencia`/`mi-plan`, checkout directo DEMO a `BASICA`, `PRO` y `MENSUAL_FULL`, y preservacion de `cambio_plan` cuando existe `license_key`.

### Que se probo
- Tests de integracion de licencias enfocados en loop, checkout y tipo de solicitud comercial.
- Se ajusto el fallback local de precio de `BASICA` a `49.900` para instalaciones nuevas sin `NEXAR_PRICE_BASICA`.
- Se re-alineo el boton lateral `Cerrar sistema` con el mismo submit form del cierre desktop por X.
- Se blindo el post-login para que DEMO activo vuelva al dashboard y no salte a `Mi Plan` salvo bloqueo comercial real.

## 2026-05-18 - Codex - feature/caja-segura-fase2 bloqueo gasto efectivo y detalle caja cerrada

### Tarea
Bloquear gastos en efectivo fuera de caja abierta y agregar consulta de caja cerrada en solo lectura.

### Archivos modificados
- `app.py`
- `database.py`
- `routes/main.py`
- `templates/caja.html`
- `templates/gasto_form.html`
- `docs/ai/AI_CHANGELOG.md`
- `docs/ai/AUDITORIA_EDICION_RESPONSABLE.md`

### Que se cambio
- Los gastos con `medio_pago=Efectivo` ahora exigen una caja abierta valida; si no existe, se bloquean con el mensaje `No podes registrar gastos con efectivo porque no hay una caja abierta.`
- Tambien se bloquean gastos en efectivo cuya fecha no coincide con la caja abierta actual, para evitar movimientos sobre cajas cerradas o fuera de jornada.
- El bloqueo se aplica tanto en rutas de gastos como en `database.add_gasto()` y `database.update_gasto()`.
- Se agrego una vista minima de detalle de caja cerrada en solo lectura, accesible desde el historial de cierres.
- La vista cerrada muestra apertura, cierre, saldo inicial, ingresos, egresos, movimientos, anulados visibles y saldo final, sin permitir agregar ni anular movimientos.

### Que se probo
- Validacion sintactica con `python3 -m py_compile app.py routes/main.py database.py iniciar.py`.
- Prueba sobre DB temporal para cubrir: bloqueo de gasto efectivo sin caja abierta, permiso de gasto no efectivo, permiso de gasto efectivo con caja abierta, bloqueo de gasto efectivo con caja cerrada y render de caja cerrada en solo lectura.

## 2026-05-18 - Codex - feature/caja-segura-fase2

### Tarea
Implementar Caja Segura Fase 2 con movimientos inmutables, anulacion responsable y proteccion de cajas cerradas.

### Archivos modificados
- `app.py`
- `database.py`
- `routes/main.py`
- `templates/caja.html`
- `docs/ai/AI_CHANGELOG.md`
- `docs/ai/AUDITORIA_EDICION_RESPONSABLE.md`

### Que se cambio
- `caja_movimientos` ahora incorpora campos minimos de trazabilidad para anulacion: `anulado`, `anulada_at`, `anulada_por`, `motivo_anulacion` y `movimiento_origen_id`.
- Se agregaron helpers de base para crear movimientos inmutables, registrar movimientos solo con caja abierta, buscar movimientos activos por gasto y anular movimientos sin borrarlos.
- El resumen de caja ahora excluye movimientos anulados para no sumar importes invalidados.
- La pantalla de Caja muestra movimientos anulados como historicos visibles y agrega modal Nexar para `Anular movimiento` con motivo obligatorio.
- Los movimientos manuales ya no se editan ni borran: solo pueden anularse una vez y solo mientras la caja siga abierta.
- Los movimientos vinculados a gastos no se pueden anular desde Caja; deben corregirse desde Gastos para mantener coherencia.
- La sincronizacion gasto-caja dejo de hacer `UPDATE` o `DELETE` destructivo sobre `caja_movimientos`: ahora anula el movimiento previo y crea uno nuevo solo si corresponde.
- Los gastos que impactaron una caja cerrada quedan bloqueados para cambios sensibles o eliminacion, evitando reescritura historica de caja.

### Que se probo
- Validacion sintactica con `python3 -m py_compile app.py routes/main.py database.py iniciar.py`.
- Prueba automatizada sobre DB temporal para cubrir creacion, anulacion, doble anulacion, saldo coherente, bloqueo sin caja abierta, bloqueo sobre caja cerrada y resincronizacion segura de gastos.

### Casos dudosos / alcance
- No se agrego reapertura de caja ni compensaciones contables avanzadas; la fase se limita a congelar historia y anular responsablemente con cambios minimos.
- Los reportes contables generales siguen leyendo `gastos`; en esta fase se protegio especificamente la coherencia de caja y la reescritura silenciosa de sus movimientos.

## 2026-05-18 - Codex - feature/caja-operativa-fase1 fix salida post cierre

### Tarea
Corregir el destino final luego de `Cerrar caja y salir` para evitar rutas placeholder o inexistentes.

### Archivos modificados
- `routes/main.py`
- `app.py`
- `docs/ai/AI_CHANGELOG.md`

### Que se cambio
- La URL final posterior al cierre de caja ahora usa el endpoint namespaced real `main.salida_protegida_cerrar_app`.
- Se agrego alias legacy para `salida_protegida_cerrar_app` y asi evitar caidas al handler `/en-construccion/...`.
- Con esto, tanto la X de ventana como el boton `Cerrar sistema` comparten el mismo cierre final sin 404 ni placeholders.

### Que se probo
- Validacion de `url_for(...)` para `main.salida_protegida_cerrar_app` y `salida_protegida_cerrar_app`.
- Validacion sintactica de Python en `app.py`, `routes/main.py` e `iniciar.py`.

## 2026-05-18 - Codex - feature/caja-operativa-fase1 salida unificada

### Tarea
Unificar el flujo de salida protegida entre la X de la ventana y el boton interno `Cerrar sistema`.

### Archivos modificados
- `templates/base.html`
- `docs/ai/AI_CHANGELOG.md`

### Que se cambio
- Se centralizo la salida protegida en una unica funcion reutilizable del layout base.
- La X de la ventana y el boton `Cerrar sistema` ahora usan el mismo modal y las mismas acciones cuando hay caja abierta.
- Se elimino la confirmacion separada del boton interno para evitar comportamientos distintos entre ambos caminos de salida.
- Se mantuvo la logica ya implementada: cerrar caja y salir, salir sin cerrar o cancelar.

### Que se probo
- Revision estatica del flujo compartido en `templates/base.html`.
- Validacion sintactica de Python del proyecto principal para confirmar que no hubo regresiones colaterales.

## 2026-05-18 - Codex - feature/caja-operativa-fase1 salida protegida

### Tarea
Completar la salida protegida de Nexar cuando hay caja abierta al cerrar la app.

### Archivos modificados
- `iniciar.py`
- `routes/main.py`
- `templates/base.html`
- `docs/ai/AI_CHANGELOG.md`
- `docs/ai/AUDITORIA_EDICION_RESPONSABLE.md`

### Que se cambio
- El interceptor de `pywebview` ahora solo bloquea el cierre nativo cuando hay una caja abierta. Con caja cerrada, la app puede salir normal.
- El modal de salida protegida ahora muestra `Cerrar caja y salir`, `Salir sin cerrar` y `Cancelar`.
- `Cerrar caja y salir` redirige al flujo real de cierre de caja ya existente, autoabre su modal y, si el cierre se concreta, apaga la app automaticamente.
- Se agrego una salida protegida final que se ejecuta solo despues de cerrar caja con exito.
- Si ya no hay caja abierta al intentar cerrar, el sistema muestra aviso y no apaga la app por error.

### Que se probo
- Validacion sintactica de Python en `app.py`, `routes/main.py` e `iniciar.py`.
- Revision estatica del flujo desktop: cierre nativo, aviso, cierre de caja y apagado final.

### Limitaciones
- El cierre automatico posterior depende del flujo desktop con `pywebview`. En navegador externo sigue sin existir una intercepcion nativa equivalente del boton cerrar pestana.

## 2026-05-18 - Codex - feature/caja-operativa-fase1

### Tarea
Implementar Caja Operativa Fase 1 con validacion previa a venta, aviso de caja abierta al entrar y recordatorio al intentar cerrar la app.

### Archivos modificados
- `app.py`
- `routes/main.py`
- `templates/base.html`
- `templates/caja.html`
- `templates/punto_venta.html`
- `docs/ai/AI_CHANGELOG.md`
- `docs/ai/AUDITORIA_EDICION_RESPONSABLE.md`

### Que se cambio
- El backend de ventas ahora rechaza `venta_finalizar` si no hay una caja abierta.
- El Punto de Venta ahora muestra un modal SweetAlert2 con el mensaje `Necesitas abrir caja para realizar ventas.` y acciones `Abrir caja` y `Cancelar`.
- `Abrir caja` lleva al flujo existente de caja, autoabre el modal de apertura y vuelve al POS al confirmar.
- La app ahora muestra un aviso visual no invasivo cuando detecta una caja abierta al entrar, con fecha/hora de apertura y acciones `Continuar` o `Ir a caja`.
- El recordatorio de cierre desktop ahora detecta caja abierta y ofrece `Cerrar caja`, `Salir sin cerrar` o `Cancelar`.
- `Salir sin cerrar` usa el flujo interno de apagado rapido, por lo que la caja permanece abierta.
- La pantalla de caja ahora acepta `next` seguro y `auto_open` para reutilizar los modales existentes de apertura/cierre.

### Que se probo
- Validacion sintactica de Python en `app.py`, `routes/main.py` e `iniciar.py`.
- Revision estatica del flujo entre POS, caja, layout base y cierre desktop.

### Limitaciones
- El recordatorio al cerrar depende del flujo desktop con `pywebview` ya existente. En navegador externo no se puede interceptar el cierre nativo con el mismo control.
- Al elegir `Cerrar caja` desde el recordatorio de salida, se redirige al flujo de cierre existente; no se automatiza el cierre de la app despues del arqueo.

## 2026-05-17 â€” ChatGPT â€” documentaciÃ³n inicial

### Tarea
Definir documentaciÃ³n viva para IA y roadmap de mejoras de Nexar Comercio.

### Hallazgos
- Producto visible: Nexar Comercio.
- Repo tÃ©cnico: nexar-tienda.
- Regla agregada: nunca trabajar directo sobre main.
- Cada mejora debe ir en rama propia.
- Hay fricciÃ³n al crear producto desde compra porque exige descripciÃ³n previa.
- Ya existe flujo return_to=compra_nueva.
- CatÃ¡logo tiene bÃºsqueda y filtro por categorÃ­a.
- Falta filtro por proveedor.
- CategorÃ­as deben volverse configurables.
- Reportes deben estar habilitados en demo.

### Pendiente inmediato recomendado
Implementar prioridad 1:
flujo Ã¡gil de compra con producto nuevo sin exigir descripciÃ³n previa.

## 2026-05-17 â€” ChatGPT â€” feature/flujo-compra-producto-nuevo

### Tarea
Implementar Prioridad 1 del roadmap: permitir crear producto desde una compra sin exigir descripciÃ³n previa.

### Archivos modificados
- `templates/compras.html`

### QuÃ© se cambiÃ³
- Se eliminÃ³ el bloqueo JavaScript que impedÃ­a abrir â€œCrear productoâ€ si `producto_descripcion` estaba vacÃ­o.
- Se mantuvo el flujo existente `return_to=compra_nueva`.
- Se conservÃ³ el borrador de compra al avanzar hacia la creaciÃ³n del producto.
- No se modificÃ³ la creaciÃ³n de proveedor desde compra.

### QuÃ© se probÃ³
- RevisiÃ³n estÃ¡tica del flujo en template.
- VerificaciÃ³n de que `buildProductoUrl()` sigue enviando los parÃ¡metros del borrador.

### Pendiente
- Probar manualmente en la app:
  1. abrir Nueva Compra
  2. presionar Crear producto sin descripciÃ³n
  3. crear producto
  4. verificar regreso a compra con producto seleccionado
- Luego de validar y mergear esta rama, continuar con Prioridad 2: filtro por proveedor en catÃ¡logo.

## 2026-05-17 â€” Codex â€” feature/filtro-proveedor-catalogo

### Tarea
Implementar Prioridad 2 del roadmap: filtro por proveedor en catÃ¡logo, combinable con bÃºsqueda textual y categorÃ­a.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/productos.html`
- `docs/ai/AI_CHANGELOG.md`

### QuÃ© se cambiÃ³
- `get_productos()` ahora hace `LEFT JOIN` con `stock` para exponer `proveedor_habitual` sin cambiar la estructura de la base.
- Se agregÃ³ soporte opcional para filtrar por proveedor en `get_productos()`, manteniendo compatibilidad con llamadas existentes.
- La ruta `/productos` ahora lee `proveedor`, arma la lista de proveedores visibles y la envÃ­a al template junto al filtro seleccionado.
- El catÃ¡logo ahora muestra un selector "Todos los proveedores", incluye `proveedor_habitual` en la bÃºsqueda textual y lo muestra de forma discreta debajo de la descripciÃ³n.
- El JavaScript del catÃ¡logo ahora combina bÃºsqueda + categorÃ­a + proveedor sobre la misma tabla.

### QuÃ© se probÃ³
- VerificaciÃ³n estÃ¡tica del flujo en `database.py`, `routes/main.py` y `templates/productos.html`.
- ValidaciÃ³n sintÃ¡ctica de Python con `python3 -m py_compile database.py routes/main.py`.

### Pendiente de prueba manual
- Abrir `/productos` y verificar carga sin errores.
- Probar filtro solo por categorÃ­a.
- Probar filtro solo por proveedor.
- Probar combinaciÃ³n de bÃºsqueda + categorÃ­a + proveedor.
- Verificar que productos sin `proveedor_habitual` sigan visibles cuando el filtro estÃ¡ en "Todos los proveedores".

## 2026-05-17 â€” Codex â€” feature/filtro-proveedor-catalogo correcciÃ³n

### Tarea
Corregir el filtro por proveedor del catÃ¡logo para comparar por nombre visible y sin distinguir mayÃºsculas/minÃºsculas.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/productos.html`
- `docs/ai/AI_CHANGELOG.md`

### QuÃ© se cambiÃ³
- Se normalizÃ³ el filtro opcional `proveedor` en `get_productos()` usando `LOWER(...)` para evitar comparaciones sensibles a mayÃºsculas/minÃºsculas.
- La ruta `/productos` ahora deduplica proveedores visibles por `lower()` pero conserva el nombre original para mostrarlo en el selector.
- El template guarda categorÃ­a y proveedor normalizados en `data-*` y mantiene el `option value` con el nombre visible del proveedor.
- El JavaScript ahora normaliza bÃºsqueda, categorÃ­a y proveedor antes de comparar.

### QuÃ© se probÃ³
- RevisiÃ³n estÃ¡tica del flujo entre SQL, ruta, template y filtro JavaScript.

### Pendiente de prueba manual
- Verificar que un mismo proveedor escrito con distintas mayÃºsculas no se duplique en el selector.
- Probar filtro por proveedor, categorÃ­a y bÃºsqueda en combinaciÃ³n.
- Confirmar que productos sin proveedor solo se oculten al elegir un proveedor especÃ­fico.

## 2026-05-17 â€” Codex â€” feature/filtro-proveedor-catalogo circuito completo

### Tarea
Cerrar el circuito completo de `proveedor_habitual` para alta, ediciÃ³n y filtrado del catÃ¡logo.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/producto_form.html`
- `templates/compras.html`
- `docs/ai/AI_CHANGELOG.md`

### QuÃ© se cambiÃ³
- `add_producto()` ahora guarda `proveedor_habitual` en la fila de `stock` cuando viene informado en el formulario.
- La ruta `/productos` ahora arma `proveedores_visibles` desde un listado sin aplicar el filtro actual de proveedor, evitando que el selector se achique mal.
- Crear producto desde catÃ¡logo ahora permite elegir proveedor habitual.
- Crear producto desde compra ahora hereda el proveedor seleccionado mediante `prefill_proveedor_id` y lo guarda en el producto si no se eligiÃ³ otro manualmente.
- Editar producto mantiene disponible el selector de proveedor habitual usando el valor actual de `stock`.
- El catÃ¡logo sigue mostrando y filtrando por proveedor usando nombre visible y comparaciÃ³n case-insensitive.

### QuÃ© se probÃ³
- ValidaciÃ³n estÃ¡tica del flujo entre catÃ¡logo, alta/ediciÃ³n de producto y creaciÃ³n desde compras.

### Pendiente de prueba manual
- Caso A: crear producto desde catÃ¡logo con proveedor y verificar visualizaciÃ³n y filtro.
- Caso B: crear producto desde compra con proveedor preseleccionado y verificar herencia en catÃ¡logo.
- Caso C: probar variantes de mayÃºsculas/minÃºsculas del mismo proveedor en el filtro.

## 2026-05-17 â€” Codex â€” feature/aumento-precios-proveedor

### Tarea
Implementar Prioridad 3 del roadmap: aumento masivo de precios por proveedor y categorÃ­a con previsualizaciÃ³n y confirmaciÃ³n.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/proveedores.html`
- `templates/proveedor_detalle.html`
- `templates/precios_proveedor.html`
- `docs/ai/AI_CHANGELOG.md`

### QuÃ© se cambiÃ³
- Se agregaron funciones de base de datos para obtener productos activos por `proveedor_habitual` y categorÃ­a opcional, y para aplicar aumentos porcentuales redondeados a 2 decimales sobre `costo` y `precio_venta`.
- Se agregaron rutas para abrir la herramienta, previsualizar productos afectados y confirmar el aumento recalculando siempre del lado servidor.
- Se agregÃ³ acceso discreto desde la lista de proveedores y desde el detalle del proveedor con nombre preseleccionado.
- La previsualizaciÃ³n muestra costo/venta actual y nuevo antes de aplicar cambios.

### QuÃ© se probÃ³
- ValidaciÃ³n sintÃ¡ctica de Python.
- RevisiÃ³n estÃ¡tica del flujo GET/POST, previsualizaciÃ³n y confirmaciÃ³n.

### Pendiente de prueba manual
- Caso A: aumento por proveedor sin categorÃ­a.
- Caso B: aumento por proveedor + categorÃ­a.
- Caso C: proveedor sin productos.
- Caso D: porcentaje vacÃ­o, cero o negativo.

## 2026-05-17 â€” Codex â€” feature/aumento-precios-proveedor correcciÃ³n acceso

### Tarea
Corregir el acceso a "% Actualizar Precios" para que abra la pantalla sin `Not Found`.

### Archivos modificados
- `app.py`
- `docs/ai/AI_CHANGELOG.md`

### QuÃ© se cambiÃ³
- Se agregaron aliases legacy para `precios_proveedor`, `precios_proveedor_previsualizar` y `precios_proveedor_aplicar`, siguiendo el patrÃ³n ya usado por el proyecto para endpoints de `main_bp` sin prefijo.
- Con esto, los enlaces y formularios existentes con `url_for('precios_proveedor')` vuelven a resolver contra `/precios/proveedor`.

### QuÃ© se probÃ³
- VerificaciÃ³n del `url_map` para confirmar que `/precios/proveedor` queda accesible tanto por `main.precios_proveedor` como por `precios_proveedor`.

### Pendiente de prueba manual
- Hacer click en "% Actualizar Precios" desde listado de proveedores.
- Hacer click en "Actualizar precios" desde detalle de proveedor.
- Confirmar que la pantalla abre correctamente sin aplicar cambios todavÃ­a.

## 2026-05-17 â€” Codex â€” feature/aumento-precios-proveedor mejora confirmaciÃ³n

### Tarea
Reemplazar la confirmaciÃ³n nativa del navegador por un modal SweetAlert2 en la aplicaciÃ³n de aumentos masivos.

### Archivos modificados
- `templates/precios_proveedor.html`
- `docs/ai/AI_CHANGELOG.md`

### QuÃ© se cambiÃ³
- Se eliminÃ³ el `confirm()` nativo del botÃ³n "Confirmar aumento".
- Se agregÃ³ un formulario identificado con `data-*` para porcentaje, proveedor, categorÃ­a y cantidad afectada.
- Se incorporÃ³ confirmaciÃ³n visual con SweetAlert2, manteniendo la lÃ³gica actual de aplicaciÃ³n por POST.
- El texto del modal ahora corrige el plural entre `1 producto` y `N productos`.

### QuÃ© se probÃ³
- RevisiÃ³n estÃ¡tica del flujo de previsualizaciÃ³n y confirmaciÃ³n en el template.

### Pendiente de prueba manual
- Confirmar que al presionar "Confirmar aumento" aparece el modal SweetAlert2.
- Verificar que "Cancelar" no aplique cambios.
- Verificar que "SÃ­, aplicar aumento" ejecute el POST correctamente.

## 2026-05-17 â€” Codex â€” feature/categorias-configurables

### Tarea
Implementar Prioridad 4 del roadmap: categorÃ­as configurables para productos, manteniendo compatibilidad con categorÃ­as base y productos existentes.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/config.html`
- `app.py`
- `docs/ai/AI_CHANGELOG.md`

### QuÃ© se cambiÃ³
- Se agregaron funciones para listar categorÃ­as personalizadas, categorÃ­as usadas, categorÃ­as configurables y su estado consolidado por rubro actual.
- La gestiÃ³n de categorÃ­as ahora permite crear, renombrar y activar/desactivar sin borrado destructivo, con validaciÃ³n case-insensitive y actualizaciÃ³n de `productos.categoria` al renombrar.
- Las categorÃ­as base hardcodeadas siguen existiendo, pero ahora pueden ocultarse mediante registros de tabla inactivos sin romper compatibilidad.
- La pantalla de ConfiguraciÃ³n ahora muestra estado, origen y cantidad de productos por categorÃ­a, con acciones de agregar, renombrar y activar/desactivar.
- Los formularios siguen usando la lista unificada de categorÃ­as visibles, manteniendo la categorÃ­a actual incluso si quedÃ³ inactiva en ediciÃ³n.
- Se agregaron aliases legacy para los nuevos endpoints de categorÃ­as en `app.py`.

### QuÃ© se probÃ³
- ValidaciÃ³n sintÃ¡ctica de Python.
- RevisiÃ³n estÃ¡tica del flujo de configuraciÃ³n y de los selects de categorÃ­a en alta/ediciÃ³n de productos.

### Pendientes
- Caso A: crear una categorÃ­a nueva y usarla en un producto.
- Caso B: renombrar una categorÃ­a y verificar actualizaciÃ³n en productos existentes.
- Caso C: desactivar una categorÃ­a y confirmar que no aparezca en productos nuevos pero sÃ­ siga visible en ediciÃ³n si ya estÃ¡ asignada.
- Caso D: intentar crear una categorÃ­a duplicada con distinta capitalizaciÃ³n.
- Caso E: verificar que categorÃ­as de gastos y reportes sigan funcionando igual.

## 2026-05-17 â€” Codex â€” feature/carga-lotes-productos

### Tarea
Implementar Prioridad 5A del roadmap: carga por lotes de productos Ãºnicos reutilizando la lÃ³gica existente de alta.

### Archivos modificados
- `routes/main.py`
- `templates/productos.html`
- `templates/productos_lote.html`
- `app.py`
- `docs/ai/AI_CHANGELOG.md`

### QuÃ© se cambiÃ³
- Se agregÃ³ una pantalla de "Carga por lote" accesible desde CatÃ¡logo.
- La carga por lote permite definir datos comunes del producto y varias filas individuales con descripciÃ³n, costo, precio, stock y cÃ³digo de barras.
- El guardado valida todas las filas antes de crear productos y usa `db.add_producto(data)` para cada fila vÃ¡lida, evitando duplicar lÃ³gica.
- Se ignoran filas completamente vacÃ­as y se evita guardado parcial cuando una fila cargada tiene errores.
- Se respetan categorÃ­as configurables, proveedor habitual y unidades disponibles del rubro actual.
- Se agregÃ³ alias legacy para el nuevo endpoint en `app.py`.

### QuÃ© se probÃ³
- ValidaciÃ³n sintÃ¡ctica de Python.
- RevisiÃ³n estÃ¡tica del flujo de validaciÃ³n, creaciÃ³n en lote y retorno al catÃ¡logo.

### Pendiente
- Caso A: crear varios productos desde lote y verificar proveedor/categorÃ­a en catÃ¡logo.
- Caso B: dejar filas vacÃ­as y confirmar que solo se cree la fila vÃ¡lida.
- Caso C: provocar error en una fila y verificar que no haya guardado parcial.
- Caso D: usar una categorÃ­a configurable nueva y validar que aparezca correctamente.

## 2026-05-17 â€” Codex â€” feature/importacion-productos-plantilla

### Tarea
Implementar Prioridad 6 del roadmap: importaciÃ³n de productos mediante plantilla CSV descargable.

### Archivos modificados
- `routes/main.py`
- `templates/productos.html`
- `templates/productos_importar.html`
- `app.py`
- `docs/ai/AI_CHANGELOG.md`

### QuÃ© se cambiÃ³
- Se agregÃ³ una pantalla de importaciÃ³n CSV accesible desde CatÃ¡logo con instrucciones, columnas esperadas y carga de archivo.
- Se agregÃ³ descarga de plantilla CSV usando `csv` de la librerÃ­a estÃ¡ndar y `Response`.
- La importaciÃ³n valida encabezados, tolera BOM con `utf-8-sig`, ignora filas completamente vacÃ­as y acumula errores por fila sin guardar parcialmente.
- Si no hay errores, se crean los productos usando `db.add_producto(data)` respetando proveedor habitual, categorÃ­as configurables y valores por defecto del rubro actual.
- Se agregaron aliases legacy para los nuevos endpoints en `app.py`.

### QuÃ© se probÃ³
- ValidaciÃ³n sintÃ¡ctica de Python.
- RevisiÃ³n estÃ¡tica del flujo de descarga de plantilla, validaciÃ³n e importaciÃ³n completa sin guardado parcial.

### Pendiente
- Caso A: importar 2 productos vÃ¡lidos y verificarlos en catÃ¡logo.
- Caso B: importar CSV sin `descripcion` y verificar error.
- Caso C: importar mezcla de fila vÃ¡lida e invÃ¡lida y confirmar que no se importe ninguna.
- Caso D: importar con categorÃ­a vacÃ­a y confirmar categorÃ­a por defecto.
- Caso E: importar con `proveedor_habitual` y validar visualizaciÃ³n/filtro.

## 2026-05-17 â€” Codex â€” feature/importacion-productos-plantilla correcciÃ³n plantilla nativa

### Tarea
Corregir la UX de descarga de plantilla CSV en ventana nativa pywebview para que el usuario sepa dÃ³nde se generÃ³ el archivo.

### Archivos modificados
- `routes/main.py`
- `templates/productos_importar.html`
- `app.py`
- `docs/ai/AI_CHANGELOG.md`

### QuÃ© se cambiÃ³
- El flujo principal ahora genera la plantilla CSV en una carpeta conocida: `exports/plantillas/plantilla_productos_nexar.csv`.
- La app muestra un `flash` con la ruta exacta del archivo generado.
- Se agregÃ³ un botÃ³n opcional para abrir la carpeta de plantillas reutilizando el patrÃ³n existente del proyecto.
- La pantalla de importaciÃ³n ahora explica por quÃ© en ventana nativa se usa generaciÃ³n local en vez de depender solo de la descarga del navegador embebido.

### QuÃ© se probÃ³
- ValidaciÃ³n sintÃ¡ctica de Python.
- RevisiÃ³n estÃ¡tica del flujo de generaciÃ³n de plantilla, apertura de carpeta y mantenimiento de la importaciÃ³n existente.

### Pendiente
- Generar la plantilla desde la ventana nativa y verificar que el archivo exista en la ruta informada.
- Abrir el archivo con Excel o LibreOffice.
- Confirmar que la importaciÃ³n CSV sigue funcionando sin cambios.

## 2026-05-17 â€” Codex â€” feature/importacion-productos-plantilla mejora destino

### Tarea
Mejorar la generaciÃ³n de la plantilla CSV para permitir guardarla en Descargas ademÃ¡s de la carpeta de la aplicaciÃ³n.

### Archivos modificados
- `routes/main.py`
- `templates/productos_importar.html`
- `docs/ai/AI_CHANGELOG.md`

### QuÃ© se cambiÃ³
- Se agregÃ³ selector de destino para generar la plantilla en la carpeta de la aplicaciÃ³n o en `Downloads`.
- Si `Downloads` no existe, la app usa la carpeta personal del usuario y, como Ãºltimo fallback, la carpeta de la aplicaciÃ³n.
- La generaciÃ³n sigue mostrando la ruta final exacta mediante `flash`.
- Se mantuvo intacta la importaciÃ³n CSV actual.

### QuÃ© se probÃ³
- ValidaciÃ³n sintÃ¡ctica de Python.
- RevisiÃ³n estÃ¡tica del flujo de selecciÃ³n de destino, fallback y mensaje final al usuario.

### Pendiente
- Generar la plantilla en carpeta de la app y verificar ruta.
- Generar la plantilla en Descargas y verificar ruta.
- Confirmar fallback correcto cuando `Downloads` no exista.

## 2026-05-17 â€” Codex â€” feature/importacion-productos-plantilla mejora detecciÃ³n descargas

### Tarea
Mejorar la detecciÃ³n de la carpeta Descargas/Downloads para generar la plantilla CSV.

### Archivos modificados
- `routes/main.py`
- `docs/ai/AI_CHANGELOG.md`

### QuÃ© se cambiÃ³
- La resoluciÃ³n de carpeta de descargas ahora revisa `XDG_DOWNLOAD_DIR` si existe.
- TambiÃ©n prueba `~/Downloads`, `~/Descargas` y `~/descargas`.
- Si no encuentra ninguna carpeta vÃ¡lida, usa `Path.home()` y mantiene la carpeta de la app como fallback final.

### QuÃ© se probÃ³
- ValidaciÃ³n sintÃ¡ctica de Python.
- RevisiÃ³n estÃ¡tica del flujo de selecciÃ³n de destino y fallbacks.

### Pendiente
- Verificar generaciÃ³n en Linux con carpeta `Descargas`.
- Verificar generaciÃ³n en entornos con `XDG_DOWNLOAD_DIR`.

## 2026-05-17 â€” Codex â€” feature/codigos-barras-internos

### Tarea
Implementar generaciÃ³n opcional de cÃ³digos de barras internos para productos nuevos, ediciÃ³n, carga por lote e importaciÃ³n CSV.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/producto_form.html`
- `templates/productos_lote.html`
- `templates/productos_importar.html`
- `docs/ai/AI_CHANGELOG.md`

### QuÃ© se cambiÃ³
- Se agregÃ³ un correlativo interno `NXR00000001` basado en `config.siguiente_codigo_barras_interno`, con verificaciÃ³n de unicidad contra `productos.codigo_barras`.
- `db.add_producto()` y `db.update_producto()` ahora generan el cÃ³digo interno solo cuando el usuario lo pide y el campo estÃ¡ vacÃ­o.
- TambiÃ©n se agregÃ³ validaciÃ³n centralizada para impedir cÃ³digos de barras manuales duplicados.
- En alta y ediciÃ³n de producto se sumÃ³ el checkbox para generar cÃ³digo interno cuando no hay cÃ³digo de fÃ¡brica.
- La carga por lote ahora permite generar cÃ³digos internos para filas sin cÃ³digo y valida duplicados manuales antes de crear productos.
- La importaciÃ³n CSV agregÃ³ la misma opciÃ³n y valida duplicados manuales por fila antes de importar, evitando guardados parciales.

### QuÃ© se probÃ³
- ValidaciÃ³n sintÃ¡ctica de Python.
- RevisiÃ³n estÃ¡tica del flujo de creaciÃ³n, ediciÃ³n, lote e importaciÃ³n con cÃ³digos manuales y autogenerados.

### Pendiente
- Crear producto nuevo sin cÃ³digo y confirmar generaciÃ³n `NXR...`.
- Editar producto sin cÃ³digo y confirmar generaciÃ³n.
- Probar carga por lote con varios productos sin cÃ³digo.
- Probar importaciÃ³n CSV con generaciÃ³n interna activada.
- Verificar rechazo de cÃ³digos manuales duplicados sin guardado parcial.
## 2026-05-18 Ã¢â‚¬â€ Codex Ã¢â‚¬â€ feature/reportes-demo

### Tarea
Implementar Prioridad 8 del roadmap: habilitar reportes en versiÃƒÂ³n demo.

### Archivos modificados
- `licensing/planes.py`
- `docs/ai/AI_CHANGELOG.md`

### QuÃƒÂ© se cambiÃƒÂ³
- Se agregÃƒÂ³ el mÃƒÂ³dulo `reportes` al plan `DEMO` en el mapping central de planes.
- Con ese cambio, la UI deja de ocultar "Resumen Mensual" y "EstadÃƒÂ­sticas Anuales" en demo, porque ambas pantallas ya dependen de `modulo_activo("reportes")`.
- No se habilitaron exportaciones ni otros mÃƒÂ³dulos premium: `export`, `multiusuario`, `temporadas` y demÃƒÂ¡s siguen igual.
- No fue necesario agregar un mÃƒÂ³dulo separado `estadisticas`, porque la ruta `/estadisticas` ya usa `require_modulo("reportes")`.

### QuÃƒÂ© se probÃƒÂ³
- RevisiÃƒÂ³n estÃƒÂ¡tica de `routes/main.py`: `/reportes`, `/estadisticas` y `rentabilidad_detallada` siguen protegidos por `require_modulo("reportes")`.
- RevisiÃƒÂ³n estÃƒÂ¡tica de `templates/base.html`: la navegaciÃƒÂ³n de reportes ya depende de `modulo_activo("reportes")`, por lo que se habilita correctamente en demo.
- ValidaciÃƒÂ³n local del mapping para confirmar que `DEMO` ahora resuelve `core` + `reportes`.

### Pendiente de prueba manual
- Abrir `/reportes` con licencia demo y confirmar carga correcta.
- Abrir `/estadisticas` con licencia demo y confirmar carga correcta.
- Verificar que "Mi plan" muestre `reportes` como mÃƒÂ³dulo habilitado en demo.
- Confirmar que exportaciones sigan bloqueadas en demo.

## 2026-05-18 Ã¢â‚¬â€ Codex Ã¢â‚¬â€ feature/onboarding-inicial

### Tarea
Implementar Prioridad 9A del roadmap: onboarding inicial liviano en dashboard.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/dashboard.html`
- `docs/ai/AI_CHANGELOG.md`

### QuÃƒÂ© se cambiÃƒÂ³
- Se agregÃƒÂ³ `get_onboarding_context()` para resumir estado inicial de la instalaciÃƒÂ³n usando cantidad de productos activos, proveedores activos, ventas, rubro confirmado y preferencia `onboarding_oculto`.
- La ruta `dashboard()` ahora envÃƒÂ­a `onboarding_context` al template.
- Se agregÃƒÂ³ una ruta POST para ocultar la guÃƒÂ­a y persistir `onboarding_oculto=1` en config.
- El dashboard ahora muestra una card "Primeros pasos" solo cuando falta al menos uno de estos puntos: rubro, proveedor, producto o primera venta.
- La card incluye accesos directos a configurar negocio, crear proveedor, crear producto, registrar compra/venta y ver reportes.
- Si el plan no tiene reportes activos, la card evita mandar a una pantalla bloqueada y deriva a `Mi plan`.
- La guÃƒÂ­a no bloquea la app ni obliga a completar ningÃƒÂºn paso.

### QuÃƒÂ© se probÃƒÂ³
- ValidaciÃƒÂ³n sintÃƒÂ¡ctica de Python con `python -m py_compile database.py routes/main.py`.
- RevisiÃƒÂ³n estÃƒÂ¡tica del flujo de dashboard, ocultado de onboarding y render condicional del template.

### Pendiente de prueba manual
- Abrir dashboard en una instalaciÃƒÂ³n nueva y confirmar que aparece la card.
- Ocultar la guÃƒÂ­a y verificar que no vuelva a mostrarse.
- Probar un caso con proveedor/producto/ventas ya cargados y confirmar que la card solo aparezca si todavÃƒÂ­a falta algo.
- Confirmar que el dashboard sigue cargando normal cuando no corresponde mostrar onboarding.
## 2026-05-18 Ã¢â‚¬â€ Codex Ã¢â‚¬â€ feature/imagenes-catalogo

### Tarea
Implementar Prioridad 10A del roadmap: imÃƒÂ¡genes en catÃƒÂ¡logo MVP.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/producto_form.html`
- `templates/productos.html`
- `static/uploads/productos/.gitkeep`
- `.gitignore`
- `docs/ai/AI_CHANGELOG.md`

### QuÃƒÂ© se cambiÃƒÂ³
- Se agregÃƒÂ³ la columna segura `productos.imagen` en la creaciÃƒÂ³n inicial de la tabla y en la migraciÃƒÂ³n con `PRAGMA table_info(productos)` + `ALTER TABLE` para bases existentes.
- Se agregÃƒÂ³ guardado local de imÃƒÂ¡genes bajo `static/uploads/productos/`, usando nombre ÃƒÂºnico con `uuid`, extensiones permitidas (`.jpg`, `.jpeg`, `.png`, `.webp`) y `secure_filename`.
- Alta de producto ahora acepta archivo de imagen y guarda la ruta relativa `uploads/productos/...` en `productos.imagen`.
- EdiciÃƒÂ³n de producto ahora muestra la imagen actual, permite reemplazarla y conserva la anterior si no se sube una nueva.
- El catÃƒÂ¡logo ahora muestra una miniatura de 48x48 por producto y un placeholder simple cuando no hay imagen.
- Se versionÃƒÂ³ la carpeta de uploads con `.gitkeep` y se ignoraron las imÃƒÂ¡genes reales subidas por usuario en `.gitignore`.
- No se implementÃƒÂ³ borrado automÃƒÂ¡tico de archivos anteriores ni integraciÃƒÂ³n con cÃƒÂ¡mara/telÃƒÂ©fono en este MVP.

### QuÃƒÂ© se probÃƒÂ³
- ValidaciÃƒÂ³n sintÃƒÂ¡ctica de Python con `python -m py_compile database.py routes/main.py`.
- RevisiÃƒÂ³n estÃƒÂ¡tica del flujo de alta, ediciÃƒÂ³n, validaciÃƒÂ³n de extensiones, persistencia de ruta relativa y render de miniaturas en catÃƒÂ¡logo.

### Pendiente de prueba manual
- Caso A: crear producto con imagen, guardarlo, ver miniatura en catÃƒÂ¡logo y ver imagen actual al editar.
- Caso B: crear producto sin imagen y verificar placeholder en catÃƒÂ¡logo.
- Caso C: editar producto con imagen sin subir nueva y confirmar que conserva la anterior.
- Caso D: editar producto con imagen, subir una nueva y confirmar que cambia la miniatura.
- Caso E: intentar subir un `.txt` y verificar mensaje claro sin guardar imagen invÃƒÂ¡lida.
## 2026-05-18 Ã¢â‚¬â€ Codex Ã¢â‚¬â€ feature/imagenes-catalogo mejora visual

### Tarea
Mejorar Prioridad 10A: normalizaciÃƒÂ³n visual y preview de imÃƒÂ¡genes en catÃƒÂ¡logo.

### Archivos modificados
- `routes/main.py`
- `templates/producto_form.html`
- `templates/productos.html`
- `docs/ai/AI_CHANGELOG.md`

### QuÃƒÂ© se cambiÃƒÂ³
- Se agregÃƒÂ³ texto de ayuda mÃƒÂ¡s claro en el formulario con tamaÃƒÂ±o recomendado `800 x 800 px`, formatos admitidos y aclaraciÃƒÂ³n de que la app ordena la vista del catÃƒÂ¡logo.
- La imagen actual en ediciÃƒÂ³n ahora se muestra con lÃƒÂ­mite visual razonable y `object-fit: contain`, evitando previews gigantes o deformadas.
- Las miniaturas del catÃƒÂ¡logo se normalizaron a `56 x 56 px`, con borde y placeholder uniforme cuando el producto no tiene imagen.
- Se agregÃƒÂ³ preview ampliado al pasar el mouse sobre una miniatura, con popover acotado y vista mÃƒÂ¡xima aproximada de `360 x 360 px`.
- En pantallas chicas el popover ampliado se oculta para no tapar la interfaz.
- En backend se agregÃƒÂ³ validaciÃƒÂ³n simple de tamaÃƒÂ±o para rechazar archivos mayores a `3 MB`.
- No se agregÃƒÂ³ Pillow ni redimensionado automÃƒÂ¡tico porque `requirements.txt` no lo incluye hoy.

### QuÃƒÂ© se probÃƒÂ³
- ValidaciÃƒÂ³n sintÃƒÂ¡ctica de Python con `python -m py_compile database.py routes/main.py`.
- RevisiÃƒÂ³n estÃƒÂ¡tica del render del formulario, miniaturas uniformes, popover ampliado y lÃƒÂ­mite de 3 MB.

### Pendiente de prueba manual
- Verificar que la miniatura uniforme no rompa el ancho de la tabla del catÃƒÂ¡logo.
- Confirmar que el popover ampliado aparece al pasar el mouse y no supera visualmente el tamaÃƒÂ±o esperado.
- Confirmar que en mÃƒÂ³vil o ventana angosta el popover no molesta.
- Intentar subir una imagen mayor a 3 MB y validar el mensaje de error.
## 2026-05-18 Ã¢â‚¬â€ Codex Ã¢â‚¬â€ feature/imagenes-catalogo correccion preview modal

### Tarea
Corregir el preview de imÃƒÂ¡genes en catÃƒÂ¡logo para evitar recorte dentro de la tabla responsive.

### Archivos modificados
- `templates/productos.html`
- `docs/ai/AI_CHANGELOG.md`

### QuÃƒÂ© se cambiÃƒÂ³
- Se reemplazÃƒÂ³ el preview ampliado por hover dentro de la tabla por apertura mediante modal Bootstrap al hacer click en la miniatura.
- La miniatura se mantuvo uniforme en `56 x 56 px` con `object-fit: cover`, borde redondeado y cursor `zoom-in`.
- Cada imagen real ahora carga sus datos en un ÃƒÂºnico modal reutilizable con tÃƒÂ­tulo por producto.
- Se eliminÃƒÂ³ la dependencia visual del popover hover que se cortaba por `table-responsive` o contenedores de la card.
- Los productos sin imagen siguen mostrando placeholder y no disparan modal.

### QuÃƒÂ© se probÃƒÂ³
- RevisiÃƒÂ³n estÃƒÂ¡tica del template y del JavaScript que abre/cierra el modal Bootstrap.

### Pendiente de prueba manual
- Confirmar que al hacer click en la miniatura se abre el modal con la imagen correcta.
- Confirmar que el modal cierra bien desde botÃƒÂ³n cerrar y backdrop.
- Verificar que la imagen ampliada no se corta y no ocupa toda la ventana.

## 2026-05-18 â€” Codex â€” audit/edicion-responsable

### Tarea
AuditorÃ­a de ediciÃ³n responsable global.

### Archivos modificados
- `docs/ai/AUDITORIA_EDICION_RESPONSABLE.md`
- `docs/ai/AI_CHANGELOG.md`

### QuÃ© se cambiÃ³
- Se documentaron riesgos de ediciÃ³n, eliminaciÃ³n, desactivaciÃ³n y anulaciÃ³n.
- No se modificÃ³ lÃ³gica funcional.

### Pendiente
- Implementar correcciones en ramas pequeÃ±as segÃºn prioridades detectadas.

## 2026-05-18 — Codex — fix/ventas-anulacion-segura

### Tarea
Implementar corrección de auditoría: ventas con anulación segura.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/historial.html`
- `templates/ticket.html`
- `templates/cliente_detalle.html`
- `docs/ai/AUDITORIA_EDICION_RESPONSABLE.md`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se agregaron columnas seguras en `ventas` para estado y trazabilidad de anulación: `anulada`, `anulada_at`, `anulada_por` y `motivo_anulacion`.
- El flujo principal del historial dejó de borrar ventas físicamente y ahora usa `db.anular_venta(...)`.
- La anulación restaura stock una sola vez, conserva `ventas` y `ventas_detalle`, y registra movimiento de stock de anulación.
- Si la venta tenía impacto en cuenta corriente y existía el movimiento original, se agrega una compensación simple sin borrar historial.
- Se filtraron ventas anuladas en dashboard, caja resumida y reportes/rentabilidad principales del MVP.
- La UI ahora muestra estado `Anulada`, impide reanular desde el listado y actualiza el modal de confirmación para hablar de anulación y no de borrado.
- La auditoría quedó actualizada para marcar ventas como corregido parcialmente con este MVP.

### Qué se probó
- Validación sintáctica con `python -m py_compile database.py routes/main.py`.
- Revisión estática de historial, ticket, detalle de cliente y consultas principales de ventas/reportes.

### Pendientes
- Confirmar manualmente que una venta anulada no siga sumando en todas las vistas secundarias fuera del recorte MVP.
- Definir una estrategia más formal para compensación de caja histórica si luego se requiere trazabilidad contable más estricta.

## 2026-05-18 — Codex — fix/compras-anulacion-segura

### Tarea
Implementar corrección de auditoría: compras con anulación segura.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/compras.html`
- `templates/compra_detalle.html`
- `templates/proveedor_detalle.html`
- `docs/ai/AUDITORIA_EDICION_RESPONSABLE.md`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se agregaron columnas seguras en `compras` para estado y trazabilidad de anulación: `anulada`, `anulada_at`, `anulada_por` y `motivo_anulacion`.
- El flujo principal de compras dejó de borrar registros físicamente y ahora usa `db.anular_compra(...)`.
- La anulación revierte stock una sola vez y registra movimiento `ANULACION_COMPRA`.
- Si el stock actual no alcanza para revertir la cantidad ingresada, la anulación se bloquea con mensaje claro.
- Si la compra tiene factura proveedor asociada, el MVP bloquea la anulación para no romper deuda comercial ni historial de proveedor.
- La UI ahora muestra estado `Anulada`, deshabilita acciones sobre compras anuladas y cambia el copy de eliminación por anulación.
- La auditoría quedó actualizada para marcar compras como corregido parcialmente con este MVP.

### Qué se probó
- Validación sintáctica con `python -m py_compile database.py routes/main.py`.
- Revisión estática del flujo de compras, detalle de compra, historial en proveedor y validaciones de stock/factura asociada.

### Pendientes
- Confirmar manualmente los casos de anulación con stock suficiente, bloqueo por stock insuficiente y bloqueo por factura proveedor asociada.
- Revisar futuras métricas o reportes derivados de compras si se agregan totales activos fuera del historial/listado actual.

## 2026-05-18 — Codex — fix/compras-anulacion-segura UX responsable

### Tarea
Mejorar UX de anulación de compras para igualarla a ventas.

### Archivos modificados
- `routes/main.py`
- `templates/compras.html`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se reemplazó el `confirm()` nativo del navegador por un modal Bootstrap integrado con el estilo de Nexar Comercio.
- El modal ahora muestra datos de la compra seleccionada, permite cargar motivo opcional y exige checkbox de confirmación.
- La ruta de anulación de compras ahora valida credenciales y confirmación con el mismo estándar responsable que ventas.
- No se modificó la lógica backend de reversión de stock ni las guardas de anulación segura ya implementadas, salvo la validación mínima del POST.

### Qué se probó
- Validación sintáctica con `python -m py_compile routes/main.py`.
- Revisión estática del modal, carga de data attributes y validación del POST.

### Pendientes
- Confirmar manualmente apertura/cierre del modal, cancelación sin efectos y anulación correcta con contraseña y checkbox.
## 2026-05-18 — Codex — feature/proveedores-anulacion-segura

### Tarea
Implementar anulación segura para facturas de proveedor y endurecer su manejo contable básico.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `services/cuentas_corrientes.py`
- `templates/proveedor_facturas.html`
- `templates/proveedor_detalle.html`
- `tests/test_proveedor_facturas_anulacion.py`
- `docs/ai/AUDITORIA_EDICION_RESPONSABLE.md`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se agregaron columnas seguras en `facturas_proveedores` para trazabilidad de anulación: `anulada`, `anulada_at`, `anulada_por` y `motivo_anulacion`.
- El flujo principal dejó de borrar facturas físicamente y ahora usa `db.anular_factura_proveedor(...)`, conservando historial visible.
- La anulación exige motivo obligatorio, impide doble anulación y bloquea facturas con pagos ya registrados para no romper deuda comercial.
- Las facturas anuladas dejan de computar como deuda activa, vencidas o pendientes en los resúmenes principales del MVP.
- Ya no se puede editar ni registrar pagos sobre facturas anuladas.
- La UI ahora usa un modal Bootstrap responsable, muestra advertencias claras, conserva la factura en historial y deshabilita acciones peligrosas cuando corresponde.
- Se agregaron tests mínimos para anulación sin pagos, bloqueo de doble anulación, conservación de historial y protección de facturas con pagos.
- La auditoría quedó actualizada para reflejar qué quedó protegido y qué pendientes siguen abiertos en cuenta corriente proveedor.

### Qué se probó
- Validación sintáctica con `python -m py_compile database.py routes/main.py services/cuentas_corrientes.py`.
- Tests unitarios con `python -m unittest tests.test_proveedor_facturas_anulacion`.

### Pendientes
- Confirmar manualmente el flujo visual del modal de anulación desde la ficha de proveedor.
- Evaluar en una rama futura una trazabilidad más fina para pagos parciales y para `cc_proveedores_mov` legado si se profundiza la cuenta corriente proveedor.
## 2026-05-18 — Codex — feature/proveedores-anulacion-segura UX proveedores

### Tarea
Reemplazar confirmaciones nativas del navegador por confirmación visual homogénea en Gestión de Proveedores.

### Archivos modificados
- `templates/proveedores.html`
- `docs/ai/AUDITORIA_EDICION_RESPONSABLE.md`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se reemplazó el `confirm()` nativo usado al desactivar proveedores desde el listado por un modal Bootstrap reutilizable.
- El modal ahora muestra el nombre del proveedor, la advertencia de que no se borra físicamente y botones claros de cancelar o confirmar.
- Se mantuvo intacta la lógica backend: el formulario sigue enviando el mismo POST a `proveedor_eliminar`.
- Se revisó el detalle de proveedor y no había allí confirmaciones nativas equivalentes para ajustar en este paso.
- La auditoría quedó actualizada para reflejar que la desactivación de proveedores ya usa confirmación homogénea de Nexar.

### Qué se probó
- Revisión estática del template y del JavaScript del modal reutilizable.
- Búsqueda local de `confirm(` y `alert(` en las vistas de proveedores para verificar que no queden popups nativos en este alcance.

### Pendientes
- Confirmar manualmente el flujo de desactivar proveedor desde el listado y la cancelación sin efectos visibles.
## 2026-05-18 — Codex — feature/mejorar-config-ui-categorias corrección renombrado

### Tarea
Corregir el bug crítico de renombrado de categorías y limpiar duplicados de forma segura en configuración.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/config.html`
- `docs/ai/AI_CHANGELOG.md`

### Qué se cambió
- Se corrigió `update_categoria(...)` para que renombre la categoría existente en lugar de crear una nueva y desactivar la anterior.
- El renombrado ahora usa el `id` de la categoría cuando está disponible y conserva el estado activo/inactivo del registro original.
- Se simplificó el submit del formulario inline en `config.html` para que Guardar y Enter envíen solo el form de renombre, sin mezclar acciones con activar/desactivar ni agregar categoría.
- Se agregó limpieza segura de duplicados por nombre normalizado en categorías de productos, con migración de referencias de productos al nombre canónico y consolidación de filas sobrantes.
- Se evitó que categorías base aparezcan también como `personalizada` en la configuración cuando en realidad corresponden al seed/base del rubro.
- Se reforzó la validación para impedir nuevas categorías duplicadas en productos y en categorías de gasto, incluyendo variantes por mayúsculas, espacios y nombres normalizados.
- También se consolidan duplicados existentes en categorías de gasto y se muestran mensajes claros cuando un nombre ya existe.

### Qué se probó
- Validación sintáctica con `python -B -m py_compile database.py routes/main.py`.
- Prueba local con base temporal para verificar:
  - deduplicación de categorías existentes
  - renombrado por `id` sin crear una fila nueva
  - conservación del estado activo
  - migración de productos al nombre renombrado
  - bloqueo de altas duplicadas en categorías de producto y gasto

### Pendientes
- Confirmar manualmente en UI el flujo completo de agregar, renombrar con Enter, renombrar con botón Guardar y activar/desactivar desde `config.html`.
## 2026-05-19 - Codex - feature/cc-clientes-segura

### Tarea
Implementar proteccion operativa MVP para Cuenta Corriente Clientes con anulacion responsable, historial visible y coherencia basica con caja.

### Archivos modificados
- `database.py`
- `routes/main.py`
- `templates/cliente_detalle.html`
- `tests/test_cc_clientes_anulacion.py`
- `docs/ai/AI_CHANGELOG.md`
- `docs/ai/AUDITORIA_EDICION_RESPONSABLE.md`

### Que se cambio
- `cc_clientes_mov` ahora incorpora trazabilidad minima de anulacion: `medio_pago`, `anulado`, `anulada_at`, `anulada_por`, `motivo_anulacion`, `caja_movimiento_id` y `movimiento_origen_id`, con migracion segura para bases existentes.
- La deuda de clientes y los listados/resumenes principales ahora calculan saldo solo con movimientos activos, sin borrar historial anulado.
- Los pagos de clientes dejan de ser simples movimientos genericos: ahora validan importe, conservan historial y, si son en efectivo, generan un `INGRESO` en caja abierta para mantener caja y cuenta corriente alineadas.
- La anulacion de movimientos de clientes exige motivo obligatorio, impide doble anulacion y bloquea movimientos originados por ventas fiadas para que esas correcciones sigan pasando por Historial de ventas.
- Al anular un pago con movimiento de caja asociado, tambien se anula su movimiento de caja relacionado, evitando desalineacion u orfandad.
- El detalle del cliente ahora muestra movimientos anulados en historial visible, deshabilita acciones no permitidas y agrega modal Nexar homogeneo para anular con el aviso: `El movimiento no se borrara. Quedara anulado para conservar historial.`

### Que se probo
- Validacion sintactica con `python -m py_compile database.py routes/main.py`.
- Tests unitarios con `python -m unittest tests.test_cc_clientes_anulacion`.
- Casos cubiertos: venta fiada, registracion de pago, anulacion de pago, bloqueo de doble anulacion, restauracion correcta del saldo, anulacion relacionada de caja y compensacion de deuda al anular la venta fiada.

### Casos dudosos / alcance
- El MVP mantiene el formulario manual de movimientos para ajustes/notas de credito, pero endurece especificamente pagos y movimientos originados por ventas. No incorpora todavia una bitacora avanzada de edicion ni medios de pago diferenciados en UI para cada ajuste manual.
- La UI del detalle cliente quedo protegida sin rehacer la pantalla completa; si despues se profundiza la cuenta corriente, conviene limpiar el formulario heredado y especializar mas el flujo de cobros.
## 2026-05-19 - Codex - feature/gastos-seguros
### Tarea
Implementar gastos seguros con anulacion responsable, sin borrado fisico, con coherencia minima entre gastos, caja e indicadores.
### Archivos modificados
- database.py
- outes/main.py
- 	emplates/gastos.html
- 	ests/test_gastos_seguros.py
- docs/ai/AI_CHANGELOG.md
- docs/ai/AUDITORIA_EDICION_RESPONSABLE.md
### Que se cambio
- La tabla gastos ahora soporta trazabilidad de anulacion con nulado, nulada_at, nulada_por y motivo_anulacion, incluyendo migracion segura para bases existentes.
- Los gastos ya no se eliminan fisicamente ni se editan de forma destructiva: la correccion operativa pasa por anulacion responsable y nueva carga.
- La anulacion exige motivo obligatorio, impide doble anulacion y, si el gasto genero un EGRESO en caja abierta, tambien anula ese movimiento vinculado para no dejar inconsistencias.
- Los reportes y agregados de rentabilidad dejan de contar gastos anulados, pero el historial de gastos los mantiene visibles y marcados.
- La pantalla gastos.html reemplaza el confirm(...) nativo por un modal Nexar homogeneo que muestra fecha, categoria, medio de pago, importe y descripcion reales antes de confirmar la anulacion.
### Que se probo
- Validacion sintactica con python -m py_compile database.py routes/main.py.
- Tests unitarios con python -m unittest tests.test_gastos_seguros tests.test_cc_clientes_anulacion tests.test_proveedor_facturas_anulacion.
- Casos cubiertos en gastos: alta con caja abierta, bloqueo de gasto en efectivo sin caja abierta, anulacion con motivo, bloqueo de doble anulacion, anulacion del movimiento asociado de caja y exclusion de anulados en reportes sin perder historial.
### Casos dudosos / alcance
- El endpoint sigue llamandose gasto_eliminar por compatibilidad, pero ahora ejecuta anulacion responsable.
- La vista deja el acceso de edicion bloqueado para gastos ya registrados; cualquier correccion posterior se resuelve anulando y cargando un nuevo gasto.

## 2026-05-19 - Codex - feature/reportes-historicos-coherentes

### Tarea
Auditar y corregir reportes principales para que no cuenten registros anulados como activos, manteniendo el historial visible donde corresponde.

### Archivos modificados
- `routes/main.py`
- `tests/test_reportes_historicos_coherentes.py`
- `docs/ai/AI_CHANGELOG.md`
- `docs/ai/AUDITORIA_EDICION_RESPONSABLE.md`

### Que se cambio
- Se corrigio el resumen de gastos de `reportes()` para excluir gastos anulados al calcular necesarios, prescindibles y porcentaje.
- Se agrego un helper minimo `_resumen_gastos_reportes(...)` para centralizar ese calculo sin tocar la estructura del modulo.
- Se auditaron los reportes principales y se confirmo que dashboard financiero, estadisticas anuales, rentabilidad detallada y caja diaria ya venian excluyendo ventas/gastos/movimientos anulados en sus consultas clave.

### Que se probo
- Validacion sintactica con `python -m py_compile routes/main.py database.py tests/test_reportes_historicos_coherentes.py`.
- Tests unitarios con `python -m unittest tests.test_reportes_historicos_coherentes tests.test_gastos_seguros tests.test_cc_clientes_anulacion tests.test_proveedor_facturas_anulacion`.
- Casos cubiertos: gasto anulado no suma en reportes, venta anulada no suma en dashboard/rentabilidad, compra anulada no suma como compra activa en estadisticas de proveedor, y caja no duplica movimientos anulados.

### Casos dudosos / alcance
- El alcance efectivo del fix fue chico: el hueco detectado estaba en el resumen mensual de gastos de `reportes()`. El resto de las consultas principales ya estaba alineado con anulaciones seguras.
- Se mantuvo visible el historial anulado en vistas historicas; no se agregaron cambios visuales nuevos porque no hacian falta para la coherencia numerica.

## 2026-05-19 - Codex - feature/auditoria-visual

### Tarea
Implementar un MVP de auditoria visual para acciones criticas ya protegidas, con bitacora de solo lectura y diff minimo.

### Archivos modificados
- `app.py`
- `database.py`
- `routes/main.py`
- `templates/base.html`
- `templates/auditoria.html`
- `tests/test_auditoria_visual.py`
- `docs/ai/AI_CHANGELOG.md`
- `docs/ai/AUDITORIA_EDICION_RESPONSABLE.md`

### Que se cambio
- Se agrego una tabla minima `auditoria` con `fecha`, `usuario`, `accion`, `entidad`, `entidad_id`, `detalle` y `motivo`.
- Se sumaron helpers chicos en `database.py` para registrar y consultar auditoria con filtros simples.
- Se registra auditoria al anular venta, compra, gasto, movimiento de cuenta corriente cliente y factura de proveedor.
- Tambien se registra auditoria al abrir y cerrar caja desde sus rutas existentes.
- Se agrego la pantalla de solo lectura `/auditoria` con tabla Nexar simple y filtros GET por accion, entidad y rango de fechas.
- Se expuso el endpoint legacy `auditoria` para mantener compatibilidad con `url_for(...)` sin prefijo, y se agrego acceso visual en sidebar para admin.

### Que se probo
- Validacion sintactica con `python -m py_compile app.py database.py routes/main.py tests/test_auditoria_visual.py`.
- Tests unitarios con `python -m unittest tests.test_auditoria_visual tests.test_gastos_seguros tests.test_cc_clientes_anulacion tests.test_proveedor_facturas_anulacion tests.test_reportes_historicos_coherentes`.
- Casos cubiertos: anulacion de gasto, anulacion de pago cliente, apertura/cierre de caja y visualizacion de registros en `/auditoria`.

### Casos dudosos / alcance
- No existia mecanismo previo de auditoria, por eso se creo una tabla minima nueva en vez de agregar una solucion mas grande.
- El MVP registra anulacion de factura de proveedor como caso representativo de proveedor protegido; no agrega todavia una bitacora completa para todos los movimientos auxiliares de `cc_proveedores_mov`.

## 2026-05-19 - feature/permisos-basicos

### Tarea
Implementar un MVP de permisos basicos admin/empleado con diff minimo, reutilizando la sesion y los roles existentes.

### Archivos modificados
- `routes/main.py`
- `templates/historial.html`
- `templates/compras.html`
- `templates/gastos.html`
- `templates/cliente_detalle.html`
- `templates/proveedor_facturas.html`
- `tests/test_permisos_basicos.py`
- `docs/ai/AI_CHANGELOG.md`
- `docs/ai/AUDITORIA_EDICION_RESPONSABLE.md`

### Que se cambio
- Se reutilizo el esquema actual de roles y se tomo como admin a `Administrador/admin`; el resto de roles operan como empleado para este MVP.
- Las anulaciones criticas y el ajuste de factura de proveedor quedaron validadas en backend con `@admin_required`.
- Se cerro la autorizacion sensible que antes permitia a un no-admin anular usando credenciales de otro admin; ahora solo un admin logueado puede confirmar con su propia contrasena.
- La UI oculta o reemplaza por candado los botones de anulacion no permitidos en ventas, compras, gastos, cuenta corriente cliente y facturas de proveedor.
- La vista `/auditoria` se mantiene solo para admin y el flujo operativo de empleado para registrar cobros no se bloqueo.

### Que se probo
- Validacion sintactica con `python -m py_compile routes/main.py tests/test_permisos_basicos.py`.
- Tests unitarios con `python -m unittest tests.test_permisos_basicos tests.test_gastos_seguros tests.test_cc_clientes_anulacion tests.test_auditoria_visual tests.test_reportes_historicos_coherentes`.
- Casos cubiertos: admin puede anular gasto, empleado no puede anular venta/compra/gasto/movimiento CC/factura proveedor, empleado no accede a auditoria y empleado puede registrar cobros.

### Casos dudosos / alcance
- No se agrego un catalogo nuevo de roles para evitar refactor; el MVP se apoya en los roles ya presentes (`Administrador`, `Vendedor`, `Encargado`) y reconoce tambien `admin` por compatibilidad.
- Se protegieron solo las acciones criticas pedidas; no se endurecieron otros permisos operativos fuera de alcance.
