# Importar catálogo CSV

Nexar Comercio admite el CSV exportado por Tiendanube. El adaptador reconoce
`Identificador de URL`, `Nombre`, categorías, hasta tres pares de propiedad y
valor, precio, costo, stock, SKU, código de barras y visibilidad. Esos nombres
son exclusivos del adaptador: el catálogo interno usa productos, atributos,
valores y variantes neutrales.

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
