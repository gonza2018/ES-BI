import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail import EmailMessage
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_safe, require_http_methods

from .contenido import SERVICIOS, SERVICIOS_EN_DIAPOSITIVAS
from .forms import ContactoForm
from .models import MensajeContacto, Proyecto

logger = logging.getLogger(__name__)


def _contexto_inicio(form=None, error_envio=False):
    return {
        "form": form or ContactoForm(),
        "error_envio": error_envio,
        "proyectos": Proyecto.objects.filter(publicado=True),
        "servicios": SERVICIOS,
        "diapositivas": SERVICIOS_EN_DIAPOSITIVAS,
    }


def modo_contacto():
    return f"Formspree ({settings.FORMSPREE_ID})" if settings.FORMSPREE_ID else "SMTP"


def enviar_contacto(datos, origen=""):
    """Envía el mensaje del formulario.

    Si está definida FORMSPREE_ID, lo manda a Formspree por HTTPS (funciona
    incluso en el plan free de Render, que bloquea SMTP). Si no, por SMTP.
    `origen` es la dirección del sitio (https://...), que Formspree usa si el
    formulario tiene restringidos los dominios permitidos.
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
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                # Sin esto Python se presenta como "Python-urllib", que algunos
                # servicios bloquean como si fuera un robot.
                "User-Agent": "gserelic.com formulario de contacto",
                **({"Origin": origen, "Referer": origen + "/"} if origen else {}),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(pedido, timeout=15) as respuesta:
                if respuesta.status != 200:
                    raise RuntimeError(f"Formspree respondió {respuesta.status}")
        except urllib.error.HTTPError as error:
            # Formspree explica el motivo del rechazo en el cuerpo de la respuesta.
            detalle = error.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(f"Formspree rechazó el envío (HTTP {error.code}): {detalle}") from error
        return

    EmailMessage(
        subject=f"Contacto web ES & BI: {datos['nombre']}",
        body=f"Nombre: {datos['nombre']}\nCorreo: {datos['email']}\n\nMensaje:\n{datos['mensaje']}\n",
        from_email=settings.DEFAULT_FROM_EMAIL,  # siempre desde nuestra cuenta
        to=settings.CONTACTO_DESTINATARIOS,
        reply_to=[datos["email"]],  # "Responder" le contesta al visitante
    ).send(fail_silently=False)


def avisar_mensaje(mensaje, origen=""):
    """Intenta avisar por correo de un mensaje ya guardado. Devuelve True si salió."""
    datos = {"nombre": mensaje.nombre, "email": mensaje.email, "mensaje": mensaje.mensaje}
    try:
        enviar_contacto(datos, origen=origen)
    except Exception as error:
        logger.exception("Falló el aviso del mensaje de contacto %s (modo: %s)", mensaje.pk, modo_contacto())
        mensaje.aviso_enviado = False
        mensaje.aviso_error = f"{modo_contacto()}: {error}"[:2000]
    else:
        mensaje.aviso_enviado = True
        mensaje.aviso_error = ""
    mensaje.save(update_fields=["aviso_enviado", "aviso_error"])
    return mensaje.aviso_enviado


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

    origen = request.build_absolute_uri("/").rstrip("/")
    datos = form.cleaned_data
    try:
        # 1) Guardar primero: aunque el correo falle, el mensaje queda en /gestion/.
        mensaje = MensajeContacto.objects.create(
            nombre=datos["nombre"], email=datos["email"], mensaje=datos["mensaje"]
        )
    except Exception:
        logger.exception("No se pudo guardar el mensaje de contacto; se intenta solo el correo")
        try:
            enviar_contacto(datos, origen=origen)
        except Exception:
            logger.exception("Tampoco salió el correo (modo: %s)", modo_contacto())
            return render(request, "sitio/inicio.html", _contexto_inicio(form, error_envio=True), status=503)
        return redirect("sitio:contacto_enviado")

    # 2) Avisar por correo. Si falla, queda registrado en el mensaje y se reintenta desde el admin.
    avisar_mensaje(mensaje, origen=origen)
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
