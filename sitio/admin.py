from django.contrib import admin

from .models import Proyecto


@admin.register(Proyecto)
class ProyectoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "organismo", "anio", "publicado", "orden")
    list_editable = ("publicado", "orden")
    list_filter = ("publicado", "anio")
    search_fields = ("titulo", "organismo")
