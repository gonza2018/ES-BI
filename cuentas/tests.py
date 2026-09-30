from django.contrib.auth import get_user_model
from django.test import TestCase


class UsuarioTests(TestCase):
    def test_crear_usuario_por_correo_normaliza(self):
        u = get_user_model().objects.create_user("Evaluador@Organismo.GOB.AR", "clave-segura-123")
        self.assertEqual(u.email, "evaluador@organismo.gob.ar")
        self.assertTrue(u.check_password("clave-segura-123"))
        self.assertFalse(u.is_staff)

    def test_superusuario(self):
        u = get_user_model().objects.create_superuser("yo@gserelic.com", "clave-segura-123")
        self.assertTrue(u.is_staff and u.is_superuser)

    def test_correo_obligatorio(self):
        with self.assertRaises(ValueError):
            get_user_model().objects.create_user("", "x")
