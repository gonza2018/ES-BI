import json
import logging
import urllib.request

from django.conf import settings
from django.core.mail import EmailMessage
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_safe, require_http_methods

from .contenido import SERVICIOS, SERVICIOS_EN_DIAPOSITIVAS
from .forms import ContactoForm
from .models import Proyecto

logger = logging.getLogger(__name__)


def _contexto_inicio(form=None, error_envio=False):
    return {
        "form": form or ContactoForm(),
        "error_envio": error_envio,
        "proyectos": Proyecto.objects.filter(publicado=True),
        "servicios": SERVICIOS,
        "diapositivas": SERVICIOS_EN_DIAPOSITIVAS,
    }


def enviar_contacto(datos):
    """Envía el mensaje del formulario.

    Si está definida FORMSPREE_ID, lo manda a Formspree por HTTPS (funciona
    incluso en el plan free de Render, que bloquea SMTP). Si no, por SMTP.
    """
    if settings.FORMSPREE_ID:
        cuerpo = json.dumps(
            {
                "name": datos["nombre"],
                "email": datos["email"],  # Formspree lo usa como "Responder a"
                "message": datos["mensaje"],
                "_subject": f"Contacto web ES & BI: {datos['nombre']}",
            }
        ).encode("utf-8")
        pedido = urllib.request.Request(
            f"https://formspree.io/f/{settings.FORMSPREE_ID}",
            data=cuerpo,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(pedido, timeout=15) as respuesta:
            if respuesta.status != 200:
                raise RuntimeError(f"Formspree respondió {respuesta.status}")
        return

    EmailMessage(
        subject=f"Contacto web ES & BI: {datos['nombre']}",
        body=f"Nombre: {datos['nombre']}\nCorreo: {datos['email']}\n\nMensaje:\n{datos['mensaje']}\n",
        from_email=settings.DEFAULT_FROM_EMAIL,  # siempre desde nuestra cuenta
        to=settings.CONTACTO_DESTINATARIOS,
        reply_to=[datos["email"]],  # "Responder" le contesta al visitante
    ).send(fail_silently=False)


@require_safe
def inicio(request):
    return render(request, "sitio/inicio.html", _contexto_inicio())


@require_safe
def cv(request):
    return render(request, "sitio/cv.html")


@require_http_methods(["GET", "POST"])
def contacto(request):
    if request.method == "GET":
        return redirect(reverse("sitio:inicio") + "#contacto")

    form = ContactoForm(request.POST)
    if not form.is_valid():
        return render(request, "sitio/inicio.html", _contexto_inicio(form), status=400)

    if form.es_spam():
        # No avisamos al bot: simulamos éxito.
        return redirect("sitio:contacto_enviado")

    try:
        enviar_contacto(form.cleaned_data)
    except Exception:
        logger.exception("Falló el envío del formulario de contacto")
        return render(request, "sitio/inicio.html", _contexto_inicio(form, error_envio=True), status=503)

    return redirect("sitio:contacto_enviado")


@require_safe
def contacto_enviado(request):
    return render(request, "sitio/contacto_enviado.html")


@require_safe
def robots_txt(request):
    base = f"https://{settings.HOST_CANONICO}" if settings.HOST_CANONICO else request.build_absolute_uri("/").rstrip("/")
    lineas = [
        "User-agent: *",
        "Disallow: /portal/",
        "Disallow: /gestion/",
        "Disallow: /contacto/",
        "",
        f"Sitemap: {base}/sitemap.xml",
    ]
    return HttpResponse("\n".join(lineas) + "\n", content_type="text/plain; charset=utf-8")
