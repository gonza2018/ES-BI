// "Consultar por este servicio": cierra la ventana, va al formulario y deja
// sugerido el tema en el mensaje (si el visitante todavía no escribió nada).
document.addEventListener("DOMContentLoaded", function () {
  var pendiente = null;

  document.querySelectorAll(".cerrar-y-contactar").forEach(function (boton) {
    boton.addEventListener("click", function () {
      pendiente = boton.getAttribute("data-servicio");
    });
  });

  document.querySelectorAll(".modal").forEach(function (modal) {
    modal.addEventListener("hidden.bs.modal", function () {
      if (!pendiente) return;
      var mensaje = document.getElementById("id_mensaje");
      if (mensaje && !mensaje.value.trim()) {
        mensaje.value = "Quisiera consultar por el servicio de " + pendiente + ".\n\n";
      }
      pendiente = null;
      var seccion = document.getElementById("contacto");
      if (seccion) seccion.scrollIntoView();
      var nombre = document.getElementById("id_nombre");
      if (nombre) nombre.focus({ preventScroll: true });
    });
  });
});
