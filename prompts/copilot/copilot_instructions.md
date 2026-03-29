# Instrucciones para GitHub Copilot — Nexar Tienda

## ¿Qué es este proyecto?
Sistema de gestión (POS + inventario + clientes + proveedores) para una tienda
de regalos, marroquinería, bijouterie y productos de temporada.
Desarrollado con Python 3.11, Flask 3.0, SQLite y Bootstrap 5.

## Stack tecnológico
- **Backend:** Flask con Jinja2 para templates
- **Base de datos:** SQLite mediante el módulo `database.py`
- **Frontend:** Bootstrap 5.3 + Font Awesome 6.4 + JS vanilla
- **Paleta de colores:** Azul marino (#1e3a5f) + plateado (#94a3b8)

## Convenciones del proyecto

### Python / Flask
- Todas las rutas están en `app.py`
- Las consultas SQL se hacen con la función `q()` de `database.py`
- Los decoradores `@login_required` y `@admin_required` protegen las rutas
- Los mensajes al usuario se envían con `flash()` siempre con emoji inicial
- Los precios se formatean con la función `fmt_ars()` (formato ARS argentino)

### Templates HTML
- Todos extienden `base.html` con `{% extends "base.html" %}`
- El bloque principal es `{% block content %}...{% endblock %}`
- Las tablas usan la clase `.table-card` para consistencia visual
- Los formularios usan POST y redirigen con `redirect()` después de guardar

### Base de datos
- La función `q(sql, params, fetchone, fetchall, commit)` maneja todo
- Las claves foráneas están activadas con `PRAGMA foreign_keys = ON`
- Usar siempre parámetros `?` para evitar SQL injection

### Categorías de productos (específicas de esta tienda)
- Bijouterie
- Marroquinería
- Mates y Termos
- Adornos y Decoración
- Regalos Varios
- Regalos de Temporada
- Papelería y Librería
- Textil e Indumentaria
- Juguetería
- Cotillón

### Módulo de Temporadas (específico de esta app)
- Tabla: `temporadas` (id, nombre, fecha_inicio, fecha_fin, activa, descripcion)
- Tabla: `productos_temporada` (producto_id, temporada_id, destacado)
- El dashboard muestra alertas cuando una temporada se aproxima en los próximos 30 días

### IVA
- Los productos tienen campo `iva_tipo`: 'incluido' o 'discriminado'
- En el POS se muestra según preferencia del cliente
- IVA por defecto: 21%

## Lo que NO hay en este proyecto
- Sin integración con OpenFoodFacts (es una tienda, no un almacén)
- Sin sistema de licencias (es para uso propio)
- Sin pywebview (corre en el navegador, no como app nativa)
- Sin código de barras obligatorio (los productos se buscan por nombre)
