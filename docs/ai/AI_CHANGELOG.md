# AI_CHANGELOG.md

Registro de avances hechos por Codex, Copilot, Gemini o ChatGPT.

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
