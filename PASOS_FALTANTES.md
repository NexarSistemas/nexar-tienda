# 🗺️ Nexar Tienda — Pasos Faltantes (Paso 15 → Paso 22)

> **Base:** Se parte de la versión `v1.4.0` con 14 pasos completados.  
> **Referencia:** Nexar Almacén como guía estructural.  
> **Stack:** Python 3.11 · Flask 3.0 · SQLite · Bootstrap 5.3 · Font Awesome 6.4  
> **Paleta:** Navy blue `#1e3a5f` con acentos plateados.

---

## Estado actual (resumen)

| Paso | Módulo | Versión | Estado |
|------|--------|---------|--------|
| 3 | Login / Autenticación | v0.1.1 | ✅ |
| 4 | Productos (ABM) | v0.2.0 | ✅ |
| 5 | Stock | v0.3.0 | ✅ |
| 6 | Punto de Venta (POS) | v0.4.0 | ✅ |
| 7 | Clientes + Cuenta Corriente | v0.5.0 | ✅ |
| 8 | Proveedores | v0.6.0 | ✅ |
| 9 | Compras | v0.7.0 | ✅ |
| 10 | Caja / Liquidación diaria | v1.0.0 | ✅ |
| 11 | Gastos operativos | v1.1.0 | ✅ |
| 12 | Estadísticas / Reportes básicos | v1.2.0 | ✅ |
| 13 | Usuarios y Permisos (RBAC) | v1.3.0 | ✅ |
| 14 | Temporadas (DB + templates) | v1.4.0 | ✅ |

---

---

## PASO 15 — Temporadas: Rutas y CRUD completo ⚠️

**Versión objetivo:** `v1.5.0`  
**Prioridad:** 🔴 Alta — El Paso 14 dejó las rutas sin implementar. El menú del sidebar apunta a páginas que retornan 404.

### Problema a resolver

El Paso 14 creó las tablas `temporadas` y `productos_temporada` en `database.py` y los templates `temporadas.html` y `temporada_form.html`, pero **nunca se agregaron las rutas en `app.py`**. El módulo está inactivo.

### Archivos a modificar

- `app.py` — agregar bloque de rutas de temporadas
- `database.py` — verificar/agregar funciones de soporte
- `templates/temporadas.html` — ajustes si son necesarios
- `templates/temporada_form.html` — ajustes si son necesarios
- `templates/punto_venta.html` — agregar filtro por temporada activa

### Rutas a implementar en `app.py`

```python
# ─── TEMPORADAS (PASO 15) ──────────────────────────────────────────────────

@app.route('/temporadas')
@login_required
def temporadas():
    """Lista todas las temporadas con su estado de vigencia."""
    lista = db.get_temporadas()
    activa = db.get_temporada_actual()
    proxima = db.get_proxima_temporada()
    return render_template(
        'temporadas.html',
        app_version=APP_VERSION,
        usuario=session['user'],
        temporadas=lista,
        activa=activa,
        proxima=proxima
    )

@app.route('/temporadas/nueva', methods=['GET', 'POST'])
@admin_required
def temporada_nueva():
    """Formulario para crear una nueva temporada."""
    if request.method == 'POST':
        data = request.form.to_dict()
        db.add_temporada(data)
        flash('✅ Temporada creada correctamente.', 'success')
        return redirect(url_for('temporadas'))
    return render_template(
        'temporada_form.html',
        app_version=APP_VERSION,
        usuario=session['user'],
        accion='Nueva',
        temporada={}
    )

@app.route('/temporadas/<int:tid>/editar', methods=['GET', 'POST'])
@admin_required
def temporada_editar(tid):
    """Editar una temporada existente."""
    temporada = db.get_temporada(tid)
    if not temporada:
        flash('❌ Temporada no encontrada.', 'danger')
        return redirect(url_for('temporadas'))
    if request.method == 'POST':
        data = request.form.to_dict()
        db.update_temporada(tid, data)
        flash('✅ Temporada actualizada.', 'success')
        return redirect(url_for('temporadas'))
    return render_template(
        'temporada_form.html',
        app_version=APP_VERSION,
        usuario=session['user'],
        accion='Editar',
        temporada=temporada
    )

@app.route('/temporadas/<int:tid>/eliminar', methods=['POST'])
@admin_required
def temporada_eliminar(tid):
    """Elimina una temporada y sus vínculos con productos."""
    try:
        db.delete_temporada(tid)
        flash('🗑 Temporada eliminada.', 'warning')
    except Exception as e:
        flash(f'❌ Error al eliminar: {str(e)}', 'danger')
    return redirect(url_for('temporadas'))

@app.route('/api/temporada/<int:tid>/productos', methods=['GET'])
@login_required
def api_temporada_productos(tid):
    """Retorna productos vinculados a una temporada (para el POS)."""
    productos = db.get_productos_por_temporada(tid)
    return jsonify([dict(p) for p in productos])
```

### Funciones a agregar/verificar en `database.py`

