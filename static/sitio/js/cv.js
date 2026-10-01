// Página /cv/: texto que se escribe solo y aparición suave de secciones.
// Sin librerías externas. Respeta "reducir movimiento" del sistema.
document.addEventListener("DOMContentLoaded", function () {
  var reducir = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var el = document.querySelector(".texto-rotativo");
  if (el && !reducir) {
    var frases = el.getAttribute("data-frases").split("|");
    var i = 0, pos = frases[0].length, borrando = true;
    (function paso() {
      var frase = frases[i];
      if (borrando) {
        pos--;
        if (pos <= 0) { borrando = false; i = (i + 1) % frases.length; }
      } else {
        pos++;
        if (pos >= frases[i].length) { borrando = true; el.textContent = frases[i]; return setTimeout(paso, 1800); }
      }
      el.textContent = frases[i].slice(0, Math.max(pos, 0));
      setTimeout(paso, borrando ? 35 : 70);
    })();
  }

  if (!reducir && "IntersectionObserver" in window) {
    document.body.classList.add("js-animar");
    var obs = new IntersectionObserver(function (entradas) {
      entradas.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("visible"); obs.unobserve(e.target); }
      });
    }, { threshold: 0.15 });
    document.querySelectorAll(".aparecer").forEach(function (s) { obs.observe(s); });
  }
});
