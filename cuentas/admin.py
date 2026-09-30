from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import Usuario


class UsuarioCreationForm(UserCreationForm):
    class Meta:
        model = Usuario
        fields = ("email",)


class UsuarioChangeForm(UserChangeForm):
    class Meta:
        model = Usuario
        fields = "__all__"


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    form = UsuarioChangeForm
    add_form = UsuarioCreationForm
    model = Usuario

    list_display = ("email", "nombre", "organismo", "grupos", "is_active", "last_login")
    list_filter = ("is_active", "is_staff", "is_superuser", "groups")
    search_fields = ("email", "nombre", "organismo")
    ordering = ("email",)
    readonly_fields = ("last_login", "date_joined")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Datos", {"fields": ("nombre", "organismo")}),
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
                "fields": ("email", "nombre", "organismo", "password1", "password2", "groups"),
            },
        ),
    )
    filter_horizontal = ("groups", "user_permissions")

    @admin.display(description="grupos")
    def grupos(self, obj):
        return ", ".join(g.name for g in obj.groups.all()) or "—"