```python
def get_temporadas(self):
    """Retorna todas las temporadas ordenadas por fecha de inicio."""
    return self.q("SELECT * FROM temporadas ORDER BY fecha_inicio")

def get_temporada(self, tid):
    """Retorna una temporada por ID."""
    return self.q("SELECT * FROM temporadas WHERE id=?", (tid,), fetchone=True)

def add_temporada(self, data):
    """Crea una nueva temporada."""
    self.q("""
        INSERT INTO temporadas (nombre, fecha_inicio, fecha_fin, color)
        VALUES (:nombre, :fecha_inicio, :fecha_fin, :color)
    """, data, commit=True)

def update_temporada(self, tid, data):
    """Actualiza una temporada existente."""
    data['id'] = tid
    self.q("""
        UPDATE temporadas SET nombre=:nombre, fecha_inicio=:fecha_inicio,
        fecha_fin=:fecha_fin, color=:color WHERE id=:id
    """, data, commit=True)

def delete_temporada(self, tid):
    """Elimina una temporada y sus relaciones."""
    self.q("DELETE FROM productos_temporada WHERE temporada_id=?", (tid,), commit=True)
    self.q("DELETE FROM temporadas WHERE id=?", (tid,), commit=True)

def get_proxima_temporada(self):
    """Retorna la próxima temporada que aún no comenzó."""
    hoy = datetime.now().strftime('%Y-%m-%d')
    return self.q("""
        SELECT * FROM temporadas WHERE fecha_inicio > ? ORDER BY fecha_inicio LIMIT 1
    """, (hoy,), fetchone=True)

def get_productos_por_temporada(self, tid):
    """Retorna productos asociados a una temporada."""
    return self.q("""
        SELECT p.* FROM productos p
        JOIN productos_temporada pt ON p.id = pt.producto_id
        WHERE pt.temporada_id = ?
    """, (tid,))
```

### Tests a ejecutar

```bash
# Verificar que las rutas respondan
python -c "
from app import app
with app.test_client() as c:
    c.post('/login', data={'username':'admin','password':'admin123'})
    r = c.get('/temporadas')
    assert r.status_code == 200, f'Fallo: {r.status_code}'
    print('✅ /temporadas OK')
"
```

### Commit sugerido

```bash
git add app.py database.py templates/temporadas.html templates/temporada_form.html
git commit -m "feat(temporadas): implementar rutas CRUD completas - Paso 15 v1.5.0"
git tag v1.5.0
```

---

---

## PASO 16 — Módulo de Respaldo (Backup / Restore) 🔒

**Versión objetivo:** `v1.6.0`  
**Prioridad:** 🔴 Alta — Sin interfaz de respaldo, un error puede significar pérdida total de datos en producción.

### Problema a resolver

Nexar Tienda tiene la función interna `hacer_backup()` y un scheduler automático en `app.py`, pero el usuario **no puede ver, descargar ni restaurar** sus respaldos desde la interfaz. Nexar Almacén tiene un módulo completo en `/respaldo` que se adapta directamente.

### Archivos a crear/modificar

- `app.py` — agregar bloque de rutas `/respaldo`
- `templates/respaldo.html` — nuevo template adaptado desde Almacén

### Rutas a implementar en `app.py`

```python
# ─── RESPALDO (PASO 16) ────────────────────────────────────────────────────

@app.route('/respaldo')
@admin_required
def respaldo():
    """Panel de gestión de respaldos."""
    import glob
    cfg = db.get_config()
    backup_dir = get_backup_dir()
    archivos = []
    if os.path.isdir(backup_dir):
        patron = os.path.join(backup_dir, 'tienda_*.db')
        for f in sorted(glob.glob(patron), reverse=True):
            stat = os.stat(f)
            archivos.append({
                'nombre': os.path.basename(f),
                'tamanio_kb': round(stat.st_size / 1024, 1),
                'fecha': datetime.fromtimestamp(stat.st_mtime).strftime('%d/%m/%Y %H:%M'),
            })
    return render_template(
        'respaldo.html',
        app_version=APP_VERSION,
        usuario=session['user'],
        archivos=archivos,
        backup_dir=backup_dir,
        ultimo=cfg.get('backup_ultimo', '—'),
        intervalo=cfg.get('backup_intervalo_h', '24'),
        keep=cfg.get('backup_keep', '10')
    )

@app.route('/respaldo/ahora', methods=['POST'])
@admin_required
def respaldo_ahora():
    """Genera un respaldo manual inmediato."""
    ok, msg = hacer_backup(manual=True)
    if ok:
        flash(f'✅ Respaldo creado: {os.path.basename(msg)}', 'success')
    else:
        flash(f'❌ Error al respaldar: {msg}', 'danger')
    return redirect(url_for('respaldo'))

@app.route('/respaldo/config', methods=['POST'])
@admin_required
def respaldo_config():
    """Guarda configuración del scheduler de respaldos."""
    data = {
        'backup_intervalo_h': request.form.get('backup_intervalo_h', '24'),
        'backup_keep': request.form.get('backup_keep', '10'),
    }
    db.set_config(data)
    iniciar_backup_scheduler()
    flash('✅ Configuración de respaldos guardada.', 'success')
    return redirect(url_for('respaldo'))

@app.route('/respaldo/descargar/<nombre>')
@admin_required
def respaldo_descargar(nombre):
    """Descarga un archivo de respaldo."""
    import re
    if not re.match(r'^tienda_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.db$', nombre):
        flash('❌ Nombre de archivo inválido.', 'danger')
        return redirect(url_for('respaldo'))
    ruta = os.path.join(get_backup_dir(), nombre)
    if not os.path.exists(ruta):
        flash('❌ Archivo no encontrado.', 'danger')
        return redirect(url_for('respaldo'))
    return send_file(ruta, as_attachment=True, download_name=nombre)

@app.route('/respaldo/eliminar/<nombre>', methods=['POST'])
@admin_required
def respaldo_eliminar(nombre):
    """Elimina un archivo de respaldo."""
    import re
    if not re.match(r'^tienda_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.db$', nombre):
        flash('❌ Nombre de archivo inválido.', 'danger')
    else:
        ruta = os.path.join(get_backup_dir(), nombre)
        if os.path.exists(ruta):
            os.remove(ruta)
            flash(f'🗑 Respaldo eliminado: {nombre}', 'warning')
    return redirect(url_for('respaldo'))

@app.route('/respaldo/restaurar/<nombre>', methods=['POST'])
@admin_required
def respaldo_restaurar(nombre):
    """Restaura la base de datos desde un respaldo."""
    import re, shutil
    if not re.match(r'^tienda_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.db$', nombre):
        flash('❌ Nombre de archivo inválido.', 'danger')
        return redirect(url_for('respaldo'))
    ruta = os.path.join(get_backup_dir(), nombre)
    if not os.path.exists(ruta):
        flash('❌ Archivo no encontrado.', 'danger')
        return redirect(url_for('respaldo'))
    try:
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tienda.db')
        # Guardar copia del estado actual antes de restaurar
        ts = datetime.now().strftime('%Y-%m-%d_%H-%M')
        copia_previa = os.path.join(get_backup_dir(), f'tienda_{ts}_antes_restaurar.db')
        if os.path.exists(db_path):
            shutil.copy2(db_path, copia_previa)
        shutil.copy2(ruta, db_path)
        flash(f'✅ Base de datos restaurada desde «{nombre}». Se guardó copia del estado anterior.', 'success')
    except Exception as e:
        flash(f'❌ Error al restaurar: {str(e)}', 'danger')
    return redirect(url_for('respaldo'))
```

