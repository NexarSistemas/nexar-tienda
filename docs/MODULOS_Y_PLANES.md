# Módulos y planes

Nexar Tienda usa módulos para habilitar u ocultar funciones según el plan activo. La capa vive en `licensing/` y se usa tanto en templates como en rutas reales.

## Arquitectura de Licencias (Integración Modular)

El sistema de licencias tiene dos modos:

### DEV mode (`NEXAR_LICENSE_MODE=dev`)
Leer módulos desde variables de entorno. Ideal para desarrollo local.
- `NEXAR_PLAN`: Plan a probar (DEMO, BASICA, MENSUAL_FULL)
- `NEXAR_MODULES`: Módulos adicionales separados por coma

### PROD mode (`NEXAR_LICENSE_MODE=prod`)
Leer módulos con esta prioridad:
1. **SDK nexar_licencias**: Si devuelve módulos explícitamente
2. **Base de datos (SQLite)**: Campo `license_tier` en tabla `config`, mapeado a módulos via tabla `license_module_map`
3. **Fallback**: Variables de entorno (NEXAR_PLAN, NEXAR_MODULES)

## Tiers de Licencia

Nexar Tienda soporta los siguientes tiers (con soporte para aliases):

| Tier Canónico | Aliases | Módulos |
|---|---|---|
| `DEMO` | - | `core` |
| `BASICA` | `BASIC`, `BASICO`, `TDA_BASICA` | `core`, `clientes`, `proveedores`, `pos`, `stock`, `caja`, `gastos` |
| `PRO` | `PRO` | `core`, `clientes`, `proveedores`, `pos`, `stock`, `caja`, `gastos`, `compras`, `historial`, `reportes`, `export`, `multiusuario` |
| `MENSUAL_FULL` | `FULL`, `MENSUAL`, `TDA_PRO` | `core`, `clientes`, `proveedores`, `pos`, `stock`, `caja`, `gastos`, `compras`, `historial`, `reportes`, `export`, `temporadas`, `ia`, `multinegocio`, `multiusuario` |

**Notas:**
- La base de datos almacena el tier en `config.license_tier`
- La tabla `license_module_map` mapea tiers a sets de módulos en JSON
- Todos los tiers incluyen el módulo `core` como mínimo
- Los aliases se normalizan automáticamente (ej: PRO → MENSUAL_FULL)

## Ejemplo de .env

### Modo DEV (Desarrollo Local)

Usar plan BASICA:

```env
NEXAR_LICENSE_MODE=dev
NEXAR_PLAN=BASICA
```

Combinar BASICA con módulos extra:

```env
NEXAR_LICENSE_MODE=dev
NEXAR_PLAN=BASICA
NEXAR_MODULES=reportes,export
```

Plan DEMO (solo core):

```env
NEXAR_LICENSE_MODE=dev
NEXAR_PLAN=DEMO
```

Plan FULL (todos los módulos):

```env
NEXAR_LICENSE_MODE=dev
NEXAR_PLAN=MENSUAL_FULL
```

### Modo PROD (Producción)

Leer tier desde BD (sincronizado desde Supabase/SDK):

```env
NEXAR_LICENSE_MODE=prod
```

En este modo:
1. La app busca el tier en `config.license_tier` (BD SQLite local)
2. Mapea el tier a módulos usando `license_module_map`
3. Si SDK está disponible, lo intenta primero
4. Fallback a env vars si todo falla

## Cómo Funciona el Sistema

### 1. Lectura de Módulos Activos

El flujo en `licensing/permisos.py`:

```
if DEV mode:
    └─ Usar NEXAR_PLAN + NEXAR_MODULES desde .env
else (PROD mode):
    ├─ Intentar SDK nexar_licencias
    ├─ Si falla, leer license_tier desde DB (config table)
    ├─ Mapear tier a módulos usando license_module_map
    └─ Si todo falla, fallback a env vars
```

### 2. Normalización de Tiers

Los tiers se normalizan automáticamente:

- `BASIC` → `BASICA`
- `BASICO` → `BASICA`
- `TDA_BASICA` → `BASICA`
- `FULL` → `MENSUAL_FULL`
- `PRO` → `MENSUAL_FULL`
- `MENSUAL` → `MENSUAL_FULL`
- `TDA_PRO` → `MENSUAL_FULL`

### 3. Mapeo Tier → Módulos

La tabla `license_module_map` almacena el mapeo:

```sql
CREATE TABLE license_module_map (
    id INTEGER PRIMARY KEY,
    license_tier TEXT UNIQUE,          -- DEMO, BASICA, MENSUAL_FULL
    modules TEXT,                      -- JSON: ["core", "clientes", ...]
    created_at TEXT,
    updated_at TEXT
);
```

Ejemplo de registros:

```sql
INSERT INTO license_module_map (license_tier, modules) VALUES
    ('DEMO', '["core"]'),
    ('BASICA', '["core", "clientes", "proveedores", "pos", "stock", "caja", "gastos"]'),
    ('PRO', '["core", "clientes", "proveedores", "pos", "stock", "caja", "gastos", "compras", "historial", "reportes", "export", "multiusuario"]'),
    ('MENSUAL_FULL', '["core", "clientes", "proveedores", "pos", "stock", "caja", "gastos", "compras", "historial", "reportes", "export", "temporadas", "ia", "multinegocio", "multiusuario"]');
```

