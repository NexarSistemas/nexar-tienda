/*
  Nexar Tienda — utils.js
  Funciones utilitarias compartidas entre templates
  Se completará según se necesite
*/

// Formatea un número como precio argentino: $ 1.234,50
function fmtARS(v) {
  return '$ ' + parseFloat(v || 0).toLocaleString('es-AR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}
