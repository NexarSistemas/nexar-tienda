# Exportar catálogo CSV para Tiendanube

La acción **Exportar > CSV para Tiendanube** genera un archivo CSV delimitado
por comas, UTF-8 con BOM y compatible con Excel. Es un adaptador de salida: no
escribe ni modifica productos, variantes, stock ni identificadores internos.

## Formato soportado

La fixture versionada
[`../tests/fixtures/tiendanube_catalog_csv_v2026_07.csv`](../tests/fixtures/tiendanube_catalog_csv_v2026_07.csv)
conserva la cabecera de la plantilla argentina documentada por Tiendanube en
julio de 2026. Se emiten las 30 columnas de la plantilla; Nexar completa:

- `Identificador de URL` estable `nexar-{id_producto}`, independiente del
  nombre editable del producto.
- `Nombre`, `Categorías` y `Marca` del producto base. `Producto físico` queda
  vacío porque Nexar no modela ese dato.
- Hasta tres pares `Nombre de propiedad` / `Valor de propiedad` por variante.
- `Precio`, `Precio promocional`, `Costo`, `Stock`, `SKU` y `Código de barras`.
- `Mostrar en tienda=SI` para productos activos.

Las columnas que Nexar no modela (peso, dimensiones, envío sin cargo,
descripción extendida, tags, SEO, MPN, sexo y rango de edad) se mantienen
vacías. Tiendanube requiere un identificador de URL compartido por todas las
variantes de un producto y una fila por combinación; el adaptador aplica ambas
reglas. La referencia oficial es [Cómo completar el Excel de carga masiva de
productos](https://ayuda.tiendanube.com/122710-importar-y-exportar-productos/como-completar-el-excel-de-carga-masiva-de-productos).

## Productos, variantes y filtros

Se exportan los productos activos visibles para el rubro actual. Los filtros de
búsqueda, categoría y proveedor activos en el catálogo se trasladan a la
descarga. En productos con variantes se exporta una fila por variante activa;
las columnas comunes del producto se escriben en la primera fila, como indica
la plantilla de Tiendanube. Los productos con `stock_modo='variantes'` se
exportan por variante activa. Los productos legacy, aun con variantes
configuradas, usan precio, costo, código de barras y stock de
`productos`/`stock`; un `stock_modo` desconocido rechaza la descarga.

Una variante inactiva no se publica. Si un producto con variantes no tiene
ninguna variante activa, o una variante activa no puede representarse (sin
atributos, más de tres atributos, atributos repetidos, números no finitos o
precio promocional no menor al precio), la descarga se rechaza y se informa el
motivo; no se omite silenciosamente ningún registro inválido.

Los decimales se emiten con punto y sin notación científica, los valores vacíos
permanecen vacíos, las tildes y saltos de línea se codifican correctamente por
el escritor CSV. Las categorías escapan `\\`, `,` y `>` conforme al contrato de
Tiendanube, y los
valores controlados por usuarios que empiezan con `=`, `+`, `-` o `@` se
protegen para evitar fórmulas de planilla. El archivo se entrega como
`catalogo_tiendanube_YYYYMMDD.csv`. Antes de iniciar la respuesta HTTP, el
exportador fija una única instantánea de lectura, valida y escribe el CSV en un
temporal con derrame a disco; así no entrega archivos parciales ni retiene
catálogos grandes en memoria.

## Limitaciones

Esta fase no incluye API, OAuth, webhooks ni sincronización automática. La
aplicación ya dispone de su importador CSV independiente; la prueba de ida y
vuelta cubre los campos compartidos por ese adaptador, incluido el precio
promocional de variantes. No se exportan imágenes ni datos no existentes en el dominio
interno.
