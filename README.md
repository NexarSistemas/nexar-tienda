# Nexar Comercio v1.36.7

Sistema integral de gestion comercial para tiendas y comercios minoristas.
`Nexar Comercio` es la marca visible del producto. `nexar-tienda` se mantiene
como identificador tecnico compatible para builds, instaladores, actualizaciones
y artefactos existentes.

Estado actual:

- Estado del repositorio: activo
- Version actual: `1.36.7`
- Contexto central del ecosistema: repo externo `nexar-ai-context`, archivo `CONTEXTO_NEXAR.md`
- Relacion con `nexar-comercio`: repo legacy/no activo dentro del ecosistema vigente; no usarlo como reemplazo operativo de `nexar-tienda`.
- Relacion con `nexar-almacen`: si aparece como repo separado, tratarlo tambien como legacy/no activo.

Release comercial estable `v1.36.7`:

- Se elimina el aviso duplicado de vencimiento proximo en `Mi Plan` y se conserva una unica alerta preventiva junto con la renovacion manual.
- Una licencia FULL activa ya no muestra un falso error cuando solo corresponde ofrecer renovacion.
- Cada render de `Mi Plan` reutiliza una unica resolucion remota de precios y mantiene el producto alineado con el checkout.
- La cache runtime de precios conserva cobertura valida ante respuestas parciales de Supabase.
- Versionado sincronizado entre app, documentacion e instaladores.

Desarrollado por Nexar Sistemas - 2026

---

## Estructura del Proyecto

