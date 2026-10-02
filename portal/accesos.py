"""Acceso por carta personal, confirmaciones y avisos de actualización.

Mensajes editables en templates/portal/mensajes/ (texto plano):
  aviso_actualizacion.txt  ·  confirmacion_carga.txt  ·  carta_acceso.txt
"""
import hashlib
import logging
import secrets
from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .models import AccesoPersonal, Aviso

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enlaces y tokens
# ---------------------------------------------------------------------------

def url_absoluta(request, ruta):
    if settings.HOST_CANONICO:
        return f"https://{settings.HOST_CANONICO}{ruta}"
    return request.build_absolute_uri(ruta)


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generar_acceso(usuario, paquete, restablecer_contrasena=False):
    """Crea el enlace personal (reemplaza el anterior). Devuelve el token EN CLARO,
    que solo debe usarse para armar la carta: en la base queda únicamente su hash."""
    if usuario.is_staff or usuario.is_superuser:
        raise ValueError("No se generan cartas para cuentas con acceso al panel de administración.")
    token = secrets.token_urlsafe(32)
    AccesoPersonal.objects.filter(usuario=usuario).delete()
    AccesoPersonal.objects.create(usuario=usuario, token_hash=hash_token(token), paquete=paquete)
    if restablecer_contrasena or not usuario.has_usable_password():
        usuario.set_unusable_password()  # también cierra sus sesiones abiertas
        usuario.save(update_fields=["password"])
    return token


def buscar_acceso(token):
    if not token or len(token) > 100:
        return None
    return AccesoPersonal.objects.select_related("usuario").filter(token_hash=hash_token(token)).first()


def acceso_vencido(acceso):
    """Vence solo si la persona todavía no creó su contraseña y pasaron más de N días."""
    if acceso.usuario.has_usable_password():
        return False
    return timezone.now() - acceso.creado > timedelta(days=settings.ACCESO_VIGENCIA_DIAS)


def ruta_acceso(token, slug):
    return reverse("portal:acceso", args=[token, slug])


# ---------------------------------------------------------------------------
# Correo
# ---------------------------------------------------------------------------

def firma():
    return {"firma_nombre": settings.FIRMA_NOMBRE, "firma_matricula": settings.FIRMA_MATRICULA}


def smtp_configurado():
    """¿Se puede mandar correo a terceros? (Formspree solo le escribe al dueño del formulario.)"""
    if settings.EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend":
        return True  # consola/locmem en desarrollo y tests
    return bool(settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD)


def enviar_a_mi(asunto, cuerpo, correo_respaldo=""):
    """Correo para Gonzalo: por SMTP si está configurado; si no, por Formspree."""
    destinatarios = settings.CONTACTO_DESTINATARIOS or ([correo_respaldo] if correo_respaldo else [])
    if smtp_configurado() and destinatarios:
        EmailMessage(asunto, cuerpo, settings.DEFAULT_FROM_EMAIL, destinatarios).send(fail_silently=False)
        return
    if settings.FORMSPREE_ID:
        from sitio.views import enviar_contacto

        enviar_contacto(
            {"nombre": "Portal ES & BI", "email": correo_respaldo or "portal@gserelic.com",
             "mensaje": f"{asunto}\n\n{cuerpo}"}
        )
        return
    raise RuntimeError("No hay correo configurado (ni SMTP ni FORMSPREE_ID).")


def confirmar_carga(request, paquete, es_actualizacion):
    contexto = {
        "paquete": paquete,
        "es_actualizacion": es_actualizacion,
        "grupos": ", ".join(g.name for g in paquete.grupos.all()),
        "enlace": url_absoluta(request, reverse("portal:tablero", args=[paquete.slug])),
        **firma(),
    }
    asunto = f"Tablero disponible: {paquete.titulo} (v{paquete.version or '?'})"
    enviar_a_mi(asunto, render_to_string("portal/mensajes/confirmacion_carga.txt", contexto),
                correo_respaldo=getattr(request.user, "email", ""))


# ---------------------------------------------------------------------------
# Avisos de actualización
# ---------------------------------------------------------------------------

def texto_aviso(request, paquete, usuario):
    # NUNCA lleva el enlace con token: solo el del visor (si no hay sesión, pide login).
    enlace = url_absoluta(request, reverse("portal:tablero", args=[paquete.slug]))
    cuerpo = render_to_string(
        "portal/mensajes/aviso_actualizacion.txt",
        {"usuario": usuario, "paquete": paquete, "enlace": enlace, **firma()},
    )
    asunto = f"Actualización del tablero «{paquete.titulo}» (versión {paquete.version or '?'})"
    return asunto, cuerpo


def url_whatsapp(aviso):
    return f"https://wa.me/{aviso.usuario.celular_whatsapp}?text={quote(aviso.mensaje, safe='')}"


def url_mailto(aviso):
    return f"mailto:{aviso.usuario.email}?subject={quote(aviso.asunto, safe='')}&body={quote(aviso.mensaje, safe='')}"


def enviar_aviso_correo(aviso):
    """Envía un aviso por correo (SMTP). Devuelve True si salió."""
    if not smtp_configurado():
        aviso.estado = "pendiente"
        aviso.detalle = "Sin SMTP configurado: usar el botón «Enviar por correo» (abre tu programa de correo)."
        aviso.save(update_fields=["estado", "detalle"])
        return False
    try:
        EmailMessage(aviso.asunto, aviso.mensaje, settings.DEFAULT_FROM_EMAIL, [aviso.usuario.email]).send(
            fail_silently=False
        )
    except Exception as error:
        logger.exception("Falló el aviso por correo %s", aviso.pk)
        aviso.estado, aviso.detalle = "error", str(error)[:1000]
        aviso.save(update_fields=["estado", "detalle"])
        return False
    aviso.estado, aviso.enviado, aviso.detalle = "enviado", timezone.now(), ""
    aviso.save(update_fields=["estado", "enviado", "detalle"])
    return True


def crear_avisos(request, paquete):
    """Una línea por usuario activo de los grupos del paquete (no administradores).
    Con celular: WhatsApp (lo envía Gonzalo con un clic). Sin celular: correo automático."""
    from django.contrib.auth import get_user_model

    usuarios = (
        get_user_model().objects.filter(is_active=True, is_staff=False, groups__in=paquete.grupos.all())
        .distinct().order_by("nombre", "email")
    )
    avisos = []
    for usuario in usuarios:
        asunto, mensaje = texto_aviso(request, paquete, usuario)
        aviso = Aviso.objects.create(
            paquete=paquete, version=paquete.version_actual, usuario=usuario,
            medio="whatsapp" if usuario.celular else "correo", asunto=asunto, mensaje=mensaje,
        )
        if aviso.medio == "correo":
            enviar_aviso_correo(aviso)
        avisos.append(aviso)
    return avisos
