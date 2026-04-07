# Nexar Tienda 🛍️

Sistema integral de gestión para tiendas de regalos, marroquinería, bijouterie y comercios de temporada.

**Versión actual:** `v1.1.0` - PASO 11: Gastos Operativos

Desarrollado con **Python + Flask + SQLite**.

---

## 🚀 Características Implementadas

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

## 📊 Estado del Proyecto (Release 1.0.0)

| Paso | Módulo | Versión | Tests | Estado |
|------|--------|---------|-------|--------|
| 11 | Gastos Operativos | `v1.1.0` | 5/5 ✅ | Completo |
| 10 | Caja y Liquidación | `v1.0.0` | 5/5 ✅ | Completo |
| 9 | Compras | `v0.9.0` | 5/5 ✅ | Completo |
| 8 | Gestión de Proveedores | `v0.8.0` | 8/8 ✅ | Completo |
| 7 | Gestión de Clientes | `v0.7.0` | 8/8 ✅ | Completo |
| 5 | Stock Management | `v0.5.0` | 23/23 ✅ | Completo |
| 4 | Productos CRUD + TIER | `v0.4.0` | 12/12 ✅ | Completo |
| 3 | Auth + Dashboard | `v0.3.0` | 6/6 ✅ | Completo |

**Total Tests:** 59/59 ✅ (100%)

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

### 🔄 PASO 12: Estadísticas Avanzadas (v0.12.0)
- Dashboard con gráficos y métricas
- Reportes de ventas por período
- Análisis de rentabilidad por producto

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

**Última actualización:** 07 de abril de 2026 - v1.1.0
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