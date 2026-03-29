"""
Nexar Tienda — database.py
Conexión y consultas SQLite.

Se completará en el Paso 2 con todas las tablas.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tienda.db')

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def q(sql, params=(), fetchall=True, fetchone=False, commit=False):
    """Función única para ejecutar consultas SQL."""
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute(sql, params)
        if commit:
            conn.commit()
            return c.lastrowid
        if fetchone:
            return c.fetchone()
        if fetchall:
            return c.fetchall()
    finally:
        conn.close()

# Las tablas se crearán en el Paso 2
