"""Tests del Paso 2B: carta de acceso, enlace personal, confirmación y avisos."""
import hashlib
import io
import re
from datetime import timedelta
from unittest import mock, skipUnless

from django.contrib.auth.models import Group
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from cuentas.models import Usuario

from .accesos import buscar_acceso, generar_acceso, hash_token, ruta_acceso
from .carta import generar_carta, imagen_qr
from .models import AccesoPersonal, Aviso, Paquete
from .paquetes import instalar
from .tests_paquetes import META, BasePaquetes, archivos_base, hacer_zip

try:
    import pypdf
    import zxingcpp
    from PIL import Image

    HAY_HERRAMIENTAS_PDF = True
except ImportError:  # dependencias solo de desarrollo (requirements-dev.txt)
    HAY_HERRAMIENTAS_PDF = False

META_V12 = {**META, "version": "1.2", "resumen": "Resumen formal del tablero.", "novedades": "Se corrigió el ITAE."}


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", HOST_CANONICO="www.gserelic.com")
class BaseAccesos(BasePaquetes):
    def setUp(self):
        super().setUp()
        self.paquete = self.subir()
        self.cliente = Usuario.objects.create_user(
            "ana@dgeyc.gob.ar", None, nombre="Ana Pérez", tratamiento="Lic.", organismo="DGEyC SDE",
        )
        self.cliente.groups.add(self.grupo)

    def carta(self, usuario=None, restablecer=False):
        token = generar_acceso(usuario or self.cliente, self.paquete, restablecer)
        return token, ruta_acceso(token, "pbg-sde")


class EnlacePrimeraVezTests(BaseAccesos):
    def test_sin_contrasena_crea_contrasena_inicia_sesion_y_abre_el_tablero(self):
        _, url = self.carta()
        r = self.client.get(url)
        self.assertContains(r, "Le damos la bienvenida, Lic. Ana Pérez")
        self.assertContains(r, "Guarde su contraseña por escrito")
        self.assertContains(r, "Sus datos de contacto se usan solo para enviarle este tablero")
        self.assertNotContains(r, "ana@dgeyc.gob.ar")  # el correo no se muestra
        # same-origin y NO no-referrer: con no-referrer el navegador manda Origin: null y el CSRF falla
        self.assertEqual(r["Referrer-Policy"], "same-origin")
        r = self.client.post(url, {"new_password1": "una-clave-larga-1", "new_password2": "una-clave-larga-1"})
        self.assertRedirects(r, "/portal/tablero/pbg-sde/")
        r = self.client.get("/portal/tablero/pbg-sde/")
        self.assertContains(r, "Tablero preparado para Lic. Ana Pérez")
        self.assertContains(r, "Cerrar sesión")
        self.cliente.refresh_from_db()
        self.assertTrue(self.cliente.check_password("una-clave-larga-1"))

    def test_formulario_con_csrf_y_origen_como_un_navegador(self):
        from django.test import Client

        navegador = Client(enforce_csrf_checks=True)
        _, url = self.carta()
        r = navegador.get(url)
        token_csrf = r.cookies["csrftoken"].value
        r = navegador.post(url, {"new_password1": "una-clave-larga-1", "new_password2": "una-clave-larga-1",
                                 "csrfmiddlewaretoken": token_csrf}, HTTP_ORIGIN="http://testserver")
        self.assertRedirects(r, "/portal/tablero/pbg-sde/", fetch_redirect_response=False)
        # Con Origin "null" (lo que manda el navegador bajo no-referrer) Django lo rechaza:
        _, url = self.carta(restablecer=True)
        r = navegador.post(url, {"new_password1": "otra-clave-larga-2", "new_password2": "otra-clave-larga-2",
                                 "csrfmiddlewaretoken": token_csrf}, HTTP_ORIGIN="null")
        self.assertEqual(r.status_code, 403)

    def test_contrasena_corta_o_distinta_se_rechaza(self):
        _, url = self.carta()
        r = self.client.post(url, {"new_password1": "corta", "new_password2": "corta"})
        self.assertEqual(r.status_code, 200)
        r = self.client.post(url, {"new_password1": "una-clave-larga-1", "new_password2": "otra-clave-larga-2"})
        self.assertEqual(r.status_code, 200)
        self.cliente.refresh_from_db()
        self.assertFalse(self.cliente.has_usable_password())

    def test_enlace_vencido(self):
        _, url = self.carta()
        AccesoPersonal.objects.update(creado=timezone.now() - timedelta(days=8))
        r = self.client.get(url)
        self.assertEqual(r.status_code, 410)
        self.assertContains(r, "Este enlace venció. Solicite uno nuevo al Lic. en Economía Gonzalo Javier Sereno - CPCESE M. 22.", status_code=410)
        self.client.post(url, {"new_password1": "una-clave-larga-1", "new_password2": "una-clave-larga-1"})
        self.cliente.refresh_from_db()
        self.assertFalse(self.cliente.has_usable_password())

    def test_seis_dias_todavia_sirve(self):
        _, url = self.carta()
        AccesoPersonal.objects.update(creado=timezone.now() - timedelta(days=6))
        self.assertEqual(self.client.get(url).status_code, 200)