### Agregar import en `app.py` (si no está)

```python
from flask import send_file
```

### Template `templates/respaldo.html` — estructura base

```html
{% extends "base.html" %}
{% block title %}Respaldos{% endblock %}
{% block content %}
<div class="container-fluid py-4">
  <h2><i class="fas fa-database me-2"></i>Gestión de Respaldos</h2>

  <!-- Acciones rápidas -->
  <div class="card mb-4">
    <div class="card-body d-flex gap-2 align-items-center">
      <form method="POST" action="{{ url_for('respaldo_ahora') }}">
        <button class="btn btn-primary"><i class="fas fa-save me-1"></i>Respaldar ahora</button>
      </form>
      <span class="text-muted">Último respaldo: <strong>{{ ultimo }}</strong></span>
    </div>
  </div>

  <!-- Configuración del scheduler -->
  <div class="card mb-4">
    <div class="card-header">Programación automática</div>
    <div class="card-body">
      <form method="POST" action="{{ url_for('respaldo_config') }}" class="row g-3">
        <div class="col-md-4">
          <label class="form-label">Intervalo (horas)</label>
          <input type="number" name="backup_intervalo_h" class="form-control" value="{{ intervalo }}" min="1" max="168">
        </div>
        <div class="col-md-4">
          <label class="form-label">Respaldos a conservar</label>
          <input type="number" name="backup_keep" class="form-control" value="{{ keep }}" min="1" max="50">
        </div>
        <div class="col-md-4 d-flex align-items-end">
          <button class="btn btn-outline-primary w-100">Guardar configuración</button>
        </div>
      </form>
    </div>
  </div>

  <!-- Lista de respaldos -->
  <div class="card">
    <div class="card-header">Archivos de respaldo disponibles</div>
    <div class="card-body p-0">
      <table class="table table-hover mb-0">
        <thead>
          <tr>
            <th>Archivo</th><th>Fecha</th><th>Tamaño</th><th>Acciones</th>
          </tr>
        </thead>
        <tbody>
          {% for a in archivos %}
          <tr>
            <td>{{ a.nombre }}</td>
            <td>{{ a.fecha }}</td>
            <td>{{ a.tamanio_kb }} KB</td>
            <td>
              <a href="{{ url_for('respaldo_descargar', nombre=a.nombre) }}" class="btn btn-sm btn-outline-success">
                <i class="fas fa-download"></i>
              </a>
              <form method="POST" action="{{ url_for('respaldo_restaurar', nombre=a.nombre) }}" class="d-inline"
                    onsubmit="return confirm('¿Restaurar este respaldo? El estado actual se guardará como copia.')">
                <button class="btn btn-sm btn-outline-warning"><i class="fas fa-undo"></i></button>
              </form>
              <form method="POST" action="{{ url_for('respaldo_eliminar', nombre=a.nombre) }}" class="d-inline"
                    onsubmit="return confirm('¿Eliminar este respaldo?')">
                <button class="btn btn-sm btn-outline-danger"><i class="fas fa-trash"></i></button>
              </form>
            </td>
          </tr>
          {% else %}
          <tr><td colspan="4" class="text-center text-muted py-4">No hay respaldos disponibles.</td></tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
</div>
{% endblock %}
```

### Agregar al sidebar en `templates/base.html`

```html
<!-- Dentro del bloque de administración -->
<li class="nav-item">
  <a class="nav-link" href="{{ url_for('respaldo') }}">
    <i class="fas fa-database me-2"></i>Respaldos
  </a>
</li>
```

### Commit sugerido

```bash
git add app.py templates/respaldo.html templates/base.html
git commit -m "feat(respaldo): panel de backup, descarga y restauración - Paso 16 v1.6.0"
git tag v1.6.0
```

---

---

## PASO 17 — Configuración del sistema ⚙️

**Versión objetivo:** `v1.7.0`  
**Prioridad:** 🟠 Media-Alta — Permite personalizar el ticket, los datos del negocio y el comportamiento del IVA.

### Problema a resolver

No existe ninguna pantalla donde el usuario pueda cambiar el nombre del negocio, la dirección, el CUIT, el comportamiento del IVA, o gestionar las categorías de productos desde la interfaz. Todo está hardcodeado o en la base de datos sin UI.

