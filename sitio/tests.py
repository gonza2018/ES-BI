from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import MensajeContacto, Proyecto

DATOS = {"nombre": "Ana Pérez", "email": "ana@ejemplo.com", "mensaje": "Quisiera una cotización."}


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="web@gserelic.com",
    CONTACTO_DESTINATARIOS=["gonzalo@ejemplo.com"],
)
class ContactoTests(TestCase):
    def test_envio_correcto(self):
        r = self.client.post(reverse("sitio:contacto"), DATOS)
        self.assertRedirects(r, reverse("sitio:contacto_enviado"))
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        self.assertEqual(m.from_email, "web@gserelic.com")  # nunca el correo del visitante
        self.assertEqual(m.reply_to, ["ana@ejemplo.com"])
        self.assertEqual(m.to, ["gonzalo@ejemplo.com"])
        self.assertIn("Quisiera una cotización.", m.body)

    def test_campo_trampa_no_envia(self):
        r = self.client.post(reverse("sitio:contacto"), {**DATOS, "sitio_web": "http://spam"})
        self.assertRedirects(r, reverse("sitio:contacto_enviado"))
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(MensajeContacto.objects.count(), 0)  # el spam no se guarda

    def test_datos_invalidos(self):
        r = self.client.post(reverse("sitio:contacto"), {**DATOS, "email": "no-es-correo"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="127.0.0.1", EMAIL_PORT=1)
    def test_falla_smtp_el_mensaje_igual_queda_guardado(self):
        r = self.client.post(reverse("sitio:contacto"), DATOS)
        self.assertRedirects(r, reverse("sitio:contacto_enviado"))
        m = MensajeContacto.objects.get()
        self.assertEqual(m.mensaje, "Quisiera una cotización.")
        self.assertFalse(m.aviso_enviado)
        self.assertIn("SMTP", m.aviso_error)

    def test_envio_correcto_guarda_y_marca_aviso(self):
        self.client.post(reverse("sitio:contacto"), DATOS)
        m = MensajeContacto.objects.get()
        self.assertTrue(m.aviso_enviado)
        self.assertFalse(m.leido)

    def test_si_no_se_puede_guardar_ni_enviar_muestra_error(self):
        from unittest import mock

        with mock.patch.object(MensajeContacto.objects, "create", side_effect=Exception("disco")), \
                mock.patch("sitio.views.enviar_contacto", side_effect=Exception("sin correo")):
            r = self.client.post(reverse("sitio:contacto"), DATOS)
        self.assertEqual(r.status_code, 503)
        self.assertContains(r, "No se pudo enviar el mensaje", status_code=503)

    def test_get_redirige_a_seccion(self):
        r = self.client.get(reverse("sitio:contacto"))
        self.assertRedirects(r, reverse("sitio:inicio") + "#contacto", fetch_redirect_response=False)


class PaginasTests(TestCase):
    def test_inicio(self):
        r = self.client.get("/")
        self.assertContains(r, "Estadísticas Económicas e Inteligencia de Negocios")
        self.assertContains(r, 'id="nosotros"')
        self.assertContains(r, "Acceso clientes")
        self.assertNotContains(r, 'id="proyectos"')  # sin fichas publicadas no se muestra
        self.assertIn("Content-Security-Policy", r.headers)

    def test_proyectos_publicados(self):
        Proyecto.objects.create(titulo="Tablero de empleo", organismo="DGEyC SDE", anio=2026, publicado=True)
        Proyecto.objects.create(titulo="Borrador oculto", organismo="X", anio=2026, publicado=False)
        r = self.client.get("/")
        self.assertContains(r, "Tablero de empleo")
        self.assertNotContains(r, "Borrador oculto")

    def test_robots_y_sitemap(self):
        r = self.client.get("/robots.txt")
        self.assertContains(r, "Disallow: /portal/")
        r = self.client.get("/sitemap.xml")
        self.assertEqual(r.status_code, 200)

    @override_settings(HOST_CANONICO="www.gserelic.com", REDIRIGIR_A_CANONICO=["gserelic.com"],
                       ALLOWED_HOSTS=["gserelic.com", "www.gserelic.com"])
    def test_apex_redirige_a_www(self):
        r = self.client.get("/?a=1", HTTP_HOST="gserelic.com")
        self.assertEqual(r.status_code, 301)
        self.assertEqual(r["Location"], "https://www.gserelic.com/?a=1")
        r = self.client.get("/", HTTP_HOST="www.gserelic.com")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '<link rel="canonical" href="https://www.gserelic.com/">', html=False)

    def test_paquetes_privados_no_accesibles_por_media(self):
        r = self.client.get("/media/paquetes_privados/algo/index.html")
        self.assertEqual(r.status_code, 404)


