from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("ingresar/", views.LoginView.as_view(), name="login"),
    path("salir/", views.LogoutView.as_view(), name="logout"),
]