### Archivos a crear/modificar

- `app.py` — agregar bloque de rutas `/config`
- `templates/config.html` — nuevo template
- `database.py` — verificar que `get_config()` y `set_config()` funcionen correctamente

### Rutas a implementar en `app.py`

```python
# ─── CONFIGURACIÓN (PASO 17) ───────────────────────────────────────────────

@app.route('/config', methods=['GET', 'POST'])
@admin_required
def config():
    """Panel de configuración general del sistema."""
    if request.method == 'POST':
        data = request.form.to_dict()
        db.set_config(data)
        flash('✅ Configuración guardada correctamente.', 'success')
        return redirect(url_for('config'))
    cfg = db.get_config()
    categorias = db.get_categorias()
    return render_template(
        'config.html',
        app_version=APP_VERSION,
        usuario=session['user'],
        cfg=cfg,
        categorias=categorias
    )

@app.route('/config/categoria', methods=['POST'])
@admin_required
def config_categoria():
    """Agrega una nueva categoría de producto."""
    nombre = request.form.get('nombre', '').strip()
    if nombre:
        db.add_categoria(nombre)
        flash(f'✅ Categoría "{nombre}" agregada.', 'success')
    else:
        flash('❌ El nombre de la categoría no puede estar vacío.', 'danger')
    return redirect(url_for('config'))

@app.route('/config/categoria/eliminar', methods=['POST'])
@admin_required
def config_categoria_eliminar():
    """Elimina una categoría de producto."""
    nombre = request.form.get('nombre', '').strip()
    if nombre:
        db.delete_categoria(nombre)
        flash(f'🗑 Categoría "{nombre}" eliminada.', 'warning')
    return redirect(url_for('config'))
```

### Funciones a agregar/verificar en `database.py`

```python
def add_categoria(self, nombre):
    """Agrega una nueva categoría si no existe."""
    self.q(
        "INSERT OR IGNORE INTO categorias (nombre) VALUES (?)",
        (nombre,), commit=True
    )

def delete_categoria(self, nombre):
    """Elimina una categoría por nombre."""
    self.q(
        "DELETE FROM categorias WHERE nombre=?",
        (nombre,), commit=True
    )
```

### Campos de configuración sugeridos para `config.html`

El template debe tener secciones separadas para:

**Datos del negocio:**
- `negocio_nombre` — Nombre de la tienda
- `negocio_direccion` — Dirección
- `negocio_telefono` — Teléfono
- `negocio_cuit` — CUIT / DNI
- `negocio_email` — Email de contacto

**Configuración del ticket:**
- `ticket_pie` — Texto al pie del ticket (ej: "¡Gracias por su compra!")
- `ticket_mostrar_iva` — Si el ticket muestra el IVA desglosado (checkbox)

**Configuración de stock:**
- `stock_alerta_minimo` — Umbral global de stock bajo (número)

**Gestión de categorías:**
- Listado de categorías actuales con botón eliminar
- Formulario para agregar nueva categoría

### Commit sugerido

```bash
git add app.py templates/config.html templates/base.html database.py
git commit -m "feat(config): panel de configuración del sistema y categorías - Paso 17 v1.7.0"
git tag v1.7.0
```

---

---

## PASO 18 — Historial de ventas 📜

**Versión objetivo:** `v1.8.0`  
**Prioridad:** 🟠 Media — Muy pedido en negocios reales. Permite auditar ventas pasadas y reimprimir tickets.

### Problema a resolver

Nexar Tienda genera tickets al finalizar ventas, pero no tiene una vista para **navegar el historial de ventas pasadas**. El único acceso es por URL directa si se conoce el ID. Nexar Almacén tiene `/historial` con filtros y detalle.

### Archivos a crear/modificar

- `app.py` — agregar rutas `/historial`
- `templates/historial.html` — nuevo template
- `database.py` — agregar función `get_ventas()` con filtros

### Rutas a implementar en `app.py`

```python
# ─── HISTORIAL DE VENTAS (PASO 18) ────────────────────────────────────────

@app.route('/historial')
@permission_required('reportes.ver')
def historial():
    """Lista de todas las ventas con filtros."""
    search = request.args.get('q', '')
    fecha_desde = request.args.get('desde', '')
    fecha_hasta = request.args.get('hasta', '')
    medio_pago = request.args.get('medio', '')

    ventas = db.get_ventas_historial(
        search=search,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        medio_pago=medio_pago
    )
    total_filtro = sum(v['total'] for v in ventas)

    return render_template(
        'historial.html',
        app_version=APP_VERSION,
        usuario=session['user'],
        ventas=ventas,
        search=search,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        medio_pago=medio_pago,
        total_filtro=total_filtro
    )

@app.route('/historial/<int:vid>')
@permission_required('reportes.ver')
def historial_detalle(vid):
    """Detalle de una venta (reimpresión de ticket)."""
    venta = db.q("SELECT * FROM ventas WHERE id=?", (vid,), fetchone=True)
    if not venta:
        flash('❌ Venta no encontrada.', 'danger')
        return redirect(url_for('historial'))
    detalle = db.get_venta_detalle(vid)
    cfg = db.get_config()
    return render_template('ticket.html', venta=venta, detalle=detalle, cfg=cfg)
```

### Función a agregar en `database.py`

