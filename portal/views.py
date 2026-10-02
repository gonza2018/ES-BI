from django.contrib.auth import authenticate, login
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from config.middleware import CSP_PAQUETES

from .accesos import acceso_vencido, buscar_acceso
from .forms import ContrasenaAccesoForm, LoginCorreoForm
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


@never_cache
@require_http_methods(["GET", "POST"])
def acceso(request, token, slug):
    """Enlace personal de la carta: /portal/acceso/<token>/<slug>/

    - Sin contraseña todavía: bienvenida y creación de contraseña (vence a los N días).
    - Con contraseña: solo pide la contraseña (el enlace identifica a la persona). Axes protege.
    - Token inválido, usuario inactivo o tablero fuera de sus grupos: 404 sin detalles.
    """
    registro = buscar_acceso(token)
    if registro is None or not registro.usuario.is_active:
        raise Http404
    usuario = registro.usuario
    if not Paquete.visibles_para(usuario).filter(slug=slug).exists():
        raise Http404
    destino = reverse("portal:tablero", args=[slug])

    if request.user.is_authenticated and request.user.pk == usuario.pk:
        return redirect(destino)

    def entrar():
        login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
        registro.ultimo_uso = timezone.now()
        registro.save(update_fields=["ultimo_uso"])
        return redirect(destino)

    contexto = {"usuario": usuario}
    if not usuario.has_usable_password():
        if acceso_vencido(registro):
            respuesta = render(request, "portal/acceso.html", {**contexto, "modo": "vencido"}, status=410)
        else:
            form = SetPasswordForm(usuario, request.POST or None)
            for campo in form.fields.values():
                campo.widget.attrs.setdefault("class", "form-control")
            if request.method == "POST" and form.is_valid():
                form.save()
                return entrar()
            respuesta = render(request, "portal/acceso.html", {**contexto, "modo": "crear", "form": form})
    else:
        form = ContrasenaAccesoForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            # authenticate() con el correo: django-axes cuenta los intentos fallidos
            # (usuario + IP) igual que en el login general.
            if authenticate(request, username=usuario.email, password=form.cleaned_data["password"]):
                return entrar()
            form.add_error("password", "La contraseña no es correcta.")
        respuesta = render(request, "portal/acceso.html", {**contexto, "modo": "ingresar", "form": form})
    # La URL lleva el token: que no viaje como "Referer" a OTRO sitio. Ojo: "no-referrer"
    # rompe el formulario (el navegador manda Origin: null y Django lo rechaza por CSRF).
    respuesta["Referrer-Policy"] = "same-origin"
    return respuesta
