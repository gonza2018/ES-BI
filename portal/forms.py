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
    notificar = forms.BooleanField(
        label="Notificar a los usuarios asignados",
        required=False,
        initial=False,
        help_text="Solo para versiones nuevas de un tablero que ya existe. Arma los avisos: WhatsApp "
        "(lo enviás vos con un clic) para quien tiene celular y correo automático para quien no.",
    )


class ContrasenaAccesoForm(forms.Form):
    password = forms.CharField(
        label="Contraseña", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "class": "form-control", "autofocus": True}),
    )


class CartaAccesoForm(forms.Form):
    paquete = forms.ModelChoiceField(label="Tablero", queryset=None, empty_label=None)
    restablecer = forms.BooleanField(
        label="Restablecer la contraseña (la persona la olvidó)",
        required=False,
        help_text="Borra la contraseña actual: la persona va a tener que crear una nueva con el enlace de esta carta.",
    )

    def __init__(self, *args, paquetes=None, tiene_contrasena=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["paquete"].queryset = paquetes
        if not tiene_contrasena:
            del self.fields["restablecer"]
