# 🛍️ Nexar Tienda

**Nexar Tienda** es un sistema integral de gestión diseñado específicamente para tiendas de regalos, accesorios y comercios minoristas. Basado en la arquitectura robusta de *Nexar Almacén*, esta versión ha sido optimizada para ofrecer una experiencia de usuario fluida, seguridad avanzada y herramientas de inteligencia de negocios.

> **Versión Actual:** v1.20.0 (Seguridad y Autogestión)  
> **Estado:** Productivo / Estable

---

## 🚀 Características Principales

### 🛒 Punto de Venta (POS)
*   Búsqueda inteligente de productos por código, nombre o categoría.
*   Gestión de múltiples medios de pago (Efectivo, Débito, Crédito, Transferencia).
*   Generación de tickets de venta profesionales.
*   Validación de stock en tiempo real.

### 📦 Inventario y Proveedores
*   Control de stock con alertas de niveles críticos y bajos.
*   Gestión de proveedores y cuentas corrientes (Debe/Haber).
*   Módulo de compras para ingreso automatizado de mercadería.
*   Categorización dinámica de productos.

### 📊 Inteligencia y Finanzas
*   **Caja Diaria:** Apertura, movimientos de caja y arqueo de cierre.
*   **Estadísticas:** Dashboards anuales y mensuales con gráficos interactivos (Chart.js).
*   **Análisis:** Reportes de rentabilidad por producto y temporada.
*   **Exportación:** Generación de catálogos en Excel y listas de precios en PDF.

### 🔒 Seguridad y Administración
*   **RBAC:** Control de acceso basado en roles (Administrador, Encargado, Vendedor).
*   **Seguridad:** Validación de contraseñas fuertes y recuperación mediante desafío secreto.
*   **Backups:** Sistema de respaldo automático y manual de la base de datos.
*   **Modo App:** Ejecución como ventana nativa independiente mediante `pywebview`.

---

## 🛠️ Stack Tecnológico

*   **Lenguaje:** Python 3.11+
*   **Framework Web:** Flask 3.0
*   **Base de Datos:** SQLite (Motor ligero y portable)
*   **Frontend:** Bootstrap 5.3, Font Awesome 6.4, Chart.js
*   **Ventana Nativa:** PyWebView

---

## 💻 Instalación y Uso

### Requisitos Previos
Asegúrate de tener Python 3.11 o superior instalado. El sistema gestionará sus propias dependencias al iniciar.

### Arranque Rápido

**En Windows:**
Ejecuta el archivo `iniciar.bat` o directamente mediante la consola:
```bash
python iniciar.py
```

**En Linux:**
Otorga permisos de ejecución e inicia:
```bash
chmod +x iniciar.sh
./iniciar.sh
```

El sistema buscará automáticamente un puerto libre (rango 5200-5999) e intentará abrir la aplicación en una ventana independiente. Si no es posible, se abrirá en tu navegador predeterminado en `http://127.0.0.1:<puerto>`.

---

## ⚙️ Configuración Inicial
Al iniciar el sistema por primera vez (o tras un reset), se te pedirá configurar:
1.  **Credenciales de Administrador:** Nombre de usuario y contraseña segura.
2.  **Seguridad:** Pregunta y respuesta secreta para recuperación.
3.  **Datos del Negocio:** Nombre, CUIT/DNI y dirección para los tickets.

---

## 🏗️ Estructura del Proyecto

*   `/app.py`: Servidor principal y rutas.
*   `/database.py`: Capa de persistencia y lógica SQL.
*   `/iniciar.py`: Launcher inteligente y gestión de entorno.
*   `/services/`: Lógica de negocio adicional (Licencias, Seguridad).
*   `/static/`: Recursos CSS, JS e imágenes.
*   `/templates/`: Vistas HTML (Jinja2).
*   `/build/`: Scripts para generación de ejecutables (.exe, .deb).

---

## 📄 Licencia

Este software es propiedad de **Nexar Sistemas**. El uso no autorizado o la distribución de este código está prohibido bajo los términos de la licencia comercial de la suite Nexar.

---
*Desarrollado con por Nexar Sistemas — &copy; 2026*