### 4. Funciones Disponibles

En `licensing/permisos.py`:

```python
# Obtener todos los módulos activos (retorna set)
get_modulos_activos() -> set[str]

# Verificar si un módulo está activo (retorna bool)
modulo_activo("reportes") -> True|False

# Bloquear acceso a ruta si módulo no está activo (abort 403)
require_modulo("reportes")
```

En `database.py`:

```python
# Obtener tier actual desde DB
get_license_tier_from_db() -> str  # ej: "BASICA"

# Obtener módulos para un tier específico
get_modulos_from_tier(tier: str) -> set[str]
```

## Qué es un módulo

Un módulo es una clave simple que representa una funcionalidad del sistema. Ejemplos: `reportes`, `export`, `temporadas`.

Si un módulo no está activo:
- el menú puede ocultar esa opción con `modulo_activo("modulo")`;
- la ruta puede bloquear el acceso directo con `require_modulo("modulo")`;
- el usuario recibe una pantalla `403`.

## Módulos actuales

- `core`: funciones básicas (inventario, ventas, caja).
- `clientes`: gestión de clientes y cuentas corrientes.
- `reportes`: reportes, estadísticas y análisis de rentabilidad.
- `export`: exportación de catálogo (Excel, CSV).
- `temporadas`: gestión de temporadas y productos destacados.
- `ia`: análisis predictivo y recomendaciones.
- `multinegocio`: soporte para múltiples negocios/sucursales (reservado).
- `multiusuario`: gestión avanzada de roles y permisos de usuarios.

## Cómo probar permisos

### Test Local (DEV Mode)

1. Configurar para DEMO (sin clientes ni reportes):

```env
NEXAR_LICENSE_MODE=dev
NEXAR_PLAN=DEMO
```

2. Reiniciar la app.
3. Intentar acceder a rutas protegidas - deben mostrar `403`:

- `/clientes`
- `/reportes`
- `/estadisticas`
- `/temporadas`
- `/analisis`
- `/usuarios`
- `/productos/exportar/excel`

4. Cambiar a BASICA:

```env
NEXAR_PLAN=BASICA
```

5. Reiniciar - ahora `/clientes` debe funcionar pero `/reportes` bloqueada.

6. Ver el estado visual:

- Entrar a `/mi-plan`
- Verificar módulos habilitados y bloqueados
- Revisar que el menú oculte opciones

### Test en Base de Datos

1. Inicializar BD:

```python
from database import init_db, get_config, q
init_db()

# Ver tier actual
config = get_config()
print(config.get('license_tier'))  # Debería ser DEMO

# Cambiar a BASICA
q("UPDATE config SET valor='BASICA' WHERE clave='license_tier'", commit=True)

# Verificar
from licensing.permisos import get_modulos_activos
print(get_modulos_activos())  # {core, clientes}
```

2. Ejecutar tests:

```bash
python tests/test_license_tiers.py
```

## Compatibilidad Hacia Atrás

La integración modular **no rompe** compatibilidad existente:

- ✅ Campo `license_tier` en `config` se mantiene
- ✅ Campos `license_type`, `license_plan`, `license_support`, `license_updates` existentes se mantienen
- ✅ `TIER_LIMITS` en `database.py` se mantiene para controlar cantidad de registros
- ✅ Función `normalize_license_plan()` maneja alias históricos
- ✅ Tablas de productos, ventas, stock, clientes NO cambian
- ✅ `require_modulo()` y `modulo_activo()` siguen funcionando igual

## Notas Técnicas

### Integración con Supabase/SDK

El plan futuro:

1. SDK `nexar_licencias` valida licencia contra Supabase
2. Retorna `modules` activos explícitamente
3. `licensing/permisos.py` intenta SDK primero en modo PROD
4. Si SDK no está disponible, fallback a lectura local desde DB

### Tabla license_module_map

Se inicializa automáticamente en `init_db()` con los mapeos por defecto.
Para agregar tiers nuevos o cambiar mapeos:

```python
from database import q
import json

q(
    "INSERT OR REPLACE INTO license_module_map (license_tier, modules) VALUES (?,?)",
    ("CUSTOM_TIER", json.dumps(["core", "clientes", "reportes"])),
    commit=True
)
```

### Logging

Para debug, habilitar logs en DEBUG:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

El sistema loga el origen de módulos: `env`, `sdk`, `db`, o `fallback`.

## Cómo agregar un módulo nuevo

1. Agregar la clave del módulo en `licensing/planes.py`, dentro del plan que corresponda.
2. En templates, ocultar enlaces con:

```jinja2
{% if modulo_activo("nuevo_modulo") %}
...
{% endif %}
```

3. En rutas protegidas, agregar al inicio de la vista:

```python
require_modulo("nuevo_modulo")
```

4. Probar con:

```env
NEXAR_MODULES=nuevo_modulo
```

No hace falta cambiar base de datos para agregar un módulo.
