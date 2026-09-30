from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_safe

from .forms import LoginCorreoForm


class LoginView(auth_views.LoginView):
    template_name = "portal/login.html"
    authentication_form = LoginCorreoForm
    redirect_authenticated_user = True


class LogoutView(auth_views.LogoutView):
    pass


@require_safe
@login_required
def inicio(request):
    # Paso 2: acá se listarán los paquetes (dashboards y sitios) de los grupos del usuario.
    grupos = list(request.user.groups.values_list("name", flat=True))
    return render(request, "portal/inicio.html", {"grupos": grupos, "paquetes": []})
