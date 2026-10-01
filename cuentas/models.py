from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, UserManager
from django.db import models
from django.utils import timezone


class UsuarioManager(UserManager):
    """Manager que usa el correo como identificador en lugar de un username."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("El correo es obligatorio.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError("El superusuario necesita is_staff=True e is_superuser=True.")
        return self._create_user(email, password, **extra_fields)

    def get_by_natural_key(self, email):
        return self.get(email__iexact=email)


class Usuario(AbstractBaseUser, PermissionsMixin):
    """Usuario del portal. El correo es el identificador; no hay registro público.

    `last_login` (heredado) registra el último acceso: sirve para saber si
    los evaluadores de un organismo abrieron el portal.
    """

    email = models.EmailField("correo electrónico", unique=True)
    nombre = models.CharField("nombre", max_length=150, blank=True)
    organismo = models.CharField(
        "organismo", max_length=150, blank=True, help_text="Solo informativo. Los permisos se dan con los grupos."
    )
    is_staff = models.BooleanField(
        "acceso al admin", default=False, help_text="Permite entrar al panel de administración."
    )
    is_active = models.BooleanField(
        "activo", default=True, help_text="Desmarcar en lugar de borrar para quitar el acceso."
    )
    date_joined = models.DateTimeField("alta", default=timezone.now)

    objects = UsuarioManager()

    EMAIL_FIELD = "email"
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["email"]

    def __str__(self):
        return self.email

    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email).lower()

    def get_full_name(self):
        return self.nombre or self.email

    def get_short_name(self):
        return self.nombre.split(" ")[0] if self.nombre else self.email
