from django.contrib import admin, messages
from django.utils.text import Truncator

from .models import MensajeContacto, Proyecto


@admin.register(Proyecto)
class ProyectoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "organismo", "anio", "publicado", "orden")
    list_editable = ("publicado", "orden")
    list_filter = ("publicado", "anio")
    search_fields = ("titulo", "organismo")


@admin.register(MensajeContacto)
class MensajeContactoAdmin(admin.ModelAdmin):
    list_display = ("recibido", "nombre", "email", "extracto", "leido", "aviso_enviado")
    list_display_links = ("recibido", "nombre")
    list_filter = ("leido", "aviso_enviado")
    search_fields = ("nombre", "email", "mensaje")
    readonly_fields = ("recibido", "nombre", "email", "mensaje", "aviso_enviado", "aviso_error")
    fields = ("recibido", "nombre", "email", "mensaje", "leido", "aviso_enviado", "aviso_error")
    actions = ["marcar_leidos", "reintentar_aviso"]
    date_hierarchy = "recibido"

    def has_add_permission(self, request):
        return False  # los mensajes solo llegan por el formulario

    @admin.display(description="mensaje")
    def extracto(self, obj):
        return Truncator(obj.mensaje).chars(80)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        # Abrir un mensaje lo marca como leído.
        MensajeContacto.objects.filter(pk=object_id, leido=False).update(leido=True)
        return super().change_view(request, object_id, form_url, extra_context)

    @admin.action(description="Marcar como leídos")
    def marcar_leidos(self, request, queryset):
        n = queryset.update(leido=True)
        self.message_user(request, f"{n} mensaje(s) marcados como leídos.")

    @admin.action(description="Reintentar el aviso por correo")
    def reintentar_aviso(self, request, queryset):
        from .views import avisar_mensaje

        ok = sum(avisar_mensaje(m) for m in queryset)
        nivel = messages.SUCCESS if ok == queryset.count() else messages.WARNING
        self.message_user(request, f"Avisos enviados: {ok} de {queryset.count()}.", nivel)