```python
def get_ventas_historial(self, search='', fecha_desde='', fecha_hasta='', medio_pago=''):
    """Retorna ventas filtradas por búsqueda, fecha y medio de pago."""
    params = []
    condiciones = []

    if search:
        condiciones.append("(v.id LIKE ? OR c.nombre LIKE ?)")
        params += [f'%{search}%', f'%{search}%']
    if fecha_desde:
        condiciones.append("v.fecha >= ?")
        params.append(fecha_desde)
    if fecha_hasta:
        condiciones.append("v.fecha <= ?")
        params.append(fecha_hasta)
    if medio_pago:
        condiciones.append("v.medio_pago = ?")
        params.append(medio_pago)

    where = "WHERE " + " AND ".join(condiciones) if condiciones else ""

    return self.q(f"""
        SELECT v.*, c.nombre as cliente_nombre
        FROM ventas v
        LEFT JOIN clientes c ON v.cliente_id = c.id
        {where}
        ORDER BY v.id DESC
        LIMIT 500
    """, params)
```

### Estructura del template `templates/historial.html`

Debe contener:
- Barra de filtros: campo de búsqueda, fecha desde/hasta, selector de medio de pago
- Tabla con columnas: ID, Fecha, Cliente, Medio de pago, Total, acciones (ver ticket)
- Fila de totales al pie
- Paginación si hay muchos resultados

### Commit sugerido

```bash
git add app.py templates/historial.html database.py templates/base.html
git commit -m "feat(historial): listado y detalle de ventas con filtros - Paso 18 v1.8.0"
git tag v1.8.0
```

---

---

## PASO 19 — Estadísticas avanzadas y Análisis 📊

**Versión objetivo:** `v1.9.0`  
**Prioridad:** 🟡 Media — Transforma el sistema en una herramienta de inteligencia de negocio.

### Problema a resolver

El Paso 12 implementó un módulo básico de reportes en `/reportes`. Nexar Almacén tiene además `/estadisticas` (dashboard financiero anual) y `/analisis` (rentabilidad por producto y temporada). Nexar Tienda debe adaptarlos incorporando la dimensión de **temporadas**.

### Archivos a crear/modificar

- `app.py` — agregar rutas `/estadisticas` y `/analisis`
- `templates/estadisticas.html` — nuevo template con Chart.js
- `templates/analisis.html` — nuevo template
- `database.py` — agregar funciones de estadísticas

### Rutas a implementar en `app.py`

```python
import json
from datetime import date

# ─── ESTADÍSTICAS AVANZADAS (PASO 19) ─────────────────────────────────────

@app.route('/estadisticas')
@permission_required('reportes.ver')
def estadisticas():
    """Dashboard financiero anual con gráficos."""
    year = int(request.args.get('year', date.today().year))

    ventas_mes = db.get_ventas_por_mes(year)
    meses_labels = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
    ventas_vals = [ventas_mes.get(m, {}).get('total', 0) for m in range(1, 13)]
    tickets_vals = [ventas_mes.get(m, {}).get('tickets', 0) for m in range(1, 13)]

    semanas = db.get_ventas_por_semana(8)
    medios = db.get_ventas_por_medio_pago(year, date.today().month)
    temporadas = db.get_ventas_por_temporada()
    cats = db.get_ventas_por_categoria()

    return render_template(
        'estadisticas.html',
        app_version=APP_VERSION,
        usuario=session['user'],
        year=year,
        meses_labels=json.dumps(meses_labels),
        ventas_vals=json.dumps(ventas_vals),
        tickets_vals=json.dumps(tickets_vals),
        semanas=semanas,
        semanas_labels=json.dumps([s['label'] for s in semanas]),
        semanas_vals=json.dumps([s['total'] for s in semanas]),
        medios=medios,
        medios_labels=json.dumps([m['medio_pago'] for m in medios]),
        medios_vals=json.dumps([m['total'] for m in medios]),
        temporadas=temporadas,
        cats=cats,
        cats_labels=json.dumps([c['categoria'] for c in cats[:8]]),
        cats_vals=json.dumps([c['total'] for c in cats[:8]]),
    )

@app.route('/analisis')
@permission_required('reportes.ver')
def analisis():
    """Análisis de rentabilidad por producto y categoría."""
    desde = request.args.get('desde', (date.today() - timedelta(days=30)).isoformat())
    hasta = request.args.get('hasta', date.today().isoformat())

    top = db.get_top_productos(15, desde, hasta)
    bottom = db.get_bottom_productos(10)
    temporadas = db.get_ventas_por_temporada()
    rent = db.get_rentabilidad_mes()
    gastos_cat = db.q("""
        SELECT categoria, ROUND(SUM(monto), 2) as total
        FROM gastos GROUP BY categoria ORDER BY total DESC
    """)

    return render_template(
        'analisis.html',
        app_version=APP_VERSION,
        usuario=session['user'],
        top=top,
        bottom=bottom,
        temporadas=temporadas,
        rent=rent,
        gastos_cat=gastos_cat,
        fecha_desde=desde,
        fecha_hasta=hasta,
        top_labels=json.dumps([t['descripcion'][:20] for t in top]),
        top_vals=json.dumps([t['total_pesos'] for t in top])
    )
```

### Funciones a agregar en `database.py`

