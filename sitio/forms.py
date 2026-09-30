from django import forms


class ContactoForm(forms.Form):
    nombre = forms.CharField(label="Nombre completo", max_length=120)
    email = forms.EmailField(label="Correo electrónico", max_length=254)
    mensaje = forms.CharField(label="Mensaje", max_length=5000, widget=forms.Textarea(attrs={"rows": 5}))
    # Campo trampa: invisible para personas; los bots suelen completarlo.
    sitio_web = forms.CharField(required=False, label="No completar este campo")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nombre, campo in self.fields.items():
            if nombre != "sitio_web":
                campo.widget.attrs.setdefault("class", "form-control")
        self.fields["email"].widget.attrs["autocomplete"] = "email"
        self.fields["nombre"].widget.attrs["autocomplete"] = "name"
        self.fields["sitio_web"].widget.attrs.update({"tabindex": "-1", "autocomplete": "off"})

    def es_spam(self):
        return bool(self.cleaned_data.get("sitio_web"))
