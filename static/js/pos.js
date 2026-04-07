// Nexar Tienda - Punto de Venta JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Elementos DOM
    const busquedaInput = document.getElementById('busqueda');
    const btnBuscar = document.getElementById('btn-buscar');
    const resultadosDiv = document.getElementById('resultados');
    const carritoItemsDiv = document.getElementById('carrito-items');
    const carritoTotalDiv = document.getElementById('carrito-total');
    const subtotalSpan = document.getElementById('subtotal');
    const totalSpan = document.getElementById('total');
    const descuentoInput = document.getElementById('descuento-adicional');
    const btnFinalizar = document.getElementById('btn-finalizar');
    const btnVaciar = document.getElementById('btn-vaciar');
    const clienteSelect = document.getElementById('cliente');
    const clienteNombreInput = document.getElementById('cliente-nombre');
    const modalCantidad = new bootstrap.Modal(document.getElementById('modal-cantidad'));
    const cantidadInput = document.getElementById('cantidad-input');
    const stockDisponibleSpan = document.getElementById('stock-disponible');
    const btnAgregarCarrito = document.getElementById('btn-agregar-carrito');

    let productoSeleccionado = null;

    // ─── FUNCIONES ──────────────────────────────────────────────────────────

    function buscarProductos(query = '') {
        fetch(`/api/buscar_productos?q=${encodeURIComponent(query)}`)
            .then(response => response.json())
            .then(data => {
                if (data.ok) {
                    mostrarResultados(data.productos);
                } else {
                    console.error('Error en búsqueda:', data.error);
                }
            })
            .catch(error => console.error('Error:', error));
    }

    function mostrarResultados(productos) {
        if (productos.length === 0) {
            resultadosDiv.innerHTML = '<div class="col-12"><p class="text-muted text-center">No se encontraron productos</p></div>';
            return;
        }

        resultadosDiv.innerHTML = productos.map(producto => `
            <div class="col-md-6 col-lg-4 mb-3">
                <div class="card h-100">
                    <div class="card-body">
                        <h6 class="card-title">${producto.descripcion}</h6>
                        <p class="card-text small text-muted">
                            Código: ${producto.codigo_interno}<br>
                            Categoría: ${producto.categoria}<br>
                            Stock: ${producto.stock_actual} ${producto.unidad}
                        </p>
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="fw-bold">${formatearARS(producto.precio_venta)}</span>
                            <button class="btn btn-primary btn-sm" onclick="agregarProducto(${producto.id}, '${producto.descripcion}', ${producto.stock_actual})">
                                <i class="fas fa-plus"></i> Agregar
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `).join('');
    }

    function agregarProducto(productoId, descripcion, stock) {
        productoSeleccionado = { id: productoId, descripcion, stock };
        cantidadInput.value = 1;
        stockDisponibleSpan.textContent = stock;
        modalCantidad.show();
    }
    
    // Exponer a nivel global para que los onclick de los resultados funcionen
    window.agregarProducto = agregarProducto;
    window.quitarDelCarrito = quitarDelCarrito;

    function agregarAlCarrito() {
        const cantidad = parseFloat(cantidadInput.value);
        if (!productoSeleccionado || cantidad <= 0 || cantidad > productoSeleccionado.stock) {
            alert('Cantidad inválida');
            return;
        }

        fetch('/api/carrito/agregar', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                producto_id: productoSeleccionado.id,
                cantidad: cantidad
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.ok) {
                actualizarCarrito(data.carrito);
                modalCantidad.hide();
                productoSeleccionado = null;
            } else {
                alert('Error: ' + data.error);
            }
        })
        .catch(error => console.error('Error:', error));
    }

    function actualizarCarrito(carrito) {
        if (carrito.length === 0) {
            carritoItemsDiv.innerHTML = '<p class="text-muted text-center">Carrito vacío</p>';
            carritoTotalDiv.classList.add('d-none');
            btnFinalizar.disabled = true;
            return;
        }

        carritoItemsDiv.innerHTML = carrito.map(item => `
            <div class="d-flex justify-content-between align-items-center mb-2 p-2 border rounded">
                <div class="flex-grow-1">
                    <div class="fw-bold">${item.descripcion}</div>
                    <small class="text-muted">${item.cantidad} x ${formatearARS(item.precio_unitario)}</small>
                </div>
                <div class="text-end">
                    <div class="fw-bold">${formatearARS(item.subtotal)}</div>
                    <button class="btn btn-sm btn-outline-danger" onclick="quitarDelCarrito(${item.producto_id})">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
        `).join('');

        const subtotal = carrito.reduce((sum, item) => sum + item.subtotal, 0);
        const descuento = parseFloat(descuentoInput.value) || 0;
        const total = Math.max(0, subtotal - descuento);

        subtotalSpan.textContent = formatearARS(subtotal);
        totalSpan.textContent = formatearARS(total);

        carritoTotalDiv.classList.remove('d-none');
        btnFinalizar.disabled = false;
    }

    function quitarDelCarrito(productoId) {
        fetch(`/api/carrito/quitar/${productoId}`, {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            if (data.ok) {
                actualizarCarrito(data.carrito);
            } else {
                alert('Error: ' + data.error);
            }
        })
        .catch(error => console.error('Error:', error));
    }

    function vaciarCarrito() {
        if (!confirm('¿Vaciar el carrito?')) return;

        fetch('/api/carrito/vaciar', {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            if (data.ok) {
                actualizarCarrito([]);
            } else {
                alert('Error: ' + data.error);
            }
        })
        .catch(error => console.error('Error:', error));
    }

    function formatearARS(valor) {
        return '$' + valor.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    // ─── EVENTOS ───────────────────────────────────────────────────────────

    // Búsqueda
    busquedaInput.addEventListener('input', function() {
        buscarProductos(this.value);
    });

    btnBuscar.addEventListener('click', function() {
        buscarProductos(busquedaInput.value);
    });

    busquedaInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            buscarProductos(this.value);
        }
    });

    // Modal cantidad
    btnAgregarCarrito.addEventListener('click', agregarAlCarrito);

    cantidadInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            agregarAlCarrito();
        }
    });

    // Carrito
    descuentoInput.addEventListener('input', function() {
        // Recargar carrito para recalcular total
        fetch('/api/carrito/agregar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ producto_id: -1, cantidad: 0 }) // Dummy request
        })
        .then(response => response.json())
        .then(data => {
            if (data.ok) {
                actualizarCarrito(data.carrito);
            }
        })
        .catch(() => {
            // Ignorar error, solo recalcular
            const carrito = JSON.parse(localStorage.getItem('carrito') || '[]');
            actualizarCarrito(carrito);
        });
    });

    btnVaciar.addEventListener('click', vaciarCarrito);

    // Cliente
    clienteSelect.addEventListener('change', function() {
        if (this.value === '0') {
            clienteNombreInput.style.display = 'none';
            clienteNombreInput.value = '';
        } else {
            clienteNombreInput.style.display = 'block';
            const option = this.options[this.selectedIndex];
            clienteNombreInput.value = option.text;
        }
    });

    // ─── INICIALIZACIÓN ────────────────────────────────────────────────────

    // Cargar carrito inicial
    fetch('/api/carrito/agregar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ producto_id: -1, cantidad: 0 })
    })
    .then(response => response.json())
    .then(data => {
        if (data.ok) {
            actualizarCarrito(data.carrito);
        }
    })
    .catch(() => {
        // Si no hay carrito en sesión, inicializar vacío
        actualizarCarrito([]);
    });

    // Búsqueda inicial vacía
    buscarProductos();
});

// ─── FUNCIONES GLOBALES ───────────────────────────────────────────────────