class ContenidoTests(TestCase):
    def test_servicios_con_ventanas(self):
        r = self.client.get("/")
        from .contenido import SERVICIOS

        for s in SERVICIOS:
            self.assertContains(r, f'data-bs-target="#modal-{s["id"]}"')
            self.assertContains(r, f'id="modal-{s["id"]}"')
        self.assertContains(r, "carruselServicios")
        self.assertContains(r, 'href="/cv/"')

    def test_pagina_cv(self):
        r = self.client.get("/cv/")
        self.assertContains(r, "Hola, soy Gonzalo Sereno")
        self.assertContains(r, "Gonzalo_Sereno_CV_Resumen.pdf")
        # Sin recursos externos: todo local (compatible con la CSP estricta)
        self.assertNotContains(r, "cdn.jsdelivr.net")
        self.assertNotContains(r, "fonts.googleapis.com")

    def test_rutas_del_sitio_anterior(self):
        self.assertRedirects(self.client.get("/cv"), "/cv/", status_code=301)
        self.assertRedirects(self.client.get("/send_mail"), "/", status_code=301)

    def test_manifest_y_sitemap_incluye_cv(self):
        self.assertContains(self.client.get("/sitemap.xml"), "/cv/")


class FormspreeTests(TestCase):
    @override_settings(FORMSPREE_ID="abc123")
    def test_envio_por_formspree(self):
        from unittest import mock

        respuesta = mock.MagicMock(status=200)
        respuesta.__enter__.return_value = respuesta
        with mock.patch("sitio.views.urllib.request.urlopen", return_value=respuesta) as abrir:
            r = self.client.post(reverse("sitio:contacto"), DATOS)
        self.assertRedirects(r, reverse("sitio:contacto_enviado"))
        pedido = abrir.call_args[0][0]
        self.assertEqual(pedido.full_url, "https://formspree.io/f/abc123")
        import json

        self.assertEqual(pedido.get_header("User-agent"), "gserelic.com formulario de contacto")
        self.assertEqual(pedido.get_header("Origin"), "http://testserver")
        cuerpo = json.loads(pedido.data)
        self.assertEqual(cuerpo["email"], "ana@ejemplo.com")
        self.assertEqual(cuerpo["message"], "Quisiera una cotización.")

    @override_settings(FORMSPREE_ID="abc123")
    def test_rechazo_de_formspree_queda_en_el_log_con_el_motivo(self):
        import io
        import urllib.error
        from unittest import mock

        error = urllib.error.HTTPError(
            "https://formspree.io/f/abc123", 403, "Forbidden", {}, io.BytesIO(b'{"error":"Form not active"}')
        )
        with mock.patch("sitio.views.urllib.request.urlopen", side_effect=error), \
                self.assertLogs("sitio.views", level="ERROR") as registro:
            r = self.client.post(reverse("sitio:contacto"), DATOS)
        self.assertRedirects(r, reverse("sitio:contacto_enviado"))
        self.assertIn("Form not active", MensajeContacto.objects.get().aviso_error)
        texto = "\n".join(registro.output)
        self.assertIn("modo: Formspree (abc123)", texto)
        self.assertIn("HTTP 403", texto)
        self.assertIn("Form not active", texto)

    @override_settings(FORMSPREE_ID="abc123")
    def test_falla_formspree_se_reintenta_desde_el_admin(self):
        from unittest import mock

        from django.contrib.auth import get_user_model

        with mock.patch("sitio.views.urllib.request.urlopen", side_effect=OSError("sin red")):
            self.client.post(reverse("sitio:contacto"), DATOS)
        m = MensajeContacto.objects.get()
        self.assertFalse(m.aviso_enviado)

        admin = get_user_model().objects.create_superuser("yo@gserelic.com", "clave-segura-123")
        self.client.force_login(admin)
        respuesta = mock.MagicMock(status=200)
        respuesta.__enter__.return_value = respuesta
        with mock.patch("sitio.views.urllib.request.urlopen", return_value=respuesta):
            self.client.post(
                "/gestion/sitio/mensajecontacto/",
                {"action": "reintentar_aviso", "_selected_action": [m.pk]},
            )
        m.refresh_from_db()
        self.assertTrue(m.aviso_enviado)
        self.assertEqual(m.aviso_error, "")

    def test_abrir_en_el_admin_lo_marca_leido(self):
        from django.contrib.auth import get_user_model

        m = MensajeContacto.objects.create(nombre="A", email="a@b.com", mensaje="hola")
        self.client.force_login(get_user_model().objects.create_superuser("yo@gserelic.com", "clave-segura-123"))
        self.assertEqual(self.client.get(f"/gestion/sitio/mensajecontacto/{m.pk}/change/").status_code, 200)
        m.refresh_from_db()
        self.assertTrue(m.leido)


class WhatsappTests(TestCase):
    @override_settings(WHATSAPP_NUMERO="")
    def test_sin_numero_no_hay_botones(self):
        r = self.client.get("/")
        self.assertNotContains(r, "wa.me")
        self.assertContains(r, "Envíenos un mensaje")

    @override_settings(WHATSAPP_NUMERO="5493851234567")
    def test_con_numero(self):
        r = self.client.get("/")
        self.assertContains(r, "https://wa.me/5493851234567", count=2)  # pie y botón flotante
