from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("ingresar/", views.LoginView.as_view(), name="login"),
    path("salir/", views.LogoutView.as_view(), name="logout"),
    # Página del portal con el paquete en un iframe
    path("tablero/<slug:slug>/", views.tablero, name="tablero"),
    # Archivos del paquete (protegidos). La barra final es obligatoria: ver views.ver_sin_barra.
    path("ver/<slug:slug>", views.ver_sin_barra, name="ver_sin_barra"),
    path("ver/<slug:slug>/", views.ver_archivo, name="ver_indice"),
    path("ver/<slug:slug>/<path:ruta>", views.ver_archivo, name="ver_archivo"),
]
