// Franja "Nuevos datos" de Inicio: botón × con memoria.
// Guarda en localStorage la fecha (AAAA-MM-DD) del paquete cuyo aviso se cerró; cuando haya una
// versión más nueva (fecha mayor) la franja vuelve a aparecer. Si el JS no corre o el navegador
// bloquea localStorage, la franja simplemente se ve.
(function () {
  var aviso = document.getElementById("aviso-datos");
  if (!aviso) return;

  var CLAVE = "esbi:aviso-datos:cerrado";
  var fecha = aviso.getAttribute("data-fecha") || "";

  function leer() {
    try { return window.localStorage.getItem(CLAVE) || ""; } catch (e) { return ""; }
  }
  function guardar(valor) {
    try { window.localStorage.setItem(CLAVE, valor); } catch (e) { /* sin almacenamiento: no pasa nada */ }
  }

  // Las fechas ISO se comparan bien como texto.
  if (fecha && leer() >= fecha) {
    aviso.hidden = true;
    return;
  }

  var boton = aviso.querySelector(".aviso-datos__cerrar");
  if (boton) {
    boton.addEventListener("click", function () {
      if (fecha) guardar(fecha);
      aviso.hidden = true;
    });
  }
})();
