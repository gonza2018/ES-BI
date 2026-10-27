"""Marca del portal: la de ES & BI o la neutra de los tableros institucionales.

Neutra cuando:
  - el pedido llega por HOST_TABLERO (por ejemplo tablero.gserelic.com);
  - quien está en sesión solo ve tableros institucionales;
  - es la pantalla de ingreso a la que vuelve alguien que cerró una sesión neutra (?tablero=1).
"""
from django.conf import settings

NOMBRE_INSTITUCIONAL = "Santiago del Estero · Tablero económico"
CONTACTO_NEUTRO = "a quien le entregó este acceso"


def host_tablero(request):
    host = settings.HOST_TABLERO
    return bool(host) and request.get_host().split(":")[0].lower() == host


def usuario_institucional(usuario):
    """¿La persona solo ve tableros institucionales? (Administradores, nunca.)"""
    from .models import Paquete

    if usuario is None or not usuario.is_authenticated or usuario.is_staff or usuario.is_superuser:
        return False
    visibles = Paquete.visibles_para(usuario)
    return visibles.exists() and not visibles.filter(institucional=False).exists()


def es_neutro(request):
    if not hasattr(request, "_marca_neutra"):
        usuario = getattr(request, "user", None)
        request._marca_neutra = (
            host_tablero(request)
            or usuario_institucional(usuario)
            or (request.GET.get("tablero") == "1" and not (usuario and usuario.is_authenticated))
        )
    return request._marca_neutra


def contexto_marca(neutra):
    if neutra:
        return {"marca_neutra": True, "portal_nombre": NOMBRE_INSTITUCIONAL, "contacto_acceso": CONTACTO_NEUTRO}
    return {
        "marca_neutra": False,
        "portal_nombre": "Portal ES & BI",
        "contacto_acceso": f"al {settings.FIRMA_NOMBRE} - {settings.FIRMA_MATRICULA}",
    }
