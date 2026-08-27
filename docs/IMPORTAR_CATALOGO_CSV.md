# Importar catálogo CSV

Corrección operativa: la cookie guarda solo un identificador opaco; el plan se
conserva temporalmente en SQLite, asociado al usuario, durante 15 minutos y se
consume una sola vez. Los productos simples requieren código de barras para
mantener identidad persistente; un SKU simple aislado se rechaza. La
importación fija el stock objetivo y solo registra movimiento cuando cambia.
Cada preview invalida la anterior del mismo usuario. Todo intento de
confirmación consume el plan antes de persistir; si el lote falla, debe crearse
una preview nueva. En simples, los campos comerciales informados actualizan el
producto; los campos vacíos se conservan y el cero numérico actualiza a cero.
La importación conserva mínimos y máximos locales de stock.
Stock ausente o vacío conserva el valor local; `0` explícito establece cero.
Visibilidad ausente o vacía conserva el estado local; `SI` activa y `NO`
desactiva. Los valores de visibilidad no reconocidos se rechazan en preview.

Nexar Comercio admite el CSV exportado por Tiendanube. El adaptador reconoce
`Identificador de URL`, `Nombre`, categorías, hasta tres pares de propiedad y
valor, precio, costo, stock, SKU, código de barras y visibilidad. Esos nombres
son exclusivos del adaptador: el catálogo interno usa productos, atributos,
valores y variantes neutrales.

Tiendanube no informa IVA en este CSV. Antes de importar, Nexar usa la
alícuota predeterminada configurada localmente en Configuración del Sistema.
Se persiste en el producto nuevo, sin agregar columnas ni semántica fiscal al
formato de Tiendanube; las actualizaciones no cambian el IVA existente.

La vista previa no escribe datos. Agrupa las filas por identificador de URL y
ofrece confirmación explícita; el servidor conserva solamente el plan validado
en la sesión. La confirmación es atómica: si falla una persistencia, no queda
ningún producto, variante o stock parcial.

Los grupos con propiedades se importan como variantes. Los productos sin
propiedades se mantienen en el modo legacy. Una actualización solo se permite
si los SKU o códigos de barras de variantes identifican inequívocamente un único
producto existente. Una coincidencia con un producto legacy, una coincidencia
ambigua o códigos duplicados se rechaza para resolución manual. Por eso repetir
un archivo de variantes con los mismos SKU actualiza sus combinaciones en vez de
duplicarlas.

Límites: 5 MB, 2.000 filas, 500 productos, 2.000 variantes en total, 100 por
producto y 2.000 caracteres por campo. Se rechazan archivos vacíos, encabezados
incompatibles, filas malformadas, fórmulas iniciales, valores no finitos y
números negativos. El archivo se lee en memoria y no se almacena.

Nexar ignora imágenes, peso, dimensiones, etiquetas, SEO, envío y campos de
marketing del CSV. No implementa OAuth, API, webhooks ni sincronización.
