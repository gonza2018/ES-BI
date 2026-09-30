from django.conf import settings
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path, re_path
from django.views.static import serve

from sitio.sitemaps import SitioSitemap

from . import operacion

admin.site.site_header = "ES & BI · Administración"
admin.site.site_title = "ES & BI"
admin.site.index_title = "Panel"

urlpatterns = [
    path("gestion/respaldo/", operacion.descargar_respaldo, name="descargar_respaldo"),
    path("gestion/diagnostico-ip/", operacion.diagnostico_ip, name="diagnostico_ip"),
    path("gestion/", admin.site.urls),
    path("portal/", include("portal.urls")),
    path("sitemap.xml", sitemap, {"sitemaps": {"sitio": SitioSitemap}}, name="sitemap"),
    # Medios PÚBLICOS: solo imágenes de fichas de proyectos.
    # Los paquetes privados del portal viven en otro directorio y no se sirven acá.
    re_path(r"^media/(?P<path>proyectos/.+)$", serve, {"document_root": settings.MEDIA_ROOT}),
    path("", include("sitio.urls")),
]
