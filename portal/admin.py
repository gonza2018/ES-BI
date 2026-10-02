from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.shortcuts import redirect, render
from django.template.defaultfilters import filesizeformat
from django.urls import path, reverse
from django.utils.html import format_html

from .forms import SubirPaqueteForm
from .accesos import confirmar_carga, crear_avisos, enviar_aviso_correo, url_mailto, url_whatsapp
from .models import Aviso, Paquete, VersionPaquete
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
        ("Datos (vienen de meta.json)", {"fields": ("estado", "descripcion", "resumen", "novedades", "tipo", "organismo", "version", "fecha")}),
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
                # Confirmación para Gonzalo. Si el correo falla, la carga igual queda hecha.
                try:
                    confirmar_carga(request, paquete, es_actualizacion=not creado)
                except Exception:
                    import logging

                    logging.getLogger(__name__).exception("Falló la confirmación de carga de %s", paquete.slug)
                    messages.warning(request, "El paquete se cargó, pero no se pudo enviar el correo de confirmación.")
                if form.cleaned_data["notificar"] and not creado:
                    avisos = crear_avisos(request, paquete)
                    correos = sum(1 for a in avisos if a.medio == "correo" and a.estado == "enviado")
                    wsp = sum(1 for a in avisos if a.medio == "whatsapp")
                    pendientes = sum(1 for a in avisos if a.estado != "enviado")
                    messages.info(
                        request,
                        f"Avisos: {len(avisos)} ({correos} correos enviados, {wsp} por WhatsApp para enviar con un clic). "
                        f"Pendientes: {pendientes}.",
                    )
                    if avisos:
                        return redirect(
                            reverse("admin:portal_aviso_changelist") + f"?paquete__id__exact={paquete.pk}&estado__exact=pendiente"
                        )
                elif form.cleaned_data["notificar"] and creado:
                    messages.info(request, "Es un tablero nuevo: no se generan avisos de actualización (usá la carta de acceso).")
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


class RedireccionExterna(HttpResponseRedirect):
    allowed_schemes = ["https", "mailto"]


@admin.register(Aviso)
class AvisoAdmin(admin.ModelAdmin):
    list_display = ("destinatario", "boton", "medio", "estado", "tablero", "version_txt", "enviado")
    list_filter = ("estado", "medio", "paquete")
    search_fields = ("usuario__nombre", "usuario__email", "paquete__titulo")
    readonly_fields = ("paquete", "version", "usuario", "medio", "estado", "asunto", "mensaje", "creado", "enviado", "detalle")
    actions = ["marcar_enviado", "reintentar_correo"]

    def has_add_permission(self, request):
        return False

    @admin.display(description="destinatario")
    def destinatario(self, obj):
        return obj.usuario.destinatario

    @admin.display(description="tablero")
    def tablero(self, obj):
        return obj.paquete.slug

    @admin.display(description="versión")
    def version_txt(self, obj):
        return obj.version.version if obj.version else "—"

    @admin.display(description="acción")
    def boton(self, obj):
        if obj.estado == "enviado":
            return "—"
        url = reverse("admin:portal_aviso_abrir", args=[obj.pk])
        texto = "Enviar por WhatsApp" if obj.medio == "whatsapp" else "Enviar por correo"
        return format_html('<a class="button" href="{}" target="_blank" rel="noopener">{}</a>', url, texto)

    def get_urls(self):
        propias = [path("<int:pk>/abrir/", self.admin_site.admin_view(self.abrir_view), name="portal_aviso_abrir")]
        return propias + super().get_urls()

    def abrir_view(self, request, pk):
        """Registra el envío y abre WhatsApp (o el programa de correo) con el mensaje escrito.
        En WhatsApp no hay confirmación de lectura: se registra el clic."""
        if not self.has_change_permission(request):
            return redirect("admin:index")
        aviso = Aviso.objects.select_related("usuario").get(pk=pk)
        destino = url_whatsapp(aviso) if aviso.medio == "whatsapp" else url_mailto(aviso)
        aviso.estado, aviso.enviado = "enviado", timezone.now()
        aviso.detalle = "Abierto con un clic desde el panel."
        aviso.save(update_fields=["estado", "enviado", "detalle"])
        return RedireccionExterna(destino)

    @admin.action(description="Marcar como enviado")
    def marcar_enviado(self, request, queryset):
        n = queryset.exclude(estado="enviado").update(estado="enviado", enviado=timezone.now())
        self.message_user(request, f"{n} aviso(s) marcados como enviados.")

    @admin.action(description="Reintentar el correo (avisos por correo)")
    def reintentar_correo(self, request, queryset):
        ok = sum(enviar_aviso_correo(a) for a in queryset.filter(medio="correo").exclude(estado="enviado"))
        self.message_user(request, f"Correos enviados: {ok}.")
