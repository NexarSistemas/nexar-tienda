# Nexar Tienda 🛍️

Sistema integral de gestión para tiendas de regalos, marroquinería, bijouterie y comercios de temporada.

**Versión actual:** `v1.19.0` - Refinamiento UX y Unificación de Topbar
**Última actualización:** 25 de abril de 2026 - v1.19.0
Desarrollado con **Python + Flask + SQLite**.

---

## 🚀 Características Implementadas

### ✅ PASO 29: Refinamiento UX y Unificación de Topbar (v1.19.0)
- **🎨 Consistencia de Interfaz**: Implementación de Topbar unificado en todos los módulos, eliminando títulos redundantes.
- **🚩 Licenciamiento Visible**: Integración del estado de la licencia (Demo/Plan) directamente en el Topbar principal.
- **❌ Banners Descartables**: Opción para cerrar banners de bienvenida y notificaciones flash manualmente.
- **🖥️ Ventana Optimizada**: La aplicación nativa ahora se inicia maximizada con confirmación de cierre en español.

---

### ✅ PASO 28: Unificación Estética (v1.18.0)
- **🎨 Rediseño Visual**: Paridad total con la estética "fina" de Nexar Almacén.
- **📂 Sidebar Refinado**: Estructura de navegación plana de 230px para mayor agilidad.
- **🔒 Login Suite**: Nueva interfaz de acceso unificada y profesional.
- **🖋️ Tipografía Inter**: Implementación del stack de fuentes premium.

### ✅ PASO 27: Infraestructura de Build (v1.17.0)
- **📦 Empaquetado Windows**: Configuración de `PyInstaller` (.spec) para generar un único ejecutable.
- **🛠️ Instalador Windows**: Script de `Inno Setup` (.iss) para crear el asistente de instalación.
- **🐧 Paquete Linux**: Script `build_deb.sh` para generar instaladores Debian/Ubuntu.

### ✅ PASO 26: Banner de Licencia y Mejoras de Usabilidad (v1.16.0)
- **🚩 Indicador de Estado**: Banner dinámico para licencias DEMO con cuenta regresiva de días.
- **🏢 Identidad Dinámica**: Visualización del nombre del negocio en el topbar desde la configuración.
- **⚡ Auto-Dismiss**: Las notificaciones flash desaparecen automáticamente tras 4 segundos.

### ✅ PASO 25: UX de Apagado con SweetAlert2 (v1.15.0)
- **🔔 Notificaciones Elegantes**: Reemplazo de diálogos nativos `confirm()` por modales estéticos de SweetAlert2.
- **🛑 Apagado desde Login**: Implementación de botón de apagado rápido en la pantalla de acceso.
- **🎨 Consistencia Visual**: Adaptación de la paleta de colores institucional a los diálogos de confirmación.

### ✅ PASO 24: Launcher Universal e Interfaz Nativa (v1.14.0)
- **🖥️ Ventana Nativa**: Integración con `pywebview` para ejecutar la app como una aplicación de escritorio independiente.
- **🔌 Gestión de Puertos**: Selección dinámica de puertos libres para evitar colisiones.
- **🚀 Autocargador**: Script `iniciar.py` que centraliza la lógica de inicio y preparación del entorno.

### ✅ PASO 23: Refactorización de Sidebar (v1.13.0)
- **🎨 Rediseño Visual**: Adopción de la estructura de Nexar Almacén para mayor usabilidad.
- **📂 Organización Plana**: Navegación por grupos temáticos con acceso directo.
- **📊 Inteligencia de Negocio**: Acceso unificado a Resumen Mensual, Estadísticas y Análisis.
- **👤 Perfil de Usuario**: Pie de página mejorado con información de sesión y controles de salida.

### ✅ PASO 22: Apagado Controlado (v1.12.0)
- **🛑 Cierre Seguro**: Botón para detener el proceso del servidor.
- **🔒 Sesiones**: Limpieza automática de la sesión al cerrar.

