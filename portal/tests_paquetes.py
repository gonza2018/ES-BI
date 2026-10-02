"""Tests del Paso 2: portal de paquetes.

Usan un paquete SINTÉTICO con la misma estructura que pbg-sde (el real no va al
repositorio, que es público). Para correr además contra el paquete real:

    PAQUETE_REAL=C:\\ruta\\pbg-sde.zip python manage.py test portal
"""
import io
import json
import os
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from config.middleware import CSP_PAQUETES

from .models import Paquete, VersionPaquete
from .paquetes import PaqueteInvalido, instalar, resolver_ruta

# PNG de 1x1 válido
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
)

META = {
    "slug": "pbg-sde",
    "titulo": "Economía de Santiago del Estero 2019–2024",
    "tipo": "dashboard",
    "organismo": "DGEyC SDE",
    "descripcion": "Boceto de tablero.",
    "version": "1.1",
    "fecha": "2026-09-28",
    "estado": "en revisión",
}


def archivos_base(meta=None):
    return {
        "index.html": '<html><head><script src="assets/plotly.min.js"></script></head><body>PBG</body></html>',
        "meta.json": json.dumps(meta or META, ensure_ascii=False),
        "miniatura.png": PNG,
        "assets/plotly.min.js": "console.log('plotly');",
        "assets/fonts/archivo-latin-standard-normal.woff2": b"wOF2\x00\x01",
        "assets/LICENSE-plotly.txt": "MIT",
        "descargas/itae_sde.xlsx": b"PK\x03\x04xlsx",
        "descargas/Cuarto Informe PBG_ITAE-SDE.pdf": b"%PDF-1.4",
    }


def hacer_zip(archivos, carpeta="pbg-sde", nombre="pbg-sde.zip", enlaces=()):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for ruta, contenido in archivos.items():
            completo = f"{carpeta}/{ruta}" if carpeta else ruta
            zf.writestr(completo, contenido.encode() if isinstance(contenido, str) else contenido)
        for ruta, destino in enlaces:
            info = zipfile.ZipInfo(f"{carpeta}/{ruta}" if carpeta else ruta)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, destino)
    return SimpleUploadedFile(nombre, buffer.getvalue(), content_type="application/zip")


class ClienteQueCierra(Client):
    """Lee y CIERRA cada respuesta de archivo, como hace el servidor real.

    Sin esto, el archivo queda abierto y en Windows no se puede borrar la carpeta
    temporal del test (WinError 32). El contenido queda en `respuesta.contenido`.
    """

    def get(self, *args, **kwargs):
        respuesta = super().get(*args, **kwargs)
        if getattr(respuesta, "streaming", False):
            respuesta.contenido = b"".join(respuesta.streaming_content)
            respuesta.close()
        return respuesta


def archivos_abiertos_en(carpeta):
    """Archivos de `carpeta` que este proceso tiene abiertos (solo Linux, vía /proc)."""
    if not sys.platform.startswith("linux"):
        return []
    abiertos = []
    for fd in os.listdir("/proc/self/fd"):
        try:
            ruta = os.readlink(f"/proc/self/fd/{fd}")
        except OSError:
            continue
        if ruta.startswith(str(carpeta)):
            abiertos.append(ruta)
    return abiertos


class BasePaquetes(TestCase):
    client_class = ClienteQueCierra

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self._tmp.name)
        self._override = override_settings(PAQUETES_ROOT=self.raiz)
        self._override.enable()
        User = get_user_model()
        self.grupo = Group.objects.create(name="DGEyC SDE")
        self.otro_grupo = Group.objects.create(name="CFI")
        self.usuario = User.objects.create_user("eval@dgeyc.gob.ar", "clave-segura-123")
        self.usuario.groups.add(self.grupo)
        self.ajeno = User.objects.create_user("eval@cfi.org.ar", "clave-segura-123")
        self.ajeno.groups.add(self.otro_grupo)
        self.admin = User.objects.create_superuser("yo@gserelic.com", "clave-segura-123")

    def tearDown(self):
        # Control para Linux de lo que en Windows falla: ningún archivo puede quedar abierto.
        abiertos = archivos_abiertos_en(self.raiz)
        self._override.disable()
        self._tmp.cleanup()
        self.assertEqual(abiertos, [], "quedaron archivos abiertos (en Windows no se podrían borrar)")

    def subir(self, archivos=None, **kw):
        paquete, creado = instalar(hacer_zip(archivos or archivos_base(), **kw), self.admin)
        return paquete


