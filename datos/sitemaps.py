from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from portal.models import Paquete


class DatosSitemap(Sitemap):
    """/datos/ y cada /datos/<slug>/ de los paquetes públicos. Los privados no aparecen."""

    protocol = "https"
    changefreq = "weekly"

    def items(self):
        paquetes = list(Paquete.publicos())
        return ([None] if paquetes else []) + paquetes  # None = el listado /datos/

    def location(self, item):
        if item is None:
            return reverse("datos:lista")
        return reverse("datos:visor", args=[item.slug])

    def lastmod(self, item):
        if item is None:
            fechas = [p.fecha_actualizacion for p in Paquete.publicos() if p.fecha_actualizacion]
            return max(fechas) if fechas else None
        return item.fecha_actualizacion
