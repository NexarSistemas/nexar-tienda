# Contrato del catálogo universal

- Versión: `1.0`
- Estado: aceptado
- Issue: [#143](https://github.com/NexarSistemas/nexar-tienda/issues/143)
- Épica: [#142](https://github.com/NexarSistemas/nexar-tienda/issues/142)

## 1. Propósito y alcance

Este documento define el contrato estable del dominio de catálogo de Nexar
Comercio. Es neutral respecto de canales externos y sirve como límite común
para persistencia, servicios, UI, importadores y futuros adaptadores.

El contrato describe semántica, relaciones, fuentes de verdad e invariantes.
Las adopciones operativas se habilitan por Issue y deben conservar estos
límites sin extenderse a importación, exportación o sincronización salvo alcance
explícito.

Las tablas y campos citados describen la implementación disponible al publicar
esta versión. Las entidades conceptuales que todavía no tienen persistencia
propia no autorizan a crearla fuera del Issue correspondiente.

## 2. Vocabulario

### 2.1 Producto base

Representa la identidad comercial compartida de un artículo: descripción,
marca, categoría, unidad, tratamiento impositivo, estado e imagen principal.
En la persistencia actual corresponde a `productos`.

`codigo_interno` identifica al producto legacy dentro de Nexar Comercio. No es
un identificador de un proveedor externo ni reemplaza al SKU de una variante.

### 2.2 Atributo y valor

Un atributo es una dimensión configurable que puede diferenciar variantes. Un
valor es una opción perteneciente a un atributo. Actualmente corresponden a
`producto_atributos` y `producto_atributo_valores`.

Los nombres y valores son datos configurables. El dominio no conoce atributos
concretos ni condiciona comportamiento por rubro, nombre o posición.

### 2.3 Variante

Es un ítem vendible explícito perteneciente a un producto base y definido por
cero o más pares atributo/valor. Actualmente corresponde a
`producto_variantes`; su composición se registra en
`producto_variante_valores`.

`combination_key` es una clave técnica determinista construida con los pares
atributo/valor ordenados. No es una etiqueta comercial ni un identificador
externo.

Una variante sin pares puede representar la variante predeterminada, pero no
se crea implícitamente para productos legacy.

### 2.4 SKU y código de barras

- El SKU es un identificador interno opcional del ítem vendible. La
  implementación actual lo almacena en `producto_variantes.sku`.
- El código de barras es un identificador escaneable opcional del ítem
  vendible. Puede residir en `productos.codigo_barras` para el flujo legacy o
  en `producto_variantes.codigo_barras` para una variante explícita.
- `productos.codigo_interno` conserva su función de identidad técnica legacy y
  no debe reinterpretarse automáticamente como SKU o código externo.

### 2.5 Precio y costo

El producto base conserva `costo` y `precio_venta` como valores legacy y como
valores de respaldo. Una variante puede definir `costo`, `precio` y
`precio_promocional`.

Para lectura de una variante:

1. si el valor propio de costo o precio no es nulo, prevalece;
2. si es nulo, se hereda el valor correspondiente del producto base;
3. el precio promocional solo existe cuando está definido explícitamente en la
   variante.

La herencia es una regla de resolución, no una copia ni una sincronización
bidireccional.

### 2.6 Stock

El stock pertenece exactamente a un ítem vendible:

- producto legacy sin variantes operativas: fila única en `stock`;
- variante operativa: fila única en `stock_variantes`.

Los límites mínimo y máximo siguen la misma titularidad que el stock actual.
Un total por producto con variantes es una proyección calculada a partir de sus
variantes, nunca una segunda fuente editable.

### 2.7 Categoría

La categoría clasifica al producto base, no a cada variante. La implementación
actual conserva `productos.categoria` como texto y dispone del catálogo
`categorias`. Mientras no exista una migración específica, el texto persistido
en el producto es el valor efectivo y `categorias` provee opciones de gestión.

No se infiere comportamiento de variantes, stock, precios o atributos desde el
nombre de una categoría.

### 2.8 Imagen

La imagen describe visualmente un producto o, en una extensión futura, una
variante. Hoy la única fuente persistida es `productos.imagen`, que actúa como
imagen principal y respaldo visual de todas sus variantes.

El orden de galerías, imágenes por variante, almacenamiento, formatos y
publicación por canal quedan reservados. Una URL o ruta externa no constituye
por sí sola identidad de catálogo.

### 2.9 Canal e identificador externo

Un canal es un sistema externo capaz de representar el catálogo. Un
identificador externo solo tiene significado dentro de la combinación:

`canal + tipo de entidad + entidad interna + identificador externo`

La identidad interna de Nexar nunca depende de un identificador externo. El
campo `external_id` presente en entidades de variantes se considera una
compatibilidad transitoria: no expresa canal, no es fuente de verdad y no debe
usarse para agregar integraciones nuevas. El modelo persistente multicanal y
sus restricciones quedan reservados para los Issues de adaptadores.

Los formatos CSV, JSON, estados y reglas de cada proveedor pertenecen
exclusivamente a adaptadores externos.

## 3. Relaciones

```text
Categoría 1 ── * Producto base
Producto base 1 ── * Variante
Variante * ── * Valor de atributo
Atributo 1 ── * Valor de atributo
Producto legacy 1 ── 1 Stock legacy
Variante 1 ── 1 Stock de variante
Producto base 1 ── 0..* Imagen
Producto/Variante 1 ── 0..* Identidad externa por canal
```

En la implementación actual, imagen e identidad externa multicanal no poseen
las colecciones conceptuales completas indicadas por el contrato.

## 4. Fuente de verdad por dato

| Dato | Fuente de verdad actual | Regla |
| --- | --- | --- |
| Identidad y datos comunes | `productos` | Una fila por producto base |
| Categoría efectiva | `productos.categoria` | `categorias` ofrece valores; no sustituye el texto sin migración |
| Imagen principal | `productos.imagen` | Respaldo para todas las variantes |
| Atributos | `producto_atributos` | Catálogo reutilizable y neutral |
| Valores | `producto_atributo_valores` | Únicos por atributo normalizado |
| Composición de variante | `producto_variante_valores` | Un valor como máximo por atributo y variante |
| Identidad de combinación | `producto_variantes.combination_key` | Única dentro del producto |
| SKU de variante | `producto_variantes.sku` | Opcional y único cuando está informado |
| Código de barras | Producto legacy o variante | Único globalmente entre ítems vendibles |
| Costo/precio legacy | `productos` | Efectivo para producto simple y respaldo de variante |
| Costo/precio de variante | `producto_variantes` | Valor propio si no es nulo; de lo contrario hereda |
| Stock de producto simple | `stock` | Única fuente para el flujo legacy |
| Stock de variante | `stock_variantes` | Única fuente al adoptar operación por variante |
| Identidad externa | Asociación futura por canal | `external_id` actual no define un contrato multicanal |

## 5. Invariantes del dominio

1. Toda variante pertenece a exactamente un producto base.
2. Una variante tiene como máximo un valor por atributo.
3. La combinación normalizada de valores es única dentro del producto.
4. SKU informado y código de barras informado identifican como máximo un ítem
   vendible; no puede haber ambigüedad entre producto legacy y variante.
5. Stock, costo y precio deben ser números finitos; el stock no puede ser
   negativo salvo que una política futura lo autorice explícitamente.
6. Crear, editar o eliminar una variante y sus relaciones debe ser atómico.
7. Desactivar una entidad no borra historial ni reasigna referencias.
8. Un identificador externo nunca reemplaza el identificador interno.
9. El dominio no contiene condicionales por proveedor, canal, rubro, atributo o
   valor concreto.
10. Un movimiento de inventario afecta exactamente una fuente de stock.
11. Los valores heredados se resuelven al leer; no se mantienen mediante
    escrituras duplicadas.
12. Los productos legacy continúan siendo válidos sin crear variantes
    artificiales.

## 6. Compatibilidad legacy y transición de stock

La ausencia de variantes explícitas significa que el producto base es el ítem
vendible. Los módulos que todavía no adoptaron variantes continúan usando
`productos` y `stock` hasta que sus Issues de adopción sean implementados.

La mera existencia de una variante creada por la UI actual no cambia
automáticamente esos flujos. Cada módulo deberá migrar al resolvedor común de
ítem vendible en la fase que le corresponde.

La transición a operación por variantes debe respetar esta política:

1. clasificar el producto en modo legacy o modo por variantes mediante una
   decisión explícita y transaccional;
2. en modo legacy, leer y escribir solo `stock`;
3. en modo por variantes, leer y escribir solo `stock_variantes`;
4. mostrar cualquier total del producto como suma calculada de variantes;
5. no mantener un espejo editable ni descontar ambas tablas;
6. definir en #145 cómo se asigna el stock legacy al activar el modo por
   variantes, con validación, auditoría y rollback.

Este contrato no selecciona una estrategia de reparto del stock existente
porque hacerlo sin interacción o evidencia podría alterar inventario.

### 6.1 POS y lector

En el POS, el lector y la búsqueda trabajan con un único ítem vendible:

- producto legacy activo cuando `stock_modo` no es `variantes`;
- variante activa cuando el producto opera con `stock_modo='variantes'`.

Un código exacto, SKU o código de barras puede agregar directamente solo si
resuelve una opción única. Si el código del producto base corresponde a varias
variantes activas, el POS debe informar ambigüedad y pedir selección manual. La
venta guarda `ventas_detalle.variante_id` y `ventas_detalle.stock_fuente`, y el
descuento o reposición de stock se ejecuta dentro de la transacción de venta o
anulación mediante `services/inventory.py`.

## 7. Responsabilidades por capa

### Dominio

Define entidades, identidad, herencia, invariantes y resolución del ítem
vendible. No conoce SQLite, formularios ni formatos externos.

### Persistencia

Garantiza relaciones, unicidad, transacciones y compatibilidad de datos. No
decide presentación, mapeos de proveedores ni políticas comerciales ocultas.

### Servicios de aplicación

Orquestan casos de uso, aplican el contrato y ofrecen una única resolución de
producto/variante a los módulos consumidores. No duplican reglas en rutas.

### UI

Captura intención, muestra combinaciones y errores y exige confirmación en
operaciones destructivas. No calcula claves técnicas ni escribe tablas
directamente.

### Importadores y exportadores

Traducen archivos a y desde comandos o representaciones del dominio, validan
antes de persistir y reportan conflictos. No filtran columnas o semántica de un
proveedor al núcleo.

### Adaptadores externos

Encapsulan autenticación, transporte, paginación, límites, reintentos, formatos
y mapeos por canal. Traducen identidades externas sin convertirlas en identidad
interna ni definir por sí mismos la fuente de verdad.

## 8. Extensibilidad por rubro

Los perfiles de atributos por rubro son datos persistidos que sugieren un
conjunto reutilizable de atributos para una operación concreta. Un perfil tiene
nombre, descripción, estado y orden; se asocia a atributos del catálogo mediante
relaciones configurables y puede activarse manualmente para un rubro del
negocio.

La separación de responsabilidades es:

- perfil: agrupación reusable y editable de atributos sugeridos;
- rubro: contexto operativo seleccionado para el negocio;
- capacidades del negocio: reglas transversales como unidades, fraccionamiento
  o módulos activos;
- atributos: dimensiones configurables (`producto_atributos`) reutilizables por
  productos y variantes;
- variantes: combinaciones explícitas de valores de atributos para un producto.

Activar un perfil no crea variantes ni cambia el modo de stock del producto. El
perfil solo facilita atributos disponibles; no bloquea atributos adicionales ni
combinaciones válidas. Desactivar o editar un perfil no elimina atributos,
valores ni variantes ya usados.

La gestión de variantes puede consumir el perfil activo como sugerencia visual
para acelerar la carga manual. Esa sugerencia no copia atributos al producto, no
genera combinaciones, no cambia `stock_modo` y no reemplaza el catálogo global
de atributos reutilizables.

Agregar o modificar un perfil no debe requerir cambiar Python, esquema ni este
contrato. Un rubro sin perfil puede crear atributos manualmente y mantiene un
comportamiento neutro.

Ejemplos de atributos pertenecen a datos iniciales o documentación de usuario,
nunca a enums, columnas dedicadas o ramas condicionales del dominio.

## 9. Decisiones reservadas

- #144: edición, activación, desactivación, eliminación e integridad de
  variantes.
- #145: adopción del stock por variante, movimientos, modo operativo y
  transición auditada desde stock legacy.
- #146: selección y costo de variante en compras.
- #147: resolución de ítem vendible en POS, lector, ventas y reversión.
- #148: persistencia y activación de perfiles configurables por rubro.
- #149: generación atómica de combinaciones.
- #150: adaptador de importación CSV.
- #151: adaptador de exportación CSV.
- #152: asociación multicanal y adaptador API.
- #153: dirección de sincronización, marcas, idempotencia y fuente de verdad
  remota por campo.
- #154: detección y resolución de conflictos por entidad y campo.

También quedan reservados el esquema de imágenes múltiples, la generación de
SKU/códigos, las políticas de promociones, unidades monetarias, listas de
precios y cualquier migración de datos.

## 10. Criterio de evolución

Los cambios compatibles pueden aclarar ejemplos o añadir campos opcionales sin
alterar invariantes. Cambiar identidad, titularidad del stock, precedencia de
precios o límites entre capas requiere una nueva versión del contrato y una
migración explícita cuando afecte datos persistidos.