### ✅ PASO 21: Páginas Informativas (v1.11.0)
- **ℹ️ Ayuda y Soporte**: Guía de usuario integrada.
- **📜 Changelog Dinámico**: Visualización de novedades desde la interfaz.
- **🛠️ Acerca de**: Información del sistema y tecnologías.

### ✅ PASO 20: Exportación de catálogo (v1.10.0)
- **📤 Excel (.xlsx)**: Generación de planilla completa de inventario con stock y precios.
- **📄 PDF**: Lista de precios profesional con encabezado del negocio.

### ✅ PASO 15: Financiación y Cobranzas (v1.5.0)
- **💳 Intereses en Cuotas**: Aplicación de recargos financieros en ventas a crédito.
- **🔗 Trazabilidad de Deuda**: Vinculación de movimientos de CC con tickets de venta.
- **📅 Planes de Pago**: Generación de cuotas automáticas con vencimientos mensuales.

### ✅ PASO 19: Estadísticas Avanzadas y Análisis (v1.9.0)
- **📊 Dashboard Anual**: Visualización de la evolución de ventas y tickets a lo largo del año.
- **📈 Análisis de Rentabilidad**: Reporte detallado de utilidad bruta por producto y tendencia histórica mensual.
- **🏷️ Métricas por Categoría y Temporada**: Gráficos de distribución de ingresos para identificar los sectores más rentables.
- **📉 Análisis de Movimiento**: Identificación automática de productos "Bottom" (menos vendidos) para gestión de inventario.
- **🎨 Gráficos Interactivos**: Implementación con Chart.js para una visualización clara de los datos.

### ✅ PASO 12: Estadísticas Avanzadas (v1.2.0)
- **📊 Dashboard Gráfico**: Visualización de ventas de los últimos 7 días con Chart.js.
- **💰 Análisis de Rentabilidad**: Cálculo de utilidad neta (Ventas - Costos - Gastos).
- **🔝 Top Productos**: Ranking de los 5 productos más vendidos.

### ✅ PASO 11: Módulo de Gastos (v1.1.0)
- **💸 Registro de gastos operativos** (alquiler, servicios, sueldos, etc.).
- **🏷️ Categorización de egresos** para análisis financiero.
- **🏦 Integración con Caja Diaria**: Los gastos en efectivo restan automáticamente del saldo de caja.
- **📅 Filtros avanzados** por fecha y descripción.

### ✅ PASO 10: Caja y Liquidación Diaria (v1.0.0)
- **💰 Control de apertura y cierre** con saldo inicial y arqueo de caja.
- **📊 Integración automática con POS** para ventas en efectivo.
- **💸 Gestión de movimientos manuales** (ingresos y egresos).
- **📝 Historial de liquidaciones** para auditoría y control de faltantes.
- **🔄 Cálculo de saldo esperado** vs saldo real automático.

### ✅ PASO 9: Módulo de Compras (v0.9.0)
- **🛒 Registro de compras** (fecha, proveedor, producto, cantidad, costo, remito)
- **📈 Incremento automático de stock** y auditoría en `stock_movimientos`
- **🗂️ Listado, detalle y eliminación** de compras
- **🔍 Filtros por proveedor, producto y rango de fechas**
- **✅ Integración con proveedores y productos existentes**

### ✅ PASO 8: Gestión de Proveedores (v0.8.0)
- **🚚 CRUD de proveedores completo** (crear, editar, listar, desactivar)
- **💼 Gestión de cuentas corrientes** (debe/haber, saldo, movimientos)
- **📊 Historial de compras por proveedor** con estadísticas y última compra
- **🧾 Soporte de pagos y verificaciones** en movimientos de proveedores
- **🗂️ Integración con el módulo de compras** (facturas/ordenes)
- **📌 Soft delete** de proveedores (mantiene historial y coherencia)
- **💻 Interfaz responsive** con Bootstrap + validación de formularios

