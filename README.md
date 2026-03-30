# Nexar Tienda 🛍️

Sistema integral de gestión para tiendas de regalos, marroquinería, bijouterie y comercios de temporada.  
**Versión 0.5.0 — Módulo de Stock completado.**

---

## Funcionalidades principales

### Gestión de Inventario y Stock

- Estados automáticos: **SIN STOCK, CRÍTICO, BAJO, NORMAL, EXCESO**.
- Historial completo de movimientos con auditoría.
- Ajustes de stock con cálculo automático de diferencias.
- Panel de rangos recomendados y alertas en tiempo real.
- Filtros avanzados por estado y búsqueda por nombre.

### Productos y Categorías

- CRUD completo de productos.
- Categorías dinámicas.
- Soft delete con restauración.
- Integración con sistema TIER.

### Sistema TIER de Licenciamiento

- Modos: **DEMO, BÁSICA, PRO**.
- Límites automáticos de productos según licencia.
- Panel visual del estado de licencia.

### Autenticación y Seguridad

- Login/logout con sesiones seguras.
- Roles: **admin** y **vendedor**.
- Decoradores `@login_required` y `@admin_required`.
- Validaciones server-side y client-side.
- Prevención de SQL injection.

### Dashboard Administrativo

- Estadísticas generales.
- Alertas de stock.
- Accesos rápidos a módulos clave.

### Sistema de Backups

- Backups automáticos y manuales.
- Historial de copias.

---

## Tecnologías utilizadas

| Componente      | Tecnología                          |
|----------------|------------------------------------|
| Backend        | Python 3.11+ / Flask 3.0           |
| Base de datos  | SQLite (archivo local)             |
| Frontend       | Bootstrap 5.3 + Font Awesome 6     |
| Seguridad      | Hash SHA256 + validaciones         |
| Testing        | pytest (23 tests pasando en v0.5.0)|

---

## Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/tu-usuario/nexar-tienda.git
cd nexar-tienda

# 2. Crear entorno virtual
python3 -m venv venv
source venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Ejecutar la app
python app.py
```

Abrir en el navegador:  
👉 http://localhost:5000  

**Usuario inicial:** admin  
**Contraseña:** admin123  

⚠️ Cambiar la contraseña en el primer inicio.

---

## Estructura del proyecto

```bash
nexar-tienda/
├── app.py                  # Rutas y lógica principal
├── database.py             # Conexión y consultas SQLite
├── VERSION                 # Versión actual del sistema
├── CHANGELOG.md            # Historial de cambios
├── templates/              # HTML (Jinja2)
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