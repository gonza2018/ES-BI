"""Tableros institucionales: portal sin marca, carta neutra, host propio y sin avisos."""
import io
from unittest import skipUnless

from django.test import override_settings

from cuentas.models import Usuario

from .accesos import crear_avisos, generar_acceso, ruta_acceso, url_absoluta
from .carta import generar_carta
from .marca import NOMBRE_INSTITUCIONAL
from .tests_accesos import HAY_HERRAMIENTAS_PDF, BaseAccesos

FIRMA = "Firmante De Prueba"
MATRICULA = "MAT-999"
MARCAS = ["ES &amp; BI", "ES & BI", "es_bi_logo", FIRMA, MATRICULA, "Volver al sitio", "Portal de clientes"]
HOST = "tablero.ejemplo.com"


@override_settings(FIRMA_NOMBRE=FIRMA, FIRMA_MATRICULA=MATRICULA, HOST_TABLERO=HOST,
                   ALLOWED_HOSTS=["testserver", HOST, "www.gserelic.com"])
class BaseInstitucional(BaseAccesos):
    def setUp(self):
        super().setUp()
        self.paquete.institucional = True
        self.paquete.save()
        self.cliente.cargo = "Ministro de Producción"
        self.cliente.tratamiento = "Ing."
        self.cliente.nombre = "Néstor Prueba"
        self.cliente.save()

    def sin_marcas(self, respuesta):
        for marca in MARCAS:
            self.assertNotContains(respuesta, marca, msg_prefix=f"aparece «{marca}»")

    def entrar(self):
        self.cliente.set_password("una-clave-larga-1")
        self.cliente.save()
        self.client.force_login(self.cliente)


class PortalNeutroTests(BaseInstitucional):
    def test_inicio_va_directo_al_tablero_unico(self):
        self.entrar()
        r = self.client.get("/portal/")
        self.assertRedirects(r, "/portal/tablero/pbg-sde/", fetch_redirect_response=False)

    def test_tablero_con_bienvenida_y_sin_marcas(self):
        self.entrar()
        r = self.client.get("/portal/tablero/pbg-sde/")
        self.assertContains(r, "Bienvenido, Ing. Néstor Prueba")
        self.assertContains(r, "Ministro de Producción")
        self.assertContains(r, "Si usted no es Ing. Néstor Prueba, cierre esta sesión")
        self.assertContains(r, NOMBRE_INSTITUCIONAL)
        self.sin_marcas(r)
        self.assertEqual(r["Cache-Control"], "no-store")

    def test_salir_vuelve_al_ingreso_neutro(self):
        self.entrar()
        r = self.client.post("/portal/salir/")
        self.assertRedirects(r, "/portal/ingresar/?tablero=1", fetch_redirect_response=False)
        r = self.client.get("/portal/ingresar/?tablero=1")
        self.assertContains(r, "Solicite un nuevo enlace a quien le entregó este acceso")
        self.sin_marcas(r)

    def test_cliente_comun_sigue_viendo_la_marca(self):
        self.paquete.institucional = False
        self.paquete.save()
        self.entrar()
        r = self.client.get("/portal/tablero/pbg-sde/")
        self.assertContains(r, "Portal de clientes")
        self.assertNotContains(r, "Bienvenido, Ing.")

    def test_quien_ve_un_tablero_comun_ademas_no_recibe_portal_neutro(self):
        from .tests_paquetes import META, archivos_base
        otro = self.subir(archivos_base({**META, "slug": "otro-tablero", "titulo": "Otro"}),
                          carpeta="otro-tablero", nombre="otro-tablero.zip")
        otro.institucional = False
        otro.save()
        self.entrar()
        r = self.client.get("/portal/tablero/pbg-sde/")
        self.assertContains(r, "Portal de clientes")


class AccesoNeutroTests(BaseInstitucional):
    def test_crear_contrasena_sin_firma(self):
        token = generar_acceso(self.cliente, self.paquete)
        r = self.client.get(ruta_acceso(token, "pbg-sde"))
        self.assertContains(r, "Le damos la bienvenida, Ing. Néstor Prueba")
        self.assertContains(r, "solicite un nuevo enlace a quien le entregó este acceso")
        self.sin_marcas(r)

    def test_enlace_de_la_carta_usa_el_host_del_tablero(self):
        token = generar_acceso(self.cliente, self.paquete)
        self.assertTrue(url_absoluta(None, ruta_acceso(token, "pbg-sde"), self.paquete).startswith(f"https://{HOST}/portal/acceso/"))

    def test_no_se_crean_avisos(self):
        self.assertEqual(crear_avisos(None, self.paquete), [])

    @skipUnless(HAY_HERRAMIENTAS_PDF, "requiere requirements-dev.txt")
    def test_carta_sin_firma_ni_autor(self):
        import pypdf

        pdf = generar_carta(self.cliente, self.paquete, f"https://{HOST}/portal/acceso/x/pbg-sde/")
        lector = pypdf.PdfReader(io.BytesIO(pdf))
        texto = " ".join(p.extract_text() for p in lector.pages)
        self.assertIn("Ing. Néstor Prueba", texto)
        self.assertIn("Ministro de Producción", texto)
        self.assertIn("a quien le entregó este acceso", texto)
        for marca in (FIRMA, MATRICULA, "ES & BI"):
            self.assertNotIn(marca, texto)
        autor = (lector.metadata or {}).get("/Author", "") or ""
        self.assertNotIn(FIRMA, autor)


class HostTableroTests(BaseInstitucional):
    def get(self, ruta):
        return self.client.get(ruta, HTTP_HOST=HOST)

    def test_raiz_va_al_portal(self):
        r = self.get("/")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], "/portal/")

    def test_resto_del_sitio_no_existe(self):
        for ruta in ("/gestion/", "/cv/", "/datos/", "/contacto/", "/sitemap.xml"):
            self.assertEqual(self.get(ruta).status_code, 404, ruta)

    def test_robots_bloquea_todo_y_noindex(self):
        r = self.get("/robots.txt")
        self.assertContains(r, "Disallow: /")
        r = self.get("/portal/ingresar/")
        self.assertEqual(r["X-Robots-Tag"], "noindex, nofollow")
        self.assertEqual(r["Cache-Control"], "no-store")
        self.sin_marcas(r)

    def test_salir_en_el_host_vuelve_al_ingreso(self):
        self.entrar()
        r = self.client.post("/portal/salir/", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith("/portal/ingresar/"))