class PermisosYServidoTests(BasePaquetes):
    def setUp(self):
        super().setUp()
        self.paquete = self.subir()
        self.url_js = "/portal/ver/pbg-sde/assets/plotly.min.js"

    def test_preasigna_el_grupo_con_el_nombre_del_organismo(self):
        self.assertEqual(list(self.paquete.grupos.all()), [self.grupo])

    def test_usuario_del_grupo_200_con_javascript_y_cabeceras(self):
        self.client.force_login(self.usuario)
        r = self.client.get(self.url_js)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r["Content-Type"].startswith("application/javascript"))
        self.assertEqual(r["Content-Security-Policy"], CSP_PAQUETES)
        self.assertEqual(r["Cache-Control"], "private, max-age=300")
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r.contenido, b"console.log('plotly');")

    def test_usuario_de_otro_grupo_404(self):
        self.client.force_login(self.ajeno)
        self.assertEqual(self.client.get(self.url_js).status_code, 404)
        self.assertEqual(self.client.get("/portal/ver/pbg-sde/").status_code, 404)
        self.assertEqual(self.client.get("/portal/tablero/pbg-sde/").status_code, 404)

    def test_sin_sesion_redirige_al_login(self):
        r = self.client.get(self.url_js)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith(reverse("portal:login")))
        self.assertIn("next=/portal/ver/pbg-sde/assets/plotly.min.js", r["Location"])

    def test_superusuario_ve_todo(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url_js).status_code, 200)

    def test_fuente_woff2(self):
        self.client.force_login(self.usuario)
        r = self.client.get("/portal/ver/pbg-sde/assets/fonts/archivo-latin-standard-normal.woff2")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "font/woff2")

    def test_sin_barra_final_redirige(self):
        self.client.force_login(self.usuario)
        r = self.client.get("/portal/ver/pbg-sde")
        self.assertRedirects(r, "/portal/ver/pbg-sde/", fetch_redirect_response=False)
        # Sin sesión: login (no revela nada); otro grupo: 404
        self.client.logout()
        self.assertEqual(self.client.get("/portal/ver/pbg-sde").status_code, 302)
        self.client.force_login(self.ajeno)
        self.assertEqual(self.client.get("/portal/ver/pbg-sde").status_code, 404)

    def test_indice_html(self):
        self.client.force_login(self.usuario)
        r = self.client.get("/portal/ver/pbg-sde/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "text/html; charset=utf-8")
        self.assertIn(b"PBG", r.contenido)

    def test_descargas_como_adjunto(self):
        self.client.force_login(self.usuario)
        r = self.client.get("/portal/ver/pbg-sde/descargas/itae_sde.xlsx")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r["Content-Type"].startswith("application/vnd.openxmlformats"))
        self.assertTrue(r["Content-Disposition"].startswith("attachment"))
        r = self.client.get("/portal/ver/pbg-sde/descargas/Cuarto%20Informe%20PBG_ITAE-SDE.pdf")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertIn("Cuarto", r["Content-Disposition"])

    def test_extension_no_permitida_no_se_sirve(self):
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get("/portal/ver/pbg-sde/assets/LICENSE-plotly.txt").status_code, 404)

    def test_archivo_inexistente_404(self):
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get("/portal/ver/pbg-sde/assets/no-existe.js").status_code, 404)

    def test_despublicado_solo_lo_ve_el_superusuario(self):
        Paquete.objects.filter(pk=self.paquete.pk).update(publicado=False)
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(self.url_js).status_code, 404)
        self.assertNotContains(self.client.get("/portal/"), "pbg-sde")
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url_js).status_code, 200)
        self.assertContains(self.client.get("/portal/"), "No publicado")

    def test_grilla_muestra_la_tarjeta_solo_al_grupo(self):
        self.client.force_login(self.usuario)
        r = self.client.get("/portal/")
        self.assertContains(r, "Economía de Santiago del Estero 2019–2024")
        self.assertContains(r, "/portal/ver/pbg-sde/miniatura.png")
        self.assertContains(r, "/portal/tablero/pbg-sde/")
        self.assertContains(r, "En revisión")
        self.client.force_login(self.ajeno)
        self.assertNotContains(self.client.get("/portal/"), "pbg-sde")

    def test_pagina_del_visor(self):
        self.client.force_login(self.usuario)
        r = self.client.get("/portal/tablero/pbg-sde/")
        self.assertContains(r, 'src="/portal/ver/pbg-sde/"')
        self.assertContains(r, 'id="pantalla-completa"')
        self.assertContains(r, "/portal/ver/pbg-sde/descargas/itae_sde.xlsx")
        self.assertContains(r, "Cuarto Informe PBG_ITAE-SDE.pdf")
        self.assertNotContains(r, "LICENSE")  # solo lo que está en descargas/
        # La página del portal mantiene la CSP estricta (no la de paquetes)
        self.assertNotIn("unsafe-inline", r["Content-Security-Policy"])


