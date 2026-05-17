# COPILOT_CONTEXT.md

Proyecto Nexar Comercio.
Repo técnico: nexar-tienda.

Sugerir código conservador.
No inventar arquitectura nueva.
No cambiar nombres técnicos existentes.
No tocar licencias, pagos, builds ni actualizaciones salvo pedido explícito.

Nunca trabajar directo sobre main.
Cada mejora debe ir en rama propia.

Usar patrones existentes:
- Flask routes en routes/main.py
- consultas SQLite en database.py
- templates Jinja2 + Bootstrap
- JavaScript simple dentro de templates si ya existe ese patrón

Prioridades:
1. edición responsable
2. flujo ágil compra/producto/proveedor
3. filtro por proveedor
4. aumento de precios por proveedor/categoría
5. categorías configurables
6. carga por lote
7. importación Excel/CSV
8. códigos internos
9. reportes demo
10. onboarding
11. imágenes catálogo