class EnlaceConContrasenaTests(BaseAccesos):
    def setUp(self):
        super().setUp()
        _, self.url = self.carta()
        self.cliente.set_password("una-clave-larga-1")
        self.cliente.save()

    def test_pide_solo_contrasena(self):
        r = self.client.get(self.url)
        self.assertContains(r, "Lic. Ana Pérez, ingrese su contraseña.")
        self.assertContains(r, 'name="password"')
        self.assertNotContains(r, 'name="username"')
        r = self.client.post(self.url, {"password": "una-clave-larga-1"})
        self.assertRedirects(r, "/portal/tablero/pbg-sde/")

    def test_no_vence_si_ya_creo_la_contrasena(self):
        AccesoPersonal.objects.update(creado=timezone.now() - timedelta(days=60))
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_cinco_errores_bloquean(self):
        for _ in range(5):
            r = self.client.post(self.url, {"password": "mala"}, HTTP_X_FORWARDED_FOR="6.6.6.6")
        r = self.client.post(self.url, {"password": "una-clave-larga-1"}, HTTP_X_FORWARDED_FOR="6.6.6.6")
        self.assertEqual(r.status_code, 429)
        # El bloqueo también vale para el login general con ese correo, desde esa IP
        r = self.client.post("/portal/ingresar/", {"username": "ana@dgeyc.gob.ar", "password": "una-clave-larga-1"},
                             HTTP_X_FORWARDED_FOR="6.6.6.6")
        self.assertEqual(r.status_code, 429)


class CartasYTokensTests(BaseAccesos):
    def test_carta_nueva_invalida_el_enlace_anterior(self):
        _, viejo = self.carta()
        _, nuevo = self.carta()
        self.assertEqual(self.client.get(viejo).status_code, 404)
        self.assertEqual(self.client.get(nuevo).status_code, 200)
        self.assertEqual(AccesoPersonal.objects.count(), 1)

    def test_restablecer_borra_la_contrasena_y_cierra_sesiones(self):
        self.cliente.set_password("una-clave-larga-1")
        self.cliente.save()
        self.client.force_login(self.cliente)
        self.assertEqual(self.client.get("/portal/").status_code, 200)
        self.carta(restablecer=True)
        self.cliente.refresh_from_db()
        self.assertFalse(self.cliente.has_usable_password())
        self.assertEqual(self.client.get("/portal/").status_code, 302)  # su sesión se cerró

    def test_carta_de_otro_tablero_sin_restablecer_conserva_la_contrasena(self):
        self.cliente.set_password("una-clave-larga-1")
        self.cliente.save()
        self.carta(restablecer=False)
        self.cliente.refresh_from_db()
        self.assertTrue(self.cliente.check_password("una-clave-larga-1"))

    def test_token_invalido_de_otro_usuario_inactivo_o_slug_ajeno_404(self):
        token, url = self.carta()
        self.assertEqual(self.client.get(ruta_acceso("token-que-no-existe", "pbg-sde")).status_code, 404)
        # slug fuera de sus grupos
        otro = instalar(hacer_zip(archivos_base({**META, "slug": "cfi-matriz", "organismo": "CFI"})), self.admin)[0]
        self.assertEqual(self.client.get(ruta_acceso(token, otro.slug)).status_code, 404)
        # token de otro usuario: identifica a ESE usuario, no da acceso a lo que él no ve
        ajeno = Usuario.objects.create_user("x@cfi.org.ar", None, nombre="X")
        ajeno.groups.add(self.otro_grupo)
        token_ajeno, _ = generar_acceso(ajeno, otro), None
        self.assertEqual(self.client.get(ruta_acceso(token_ajeno, "pbg-sde")).status_code, 404)
        # usuario inactivo
        Usuario.objects.filter(pk=self.cliente.pk).update(is_active=False)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_en_la_base_no_queda_el_token_en_claro(self):
        token, _ = self.carta()
        registro = AccesoPersonal.objects.get()
        self.assertEqual(registro.token_hash, hashlib.sha256(token.encode()).hexdigest())
        self.assertNotIn(token, str(AccesoPersonal.objects.values().get()))
        self.assertEqual(buscar_acceso(token), registro)
        self.assertEqual(len(token), 43)  # token_urlsafe(32)

    def test_no_se_generan_cartas_para_administradores(self):
        with self.assertRaises(ValueError):
            generar_acceso(self.admin, self.paquete)
        self.client.force_login(self.admin)
        r = self.client.get(f"/gestion/cuentas/usuario/{self.admin.pk}/carta/")
        self.assertRedirects(r, f"/gestion/cuentas/usuario/{self.admin.pk}/change/")
        self.assertTrue(self.admin.has_usable_password())


