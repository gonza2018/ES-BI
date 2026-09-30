from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse


class PortalAccesoTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user("eval@organismo.gob.ar", "clave-segura-123")
        self.usuario.groups.add(Group.objects.create(name="DGEyC SDE"))

    def test_anonimo_va_al_login(self):
        r = self.client.get(reverse("portal:inicio"))
        self.assertRedirects(r, reverse("portal:login") + "?next=" + reverse("portal:inicio"))

    def test_login_con_correo_en_mayusculas(self):
        r = self.client.post(reverse("portal:login"), {"username": "EVAL@organismo.gob.ar", "password": "clave-segura-123"})
        self.assertRedirects(r, reverse("portal:inicio"))
        r = self.client.get(reverse("portal:inicio"))
        self.assertContains(r, "DGEyC SDE")
        self.usuario.refresh_from_db()
        self.assertIsNotNone(self.usuario.last_login)  # queda registrado el último acceso

    def test_login_incorrecto(self):
        r = self.client.post(reverse("portal:login"), {"username": "eval@organismo.gob.ar", "password": "mala"})
        self.assertContains(r, "no son correctos")

    def test_bloqueo_por_fuerza_bruta(self):
        for _ in range(5):
            self.client.post(reverse("portal:login"), {"username": "eval@organismo.gob.ar", "password": "mala"})
        r = self.client.post(reverse("portal:login"), {"username": "eval@organismo.gob.ar", "password": "clave-segura-123"})
        self.assertEqual(r.status_code, 429)
        self.assertContains(r, "Acceso bloqueado", status_code=429)

    def test_logout_por_post(self):
        self.client.force_login(self.usuario)
        r = self.client.post(reverse("portal:logout"))
        self.assertRedirects(r, reverse("portal:login"))
        r = self.client.get(reverse("portal:inicio"))
        self.assertEqual(r.status_code, 302)
