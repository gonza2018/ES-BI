"""Paquetes del portal: dashboards y sitios estáticos privados, por organismo (grupo)."""
import shutil
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver


class Paquete(models.Model):
    TIPOS = [("dashboard", "Dashboard"), ("sitio", "Sitio")]
    ESTADOS = [("borrador", "Borrador"), ("en_revision", "En revisión"), ("aprobado", "Aprobado")]

    slug = models.SlugField("identificador", max_length=80, unique=True)
    titulo = models.CharField("título", max_length=200)
    tipo = models.CharField("tipo", max_length=20, choices=TIPOS, default="dashboard")
    organismo = models.CharField("organismo", max_length=200, blank=True)
    descripcion = models.TextField("descripción", blank=True)
    version = models.CharField("versión", max_length=40, blank=True)
    fecha = models.DateField("fecha", null=True, blank=True)
    estado = models.CharField("estado", max_length=20, choices=ESTADOS, default="borrador")
    grupos = models.ManyToManyField(
        Group,
        verbose_name="grupos con acceso",
        blank=True,
        related_name="paquetes",
        help_text="Solo los usuarios de estos grupos ven el paquete. El superusuario ve todo.",
    )
    publicado = models.BooleanField(
        "publicado", default=True, help_text="Desmarcar para ocultarlo a todos sin borrarlo."
    )
    version_actual = models.ForeignKey(
        "VersionPaquete", verbose_name="versión publicada", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    creado = models.DateTimeField("creado", auto_now_add=True)
    actualizado = models.DateTimeField("actualizado", auto_now=True)

    class Meta:
        verbose_name = "paquete"
        verbose_name_plural = "paquetes"
        ordering = ["-fecha", "titulo"]

    def __str__(self):
        return f"{self.titulo} ({self.slug})"

    @classmethod
    def visibles_para(cls, usuario):
        """Paquetes que el usuario puede ver: superusuario todo; el resto, publicados de sus grupos."""
        qs = cls.objects.filter(version_actual__isnull=False).select_related("version_actual")
        if usuario.is_superuser:
            return qs
        return qs.filter(publicado=True, grupos__in=usuario.groups.all()).distinct()

    @property
    def directorio(self):
        return self.version_actual.directorio if self.version_actual else None

    @property
    def tiene_miniatura(self):
        d = self.directorio
        return bool(d and (d / "miniatura.png").is_file())

    def descargas(self):
        """Archivos de descargas/ de la versión publicada: [(nombre, ruta relativa, bytes)]."""
        d = self.directorio
        carpeta = d / "descargas" if d else None
        if not carpeta or not carpeta.is_dir():
            return []
        from .paquetes import TIPOS_SERVIDOS  # evita import circular

        return [
            (f.name, f"descargas/{f.name}", f.stat().st_size)
            for f in sorted(carpeta.iterdir(), key=lambda x: x.name.lower())
            if f.is_file() and not f.is_symlink() and f.suffix.lower() in TIPOS_SERVIDOS
        ]


class VersionPaquete(models.Model):
    """Cada zip subido. La anterior queda como historial y se puede volver a ella."""

    paquete = models.ForeignKey(Paquete, on_delete=models.CASCADE, related_name="versiones")
    version = models.CharField("versión", max_length=40, blank=True)
    fecha = models.DateField("fecha", null=True, blank=True)
    estado = models.CharField("estado", max_length=20, choices=Paquete.ESTADOS, default="borrador")
    meta = models.JSONField("meta.json", default=dict)
    carpeta = models.CharField("carpeta", max_length=300, help_text="Relativa a PAQUETES_ROOT.")
    archivo_nombre = models.CharField("zip subido", max_length=255, blank=True)
    tamano_bytes = models.BigIntegerField("tamaño descomprimido", default=0)
    cantidad_archivos = models.PositiveIntegerField("archivos", default=0)
    subido = models.DateTimeField("subido", auto_now_add=True)
    subido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="subido por", null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        verbose_name = "versión de paquete"
        verbose_name_plural = "versiones de paquetes"
        ordering = ["-subido"]

    def __str__(self):
        return f"{self.paquete.slug} v{self.version or '?'} ({self.subido:%d/%m/%Y %H:%M})"

    @property
    def directorio(self):
        return Path(settings.PAQUETES_ROOT) / self.carpeta

    @property
    def es_actual(self):
        return self.paquete.version_actual_id == self.pk


def _borrar_carpeta(ruta):
    """Borra una carpeta solo si está dentro de PAQUETES_ROOT (nunca fuera)."""
    raiz = Path(settings.PAQUETES_ROOT).resolve()
    ruta = Path(ruta).resolve()
    if ruta != raiz and ruta.is_relative_to(raiz) and ruta.is_dir():
        shutil.rmtree(ruta, ignore_errors=True)


@receiver(post_delete, sender=VersionPaquete)
def borrar_archivos_version(sender, instance, **kwargs):
    _borrar_carpeta(instance.directorio)


@receiver(post_delete, sender=Paquete)
def borrar_archivos_paquete(sender, instance, **kwargs):
    _borrar_carpeta(Path(settings.PAQUETES_ROOT) / instance.slug)