@skipUnless(HAY_HERRAMIENTAS_PDF, "instalar requirements-dev.txt (pypdf, zxing-cpp) para verificar el PDF y el QR")
class CartaPdfTests(BaseAccesos):
    def test_carta_desde_el_admin_contiene_el_enlace_y_el_qr_lo_decodifica(self):
        self.client.force_login(self.admin)
        r = self.client.post(f"/gestion/cuentas/usuario/{self.cliente.pk}/carta/", {"paquete": self.paquete.pk})
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertIn('filename="Acceso_pbg-sde_perez.pdf"', r["Content-Disposition"])
        lector = pypdf.PdfReader(io.BytesIO(r.content))
        texto = "".join(p.extract_text() for p in lector.pages)
        enlace = re.search(r"https://www\.gserelic\.com/portal/acceso/\S+", re.sub(r"\s+", "", texto)).group(0)
        enlace = enlace[: enlace.index("/pbg-sde/") + len("/pbg-sde/")]
        # El enlace del texto funciona (es el del token vigente)
        self.assertEqual(buscar_acceso(enlace.split("/")[-3]).usuario, self.cliente)
        for esperado in ("Lic. Ana Pérez", "DGEyC SDE", "S / D", "De mi mayor consideración", "CPCESE M. 22",
                         "Lic. en Economía Gonzalo Javier Sereno", "Economía de Santiago del Estero 2019–2024"):
            self.assertIn(esperado, " ".join(texto.split()))  # el PDF parte los renglones
        # El QR (imagen del PDF) decodifica exactamente al mismo enlace
        imagenes = [img for p in lector.pages for img in p.images]
        self.assertEqual(len(imagenes), 1)
        decodificado = zxingcpp.read_barcodes(Image.open(io.BytesIO(imagenes[0].data)))
        self.assertEqual(decodificado[0].text, enlace)

    def test_qr_y_fecha_en_letras(self):
        from datetime import date

        from .carta import fecha_en_letras

        self.assertEqual(fecha_en_letras(date(2026, 10, 1)), "1 de octubre de 2026")
        decod = zxingcpp.read_barcodes(Image.open(io.BytesIO(imagen_qr("https://x.test/a"))))
        self.assertEqual(decod[0].text, "https://x.test/a")

    def test_usa_el_resumen_del_meta(self):
        paquete = self.subir(archivos_base(META_V12))
        pdf = generar_carta(self.cliente, paquete, "https://www.gserelic.com/portal/acceso/x/pbg-sde/")
        texto = "".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)
        self.assertIn("Resumen formal del tablero.", " ".join(texto.split()))