### ✅ PASO 7: Gestión de Clientes (v0.7.0)
- **👥 CRUD de clientes completo** (crear, editar, listar, desactivar)
- **💼 Gestión de cuentas corrientes** (debe/haber, saldo, movimientos)
- **📊 Historial de ventas por cliente** con estadísticas y última compra
- **🧾 Soporte de pagos y verificaciones** en movimientos de clientes
- **🗂️ Integración con el mecanismo de ventas** existente (cliente en ticket)
- **📌 Soft delete** de clientes (mantiene historial y coherencia)
- **💻 Interfaz responsive** con Bootstrap + validación de formularios

### ✅ PASO 6: Módulo de Punto de Venta (POS) (v0.6.0)
- **🛒 Sistema completo de ventas** con carrito de compras
- **🔍 Búsqueda inteligente** de productos por nombre/código/categoría
- **📱 Interfaz responsive** con Bootstrap 5
- **⚡ Validación en tiempo real** de stock disponible
- **🧾 Generación automática de tickets** imprimibles
- **💰 Múltiples medios de pago** (efectivo, débito, crédito, etc.)
- **👥 Integración con clientes** y temporadas
- **📊 Decremento automático de stock** con auditoría

### ✅ PASO 5: Módulo de Stock (v0.5.0)
- **📦 Gestión completa de inventario** con estados dinámicos
- **📊 Estados de stock**: SIN STOCK, CRÍTICO, BAJO, NORMAL, EXCESO
- **🔍 Búsqueda y filtrado** por estado de stock
- **📈 Alertas en tiempo real** con endpoint `/api/alertas`
- **📝 Historial de movimientos** completo (auditoría)
- **⚡ Formulario inteligente** de ajuste con cálculo automático
- **📋 Panel de rangos recomendados** y historial integrado

### ✅ PASO 4: CRUD de Productos + Sistema TIER (v0.4.0)
- **📝 Productos CRUD completo** (crear, editar, listar, borrar)
- **🏷️ Gestión de categorías** dinámica
- **🔒 Sistema TIER**: DEMO (5 productos), BÁSICA (50), PRO (1000)
- **📊 Dashboard de licencia** con barra de progreso

### ✅ PASO 3: Autenticación + Dashboard + Backups (v0.3.0)
- **🔐 Sistema de autenticación** con login/logout
- **📊 Dashboard administrativo** con estadísticas
- **💾 Sistema de backups** automáticos y manuales
- **👥 Gestión de usuarios** (admin y vendedor)

---

## 📊 Estado del Proyecto (v1.19.0)

| Paso | Módulo | Versión | Tests | Estado |
|------|--------|---------|-------|--------|
| 29 | Refinamiento UX y Topbar | `v1.19.0` | - | Completo |
| 28 | Unificación Estética | `v1.18.0` | - | Completo |
| 27 | Infraestructura de Build | `v1.17.0` | - | Completo |
| 26 | Mejoras de Usabilidad | `v1.16.0` | - | Completo |
| 25 | UX de Apagado | `v1.15.0` | - | Completo |
| 24 | Launcher Universal | `v1.14.0` | - | Completo |
| 23 | Refactorización Sidebar | `v1.13.0` | - | Completo |
| 15 | Financiación y Cobranzas | `v1.5.1` | 5/5 ✅ | Completo |
| 22 | Apagado Controlado | `v1.12.0` | - | Completo |
| 14 | Gestión de Temporadas | `v1.4.0` | 5/5 ✅ | Completo |
| 13 | Gestión de Usuarios y Permisos | `v1.3.0` | 5/5 ✅ | Completo |
| 19 | Estadísticas Avanzadas y Análisis | `v1.9.0` | - | Completo |
| 12 | Estadísticas Avanzadas | `v1.2.0` | 5/5 ✅ | Completo |
| 11 | Gastos Operativos | `v1.1.0` | 5/5 ✅ | Completo |
| 10 | Caja y Liquidación | `v1.0.0` | 5/5 ✅ | Completo |
| 9 | Compras | `v0.9.0` | 5/5 ✅ | Completo |
| 8 | Gestión de Proveedores | `v0.8.0` | 8/8 ✅ | Completo |
| 7 | Gestión de Clientes | `v0.7.0` | 8/8 ✅ | Completo |
| 6 | Punto de Venta (POS) | `v0.6.0` | 8/10 ✅ | Completo |
| 5 | Stock Management | `v0.5.0` | 23/23 ✅ | Completo |
| 4 | Productos CRUD + TIER | `v0.4.0` | 12/12 ✅ | Completo |
| 3 | Auth + Dashboard | `v0.3.0` | 6/6 ✅ | Completo |

