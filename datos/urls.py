from django.urls import path

from . import views

app_name = "datos"

urlpatterns = [
    path("", views.lista, name="lista"),
    # Archivos del paquete (sin login). Van antes que <slug>/ y la barra final es obligatoria:
    # ver views.ver_sin_barra.
    path("ver/<slug:slug>", views.ver_sin_barra, name="ver_sin_barra"),
    path("ver/<slug:slug>/", views.ver_archivo, name="ver_indice"),
    path("ver/<slug:slug>/<path:ruta>", views.ver_archivo, name="ver_archivo"),
    # Página con el encabezado y el paquete en un iframe
    path("<slug:slug>/", views.visor, name="visor"),
]
