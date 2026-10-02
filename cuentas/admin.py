from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm

from .models import TRATAMIENTOS, Usuario


class TratamientoFormMixin(forms.Form):
    """Tratamiento como lista desplegable + «Otro…» para escribir uno libre."""

    tratamiento_lista = forms.ChoiceField(
        label="Tratamiento",
        choices=[("", "— sin tratamiento —"), *[(t, t) for t in TRATAMIENTOS], ("otro", "Otro…")],
        required=False,
        help_text="Abogados y médicos: Dr./Dra. Contadores: Cr./Cra.",
    )
    tratamiento_otro = forms.CharField(
        label="Otro tratamiento", required=False, max_length=20,
        help_text="Solo si elegiste «Otro…». Ej.: Esc., Mtro., Tec.",
    )

    def _init_tratamiento(self):
        actual = (getattr(self.instance, "tratamiento", "") or "").strip()
        if actual in TRATAMIENTOS:
            self.initial["tratamiento_lista"] = actual
        elif actual:
            self.initial["tratamiento_lista"], self.initial["tratamiento_otro"] = "otro", actual

    def _clean_tratamiento(self, datos):
        opcion, otro = datos.get("tratamiento_lista", ""), " ".join(datos.get("tratamiento_otro", "").split())
        if opcion == "otro":
            if not otro:
                self.add_error("tratamiento_otro", "Escribí el tratamiento, o elegí uno de la lista.")
            self.instance.tratamiento = otro
        else:
            if otro:
                self.add_error("tratamiento_otro", "Elegí «Otro…» en la lista para usar un tratamiento propio.")
            self.instance.tratamiento = opcion
        return datos


class UsuarioCreationForm(TratamientoFormMixin, forms.ModelForm):
    """Alta de cliente SIN contraseña: la crea la persona con su carta de acceso."""

    class Meta:
        model = Usuario
        fields = ("email", "nombre", "organismo", "celular", "groups")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_tratamiento()

    def clean(self):
        return self._clean_tratamiento(super().clean())

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if Usuario.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Ya existe un usuario con ese correo.")
        return email

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.set_unusable_password()
        if commit:
            usuario.save()
            self.save_m2m()
        return usuario


class UsuarioChangeForm(TratamientoFormMixin, UserChangeForm):
    class Meta:
        model = Usuario
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_tratamiento()

    def clean(self):
        return self._clean_tratamiento(super().clean())


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    form = UsuarioChangeForm
    add_form = UsuarioCreationForm
    model = Usuario

    change_form_template = "admin/cuentas/usuario/change_form.html"
    list_display = ("email", "destinatario_admin", "organismo", "grupos", "tiene_contrasena", "is_active", "last_login")
    list_filter = ("is_active", "is_staff", "is_superuser", "groups")
    search_fields = ("email", "nombre", "organismo")
    ordering = ("email",)
    readonly_fields = ("last_login", "date_joined")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Datos", {"fields": ("tratamiento_lista", "tratamiento_otro", "nombre", "organismo", "celular")}),
        ("Acceso", {"fields": ("is_active", "groups")}),
        (
            "Administración",
            {"classes": ("collapse",), "fields": ("is_staff", "is_superuser", "user_permissions")},
        ),
        ("Registro", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "tratamiento_lista", "tratamiento_otro", "nombre", "organismo", "celular", "groups"),
                "description": "Sin contraseña: la persona la crea con su carta de acceso "
                "(botón «Generar carta de acceso» en la ficha, después de guardar).",
            },
        ),
    )
    filter_horizontal = ("groups", "user_permissions")

    @admin.display(description="nombre")
    def destinatario_admin(self, obj):
        return obj.destinatario if obj.nombre else "—"

    @admin.display(description="contraseña creada", boolean=True)
    def tiene_contrasena(self, obj):
        return obj.has_usable_password()

    @admin.display(description="grupos")
    def grupos(self, obj):
        return ", ".join(g.name for g in obj.groups.all()) or "—"


# --- Carta de acceso (botón en la ficha del usuario) -------------------------
def _carta_view(model_admin, request, object_id):
    from pathlib import Path

    from django.conf import settings
    from django.contrib import messages
    from django.http import HttpResponse
    from django.shortcuts import get_object_or_404, redirect, render

    from portal.accesos import generar_acceso, ruta_acceso, url_absoluta
    from portal.carta import generar_carta, nombre_archivo
    from portal.forms import CartaAccesoForm
    from portal.models import Paquete

    usuario = get_object_or_404(Usuario, pk=object_id)
    ficha = redirect("admin:cuentas_usuario_change", usuario.pk)
    if not model_admin.has_change_permission(request, usuario):
        return redirect("admin:index")
    if usuario.is_staff or usuario.is_superuser:
        messages.error(request, "No se generan cartas para cuentas con acceso al panel (se borraría su contraseña).")
        return ficha
    if not usuario.is_active:
        messages.error(request, "El usuario está inactivo.")
        return ficha
    paquetes = Paquete.visibles_para(usuario)
    if not paquetes.exists():
        messages.warning(request, "Este usuario no tiene tableros: asignale un grupo que tenga paquetes publicados.")
        return ficha

    form = CartaAccesoForm(request.POST or None, paquetes=paquetes, tiene_contrasena=usuario.has_usable_password())
    if request.method == "POST" and form.is_valid():
        paquete = form.cleaned_data["paquete"]
        token = generar_acceso(usuario, paquete, form.cleaned_data.get("restablecer", False))
        enlace = url_absoluta(request, ruta_acceso(token, paquete.slug))
        pdf = generar_carta(usuario, paquete, enlace)
        respuesta = HttpResponse(pdf, content_type="application/pdf")
        respuesta["Content-Disposition"] = f'attachment; filename="{nombre_archivo(paquete, usuario)}"'
        respuesta["Cache-Control"] = "no-store"
        return respuesta

    contexto = {
        **model_admin.admin_site.each_context(request),
        "title": "Generar carta de acceso",
        "opts": model_admin.model._meta,
        "original": usuario,
        "form": form,
        "tiene_contrasena": usuario.has_usable_password(),
        "tiene_enlace": hasattr(usuario, "acceso_personal"),
        "hay_firma": Path(settings.FIRMA_ARCHIVO).is_file(),
    }
    return render(request, "admin/cuentas/usuario/carta.html", contexto)


def _urls_con_carta(original_get_urls):
    from django.urls import path

    def get_urls(self):
        propias = [
            path("<path:object_id>/carta/", self.admin_site.admin_view(lambda r, object_id: _carta_view(self, r, object_id)),
                 name="cuentas_usuario_carta"),
        ]
        return propias + original_get_urls(self)

    return get_urls


UsuarioAdmin.get_urls = _urls_con_carta(UsuarioAdmin.get_urls)
