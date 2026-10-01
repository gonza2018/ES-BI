from django.db import models


class Proyecto(models.Model):
    """Ficha pública de un trabajo realizado. Sin datos sensibles: solo lo que
    se puede mostrar a cualquier visitante del sitio."""

    titulo = models.CharField("título", max_length=200)
    organismo = models.CharField("organismo o cliente", max_length=200)
    anio = models.PositiveSmallIntegerField("año")
    resumen = models.TextField("resumen", max_length=400, blank=True, help_text="Una o dos oraciones, opcional.")
    imagen = models.ImageField("imagen", upload_to="proyectos/", blank=True)
    texto_alternativo = models.CharField(
        "texto alternativo de la imagen",
        max_length=200,
        blank=True,
        help_text="Qué muestra la imagen, para lectores de pantalla y buscadores.",
    )
    publicado = models.BooleanField("publicado", default=False)
    orden = models.PositiveSmallIntegerField("orden", default=0, help_text="Menor número = aparece primero.")

    class Meta:
        verbose_name = "proyecto"
        verbose_name_plural = "proyectos"
        ordering = ["orden", "-anio", "titulo"]

    def __str__(self):
        return f"{self.titulo} ({self.organismo}, {self.anio})"


class MensajeContacto(models.Model):
    """Mensaje recibido por el formulario de contacto.

    Se guarda SIEMPRE antes de intentar el aviso por correo: si el correo falla,
    el mensaje no se pierde y queda en /gestion/.
    """

    nombre = models.CharField("nombre", max_length=120)
    email = models.EmailField("correo")
    mensaje = models.TextField("mensaje")
    recibido = models.DateTimeField("recibido", auto_now_add=True)
    leido = models.BooleanField("leído", default=False)
    aviso_enviado = models.BooleanField("aviso por correo enviado", default=False)
    aviso_error = models.TextField("error del aviso", blank=True)

    class Meta:
        verbose_name = "mensaje de contacto"
        verbose_name_plural = "mensajes de contacto"
        ordering = ["-recibido"]

    def __str__(self):
        return f"{self.nombre} <{self.email}> ({self.recibido:%d/%m/%Y %H:%M})"