```text
nexar-tienda/
|-- app.py                -> Logica principal y rutas Flask
|-- database.py           -> Motor SQLite y consultas SQL
|-- iniciar.py            -> Launcher desktop con ventana nativa
|-- VERSION               -> Version actual de release
|-- CHANGELOG.md          -> Historial detallado de cambios
|-- static/               -> CSS, JS e iconos
|-- templates/            -> Templates Jinja2
`-- build/                -> Specs, instalador y metadata de build
```

## Instalacion y Arranque

### Requisitos

- Python 3.11 o superior
- Dependencias: `flask`, `pywebview`, `openpyxl`, `reportlab`, `markdown`, `python-dotenv`
- Para desarrollo local y tests se usa `requirements.txt`, sin dependencias privadas.
- Para builds empaquetados se usa `requirements-build.txt`, que incluye `requirements.txt`
  y agrega `nexar_licencias` fijado a `v1.2.0` por Git SSH.

### Inicio rapido

```bash
python iniciar.py
```

El launcher busca un puerto libre e inicia la aplicacion en una ventana nativa
maximizada para uso diario.

### Instalacion Linux (.deb)

```bash
sudo apt install ./nexar-tienda_VERSION_amd64.deb
```

Si `apt` no puede leer el archivo desde `Descargas`, copiarlo antes a `/tmp`:

```bash
cp ~/Descargas/nexar-tienda_VERSION_amd64.deb /tmp/
chmod 0644 /tmp/nexar-tienda_VERSION_amd64.deb
sudo apt install /tmp/nexar-tienda_VERSION_amd64.deb
```

Si se uso `dpkg -i` y quedaron dependencias pendientes:

```bash
sudo apt --fix-broken install
```

Tambien se puede usar el helper del repo:

```bash
./install_deb.sh ./nexar-tienda_VERSION_amd64.deb
```

## Modulos Principales

### Punto de Venta

- Carrito persistente y multiples medios de pago
- Integracion con clientes y cuenta corriente
- Ticket de venta y soporte de venta fraccionada

### Inventario y Catalogo

- Stock con estados dinamicos y movimientos auditados
- Rubros y categorias alineados al negocio
- Unidades compatibles con tienda y almacen

### Caja, Reportes y Finanzas

- Caja diaria, gastos y reportes operativos
- Analisis y rentabilidad con datos historicos
- Exportaciones y herramientas de respaldo

### Clientes, Proveedores y Licencias

- Cuentas corrientes y compras
- Licenciamiento online con cache local
- Planes BASICA, PRO y FULL con modulos por tier

## Seguridad y Licenciamiento

- Acceso RBAC por roles
- Recuperacion de cuenta obligatoria para usuarios nuevos
- Activacion online mediante `nexar_licencias`
- `nexar-tienda` se conserva como `LICENSE_PRODUCT` compatible

### Ciclo de vida DEMO

Las instalaciones nuevas de Nexar Comercio reciben una DEMO de 14 dias. La app
persiste la fecha de inicio en `demo_install_date` y la fecha exclusiva de
vencimiento en `demo_expires_at`, por lo que reiniciar la aplicacion o completar
otra vez el onboarding no reinicia ni extiende el periodo.

Convencion de fechas: se usan fechas locales de calendario. El dia de activacion
cuenta como dia valido; una DEMO iniciada el `2026-01-01` queda activa hasta el
`2026-01-14` inclusive y vence al comenzar el `2026-01-15`. Los dias restantes
se muestran sin valores negativos.

Compatibilidad: las DEMO historicas conservan el periodo ya otorgado. Si una
instalacion existente tiene fechas validas o una duracion previa de 30 dias, la
migracion local respeta esos datos, completa solo campos faltantes de forma
deterministica y no reactiva DEMO vencidas.

### Proteccion anti-reinstalacion DEMO

Una DEMO nueva no se concede solo por estado local. Antes de activarla, la app
resuelve una identidad compuesta con `activation_id` estable, HWID del SDK
cuando existe, producto y senales legacy de la maquina. Supabase se consulta en
`solicitudes_demo` y una coincidencia fuerte del mismo producto bloquea otra
DEMO o recupera la DEMO vigente sin extender fechas.

El email se guarda como dato comercial y senal secundaria, pero no alcanza por
si solo para decidir que una DEMO fue usada. Los metadatos nuevos incluyen hashes
SHA-256 por producto para soportar deduplicacion remota sin exponer mas datos de
hardware que los ya existentes por compatibilidad legacy.

Estados principales:

- `eligible`: se puede registrar y activar una DEMO nueva.
- `active`: existe una DEMO vigente para este equipo; se recuperan sus fechas.
- `expired` / `already_used`: no se crea otra DEMO; quedan disponibles BASICA,
  PRO y FULL.
- `blocked`: un estado administrativo remoto prevalece.
- `offline_unverified` / `error`: no se concede una DEMO nueva hasta poder
  verificar; una DEMO local ya confirmada o una licencia paga valida no se
  bloquean.

Si una instalacion aparentemente nueva esta sin conexion, la pantalla inicial
permite reintentar, elegir un plan pago o salir, pero no activa permisos DEMO.
La proteccion no pretende resistir a un usuario con control total del equipo ni
reemplaza soporte administrativo para migraciones legitimas de equipo.

### Activacion inicial y compra directa

En una instalacion nueva, despues del registro inicial del administrador, la app
muestra `/activacion-inicial`. Desde ahi se puede elegir de forma independiente:
DEMO, BASICA, PRO o FULL. BASICA, PRO y FULL no dependen de haber iniciado una
DEMO ni de pasar por un plan intermedio.

La app separa estos estados:

1. Plan seleccionado: se guarda como intencion comercial local.
2. Pago iniciado: Nexar Comercio crea/abre checkout con Nexar Pagos y conserva
   `activation_id`, plan, producto, email y codigo de vendedor si existe.
3. Pago pendiente: la instalacion sigue sin permisos pagos hasta que Licencias
   confirme una licencia valida.
4. Licencia confirmada: la fuente oficial devuelve una licencia activa para el
   `activation_id` estable de la instalacion.
5. Plan activo: la app sincroniza con la capa central de licencias y solo ahi
   habilita modulos BASICA, PRO o FULL.

Elegir un plan, abrir Mercado Pago o declarar "Ya pague" no concede permisos.
El boton de verificacion vuelve a consultar la fuente oficial ya integrada. Si
el pago sigue pendiente, muestra un mensaje de espera y permite reintentar. Si
hay error de red o falta configuracion online, conserva el estado local y no
activa permisos. Si la licencia ya existe y es valida, guarda la licencia local,
marca la activacion inicial como completada y permite entrar a la aplicacion sin
reinstalar.

Dependencia externa: para activacion inmediata sin clave manual, Nexar Pagos,
Licencias o Admin deben emitir la licencia oficial vinculada al mismo
`activation_id`/HWID enviado en el checkout. Si esa licencia aun no esta
disponible, Nexar Comercio mantiene el pago como pendiente.

### Mi Plan

La seccion `/mi-plan` muestra una vista comercial del estado de licencia ya
resuelto por la capa central: plan efectivo, estado visible, fecha de
activacion, vencimiento cuando corresponde, dias restantes para DEMO/PRO/FULL,
limites del plan, modulos habilitados, email asociado y codigo de vendedor solo
si fue informado.

Las acciones se calculan fuera del template con helpers existentes de planes,
permisos, precios y checkout:

- DEMO activa o vencida: permite adquirir BASICA, PRO o FULL; no ofrece otra
  DEMO.
- BASICA activa: indica que no vence, no muestra renovacion y permite upgrades
  validos.
- PRO activa: muestra vencimiento, renovacion y upgrade a FULL.
- FULL activa: muestra vencimiento y renovacion; no muestra upgrades.
- Licencia suspendida, bloqueada, revocada o anulada: no se presenta como plan
  activo y conserva acciones seguras de revalidacion/activacion ya soportadas.

El boton "Ya pague" aparece solo cuando hay una revalidacion admitida o un
checkout pendiente. La pantalla no expone HWID, hashes ni detalles internos del
SDK.

### Licencia BASICA permanente

La licencia BASICA es de pago unico y permanente. Una BASICA valida no tiene
vencimiento temporal, no calcula dias restantes, no muestra cuenta regresiva y
no solicita renovacion. Si existen datos legacy con `license_expires_at`,
`expires_at` o campos equivalentes, la app los conserva como metadatos
historicos y no los usa para vencer el plan BASICA.

La permanencia aplica solo a licencias validas. Estados administrativos
explicitos como `revocada`, `suspendida`, `bloqueada` o `anulada` siguen
bloqueando el acceso aunque el plan original sea BASICA.

### Licencias vencidas y reactivacion

La app resuelve un unico estado efectivo antes de habilitar modulos o rutas. La
precedencia es:

1. Estados administrativos explicitos como revocada, suspendida, bloqueada,
   anulada o aliases equivalentes.
2. Vencimiento por fecha para DEMO, PRO y FULL.
3. Licencia activa valida.

Una fecha futura no reactiva una licencia administrativamente bloqueada. Una
licencia PRO o FULL vencida conserva su plan comercial historico, pero su plan
efectivo pasa a `SIN_PLAN` y no concede permisos PRO, FULL ni BASICA. Al renovar
o reactivar desde la fuente valida, basta con refrescar o sincronizar la
licencia desde `Mi plan` para recuperar permisos, sin reinstalar ni tocar datos
locales manualmente.

Comportamiento por plan vencido:

- DEMO vencida: no se reinicia ni se extiende automaticamente, no otorga
  permisos pagos y solo permite acceder a `Mi plan`, `Licencia`, validacion de
  estado, compra/solicitud de plan y salida de la app.
- PRO vencida: mantiene PRO como referencia historica, bloquea funciones PRO y
  muestra renovacion para recuperar el plan.
- FULL vencida: mantiene FULL como referencia historica, bloquea funciones FULL
  y muestra renovacion para recuperar funciones avanzadas.
- BASICA valida: sigue siendo permanente; las fechas legacy son metadatos y no
  la vencen. Si BASICA esta revocada, suspendida, bloqueada o anulada, queda
  bloqueada.

Con una licencia vencida se bloquean operaciones de negocio que crean o
modifican datos: ventas, compras, stock, productos, clientes, proveedores, caja
y acciones administrativas de negocio. El acceso queda limitado a recuperar o
renovar la licencia, consultar el estado del plan y salir correctamente.

Consulta, exportacion y backup: este PR no habilita un modo completo de solo
lectura, exportacion ni backup para licencias vencidas. Las rutas actuales
mezclan pantallas de consulta con acciones de escritura, por lo que habilitarlas
parcialmente podria permitir uso normal de la app o introducir regresiones. La
decision segura para este alcance es bloqueo minimo consistente y recuperacion
comercial.

### Flujo manual de solicitudes de licencia

La pantalla de licencia permite que el cliente envie una solicitud con nombre,
email, WhatsApp opcional e ID del equipo. Esa solicitud queda pendiente en
Supabase y el desarrollador la aprueba o rechaza manualmente desde
`nexar-admin`. Al aprobar, se genera una licencia real en la tabla `licencias`
y el cliente recibe la clave para pegarla en Nexar Comercio.

Tabla necesaria en Supabase:

```sql
create table if not exists public.solicitudes_licencia (
  id bigint generated by default as identity primary key,
  producto text not null,
  activation_id text not null,
  nombre text not null,
  email text not null,
  whatsapp text,
  plan text not null default 'BASICA',
  estado text not null default 'pendiente'
    check (estado in ('pendiente', 'aprobada', 'rechazada')),
  license_key text,
  admin_note text,
  machine_details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

alter table public.solicitudes_licencia enable row level security;

create policy "clientes_insertan_solicitudes_licencia"
on public.solicitudes_licencia
for insert
to anon
with check (
  estado = 'pendiente'
  and license_key is null
  and admin_note is null
);
```

La policy anterior es solo para `insert`. No agregar policies de `select`,
`update` ni `delete` para `anon`.

Para probar localmente, usar `.env.example` como referencia. La configuracion
recomendada para validacion de licencias y solicitudes usa las variables
centralizadas del SDK `nexar_licencias`:

- `NEXAR_LICENSES_VALIDATION_URL`
- `NEXAR_LICENSES_SUPABASE_KEY`
- `NEXAR_LICENSES_TIMEOUT`
- `NEXAR_LICENSES_CONNECT_TIMEOUT`
- `NEXAR_LICENSES_READ_TIMEOUT`
- `NEXAR_LICENSES_MAX_RETRIES`
- `NEXAR_LICENSES_RETRY_BACKOFF`
- `NEXAR_LICENSES_RETRY_STATUS_CODES`
- `NEXAR_LICENSES_CACHE_FILE`
- `NEXAR_LICENSES_CACHE_DIR`
- `NEXAR_LICENSES_CACHE_TTL`
- `NEXAR_LICENSES_OFFLINE_FALLBACK`

Por compatibilidad, las instalaciones existentes pueden seguir usando
`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_KEY`, `NEXAR_CACHE_FILE` y
`NEXAR_CACHE_DAYS`. La service role key debe quedar solo en `nexar-admin`,
nunca dentro del instalador de Nexar Comercio.

### Solicitudes de soporte desde la app

La pantalla de Ayuda incluye un formulario de soporte que envia nombre, email,
WhatsApp opcional, motivo, mensaje y datos tecnicos basicos de la instalacion.

Tabla necesaria:

```sql
create table if not exists public.solicitudes_soporte (
  id bigint generated by default as identity primary key,
  producto text not null,
  app_version text,
  negocio text,
  nombre text not null,
  email text not null,
  whatsapp text,
  motivo text not null default 'consulta'
    check (motivo in ('consulta', 'error', 'licencia', 'actualizacion', 'respaldo', 'otro')),
  mensaje text not null,
  plan text,
  user_name text,
  estado text not null default 'pendiente'
    check (estado in ('pendiente', 'en_revision', 'resuelta', 'descartada')),
  admin_note text,
  technical_details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

alter table public.solicitudes_soporte enable row level security;

create policy "clientes_insertan_solicitudes_soporte"
on public.solicitudes_soporte
for insert
to anon
with check (
  estado = 'pendiente'
  and admin_note is null
);
```

## Builds e Instaladores

Los instaladores se generan con GitHub Actions, PyInstaller e Inno Setup.
Los iconos se toman desde `static/icons/` conservando los nombres existentes,
por lo que la actualizacion visual no rompe rutas internas ni accesos directos.

Puntos de empaque verificados:

- Windows PyInstaller usa `static/icons/nexar_tienda.ico`
- Inno Setup usa `SetupIconFile=..\\static\\icons\\nexar_tienda.ico`
- Linux `.desktop` usa `Icon=nexar_tienda`
- El builder `.deb` copia `static/icons/nexar_tienda.PNG` a `usr/share/pixmaps/nexar_tienda.png`

Secrets y variables esperados en CI:

- `PUBLIC_KEY`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `NEXAR_LICENCIAS_DEPLOY_KEY`: clave privada de una Deploy Key de solo lectura
  configurada en `rolojnb/nexar_licencias`, usada para instalar el SDK privado
  desde `requirements-build.txt`

No se debe incluir `SUPABASE_SERVICE_ROLE_KEY` en instaladores, specs ni binarios
de cliente.

## Soporte y Contacto

- WhatsApp: +54 9 264 585-8874
- Email: nexarsistemas@outlook.com.ar

Nexar Sistemas - Soluciones de Software de Alta Calidad.
