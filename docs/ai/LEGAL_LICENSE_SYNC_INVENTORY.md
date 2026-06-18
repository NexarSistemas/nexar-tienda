# Inventario de sincronización legal Nexar

Fecha: 2026-06-18

## Alcance ejecutado

La revisión local se realizó sobre el repositorio disponible en el entorno de trabajo: `rolojnb/nexar-tienda`.

La sincronización masiva contra todos los repositorios activos de `rolojnb` y `NexarSistemas` queda pendiente de inventario remoto completo, porque desde este entorno no se pudo consultar GitHub por bloqueo de red del proxy (`curl: (56) CONNECT tunnel failed, response 403`) y no hay credenciales/API de GitHub disponibles en el repositorio local.

## Fuente oficial requerida

- Repositorio fuente: `rolojnb/nexar-legal`
- Archivo oficial: `LICENSE.txt`
- Regla: cualquier diferencia debe resolverse a favor del contenido vigente de `rolojnb/nexar-legal/LICENSE.txt`.

## Inventario local

| Repositorio | Propietario | Rama principal detectada | Rama de trabajo | LICENSE | LICENSE.txt | LICENSE.md | Documentación legal adicional |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `nexar-tienda` | `rolojnb` | No detectable localmente: el clon no tiene remoto configurado | `chore/legal-license-sync` | No | Sí | No | Sí: ruta `/acuerdo-licencia`, template `templates/acuerdo_licencia.html`, aceptación en `templates/registro_inicial.html` y `templates/licencia.html` |

## Archivos legales encontrados en `nexar-tienda`

- `LICENSE.txt`: acuerdo legal local vigente en el repositorio.
- `templates/acuerdo_licencia.html`: pantalla que muestra el contenido de `LICENSE.txt` sin resumirlo.
- `routes/main.py`: ruta `/acuerdo-licencia`, que lee `LICENSE.txt` desde `LICENSE_TEXT_PATH`.
- `templates/registro_inicial.html`: aceptación obligatoria durante configuración inicial.
- `templates/licencia.html`: aceptación obligatoria antes de solicitar o activar licencia cuando corresponde.
- `build/nexar_tienda.iss`: usa `LICENSE.txt` como licencia visible del instalador Windows e incluye una copia dentro del directorio instalado.
- `build_deb.sh`: copia `LICENSE.txt` dentro del paquete Debian cuando el archivo existe en la raíz del repositorio.

## Referencias legales detectadas en `nexar-tienda`

| Archivo | Referencia | Estado |
| --- | --- | --- |
| `templates/registro_inicial.html` | Enlace al acuerdo mediante `url_for('acuerdo_licencia')` | Apunta a la ruta local que muestra `LICENSE.txt` |
| `templates/licencia.html` | Enlace al acuerdo mediante `url_for('acuerdo_licencia')` en solicitud de licencia | Apunta a la ruta local que muestra `LICENSE.txt` |
| `templates/licencia.html` | Enlace al acuerdo mediante `url_for('acuerdo_licencia')` en activación de licencia | Apunta a la ruta local que muestra `LICENSE.txt` |
| `routes/main.py` | Mensaje de validación cuando no se acepta el acuerdo | Consistente con el flujo de aceptación |
| `CHANGELOG.md` | Mención histórica al instalador Windows con aceptación de licencia | Referencia informativa histórica; no se modificó |
| `build/nexar_tienda.iss` | `LicenseFile=..\LICENSE.txt` | Usa `LICENSE.txt` como licencia presentada por el instalador Windows |
| `build/nexar_tienda.iss` | `Source: "..\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion` | Incluye/copia `LICENSE.txt` dentro del instalador Windows |
| `build_deb.sh` | Copia condicional de `${SCRIPT_DIR}/LICENSE.txt` a `${INSTALL_DIR}/` | Incluye/copia `LICENSE.txt` dentro del paquete Debian cuando existe |

## Flujos de aceptación identificados

1. Configuración inicial (`templates/registro_inicial.html`): el usuario debe marcar `accept_license_agreement` para finalizar la configuración inicial.
2. Solicitud de licencia (`templates/licencia.html`): cuando `requires_initial_license_acceptance` está activo, el formulario exige aceptar el acuerdo antes de enviar la solicitud.
3. Activación de licencia (`templates/licencia.html`): cuando `requires_initial_license_acceptance` está activo, el formulario exige aceptar el acuerdo antes de activar una clave.
4. Validación backend (`routes/main.py`): si el checkbox requerido no llega en el POST, se rechaza la operación con el mensaje `Debés aceptar el Acuerdo de Licencia de Uso para continuar.`.

## Problemas detectados

- No se pudo comparar `LICENSE.txt` local contra `rolojnb/nexar-legal/LICENSE.txt` por falta de acceso remoto desde el entorno.
- No se pudo generar el inventario de todos los repositorios activos de `rolojnb` y `NexarSistemas` por la misma limitación de red/API.
- El clon local no tiene remoto configurado, por lo que no se pudo confirmar la rama principal desde Git.

## Cambios recomendados antes de la sincronización masiva

1. Ejecutar el inventario remoto con credenciales de GitHub o desde un entorno con acceso a `api.github.com`.
2. Descargar `rolojnb/nexar-legal/LICENSE.txt` y calcular checksum oficial.
3. Para cada repositorio activo no archivado/no legacy/no fork sin uso, crear `chore/legal-license-sync`, copiar o reemplazar `LICENSE.txt` exactamente, actualizar referencias documentales mínimas y abrir PR.
4. Mantener fuera de alcance la lógica de licencias técnicas, planes, pagos, Supabase, workflows, builds y deploys.