```python
def get_ventas_por_mes(self, year):
    """Retorna total de ventas y cantidad de tickets por mes para un año dado."""
    rows = self.q("""
        SELECT strftime('%m', fecha) as mes,
               COUNT(*) as tickets,
               ROUND(SUM(total), 2) as total
        FROM ventas
        WHERE strftime('%Y', fecha) = ?
        GROUP BY mes
    """, (str(year),))
    return {int(r['mes']): dict(r) for r in rows}

def get_ventas_por_semana(self, semanas=8):
    """Retorna ventas agrupadas por semana para las últimas N semanas."""
    rows = self.q(f"""
        SELECT strftime('%W/%Y', fecha) as label,
               ROUND(SUM(total), 2) as total,
               COUNT(*) as tickets
        FROM ventas
        WHERE fecha >= date('now', '-{semanas * 7} days')
        GROUP BY label ORDER BY label
    """)
    return [dict(r) for r in rows]

def get_ventas_por_medio_pago(self, year, mes):
    """Retorna ventas agrupadas por medio de pago para un año y mes."""
    return self.q("""
        SELECT medio_pago,
               COUNT(*) as cant,
               ROUND(SUM(total), 2) as total
        FROM ventas
        WHERE strftime('%Y', fecha) = ? AND strftime('%m', fecha) = ?
        GROUP BY medio_pago
    """, (str(year), str(mes).zfill(2)))

def get_ventas_por_temporada(self):
    """Retorna ventas agrupadas por temporada."""
    return self.q("""
        SELECT t.nombre, COUNT(v.id) as cant, ROUND(SUM(v.total), 2) as total
        FROM ventas v
        JOIN temporadas t ON v.temporada = t.nombre
        GROUP BY t.nombre ORDER BY total DESC
    """)

def get_ventas_por_categoria(self):
    """Retorna ventas agrupadas por categoría de producto."""
    return self.q("""
        SELECT p.categoria, ROUND(SUM(vd.subtotal), 2) as total
        FROM venta_detalle vd
        JOIN productos p ON vd.producto_id = p.id
        GROUP BY p.categoria ORDER BY total DESC
    """)

def get_top_productos(self, limit=15, desde='', hasta=''):
    """Retorna los productos más vendidos en un rango de fechas."""
    params = []
    condicion = ""
    if desde and hasta:
        condicion = "WHERE v.fecha BETWEEN ? AND ?"
        params = [desde, hasta]
    return self.q(f"""
        SELECT p.descripcion, p.categoria,
               SUM(vd.cantidad) as unidades,
               ROUND(SUM(vd.subtotal), 2) as total_pesos
        FROM venta_detalle vd
        JOIN ventas v ON vd.venta_id = v.id
        JOIN productos p ON vd.producto_id = p.id
        {condicion}
        GROUP BY p.id ORDER BY total_pesos DESC LIMIT ?
    """, params + [limit])

def get_bottom_productos(self, limit=10):
    """Retorna los productos con menor movimiento."""
    return self.q("""
        SELECT p.descripcion, p.categoria,
               COALESCE(SUM(vd.cantidad), 0) as unidades
        FROM productos p
        LEFT JOIN venta_detalle vd ON p.id = vd.producto_id
        WHERE p.activo = 1
        GROUP BY p.id ORDER BY unidades ASC LIMIT ?
    """, (limit,))

def get_rentabilidad_mes(self):
    """Retorna rentabilidad de los últimos 6 meses."""
    return self.q("""
        SELECT strftime('%Y-%m', v.fecha) as mes,
               ROUND(SUM(v.total), 2) as ingresos,
               ROUND(SUM(vd.cantidad * p.precio_costo), 2) as costo
        FROM ventas v
        JOIN venta_detalle vd ON v.id = vd.venta_id
        JOIN productos p ON vd.producto_id = p.id
        WHERE v.fecha >= date('now', '-6 months')
        GROUP BY mes ORDER BY mes
    """)
```

### Gráficos en los templates (Chart.js desde CDN)

```html
<!-- Agregar en la sección head o al final del body -->
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<!-- Ejemplo: gráfico de barras de ventas mensuales -->
<canvas id="chartVentasMes"></canvas>
<script>
new Chart(document.getElementById('chartVentasMes'), {
    type: 'bar',
    data: {
        labels: {{ meses_labels|safe }},
        datasets: [{
            label: 'Ventas ($)',
            data: {{ ventas_vals|safe }},
            backgroundColor: '#1e3a5f'
        }]
    }
});
</script>
```

### Commit sugerido

```bash
git add app.py templates/estadisticas.html templates/analisis.html database.py templates/base.html
git commit -m "feat(estadisticas): dashboard financiero y análisis de rentabilidad - Paso 19 v1.9.0"
git tag v1.9.0
```

---

---

## PASO 20 — Exportación de catálogo (Excel y PDF) 📤

**Versión objetivo:** `v1.10.0`  
**Prioridad:** 🟡 Media — Muy útil en tiendas de regalos para generar listas de precios para clientes.

### Problema a resolver

No hay forma de exportar el catálogo de productos. Nexar Almacén puede generar listas en `.xlsx` y `.pdf`. Para una tienda de regalos es habitual enviar listas de precios a clientes mayoristas o imprimir catálogos por temporada.

### Dependencias a agregar en `requirements.txt`

```
openpyxl>=3.1.0
reportlab>=4.0.0
```

### Rutas a implementar en `app.py`