class AvisosTests(BaseAccesos):
    def setUp(self):
        super().setUp()
        self.con_celular = Usuario.objects.create_user("juan@dgeyc.gob.ar", None, nombre="Juan Gómez",
                                                       tratamiento="Ing.", celular="+5493854123456")
        self.con_celular.groups.add(self.grupo)
        self.token, _ = self.carta()  # el aviso NUNCA debe llevar este token
        mail.outbox.clear()

    def subir_v12(self, notificar=True):
        self.client.force_login(self.admin)
        return self.client.post(
            "/gestion/portal/paquete/subir/",
            {"archivo": hacer_zip(archivos_base(META_V12)), "notificar": "on" if notificar else ""},
        )

    def test_version_nueva_con_notificar(self):
        r = self.subir_v12()
        self.assertRedirects(r, f"/gestion/portal/aviso/?paquete__id__exact={self.paquete.pk}&estado__exact=pendiente",
                             fetch_redirect_response=False)
        wsp = Aviso.objects.get(usuario=self.con_celular)
        correo = Aviso.objects.get(usuario=self.cliente)
        self.assertEqual((wsp.medio, wsp.estado), ("whatsapp", "pendiente"))
        self.assertEqual((correo.medio, correo.estado), ("correo", "enviado"))
        self.assertFalse(Aviso.objects.filter(usuario=self.admin).exists())  # administradores no
        # Texto del aviso
        self.assertTrue(wsp.mensaje.startswith("Ing. Juan Gómez:\n"))
        self.assertIn("(versión 1.2)", wsp.mensaje)
        self.assertIn("Se corrigió el ITAE.", wsp.mensaje)
        self.assertIn("https://www.gserelic.com/portal/tablero/pbg-sde/", wsp.mensaje)
        self.assertTrue(wsp.mensaje.rstrip().endswith("Lic. en Economía Gonzalo Javier Sereno\nCPCESE M. 22"))
        # NUNCA el token ni el enlace de acceso
        aviso_correo = [m for m in mail.outbox if m.to == ["ana@dgeyc.gob.ar"]][0]
        for texto in (wsp.mensaje, correo.mensaje, aviso_correo.body):
            self.assertNotIn(self.token, texto)
            self.assertNotIn("/portal/acceso/", texto)

    def test_sin_notificar_no_genera_avisos(self):
        self.subir_v12(notificar=False)
        self.assertFalse(Aviso.objects.exists())

    def test_boton_whatsapp_abre_wa_me_y_registra(self):
        self.subir_v12()
        aviso = Aviso.objects.get(medio="whatsapp")
        r = self.client.get(f"/gestion/portal/aviso/{aviso.pk}/abrir/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith("https://wa.me/5493854123456?text=Ing.%20Juan%20G%C3%B3mez%3A%0A"))
        aviso.refresh_from_db()
        self.assertEqual(aviso.estado, "enviado")
        self.assertIsNotNone(aviso.enviado)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST_USER="", EMAIL_HOST_PASSWORD="")
    def test_sin_smtp_el_correo_queda_pendiente_con_boton(self):
        self.subir_v12()
        correo = Aviso.objects.get(usuario=self.cliente)
        self.assertEqual(correo.estado, "pendiente")
        r = self.client.get(f"/gestion/portal/aviso/{correo.pk}/abrir/")
        self.assertTrue(r["Location"].startswith("mailto:ana@dgeyc.gob.ar?subject="))


class ConfirmacionCargaTests(BaseAccesos):
    @override_settings(CONTACTO_DESTINATARIOS=["gserelic@gmail.com"])
    def test_confirmacion_al_subir(self):
        mail.outbox.clear()
        self.client.force_login(self.admin)
        self.client.post("/gestion/portal/paquete/subir/", {"archivo": hacer_zip(archivos_base(META_V12))})
        m = mail.outbox[0]
        self.assertEqual(m.subject, "Tablero disponible: Economía de Santiago del Estero 2019–2024 (v1.2)")
        self.assertEqual(m.to, ["gserelic@gmail.com"])
        for esperado in ("Resumen formal del tablero.", "Se corrigió el ITAE.", "DGEyC SDE",
                         "https://www.gserelic.com/portal/tablero/pbg-sde/", "CPCESE M. 22"):
            self.assertIn(esperado, m.body)

    @override_settings(CONTACTO_DESTINATARIOS=["gserelic@gmail.com"])
    def test_si_falla_el_correo_la_carga_igual_se_completa(self):
        self.client.force_login(self.admin)
        with mock.patch("portal.admin.confirmar_carga", side_effect=OSError("SMTP caído")):
            r = self.client.post("/gestion/portal/paquete/subir/",
                                 {"archivo": hacer_zip(archivos_base(META_V12))}, follow=True)
        self.assertEqual(Paquete.objects.get().version, "1.2")
        self.assertContains(r, "no se pudo enviar el correo de confirmación")


