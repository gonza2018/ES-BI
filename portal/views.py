from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_safe

from config.middleware import CSP_PAQUETES

from .forms import LoginCorreoForm
from .models import Paquete
from .paquetes import TIPOS_SERVIDOS, resolver_ruta


class LoginView(auth_views.LoginView):
    template_name = "portal/login.html"
    authentication_form = LoginCorreoForm
    redirect_authenticated_user = True


class LogoutView(auth_views.LogoutView):
    pass


def _paquete_visible(request, slug):
    """El paquete si el usuario puede verlo; si no, 404 (no revela que existe)."""
    paquete = Paquete.visibles_para(request.user).filter(slug=slug).first()
    if paquete is None:
        raise Http404
    return paquete


@require_safe
@login_required
def inicio(request):
    grupos = list(request.user.groups.values_list("name", flat=True))
    paquetes = Paquete.visibles_para(request.user).prefetch_related("grupos")
    return render(request, "portal/inicio.html", {"grupos": grupos, "paquetes": paquetes})


@require_safe
@login_required
def tablero(request, slug):
    """Página del portal que muestra el paquete en un iframe, con encabezado y descargas."""
    paquete = _paquete_visible(request, slug)
    return render(request, "portal/tablero.html", {"paquete": paquete, "descargas": paquete.descargas()})


@require_safe
def ver_sin_barra(request, slug):
    """/portal/ver/<slug> -> /portal/ver/<slug>/ (sin la barra, las rutas relativas no cargan)."""
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    _paquete_visible(request, slug)
    return redirect(reverse("portal:ver_indice", args=[slug]), permanent=False)


@require_safe
def ver_archivo(request, slug, ruta=""):
    """Sirve un archivo del paquete. Cada pedido verifica sesión, grupo y ruta."""
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    paquete = _paquete_visible(request, slug)
    archivo = resolver_ruta(paquete.directorio, ruta)
    tipo, como_descarga = TIPOS_SERVIDOS[archivo.suffix.lower()]
    respuesta = FileResponse(
        open(archivo, "rb"), content_type=tipo, as_attachment=como_descarga, filename=archivo.name
    )
    respuesta["Content-Security-Policy"] = CSP_PAQUETES
    respuesta["Cache-Control"] = "private, max-age=300"
    return respuesta
