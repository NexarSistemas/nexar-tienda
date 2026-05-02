# Módulos y planes

Nexar Tienda usa módulos para habilitar u ocultar funciones según el plan activo. La capa vive en `licensing/` y se usa tanto en templates como en rutas reales.

## Qué es un módulo

Un módulo es una clave simple que representa una funcionalidad del sistema. Ejemplos: `reportes`, `export`, `temporadas`.

Si un módulo no está activo:
- el menú puede ocultar esa opción con `modulo_activo("modulo")`;
- la ruta puede bloquear el acceso directo con `require_modulo("modulo")`;
- el usuario recibe una pantalla `403`.

## Módulos actuales

- `core`: funciones básicas.
- `clientes`: cuentas corrientes/clientes.
- `reportes`: reportes, estadísticas y rentabilidad detallada.
- `export`: exportación de catálogo.
- `temporadas`: gestión de temporadas.
- `ia`: análisis de productos.
- `multinegocio`: reservado para multi negocio/sucursales.
- `multiusuario`: gestión avanzada de usuarios.

## Planes disponibles

Los planes están definidos en `licensing/planes.py`.

- `DEMO`: `core`
- `BASICA`: `core`, `clientes`
- `PRO`: `core`, `clientes`, `reportes`, `export`, `temporadas`
- `FULL`: `core`, `clientes`, `reportes`, `export`, `temporadas`, `ia`, `multinegocio`, `multiusuario`

## Ejemplo de .env

Modo local de desarrollo:

```env
NEXAR_LICENSE_MODE=dev
NEXAR_PLAN=PRO
```

Para sumar módulos manuales durante desarrollo:

```env
NEXAR_LICENSE_MODE=dev
NEXAR_PLAN=BASICA
NEXAR_MODULES=reportes,export
```

En producción futura:

```env
NEXAR_LICENSE_MODE=prod
NEXAR_PLAN=PRO
```

En `prod`, la app intenta leer módulos desde el SDK `nexar_licencias` si está disponible. Si no existe, usa `NEXAR_PLAN` y `NEXAR_MODULES` como fallback.

## Cómo probar permisos

1. Configurar:

```env
NEXAR_LICENSE_MODE=dev
NEXAR_PLAN=DEMO
```

2. Reiniciar la app.
3. Entrar manualmente a rutas protegidas:

- `/reportes`
- `/estadisticas`
- `/temporadas`
- `/analisis`
- `/usuarios`
- `/productos/exportar/excel`

Las rutas no incluidas en el plan deben mostrar `403`.

Para revisar el estado visual:

- entrar a `/mi-plan`;
- verificar módulos habilitados y bloqueados;
- revisar que el menú oculte opciones no incluidas.

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
