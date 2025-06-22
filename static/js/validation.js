document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("formulario");
  const status = document.getElementById("form-status");

  form.addEventListener("submit", async function (e) {
    e.preventDefault();

    const email = form.email.value.trim();
    const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    if (!regex.test(email)) {
      status.textContent = "Por favor, ingresá un correo válido.";
      status.classList.remove("text-success");
      status.classList.add("text-danger");
      return;
    }

    const data = new FormData(form);
    
    form.querySelector("button[type='submit']").innerHTML = "Enviando...";
    form.querySelector("button[type='submit']").disabled = true;
    
    try {
      const response = await fetch("https://formspree.io/f/movwnndw", {
        method: "POST",
        body: data,
        headers: {
          Accept: "application/json",
        },
      });

      if (response.ok) {
          const toast = new bootstrap.Toast(document.getElementById("toastSuccess"));
          toast.show();
          form.reset();

          setTimeout(() => {
            window.location.href = "/send_mail";
          }, 2500);
        } else {
        const result = await response.json();
        if (result.errors) {
          status.textContent = result.errors.map(e => e.message).join(", ");
        } else {
          status.textContent = "Ocurrió un error al enviar el mensaje.";
        }
        status.classList.remove("text-success");
        status.classList.add("text-danger");
      }
    } catch (error) {
      status.textContent = "No se pudo conectar con el servidor.";
      status.classList.remove("text-success");
      status.classList.add("text-danger");
    }
    form.querySelector("button[type='submit']").innerHTML = "Enviar";
    form.querySelector("button[type='submit']").disabled = false;
  });
});