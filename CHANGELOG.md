# Changelog - Nexar Tienda

Todos los cambios importantes de este proyecto se documentan en este archivo.

---

## [0.5.0] - 29 Marzo 2026 - Módulo de Stock

### ✨ Características Nuevas
- **Gestión completa de inventario** con estados dinámicos (SIN STOCK, CRÍTICO, BAJO, NORMAL, EXCESO)
- **Historial de movimientos**: tabla `stock_movimientos` para auditoría de ajustes
- **Búsqueda y filtrado de productos** por estado de stock
- **Alertas de stock** en tiempo real con endpoint `/api/alertas`
- **Formulario inteligente de ajuste** con cálculo automat de diferencia
- **Panel de rangos recomendados** en formulario de ajuste
- **Historial de movimientos integrado** en formulario

### 🛠️ Cambios Técnicos
- **database.py**: 
  - Nueva tabla `stock_movimientos` con FK a `productos`
  - Funciones: `get_stock_movimientos()`, `get_stock_movimientos_all()`
  - Actualización de `get_alertas_count()` con cálculo de estados

- **app.py**:
  - Nueva ruta `GET /stock` - listado de inventario
  - Nueva ruta `GET/POST /stock/<pid>/ajustar` - formulario de ajuste
  - Nueva ruta `GET /api/alertas` - API endpoints
  - Validación server-side completa

- **templates/stock.html** (280 líneas)
  - Tabla responsive de inventario
  - Filtros de búsqueda y estado
  - Tarjetas de estadísticas
  - Alertas destacadas con conteos

- **templates/stock_ajustar.html** (320 líneas)
  - Formulario con validación JavaScript
  - Cálculo automático de diferencia
  - Historial de movimientos
  - Panel de rangos de alerta

- **templates/base.html**:
  - Link funcional a `/stock` en sidebar
  - Estados activos para rutas stock/stock_ajustar

### 🧪 Tests
- ✅ `test_paso5.py`: 23 tests completamente pasando
  - TestStockFunctions (5 tests)
  - TestStockRoutes (10 tests)
  - TestStockAlerts (3 tests)
  - TestStockStates (1 test)
  - TestStockIntegration (2 tests)
  - Database structure (2 tests)

### 🔐 Seguridad
- @login_required en todas las rutas
- @admin_required en POST /stock/<pid>/ajustar
- Validaciones server-side y client-side
- SQL injection prevention con placeholders

### 📊 Métricas
- 23 tests (100% pasando)
- 3 nuevos endpoints
- 1 nueva tabla en BD
- 2 nuevos templates
- ~200 líneas de código backend
- ~600 líneas de código frontend

---

## [0.4.0] - 25 Marzo 2026 - CRUD de Productos + Sistema TIER

### ✨ Características Nuevas
- **Productos CRUD completo**: crear, editar, listar, borrar (soft delete)
- **Gestión de categorías**: creación dinámica e integración en productos
- **Sistema TIER de licenciamiento**: DEMO, BÁSICA, PRO con límites de productos
- **Validación de límites TIER** antes de crear nuevos productos
- **Dashboard de licencia**: muestra estado TIER con barra de progreso

### 🛠️ Cambios Técnicos
- **database.py**:
  - Nuevas tablas: `categorias`, `productos`, `licencia`
  - Funciones TIER: `get_license_info()`, `check_license_limits()`, `activate_license()`
  - Límites TIER integrados: DEMO (5), BÁSICA (50), PRO (1000)

- **app.py**:
  - Rutas de productos: GET/POST `/productos`, `/productos/nuevo`, `/productos/<id>/editar`, `/productos/<id>/eliminar`
  - Ruta de licencia: GET/POST `/licencia`
  - Validación de límites antes de CREATE

- **templates/productos.html**: listado con búsqueda y soft delete
- **templates/producto_form.html**: formulario de creación/edición
- **templates/licencia.html**: panel de estado TIER

### 🧪 Tests
- ✅ `test_paso4.py`: 12 tests completamente pasando

### 🔐 Seguridad
- @login_required en todas las rutas
- @admin_required en operaciones de crear/editar/borrar
- Validación de TIER limits

---

## [0.3.0] - 20 Marzo 2026 - Autenticación + Dashboard + Backups

### ✨ Características Nuevas
- **Sistema de autenticación** con login/logout
- **Dashboard administrativo** con estadísticas
- **Sistema de backups** automáticos y manuales
- **Gestión de usuarios** (admin y vendedor)
- **Sesiones seguras** con tokens de sesión

### 🛠️ Cambios Técnicos
- **database.py**:
  - Tabla `usuarios` con hash SHA256
  - Tabla `backups` con historial
  - Funciones de autenticación y backups

- **app.py**:
  - Rutas: GET/POST `/login`, `/logout`, GET `/dashboard`, GET/POST `/backup`
  - Decoradores: @login_required, @admin_required
  - Manejo de sesiones Flask

- **templates/base.html**: layout principal con sidebar
- **templates/login.html**: formulario de autenticación
- **templates/dashboard.html**: panel administrativo

### 🧪 Tests
- ✅ `test_paso3.py`: 6 tests completamente pasando

---

## [0.1.0-0.2.0] - Inicialización

### ✨ Características Iniciales
- Estructura base de proyecto Flask
- Database inicial con tablas básicas
- Configuración de entorno

---

## 📋 Tabla de Versiones

| Versión | Paso | Fecha | Features | Tests | Status |
|---------|------|-------|----------|-------|--------|
| 0.5.0 | 5 | 29/03/2026 | Stock Management | 23/23 ✅ | Completo |
| 0.4.0 | 4 | 25/03/2026 | CRUD + TIER | 12/12 ✅ | Completo |
| 0.3.0 | 3 | 20/03/2026 | Auth + Dashboard | 6/6 ✅ | Completo |
| 0.2.0-0.1.0 | Init | 15/03/2026 | Base | - | Desarrollo |

---

## 🎯 Próximos Pasos (Versiones Planeadas)

- **[0.6.0]** - Módulo POS (Punto de Venta)
  - Sistema de ventas con carrito
  - Generación de boletas
  - Decremento automático de stock

- **[0.7.0]** - Gestión de Clientes
  - CRUD de clientes
  - Historial de compras
  - Cuenta corriente

- **[0.8.0]** - Gestión de Proveedores
  - CRUD de proveedores
  - Historial de compras
  - Contacto

- **[0.9.0]** - Módulo de Compras
  - Órdenes de compra
  - Incremento de stock
  - Recepción de mercadería

- **[1.0.0]** - Release Oficial
  - Caja y liquidación
  - Estadísticas completas
  - POS con multi-usuario

---

## 🏗️ Convenciones de Versionado

Usamos **Semantic Versioning** (MAJOR.MINOR.PATCH):

- **MAJOR** (0.X.0): Cambios grandes de funcionalidad (nuevos módulos)
- **MINOR** (X.5.0): Mejoras y nuevas características menores
- **PATCH** (X.X.Z): Bugfixes y ajustes menores

Cada paso completado = nueva versión MINOR con git tag.

---

**Última actualización:** 29 de marzo de 2026
