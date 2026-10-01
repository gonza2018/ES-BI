import os
import sqlite3
import sys
import tarfile
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from .ip_cliente import obtener_ip

LOGIN = "/portal/ingresar/"


class ObtenerIpTests(TestCase):
    def ip(self, **meta):
        return obtener_ip(RequestFactory().get("/", REMOTE_ADDR="10.0.0.5", **meta))

    def test_toma_la_ip_que_agrega_el_proxy_por_la_derecha(self):
        self.assertEqual(self.ip(HTTP_X_FORWARDED_FOR="200.1.1.1"), "200.1.1.1")
        # El cliente inventa una IP a la izquierda: se ignora
        self.assertEqual(self.ip(HTTP_X_FORWARDED_FOR="6.6.6.6, 200.1.1.1"), "200.1.1.1")

    @override_settings(IP_CLIENTE_PROXIES=2)
    def test_dos_proxies_de_confianza(self):
        self.assertEqual(self.ip(HTTP_X_FORWARDED_FOR="6.6.6.6, 200.1.1.1, 172.70.1.1"), "200.1.1.1")

    @override_settings(IP_CLIENTE_ENCABEZADO="HTTP_CF_CONNECTING_IP")
    def test_encabezado_de_un_solo_valor(self):
        self.assertEqual(self.ip(HTTP_CF_CONNECTING_IP="200.1.1.1", HTTP_X_FORWARDED_FOR="6.6.6.6"), "200.1.1.1")

    def test_sin_encabezado_o_invalido_usa_remote_addr(self):
        self.assertEqual(self.ip(), "10.0.0.5")
        self.assertEqual(self.ip(HTTP_X_FORWARDED_FOR="no-es-ip"), "10.0.0.5")


class BloqueoPorIpTests(TestCase):
    """5 intentos fallidos bloquean ese usuario DESDE ESA IP, no para todo el mundo."""

    def setUp(self):
        get_user_model().objects.create_user("eval@organismo.gob.ar", "clave-segura-123")

    def intentar(self, ip, clave="mala"):
        return self.client.post(
            LOGIN, {"username": "eval@organismo.gob.ar", "password": clave}, HTTP_X_FORWARDED_FOR=ip
        )

    def test_atacante_bloqueado_usuario_legitimo_no(self):
        for _ in range(5):
            self.intentar("6.6.6.6")
        self.assertEqual(self.intentar("6.6.6.6", "clave-segura-123").status_code, 429)
        r = self.intentar("200.1.1.1", "clave-segura-123")
        self.assertRedirects(r, reverse("portal:inicio"))

    def test_inventar_ips_a_la_izquierda_no_evita_el_bloqueo(self):
        for i in range(5):
            self.intentar(f"9.9.9.{i}, 6.6.6.6")
        self.assertEqual(self.intentar("1.2.3.4, 6.6.6.6", "clave-segura-123").status_code, 429)


class RespaldoTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.override = override_settings(DATA_DIR=Path(self.tmp.name))
        self.override.enable()
        base = Path(self.tmp.name)
        with closing(sqlite3.connect(base / "db.sqlite3")) as c:
            c.execute("create table t (x)")
            c.commit()
        (base / "paquetes_privados" / "demo").mkdir(parents=True)
        (base / "paquetes_privados" / "demo" / "index.html").write_text("<h1>demo</h1>")
        User = get_user_model()
        self.admin = User.objects.create_superuser("yo@gserelic.com", "clave-segura-123")
        self.staff = User.objects.create_user("staff@gserelic.com", "clave-segura-123", is_staff=True)

    def tearDown(self):
        self.override.disable()
        self.tmp.cleanup()

    def contenido(self, respuesta):
        ruta = Path(self.tmp.name) / "bajado.tar.gz"
        ruta.write_bytes(b"".join(respuesta.streaming_content))
        respuesta.close()
        with tarfile.open(ruta) as tar:
            return tar.getnames()

    @unittest.skipUnless(sys.platform.startswith("linux"), "usa /proc para listar archivos abiertos")
    def test_no_deja_archivos_abiertos(self):
        """Regresión: en Windows un archivo abierto no se puede borrar (WinError 32)."""
        from .respaldo import crear_respaldo

        crear_respaldo()
        abiertos = []
        for fd in os.listdir("/proc/self/fd"):
            try:
                ruta = os.readlink(f"/proc/self/fd/{fd}")
            except OSError:
                continue
            if ruta.startswith(self.tmp.name) or "(deleted)" in ruta and "db.sqlite3" in ruta:
                abiertos.append(ruta)
        self.assertEqual(abiertos, [])

    def test_anonimo_y_staff_no_pueden(self):
        self.assertEqual(self.client.get("/gestion/respaldo/").status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get("/gestion/respaldo/").status_code, 403)

    def test_superusuario_descarga(self):
        self.client.force_login(self.admin)
        r = self.client.get("/gestion/respaldo/")
        self.assertEqual(r.status_code, 200)
        nombres = self.contenido(r)
        self.assertIn("bases/db.sqlite3", nombres)
        self.assertIn("paquetes_privados/demo/index.html", nombres)

    def test_token(self):
        token = "t" * 40
        with override_settings(RESPALDO_TOKEN=token):
            self.assertEqual(self.client.get("/gestion/respaldo/", HTTP_AUTHORIZATION="Bearer otro").status_code, 403)
            r = self.client.get("/gestion/respaldo/", HTTP_AUTHORIZATION=f"Bearer {token}")
            self.assertEqual(r.status_code, 200)
            self.assertIn("bases/db.sqlite3", self.contenido(r))
        with override_settings(RESPALDO_TOKEN="corto"):  # token débil: deshabilitado
            self.assertEqual(self.client.get("/gestion/respaldo/", HTTP_AUTHORIZATION="Bearer corto").status_code, 403)

    def test_diagnostico_ip_solo_superusuario(self):
        self.assertEqual(self.client.get("/gestion/diagnostico-ip/").status_code, 403)
        self.client.force_login(self.admin)
        r = self.client.get("/gestion/diagnostico-ip/", HTTP_X_FORWARDED_FOR="6.6.6.6, 200.1.1.1")
        self.assertContains(r, "IP que usa el bloqueo por intentos fallidos: 200.1.1.1")