class RutasSegurasTests(BasePaquetes):
    def setUp(self):
        super().setUp()
        self.base = self.subir().directorio

    def test_rechaza_rutas_peligrosas(self):
        from django.http import Http404

        for ruta in ["../x.html", "assets/../../x.html", "/etc/passwd.html", "assets\\plotly.min.js", "a\x00.js"]:
            with self.subTest(ruta=ruta), self.assertRaises(Http404):
                resolver_ruta(self.base, ruta)

    def test_ruta_valida(self):
        self.assertEqual(resolver_ruta(self.base, "assets/plotly.min.js").name, "plotly.min.js")
        self.assertEqual(resolver_ruta(self.base, "").name, "index.html")

    def test_url_con_puntos_no_sale_del_paquete(self):
        self.client.force_login(self.usuario)
        for url in ["/portal/ver/pbg-sde/../../config/settings.py", "/portal/ver/pbg-sde/assets/%2e%2e/%2e%2e/meta.json"]:
            with self.subTest(url=url):
                self.assertIn(self.client.get(url).status_code, (404, 301, 302))

    @unittest.skipIf(sys.platform.startswith("win"), "crear enlaces simbólicos en Windows requiere permisos")
    def test_enlace_simbolico_dentro_del_paquete_no_se_sirve(self):
        from django.http import Http404

        secreto = self.raiz / "secreto.html"
        secreto.write_text("secreto")
        os.symlink(secreto, self.base / "assets" / "trampa.html")
        with self.assertRaises(Http404):
            resolver_ruta(self.base, "assets/trampa.html")


