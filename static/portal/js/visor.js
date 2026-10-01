// Botón "Pantalla completa" del visor. Si el navegador no permite pantalla completa
// sobre el iframe, abre el tablero en una pestaña nueva.
document.addEventListener("DOMContentLoaded", function () {
  var boton = document.getElementById("pantalla-completa");
  var visor = document.getElementById("visor");
  if (!boton || !visor) return;
  boton.addEventListener("click", function () {
    var pedir = visor.requestFullscreen || visor.webkitRequestFullscreen;
    if (pedir) {
      var resultado = pedir.call(visor);
      if (resultado && resultado.catch) {
        resultado.catch(function () { window.open(visor.src, "_blank", "noopener"); });
      }
    } else {
      window.open(visor.src, "_blank", "noopener");
    }
  });
});