class AltaUsuarioTests(BaseAccesos):
    def test_alta_desde_el_admin_sin_contrasena(self):
        self.client.force_login(self.admin)
        r = self.client.post("/gestion/cuentas/usuario/add/", {
            "email": "Nueva@DGEyC.gob.ar", "tratamiento_lista": "Dra.", "nombre": "María López",
            "organismo": "DGEyC SDE", "celular": "+5493851111111", "groups": [self.grupo.pk],
        })
        nuevo = Usuario.objects.get(email="nueva@dgeyc.gob.ar")
        self.assertRedirects(r, f"/gestion/cuentas/usuario/{nuevo.pk}/change/", fetch_redirect_response=False)
        self.assertFalse(nuevo.has_usable_password())
        self.assertEqual(nuevo.destinatario, "Dra. María López")
        self.assertContains(self.client.get(f"/gestion/cuentas/usuario/{nuevo.pk}/change/"), "Generar carta de acceso")

    def test_celular_validado(self):
        for malo in ("3854123456", "+54 9 385 412-3456", "+0123"):
            with self.subTest(malo=malo), self.assertRaises(ValidationError):
                Usuario(email="a@b.com", celular=malo).full_clean(exclude=["password"])
        Usuario(email="a@b.com", celular="+5493854123456").full_clean(exclude=["password"])


class DestinatarioTests(BaseAccesos):
    """Regla única de tratamiento, en los cuatro textos, con y sin tratamiento."""

    def test_funcion_destinatario(self):
        from cuentas.models import destinatario

        self.assertEqual(destinatario(Usuario(email="a@b.c", nombre="María Pérez", tratamiento="Cra.")), "Cra. María Pérez")
        self.assertEqual(destinatario(Usuario(email="a@b.c", nombre="María Pérez", tratamiento="")), "María Pérez")
        self.assertEqual(destinatario(Usuario(email="a@b.c", nombre="  María   Pérez ", tratamiento="  ")), "María Pérez")
        self.assertEqual(destinatario(Usuario(email="a@b.c", nombre="", tratamiento="")), "a@b.c")

    def _cuatro_textos(self, usuario, esperado):
        # 1) Página de acceso (primera vez y siguientes)
        token = generar_acceso(usuario, self.paquete)
        url = ruta_acceso(token, "pbg-sde")
        r = self.client.get(url)
        self.assertContains(r, f"Le damos la bienvenida, {esperado}</h1>", html=False)
        self.client.post(url, {"new_password1": "una-clave-larga-1", "new_password2": "una-clave-larga-1"})
        # 2) Visor
        self.assertContains(self.client.get("/portal/tablero/pbg-sde/"), f"Tablero preparado para {esperado}</p>")
        self.client.logout()
        self.assertContains(self.client.get(url), f"{esperado}, ingrese su contraseña.")
        # 3) Aviso
        from django.test import RequestFactory

        from .accesos import texto_aviso

        _, mensaje = texto_aviso(RequestFactory().get("/"), self.paquete, usuario)
        self.assertTrue(mensaje.startswith(f"{esperado}:\n"), mensaje[:60])
        # 4) Carta (encabezado)
        if HAY_HERRAMIENTAS_PDF:
            pdf = generar_carta(usuario, self.paquete, "https://www.gserelic.com/portal/acceso/x/pbg-sde/")
            texto = pypdf.PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
            self.assertIn(f"\n{esperado}\n", texto)
        # Nunca textos con género asumido ni puntos sueltos
        for t in (r.content.decode(), mensaje):
            self.assertNotIn("Bienvenido/a", t)
            self.assertNotIn("Estimado/a", t)
            self.assertNotIn(" . ", t)

    def test_con_tratamiento(self):
        u = Usuario.objects.create_user("cra@x.gob.ar", None, nombre="María Pérez", tratamiento="Cra.")
        u.groups.add(self.grupo)
        self._cuatro_textos(u, "Cra. María Pérez")

    def test_sin_tratamiento(self):
        u = Usuario.objects.create_user("sin@x.gob.ar", None, nombre="Juan Gómez", tratamiento="")
        u.groups.add(self.grupo)
        self._cuatro_textos(u, "Juan Gómez")

    def test_formulario_lista_y_otro(self):
        self.client.force_login(self.admin)
        base = {"email": "otro@x.gob.ar", "nombre": "Ana Ruiz", "organismo": "", "celular": "", "groups": [self.grupo.pk]}
        self.client.post("/gestion/cuentas/usuario/add/", {**base, "tratamiento_lista": "otro", "tratamiento_otro": "Esc."})
        u = Usuario.objects.get(email="otro@x.gob.ar")
        self.assertEqual(u.destinatario, "Esc. Ana Ruiz")
        # La ficha muestra «Otro…» con el texto cargado
        r = self.client.get(f"/gestion/cuentas/usuario/{u.pk}/change/")
        self.assertContains(r, 'value="Esc."')
        # «Otro…» sin texto: error
        r = self.client.post("/gestion/cuentas/usuario/add/", {**base, "email": "b@x.gob.ar", "tratamiento_lista": "otro"})
        self.assertContains(r, "Escribí el tratamiento")
        self.assertFalse(Usuario.objects.filter(email="b@x.gob.ar").exists())
        # Mg. está en la lista
        self.client.post("/gestion/cuentas/usuario/add/", {**base, "email": "c@x.gob.ar", "tratamiento_lista": "Mg."})
        self.assertEqual(Usuario.objects.get(email="c@x.gob.ar").destinatario, "Mg. Ana Ruiz")


