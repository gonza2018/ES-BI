from django.urls import path
from django.views.generic.base import RedirectView

from . import views

app_name = "sitio"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("cv/", views.cv, name="cv"),
    path("contacto/", views.contacto, name="contacto"),
    path("contacto/enviado/", views.contacto_enviado, name="contacto_enviado"),
    # Ruta del sitio anterior (Flask)
    path("send_mail", RedirectView.as_view(pattern_name="sitio:inicio", permanent=True)),
    path("robots.txt", views.robots_txt, name="robots"),
]
