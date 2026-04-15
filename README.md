# 🎁 Nexar Tienda v1.22.0

Sistema Integral de Gestión Comercial diseñado para tiendas de regalos, bijouterie, marroquinería y productos estacionales. Optimizado para un funcionamiento fluido, seguro y con una interfaz estética de alto nivel.

**Desarrollado por Nexar Sistemas — © 2026**

---

## 📦 Estructura del Proyecto

```
nexar-tienda/
├── app.py                → Lógica principal y rutas Flask
├── database.py           → Motor de base de datos SQLite y consultas SQL
├── iniciar.py            → Launcher universal con ventana nativa
├── tienda.db             → Base de datos (generada al iniciar)
├── VERSION               → Control de versión actual
├── CHANGELOG.md          → Historial detallado de cambios
├── static/               → Recursos estáticos (CSS, JS, Imágenes)
│   ├── css/main.css      → Estilos "Fine" (Azul marino & Plata)
│   └── js/pos.js         → Lógica del Punto de Venta
├── templates/            → Plantillas Jinja2 (UI/UX)
└── respaldo/             → Copias de seguridad automáticas
```

---

##  Instalación y Arranque

### Requisitos
- **Python 3.11** o superior.
- Dependencias: `flask`, `pywebview`, `openpyxl`, `reportlab`, `markdown`, `python-dotenv`.

### Inicio Rápido
Para iniciar la aplicación como una herramienta de escritorio:

```bash
python iniciar.py
```

El launcher buscará automáticamente un puerto libre (rango 5200-5999) e iniciará la aplicación en una **ventana nativa** independiente, maximizada y optimizada para el uso diario.

---

## ✨ Módulos Principales

### 🛒 Punto de Venta (POS)
- Carrito de compras persistente basado en sesiones.
- Búsqueda inteligente por nombre, código o categoría.
- Gestión de múltiples medios de pago.
- Integración directa con Cuenta Corriente de clientes.

### 📦 Control de Inventario
- Estados de stock dinámicos (Sin Stock, Crítico, Bajo, Normal, Exceso).
- Historial de movimientos y ajustes auditados.
- Soporte para productos de temporada y destacados.

### 💰 Finanzas y Gastos
- Gestión de categorías de gastos dinámicas.
- Clasificación de esencialidad: **Gastos Necesarios vs. Prescindibles**.
- Análisis de salud financiera con recomendaciones automáticas.
- **Historial Interactivo**: Registro de cambios con sistema de acordeón y filtrado de lanzamientos.
- Control de caja diaria con apertura, arqueo y liquidación.

### 👥 Clientes y Proveedores
- Gestión de Cuentas Corrientes (Debe/Haber).
- Límites de crédito personalizables por cliente.
- Historial de compras y estadísticas de lealtad.

---

## 🔐 Seguridad y Licenciamiento

- **Acceso RBAC**: Control de acceso basado en roles (Administrador, Encargado, Vendedor).
- **Seguridad de Cuentas**: Validación de contraseñas fuertes y recuperación mediante pregunta secreta.
- **Licencia RSA**: Sistema de activación offline mediante tokens Base64 firmados digitalmente (RSA-2048), vinculados al Hardware ID del equipo.
- **Tiers de Licencia**:
    - **DEMO**: 30 días de prueba con funcionalidad completa.
    - **BÁSICA**: Pago único, límites de catálogo estándar.
    - **PRO**: Suscripción mensual, recursos ilimitados y funciones BI avanzadas. Al vencer, el sistema degrada automáticamente a BÁSICA sin pérdida de datos.

---

## 💾 Backups y Exportación

- **Respaldos Automáticos**: Programables cada N horas, manteniendo un historial rotativo en la carpeta `/respaldo`.
- **Excel**: Exportación completa del catálogo para control de stock externo.
- **PDF**: Generación de listas de precios profesionales listas para imprimir o enviar.

---

## 🛠 Tecnologías

- **Backend**: Python 3.11 + Flask 3.0.
- **Frontend**: Bootstrap 5.3, Inter Font, Font Awesome 6.
- **Base de Datos**: SQLite 3 con integridad referencial.
- **Desktop Wrapper**: pywebview para una experiencia de usuario nativa.

---

## 📞 Soporte y Contacto

¿Necesitás ayuda o una licencia Pro?
- **WhatsApp**: +54 9 264 585-8874
- **Email**: nexarsistemas@outlook.com.ar

---
*Desarrollado con ❤️ para el comercio argentino.*

**Nexar Sistemas — Soluciones de Software de Alta Calidad.**