class FirmaTests(BaseAccesos):
    def setUp(self):
        super().setUp()
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image as PILImage

        buffer = io.BytesIO()
        PILImage.new("RGBA", (1000, 335), (60, 50, 230, 0)).save(buffer, format="PNG")
        self.png = SimpleUploadedFile("firma.png", buffer.getvalue(), content_type="image/png")
        self.ruta = self.raiz / "firma.png"
        self._firma = override_settings(FIRMA_ARCHIVO=self.ruta)
        self._firma.enable()

    def tearDown(self):
        self._firma.disable()
        super().tearDown()

    def test_solo_el_superusuario_sube_y_ve_la_firma(self):
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.post("/gestion/firma/", {"archivo": self.png}).status_code, 403)
        self.assertEqual(self.client.get("/gestion/firma/imagen/").status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get("/gestion/firma/imagen/").status_code, 403)
        self.client.force_login(self.admin)
        self.png.seek(0)  # el envío anterior (rechazado) ya leyó el archivo
        self.client.post("/gestion/firma/", {"archivo": self.png})
        self.assertTrue(self.ruta.is_file())
        r = self.client.get("/gestion/firma/imagen/")
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "image/png"))
        self.client.post("/gestion/firma/", {"accion": "quitar"})
        self.assertFalse(self.ruta.exists())

    def test_rechaza_lo_que_no_es_png(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_login(self.admin)
        r = self.client.post("/gestion/firma/", {"archivo": SimpleUploadedFile("firma.png", b"no soy png")}, follow=True)
        self.assertContains(r, "imagen PNG válida")
        self.assertFalse(self.ruta.exists())

    def test_la_firma_no_es_publica(self):
        self.assertEqual(self.client.get("/static/sitio/img/firma.png").status_code, 404)

    @skipUnless(HAY_HERRAMIENTAS_PDF, "requiere requirements-dev.txt")
    def test_la_carta_lleva_la_firma_si_existe(self):
        url = "https://www.gserelic.com/portal/acceso/x/pbg-sde/"
        sin = pypdf.PdfReader(io.BytesIO(generar_carta(self.cliente, self.paquete, url)))
        self.assertEqual(len(sin.pages[0].images), 1)  # solo el QR
        self.client.force_login(self.admin)
        self.client.post("/gestion/firma/", {"archivo": self.png})
        con = pypdf.PdfReader(io.BytesIO(generar_carta(self.cliente, self.paquete, url)))
        self.assertEqual(len(con.pages[0].images), 2)  # QR + firma

    @skipUnless(HAY_HERRAMIENTAS_PDF, "requiere requirements-dev.txt")
    def test_la_firma_extraida_del_pdf_tiene_resolucion_pobre(self):
        """La copia dentro del PDF: chica, sin transparencia y JPEG. El original no sale nunca."""
        from .carta import FIRMA_PDF_ANCHO_PX

        self.client.force_login(self.admin)
        self.client.post("/gestion/firma/", {"archivo": self.png})
        pdf = generar_carta(self.cliente, self.paquete, "https://www.gserelic.com/portal/acceso/x/pbg-sde/")
        imagenes = pypdf.PdfReader(io.BytesIO(pdf)).pages[0].images
        firma = [i for i in imagenes if i.image.width <= FIRMA_PDF_ANCHO_PX]
        self.assertEqual(len(firma), 1)
        extraida = firma[0].image
        self.assertEqual(extraida.width, FIRMA_PDF_ANCHO_PX)   # 220 px, no los 1000 del original
        self.assertNotIn("A", extraida.mode)                    # sin canal de transparencia
        self.assertTrue(firma[0].name.lower().endswith((".jpg", ".jpeg")))
        self.assertLess(len(pdf), 60_000)
