from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.template.defaultfilters import filesizeformat
from django.urls import path, reverse
from django.utils.html import format_html

from .forms import SubirPaqueteForm
from .models import Paquete, VersionPaquete
from .paquetes import PaqueteInvalido, activar_version, instalar


class VersionPaqueteInline(admin.TabularInline):
    model = VersionPaquete
    extra = 0
    max_num = 0
    can_delete = False
    show_change_link = True
    fields = ("version", "estado", "fecha", "subido", "subido_por", "archivo_nombre", "tamano", "actual")
    readonly_fields = fields
    verbose_name_plural = "historial de versiones (la más reciente arriba)"

    @admin.display(description="tamaño")
    def tamano(self, obj):
        return f"{filesizeformat(obj.tamano_bytes)} · {obj.cantidad_archivos} archivos"

    @admin.display(description="publicada", boolean=True)
    def actual(self, obj):
        return obj.es_actual


@admin.register(Paquete)
class PaqueteAdmin(admin.ModelAdmin):
    change_list_template = "admin/portal/paquete/change_list.html"
    change_form_template = "admin/portal/paquete/change_form.html"
    list_display = ("titulo", "slug", "tipo", "estado", "version", "fecha", "lista_grupos", "publicado", "actualizado")
    list_filter = ("estado", "tipo", "publicado", "grupos")
    search_fields = ("titulo", "slug", "organismo")
    filter_horizontal = ("grupos",)
    readonly_fields = ("slug", "tipo", "organismo", "version", "fecha", "ver_en_portal", "creado", "actualizado")
    fieldsets = (
        (None, {"fields": ("titulo", "slug", "ver_en_portal")}),
        ("Acceso", {"fields": ("grupos", "publicado")}),
        ("Datos (vienen de meta.json)", {"fields": ("estado", "descripcion", "tipo", "organismo", "version", "fecha")}),
        ("Registro", {"classes": ("collapse",), "fields": ("creado", "actualizado")}),
    )
    inlines = [VersionPaqueteInline]
    actions = ["publicar", "despublicar"]

    @admin.display(description="grupos")
    def lista_grupos(self, obj):
        return ", ".join(g.name for g in obj.grupos.all()) or "— sin grupos —"

    @admin.display(description="en el portal")
    def ver_en_portal(self, obj):
        if not obj.pk or not obj.version_actual_id:
            return "—"
        url = reverse("portal:tablero", args=[obj.slug])
        return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>', url, url)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("grupos")

    # La creación se hace siempre subiendo un zip.
    def add_view(self, request, form_url="", extra_context=None):
        return redirect("admin:portal_paquete_subir")

    def get_urls(self):
        propias = [
            path("subir/", self.admin_site.admin_view(self.subir_view), name="portal_paquete_subir"),
        ]
        return propias + super().get_urls()

    def subir_view(self, request):
        if not (self.has_add_permission(request) or self.has_change_permission(request)):
            messages.error(request, "No tiene permiso para subir paquetes.")
            return redirect("admin:index")
        form = SubirPaqueteForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            try:
                paquete, creado = instalar(form.cleaned_data["archivo"], request.user)
            except PaqueteInvalido as error:
                form.add_error("archivo", str(error))
            else:
                grupos = ", ".join(g.name for g in paquete.grupos.all())
                accion = "creado" if creado else f"actualizado a la versión {paquete.version or '(sin número)'}"
                messages.success(request, f"Paquete «{paquete.titulo}» {accion}.")
                if grupos:
                    messages.info(request, f"Grupos con acceso: {grupos}.")
                else:
                    messages.warning(
                        request,
                        "Todavía nadie lo ve: asignale uno o más grupos en «Grupos con acceso» y guardá.",
                    )
                return redirect("admin:portal_paquete_change", paquete.pk)
        contexto = {
            **self.admin_site.each_context(request),
            "title": "Subir paquete",
            "form": form,
            "opts": self.model._meta,
        }
        return render(request, "admin/portal/paquete/subir.html", contexto)

    @admin.action(description="Publicar (visible para sus grupos)")
    def publicar(self, request, queryset):
        n = queryset.update(publicado=True)
        self.message_user(request, f"{n} paquete(s) publicados.")

    @admin.action(description="Despublicar (ocultar sin borrar)")
    def despublicar(self, request, queryset):
        n = queryset.update(publicado=False)
        self.message_user(request, f"{n} paquete(s) despublicados.")


@admin.register(VersionPaquete)
class VersionPaqueteAdmin(admin.ModelAdmin):
    list_display = ("paquete", "version", "estado", "fecha", "subido", "subido_por", "es_actual_display")
    list_filter = ("paquete",)
    readonly_fields = (
        "paquete", "version", "estado", "fecha", "meta", "carpeta", "archivo_nombre",
        "tamano_bytes", "cantidad_archivos", "subido", "subido_por",
    )
    actions = ["volver_a_esta_version"]

    @admin.display(description="publicada", boolean=True)
    def es_actual_display(self, obj):
        return obj.es_actual

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        # No se puede borrar la versión publicada (el paquete quedaría vacío).
        if obj is not None and obj.es_actual:
            return False
        return super().has_delete_permission(request, obj)

    @admin.action(description="Volver a esta versión (publicarla de nuevo)")
    def volver_a_esta_version(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Elegí una sola versión.", messages.WARNING)
            return
        version = queryset.first()
        activar_version(version)
        self.message_user(request, f"Ahora está publicada la versión {version.version or version.pk} de {version.paquete.slug}.")