```python
# ─── EXPORTACIÓN DE PRODUCTOS (PASO 20) ───────────────────────────────────

@app.route('/productos/exportar/excel')
@admin_required
def exportar_excel():
    """Exporta el catálogo de productos a Excel."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from io import BytesIO

    productos = db.get_catalogo_export()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Catálogo'

    # Encabezados
    headers = ['Código', 'Descripción', 'Categoría', 'Precio c/IVA', 'Stock', 'Estado']
    header_fill = PatternFill('solid', fgColor='1e3a5f')
    header_font = Font(bold=True, color='FFFFFF')

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    # Datos
    for row_num, p in enumerate(productos, 2):
        ws.cell(row=row_num, column=1, value=p['codigo'] or '')
        ws.cell(row=row_num, column=2, value=p['descripcion'])
        ws.cell(row=row_num, column=3, value=p['categoria'])
        ws.cell(row=row_num, column=4, value=p['precio_venta'])
        ws.cell(row=row_num, column=5, value=p['stock_actual'])
        ws.cell(row=row_num, column=6, value='Activo' if p['activo'] else 'Inactivo')

    # Ajuste de columnas
    ws.column_dimensions['B'].width = 40
    ws.column_dimensions['C'].width = 25

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'catalogo_{date.today().isoformat()}.xlsx'
    )

@app.route('/productos/exportar/pdf')
@admin_required
def exportar_pdf():
    """Exporta una lista de precios en PDF."""
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from io import BytesIO

    productos = db.get_catalogo_export()
    cfg = db.get_config()
    buffer = BytesIO()

    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    # Título
    elements.append(Paragraph(cfg.get('negocio_nombre', 'Nexar Tienda'), styles['Title']))
    elements.append(Paragraph(f"Lista de Precios — {date.today().strftime('%d/%m/%Y')}", styles['Normal']))
    elements.append(Spacer(1, 20))

    # Tabla de productos
    data = [['Descripción', 'Categoría', 'Precio']]
    for p in productos:
        if p['activo']:
            data.append([p['descripcion'], p['categoria'], f"${p['precio_venta']:.2f}"])

    tabla = Table(data, colWidths=[280, 150, 80])
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f4f8')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
    ]))
    elements.append(tabla)
    doc.build(elements)

    buffer.seek(0)
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'lista_precios_{date.today().isoformat()}.pdf'
    )
```

### Función a agregar en `database.py`

```python
def get_catalogo_export(self):
    """Retorna todos los productos activos para exportación."""
    return self.q("""
        SELECT codigo, descripcion, categoria, precio_venta,
               stock_actual, activo
        FROM productos
        ORDER BY categoria, descripcion
    """)
```

### Botones a agregar en `templates/productos.html`

```html
<!-- En la barra de acciones de la lista de productos -->
<div class="dropdown">
  <button class="btn btn-outline-secondary dropdown-toggle" data-bs-toggle="dropdown">
    <i class="fas fa-file-export me-1"></i>Exportar
  </button>
  <ul class="dropdown-menu">
    <li>
      <a class="dropdown-item" href="{{ url_for('exportar_excel') }}">
        <i class="fas fa-file-excel me-2 text-success"></i>Excel (.xlsx)
      </a>
    </li>
    <li>
      <a class="dropdown-item" href="{{ url_for('exportar_pdf') }}">
        <i class="fas fa-file-pdf me-2 text-danger"></i>Lista de precios (PDF)
      </a>
    </li>
  </ul>
</div>
```

### Commit sugerido

```bash
pip install openpyxl reportlab
git add app.py database.py templates/productos.html requirements.txt
git commit -m "feat(exportar): catálogo a Excel y lista de precios PDF - Paso 20 v1.10.0"
git tag v1.10.0
```

---

---

## PASO 21 — Páginas informativas ℹ️

**Versión objetivo:** `v1.11.0`  
**Prioridad:** 🟢 Baja — Mejora la experiencia y la imagen profesional del sistema.

### Problema a resolver

No existen páginas de ayuda, información de la aplicación ni registro de cambios. Nexar Almacén tiene `/acerca`, `/ayuda` y `/changelog`. Son rápidas de implementar y agregan valor percibido.

### Rutas a implementar en `app.py`

```python
# ─── PÁGINAS INFORMATIVAS (PASO 21) ────────────────────────────────────────

@app.route('/acerca')
@login_required
def acerca():
    """Información sobre la versión y el sistema."""
    return render_template(
        'acerca.html',
        app_version=APP_VERSION,
        usuario=session['user']
    )

@app.route('/ayuda')
@login_required
def ayuda():
    """Guía de uso básica del sistema."""
    return render_template(
        'ayuda.html',
        app_version=APP_VERSION,
        usuario=session['user']
    )

@app.route('/changelog')
@login_required
def changelog():
    """Historial de versiones del sistema."""
    # Leer CHANGELOG.md y pasarlo al template
    import pathlib
    changelog_path = pathlib.Path(__file__).parent / 'CHANGELOG.md'
    contenido = changelog_path.read_text(encoding='utf-8') if changelog_path.exists() else ''
    return render_template(
        'changelog.html',
        app_version=APP_VERSION,
        usuario=session['user'],
        contenido=contenido
    )
```

### Templates a crear

**`templates/acerca.html`** — contenido sugerido:
- Logo/ícono de la aplicación
- Nombre: Nexar Tienda
- Versión actual (`{{ app_version }}`)
- Descripción breve del sistema
- Datos del desarrollador / contacto
- Tecnologías usadas (Python, Flask, SQLite, Bootstrap)

**`templates/ayuda.html`** — contenido sugerido:
- Sección por módulo (POS, Stock, Clientes, Caja, etc.)
- Preguntas frecuentes
- Atajos de teclado del POS
- Cómo hacer un respaldo manual

**`templates/changelog.html`** — contenido sugerido:
- Renderizar el contenido del `CHANGELOG.md` usando la librería `markdown` de Python, o mostrarlo como texto preformateado

```python
# Para renderizar Markdown en el template (agregar a requirements.txt):
# markdown>=3.5.0

import markdown
contenido_html = markdown.markdown(contenido)
# Pasar contenido_html al template y usar: {{ contenido_html|safe }}
```

### Agregar al sidebar/footer en `base.html`