**Total Tests:** 72/72 ✅ (100%)

---

---

## 🛠️ Tecnologías

| Componente | Tecnología |
|---|---|
| Backend | Python 3.11+ / Flask 3.0 |
| Base de datos | SQLite (archivo local) |
| Frontend | Bootstrap 5.3 + Font Awesome 6 |
| Paleta | Azul marino + plateado |
| Testing | pytest |
| Versionado | Git + Semantic Versioning |

---

## 📋 Próximos Pasos (Roadmap)

---

## 🚀 Instalación rápida

```bash
# 1. Clonar el repositorio
git clone https://github.com/NexarSistemas/nexar-tienda.git
cd nexar-tienda

# 2. Crear entorno virtual
python3 -m venv venv
source venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Ejecutar la app
python app.py
```

Luego abrir el navegador en: **http://localhost:5000**

---

## 🧪 Ejecutar Tests

```bash
# Ejecutar todos los tests
python -m pytest test_paso*.py -v

# Ejecutar tests de un paso específico
python -m pytest test_paso5.py -v
```

---

## 📝 Changelog

Ver [CHANGELOG.md](CHANGELOG.md) para el historial completo de cambios.

---

## 🤝 Contribución

1. Fork el proyecto
2. Crea tu rama de feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

---

## 📄 Licencia

Este proyecto está bajo la Licencia MIT - ver el archivo [LICENSE](LICENSE) para más detalles.

---

## 📞 Contacto

**Nexar Sistemas** - [GitHub](https://github.com/NexarSistemas)

**Última actualización:** 25 de abril de 2026 - v1.19.0
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── productos.html
│   ├── producto_form.html
│   ├── stock.html
│   ├── stock_ajustar.html
│   ├── licencia.html
│   └── ...
├── static/
│   ├── css/main.css
│   ├── js/pos.js
│   └── js/utils.js
├── tests/
│   ├── test_paso3.py
│   ├── test_paso4.py
│   └── test_paso5.py
├── docs/
│   └── ai/                 # Contexto para asistentes IA
└── prompts/
    └── copilot/            # Instrucciones para Copilot
```

---

## Estado actual del proyecto (v0.5.0)

| Módulo                    | Estado        | Tests  |
|--------------------------|--------------|--------|
| Autenticación            | ✔️ Completo   | 6/6    |
| Dashboard                | ✔️ Completo   | -      |
| Backups                  | ✔️ Completo   | -      |
| Productos + Categorías   | ✔️ Completo   | 12/12  |
| Sistema TIER             | ✔️ Completo   | Incluido |
| Stock + Movimientos      | ✔️ Completo   | 23/23  |
| Alertas                  | ✔️ Completo   | Incluido |

---

## Roadmap oficial

- **0.6.0 – Punto de Venta (POS)**  
  Carrito, ventas, tickets, decremento automático de stock.

- **0.7.0 – Clientes**  
  CRUD, historial, cuenta corriente.

- **0.8.0 – Proveedores**  
  CRUD, historial de compras, contacto.

- **0.9.0 – Compras**  
  Órdenes de compra, recepción de mercadería.

- **1.0.0 – Release Oficial**  
  Caja, estadísticas completas, multiusuario POS.

---

## Versionado

El proyecto usa **Semantic Versioning**:

- **MAJOR**: cambios grandes o ruptura.
- **MINOR**: nuevas funcionalidades (cada paso del proyecto).
- **PATCH**: correcciones menores.

Cada versión incluye:

- Actualización de `VERSION`
- Entrada en `CHANGELOG.md`
- Actualización del `README`
- Tag en Git

---

## Licencia

Proyecto privado. Todos los derechos reservados.