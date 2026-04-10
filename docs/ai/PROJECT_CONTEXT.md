# Contexto del proyecto para asistentes IA

## Proyecto: Nexar Tienda

### Descripción
Sistema de gestión completo para tienda física de regalos, marroquinería,
bijouterie, mates y termos, adornos y productos de temporada (Navidad, Día de
la Madre, Día del Padre, etc.). Funciona de forma local (offline) en una sola PC.

### Tecnologías
- Python 3.11 + Flask 3.0
- SQLite (archivo `tienda.db`)
- Bootstrap 5.3 + Font Awesome 6.4
- JavaScript vanilla (sin frameworks)

### Arquitectura
```
app.py          → todas las rutas Flask
database.py     → todas las consultas SQL
templates/      → HTML con Jinja2
static/css/     → main.css (paleta azul marino + plateado)
static/js/      → pos.js (punto de venta), utils.js (helpers)
```

### Módulos principales (MVP)
1. Login / Autenticación (admin y usuario)
2. Dashboard con KPIs y alertas de temporada
3. Productos (ABM + categorías de tienda)
4. Stock (control de inventario)
5. Punto de Venta (POS con búsqueda por nombre)
6. Historial de ventas y tickets
7. Clientes y cuenta corriente
8. Proveedores y compras
9. Caja y gastos
10. Temporadas (módulo único de esta tienda)
11. Estadísticas y análisis
12. Configuración y usuarios

### Paleta de colores CSS
```css
--sidebar-bg: #1e3a5f;       /* azul marino oscuro */
--sidebar-hover: #2d5282;    /* azul marino medio */
--sidebar-active: #3b82f6;   /* azul brillante (activo) */
--accent: #3b82f6;           /* azul acento */
--accent-light: #eff6ff;     /* azul muy claro */
--silver: #94a3b8;           /* plateado */
--silver-light: #f1f5f9;     /* plateado muy claro */
```

### Convenciones importantes
- `q(sql, params=(), fetchone=False, fetchall=True, commit=False)` → función única de DB
- Todos los precios en float, formato ARS con `fmt_ars()`
- Flash messages siempre con emoji: ✅ éxito, ❌ error, ⚠️ advertencia
- Rutas protegidas con `@login_required` o `@admin_required`
- Formularios HTML → POST → redirect (patrón PRG)

### Diferencias clave con Nexar Almacén (el proyecto original)
| Nexar Almacén | Nexar Tienda |
|---|---|
| Verde oscuro (#1a2e1a) | Azul marino (#1e3a5f) |
| Categorías de supermercado | Categorías de tienda de regalos |
| Código de barras obligatorio | Búsqueda por nombre/categoría |
| Sin módulo de temporadas | Módulo de temporadas central |
| IVA simple | IVA incluido o discriminado |
| Sin licencias | Sin licencias (uso propio) |

### Estado actual del proyecto
- v1.15.3: Corrección de flujo de apagado desde login ✅
- Próximo paso: database.py con tablas adaptadas para tienda
