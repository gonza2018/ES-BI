from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class SitioSitemap(Sitemap):
    protocol = "https"
    changefreq = "monthly"

    def items(self):
        return ["sitio:inicio", "sitio:cv"]

    def location(self, item):
        return reverse(item)
