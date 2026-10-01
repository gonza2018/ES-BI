from django import forms
from django.contrib.auth.forms import AuthenticationForm


class LoginCorreoForm(AuthenticationForm):
    """Login con correo. El campo se sigue llamando `username` porque así
    lo espera Django (y django-axes), pero se presenta como correo."""

    username = forms.EmailField(
        label="Correo electrónico",
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email", "class": "form-control"}),
    )
    password = forms.CharField(
        label="Contraseña",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "class": "form-control"}),
    )

    error_messages = {
        "invalid_login": "El correo o la contraseña no son correctos.",
        "inactive": "Esta cuenta está desactivada.",
    }

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()


class SubirPaqueteForm(forms.Form):
    archivo = forms.FileField(
        label="Paquete (.zip)",
        help_text="El zip con index.html y meta.json. Si el slug ya existe, se sube como versión nueva.",
        widget=forms.ClearableFileInput(attrs={"accept": ".zip,application/zip"}),
    )
