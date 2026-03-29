"""
Nexar Tienda — app.py
Rutas y lógica principal de Flask.

Este archivo se irá completando paso a paso:
  Paso 3  → Login, logout, dashboard básico
  Paso 4  → Productos
  Paso 5  → Stock
  Paso 6  → Punto de Venta
  Paso 7  → Clientes / CC
  Paso 8  → Proveedores / Compras
  Paso 9  → Temporadas y estadísticas
"""

from flask import Flask

app = Flask(__name__)
app.secret_key = 'nexar-tienda-dev-key-cambiar-en-produccion'

# ─── INICIO ──────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("Nexar Tienda — iniciando en http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