class ValidacionZipTests(BasePaquetes):
    def rechaza(self, subido, texto):
        with self.assertRaises(PaqueteInvalido) as ctx:
            instalar(subido, self.admin)
        self.assertIn(texto, str(ctx.exception))
        self.assertFalse(Paquete.objects.exists())
        # No deja basura en disco
        restos = [p for p in self.raiz.rglob("*") if p.is_file()]
        self.assertEqual(restos, [])

    def test_zip_slip(self):
        self.rechaza(hacer_zip({**archivos_base(), "../../evil.html": "x"}, carpeta=None), "..")

    def test_ruta_absoluta(self):
        self.rechaza(hacer_zip({**archivos_base(), "/tmp/evil.html": "x"}, carpeta=None), "absoluta")

    def test_enlace_simbolico(self):
        self.rechaza(hacer_zip(archivos_base(), enlaces=[("assets/link.js", "/etc/passwd")]), "simbólico")

    @override_settings(PAQUETE_MAX_BYTES=8000)
    def test_demasiado_grande_descomprimido(self):
        # Comprimido pesa ~2 KB (pasa el primer control); descomprimido, 50 KB.
        self.rechaza(hacer_zip({**archivos_base(), "assets/grande.js": "x" * 50000}), "descomprimido")

    def test_limite_real_de_50_mb(self):
        from django.conf import settings

        self.assertEqual(settings.PAQUETE_MAX_BYTES, 50 * 1024 * 1024)

    def test_sin_index(self):
        a = archivos_base()
        del a["index.html"]
        self.rechaza(hacer_zip(a), "Falta index.html")

    def test_sin_meta(self):
        a = archivos_base()
        del a["meta.json"]
        self.rechaza(hacer_zip(a), "Falta meta.json")

    def test_extensiones_de_servidor(self):
        for nombre in ["assets/x.py", "x.php", "cgi/run.sh", "assets/a.php.html", ".htaccess"]:
            with self.subTest(nombre=nombre):
                self.rechaza(hacer_zip({**archivos_base(), nombre: "x"}), "no permitido")

    def test_no_es_zip(self):
        self.rechaza(SimpleUploadedFile("x.zip", b"esto no es un zip"), "no es un zip")

    def test_meta_invalido(self):
        self.rechaza(hacer_zip({**archivos_base(), "meta.json": "{no json"}), "JSON válido")
        self.rechaza(hacer_zip(archivos_base({**META, "slug": "PBG SDE"})), "slug")
        self.rechaza(hacer_zip(archivos_base({**META, "titulo": ""})), "título")
        self.rechaza(hacer_zip(archivos_base({**META, "estado": "publicado"})), "estado")

    def test_ignora_basura_de_mac_y_acepta_zip_sin_carpeta_raiz(self):
        a = {**archivos_base(), "__MACOSX/._index.html": "x", ".DS_Store": "x"}
        paquete, _ = instalar(hacer_zip(a, carpeta=None), self.admin)
        self.assertTrue((paquete.directorio / "index.html").is_file())
        self.assertFalse((paquete.directorio / ".DS_Store").exists())

    def test_estado_y_fecha_desde_meta(self):
        paquete, _ = instalar(hacer_zip(archivos_base()), self.admin)
        self.assertEqual(paquete.estado, "en_revision")
        self.assertEqual(str(paquete.fecha), "2026-09-28")
        self.assertEqual(paquete.version, "1.1")


class HistorialTests(BasePaquetes):
    def test_mismo_slug_genera_historial(self):
        primero = self.subir()
        dir_v1 = primero.directorio
        nuevo_meta = {**META, "version": "1.2", "titulo": "Título nuevo", "estado": "aprobado"}
        segundo = self.subir(archivos_base(nuevo_meta))
        self.assertEqual(primero.pk, segundo.pk)
        self.assertEqual(VersionPaquete.objects.filter(paquete=segundo).count(), 2)
        self.assertEqual(segundo.version, "1.2")
        self.assertEqual(segundo.titulo, "Título nuevo")
        self.assertEqual(segundo.estado, "aprobado")
        self.assertTrue(dir_v1.is_dir())  # la versión anterior se conserva en disco
        self.assertNotEqual(segundo.directorio, dir_v1)
        # Los grupos asignados se conservan
        self.assertEqual(list(segundo.grupos.all()), [self.grupo])

    def test_dos_subidas_en_el_mismo_instante(self):
        """Regresión (Windows): el reloj avanza de a ~15 ms; dos subidas seguidas
        reciben la misma hora y no pueden compartir carpeta."""
        from unittest import mock

        from django.utils import timezone

        fijo = timezone.now()
        with mock.patch("portal.paquetes.timezone.now", return_value=fijo):
            primero = self.subir()
            dir_v1 = primero.directorio
            segundo = self.subir(archivos_base({**META, "version": "1.2"}))
        self.assertNotEqual(segundo.directorio, dir_v1)
        self.assertTrue(dir_v1.is_dir() and segundo.directorio.is_dir())
        self.assertEqual(VersionPaquete.objects.count(), 2)

    def test_volver_a_una_version_anterior_desde_el_admin(self):
        self.subir()
        self.subir(archivos_base({**META, "version": "1.2"}))
        anterior = VersionPaquete.objects.get(version="1.1")
        self.client.force_login(self.admin)
        self.client.post(
            "/gestion/portal/versionpaquete/",
            {"action": "volver_a_esta_version", "_selected_action": [anterior.pk]},
        )
        paquete = Paquete.objects.get()
        self.assertEqual(paquete.version_actual, anterior)
        self.assertEqual(paquete.version, "1.1")

    def test_borrar_paquete_borra_sus_archivos(self):
        paquete = self.subir()
        carpeta = self.raiz / "pbg-sde"
        self.assertTrue(carpeta.is_dir())
        paquete.delete()
        self.assertFalse(carpeta.exists())