```html
<!-- Al pie del sidebar o en el menú de usuario -->
<li class="nav-item"><a class="nav-link" href="{{ url_for('ayuda') }}">
  <i class="fas fa-question-circle me-2"></i>Ayuda
</a></li>
<li class="nav-item"><a class="nav-link" href="{{ url_for('changelog') }}">
  <i class="fas fa-list-alt me-2"></i>Novedades
</a></li>
<li class="nav-item"><a class="nav-link" href="{{ url_for('acerca') }}">
  <i class="fas fa-info-circle me-2"></i>Acerca de
</a></li>
```

### Commit sugerido

```bash
git add app.py templates/acerca.html templates/ayuda.html templates/changelog.html templates/base.html
git commit -m "feat(info): páginas de ayuda, changelog y acerca de - Paso 21 v1.11.0"
git tag v1.11.0
```

---

---

## PASO 22 — Apagado controlado del sistema 🛑

**Versión objetivo:** `v1.12.0`  
**Prioridad:** 🟢 Baja (opcional) — Importante para el uso offline/local. Permite cerrar el servidor Flask de forma segura desde la interfaz.

### Problema a resolver

Nexar Tienda corre localmente como servidor Flask. El usuario normalmente cierra la terminal para detenerlo, lo que puede corromper transacciones en curso. Nexar Almacén tiene un botón "Cerrar sistema" que invalida sesiones y detiene el proceso de forma controlada.

### Archivos a modificar

- `app.py` — agregar rutas `/apagar` y `/apagar_rapido`
- `templates/apagado.html` — pantalla de confirmación de apagado
- `templates/base.html` — botón en el menú de admin
- `templates/login.html` — botón de apagado rápido

### Rutas a implementar en `app.py`

```python
import signal, threading

# ─── APAGADO CONTROLADO (PASO 22) ─────────────────────────────────────────

@app.route('/apagar', methods=['POST'])
@admin_required
def apagar_sistema():
    """
    Apagado controlado:
    1. Invalida todas las sesiones activas.
    2. Limpia la sesión del usuario actual.
    3. Detiene el servidor Flask de forma segura.
    """
    try:
        db.set_config({'sessions_invalidated_at': datetime.now().isoformat()})
    except Exception:
        pass
    session.clear()

    def _shutdown():
        import time
        time.sleep(1.5)  # Dar tiempo para que se renderice la respuesta
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=_shutdown, daemon=True).start()
    return render_template('apagado.html')

@app.route('/apagar_rapido', methods=['POST'])
def apagar_rapido():
    """Apagado desde la pantalla de login (sin requerir sesión activa)."""
    try:
        db.set_config({'sessions_invalidated_at': datetime.now().isoformat()})
    except Exception:
        pass
    session.clear()

    def _shutdown():
        import time
        time.sleep(1.5)
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=_shutdown, daemon=True).start()
    return render_template('apagado.html')
```

### Template `templates/apagado.html`

```html
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Sistema cerrado — Nexar Tienda</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: #1e3a5f; color: white; }
        .container { margin-top: 20vh; text-align: center; }
    </style>
</head>
<body>
    <div class="container">
        <i class="fas fa-power-off fa-4x mb-4"></i>
        <h1>Sistema cerrado</h1>
        <p class="lead">Nexar Tienda se ha detenido correctamente.</p>
        <p class="text-muted">Podés cerrar esta ventana del navegador.</p>
    </div>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</body>
</html>
```

### Botón a agregar en `templates/base.html`

```html
<!-- Solo visible para usuarios con rol Administrador -->
{% if usuario.rol == 'Administrador' %}
<form method="POST" action="{{ url_for('apagar_sistema') }}"
      onsubmit="return confirm('¿Cerrar el sistema? Se cerrarán todas las sesiones activas.')">
    <button class="btn btn-sm btn-outline-danger w-100">
        <i class="fas fa-power-off me-1"></i>Cerrar sistema
    </button>
</form>
{% endif %}
```

### Commit sugerido

```bash
git add app.py templates/apagado.html templates/base.html templates/login.html
git commit -m "feat(apagado): cierre controlado del servidor Flask - Paso 22 v1.12.0"
git tag v1.12.0
```

---

---

## 📋 Resumen general del roadmap

| Paso | Módulo | Versión | Prioridad | Archivos principales |
|------|--------|---------|-----------|----------------------|
| **15** | Temporadas: rutas CRUD | v1.5.0 | 🔴 Alta | `app.py`, `database.py` |
| **16** | Respaldo: panel UI | v1.6.0 | 🔴 Alta | `app.py`, `respaldo.html` |
| **17** | Configuración del sistema | v1.7.0 | 🟠 Media-Alta | `app.py`, `config.html`, `database.py` |
| **18** | Historial de ventas | v1.8.0 | 🟠 Media | `app.py`, `historial.html`, `database.py` |
| **19** | Estadísticas avanzadas | v1.9.0 | 🟡 Media | `app.py`, `estadisticas.html`, `analisis.html` |
| **20** | Exportación Excel / PDF | v1.10.0 | 🟡 Media | `app.py`, `database.py` |
| **21** | Páginas informativas | v1.11.0 | 🟢 Baja | `app.py`, 3 templates |
| **22** | Apagado controlado | v1.12.0 | 🟢 Baja | `app.py`, `apagado.html` |

### Orden de ejecución recomendado

```
15 → 16 → 17 → 18 → 19 → 20 → 21 → 22
```

Los primeros cuatro pasos son los que **más valor aportan al negocio** y tienen mayor impacto en la experiencia diaria del usuario. Los últimos dos son mejoras de calidad y pulido final.

---

*Documento generado el 13/04/2026 — Nexar Tienda v1.20.0*  
*Referencia: Nexar Almacén como base estructural*
