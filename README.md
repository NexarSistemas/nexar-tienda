# Nexar Tienda 🛍️

Sistema de gestión para tienda de regalos, marroquinería, bijouterie y productos de temporada.

Desarrollado con **Python + Flask + SQLite**.

---

## ¿Qué hace esta app?

- **Punto de Venta (POS):** vendé rápido, con búsqueda por nombre o categoría.
- **Gestión de productos y stock:** catálogo con categorías propias de la tienda.
- **Clientes y cuenta corriente:** seguimiento de saldos y pagos.
- **Proveedores y compras:** control de facturas y stock entrante.
- **Temporadas:** destacá productos para Navidad, Día de la Madre, Día del Padre, etc.
- **Estadísticas y caja:** cierre diario, gastos y análisis de ventas.

---

## Tecnologías

| Componente | Tecnología |
|---|---|
| Backend | Python 3.11+ / Flask 3.0 |
| Base de datos | SQLite (archivo local) |
| Frontend | Bootstrap 5.3 + Font Awesome 6 |
| Paleta | Azul marino + plateado |

---

## Instalación rápida

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

Luego abrir el navegador en: **http://localhost:5000**

Usuario inicial: `admin` / Contraseña: `admin123`

> ⚠️ Cambiá la contraseña inmediatamente después del primer inicio de sesión.

---

## Estructura del proyecto

```
nexar-tienda/
├── app.py                  # Rutas y lógica principal de Flask
├── database.py             # Conexión y consultas SQLite
├── requirements.txt        # Dependencias Python
├── VERSION                 # Versión actual del sistema
├── .gitignore
├── templates/              # Páginas HTML (Jinja2)
│   ├── base.html           # Layout principal con sidebar
│   ├── login.html
│   ├── dashboard.html
│   ├── productos.html
│   ├── producto_form.html
│   ├── stock.html
│   ├── punto_venta.html
│   ├── ticket.html
│   ├── clientes.html
│   ├── cc_cliente_detalle.html
│   ├── proveedores.html
│   ├── compras.html
│   ├── historial.html
│   ├── gastos.html
│   ├── caja.html
│   ├── estadisticas.html
│   ├── temporadas.html     # ★ Nuevo: módulo de temporadas
│   ├── config.html
│   └── usuarios.html
├── static/
│   ├── css/
│   │   └── main.css        # Estilos globales (paleta azul marino)
│   ├── js/
│   │   ├── pos.js          # Lógica del punto de venta
│   │   └── utils.js        # Helpers compartidos
│   ├── icons/
│   └── images/
├── services/               # Módulos auxiliares
│   └── __init__.py
├── docs/
│   └── ai/                 # Contexto para asistentes IA
└── prompts/
    └── copilot/            # Instrucciones para GitHub Copilot
```

---

## Módulo de Temporadas ★

Una de las funciones más importantes para esta tienda. Permite:
- Definir temporadas con fechas (ej: "Día de la Madre: 01/05 - 20/05")
- Marcar productos como "destacados" para cada temporada
- Ver alertas en el dashboard cuando una temporada se acerca
- Analizar qué productos vendieron mejor por temporada

---

## Hoja de ruta (Roadmap)

- [x] v0.1 - Estructura base y configuración del proyecto
- [ ] v0.2 - Base de datos y modelos
- [ ] v0.3 - App Flask con login y dashboard
- [ ] v0.4 - Módulo de productos y stock
- [ ] v0.5 - Punto de venta (POS)
- [ ] v0.6 - Clientes y cuenta corriente
- [ ] v0.7 - Proveedores y compras
- [ ] v0.8 - Temporadas y estadísticas
- [ ] v1.0 - Versión completa estable

---

## Licencia

Proyecto privado. Todos los derechos reservados.