class AdminSubidaTests(BasePaquetes):
    def test_subir_desde_el_admin(self):
        self.client.force_login(self.admin)
        r = self.client.post("/gestion/portal/paquete/subir/", {"archivo": hacer_zip(archivos_base())})
        paquete = Paquete.objects.get()
        self.assertRedirects(r, f"/gestion/portal/paquete/{paquete.pk}/change/")
        r = self.client.get(f"/gestion/portal/paquete/{paquete.pk}/change/")
        self.assertContains(r, "Subir nueva versión")
        self.assertContains(r, "istorial de versiones")

    def test_error_de_validacion_se_muestra(self):
        self.client.force_login(self.admin)
        a = archivos_base()
        del a["index.html"]
        r = self.client.post("/gestion/portal/paquete/subir/", {"archivo": hacer_zip(a)})
        self.assertContains(r, "Falta index.html")
        self.assertFalse(Paquete.objects.exists())

    def test_agregar_lleva_a_subir(self):
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.get("/gestion/portal/paquete/add/"), "/gestion/portal/paquete/subir/")

    def test_usuario_sin_admin_no_puede_subir(self):
        self.client.force_login(self.usuario)
        r = self.client.post("/gestion/portal/paquete/subir/", {"archivo": hacer_zip(archivos_base())})
        self.assertNotEqual(r.status_code, 200)
        self.assertFalse(Paquete.objects.exists())


@unittest.skipUnless(os.environ.get("PAQUETE_REAL"), "definir PAQUETE_REAL=ruta/al/pbg-sde.zip para correrlo")
class PaqueteRealTests(BasePaquetes):
    """Contra el pbg-sde.zip real (no está en el repositorio)."""

    def test_pbg_sde_real(self):
        ruta = Path(os.environ["PAQUETE_REAL"])
        subido = SimpleUploadedFile(ruta.name, ruta.read_bytes(), content_type="application/zip")
        paquete, _ = instalar(subido, self.admin)
        paquete.grupos.add(self.grupo)
        self.assertEqual(paquete.slug, "pbg-sde")
        self.client.force_login(self.usuario)
        r = self.client.get("/portal/ver/pbg-sde/assets/plotly.min.js")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r["Content-Type"].startswith("application/javascript"))
        self.assertGreater(len(r.contenido), 4_000_000)
        r = self.client.get("/portal/ver/pbg-sde/assets/fonts/archivo-latin-standard-normal.woff2")
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "font/woff2"))
        self.assertRedirects(self.client.get("/portal/ver/pbg-sde"), "/portal/ver/pbg-sde/", fetch_redirect_response=False)
        self.assertEqual(len(paquete.descargas()), 10)  # 9 xlsx + 1 pdf
        self.client.force_login(self.ajeno)
        self.assertEqual(self.client.get("/portal/ver/pbg-sde/assets/plotly.min.js").status_code, 404)
