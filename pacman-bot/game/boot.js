// Entorno mínimo que el doodle espera encontrar (lo daba la portada de Google).
window.google = window.google || {};
google.dom = {
  remove: function (a) { return a && a.parentNode && a.parentNode.removeChild(a); },
  append: function (a) { return document.body.appendChild(a); }
};
google.browser = { engine: { IE: false } };
google.pacManSound = false;
