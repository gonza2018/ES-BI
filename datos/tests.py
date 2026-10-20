"""Tests de /datos/: paquetes de libre acceso, pestaña DATOS en el menú y franja de Inicio.

Usan paquetes SINTÉTICOS (los reales no van al repositorio, que es público), armados con
los mismos ayudantes que los tests del portal.
"""
import os
import re
import sys
import unittest
from datetime import timedelta
from pathlib import Path

from django.contrib.staticfiles import finders
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from config.middleware import CSP_DATOS_PUBLICOS
from portal.models import Paquete
from portal.tests_paquetes import PNG, BasePaquetes, archivos_base

SLUG = "santiago-datos-publicos"
TITULO = "Santiago del Estero en datos"

# La CSP de /datos/ver/ tal como la pide la orden: si alguien la toca, este test avisa.
CSP_ESPERADA = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'self'; "
    "object-src 'none'; base-uri 'self'; "
    "sandbox allow-scripts allow-popups allow-popups-to-escape-sandbox"
)


class BaseDatos(BasePaquetes):
    def subir_datos(self, dias=3, publico=True, publicado=True, slug=SLUG, titulo=TITULO, con_fecha=True, **meta_extra):
        """Sube un paquete cuya fecha de meta.json es "hace `dias` días" y lo marca público (o no)."""
        meta = {
            "slug": slug,
            "titulo": titulo,
            "tipo": "dashboard",
            "organismo": "ES & BI",
            "descripcion": "Indicadores económicos y sociales de la provincia.",
            "novedades": "Se agregó el indicador de empleo registrado.",
            "version": "1.3",
            "estado": "aprobado",
            **meta_extra,
        }
        if con_fecha:
            meta["fecha"] = (timezone.localdate() - timedelta(days=dias)).isoformat()
        archivos = archivos_base(meta)
        archivos.update(
            {
                "assets/estilos.css": "body{margin:0}",
                "assets/logo.svg": "<svg xmlns='http://www.w3.org/2000/svg'/>",
                "assets/foto.jpg": b"\xff\xd8\xff",
                "datos.json": '{"a": 1}',
                "descargas/tabla.csv": "a;b\n1;2",
                "descargas/grafico.png": PNG,
                "tabla.csv": "a;b",
            }
        )
        paquete = self.subir(archivos, carpeta=slug, nombre=f"{slug}.zip")
        Paquete.objects.filter(pk=paquete.pk).update(publico=publico, publicado=publicado)
        paquete.refresh_from_db()
        return paquete

    def estado(self, url="/"):
        return self.client.get(url).content.decode()


class RutasPublicasTests(BaseDatos):
    def setUp(self):
        super().setUp()
        self.paquete = self.subir_datos()
        self.visor = f"/datos/{SLUG}/"
        self.ver = f"/datos/ver/{SLUG}/"

    # --- acceso -----------------------------------------------------------
    def test_publico_y_publicado_200_sin_login(self):
        for url in ["/datos/", self.visor, self.ver]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_privado_404_en_las_tres_rutas_aunque_haya_sesion(self):
        Paquete.objects.filter(pk=self.paquete.pk).update(publico=False)
        for iniciar_sesion in (False, True):
            if iniciar_sesion:
                self.client.force_login(self.admin)  # ni el superusuario lo ve por /datos/
            for url in ["/datos/", self.visor, self.ver, self.ver + "assets/plotly.min.js"]:
                with self.subTest(url=url, sesion=iniciar_sesion):
                    self.assertEqual(self.client.get(url).status_code, 404)

    def test_despublicado_404_en_las_tres_rutas(self):
        Paquete.objects.filter(pk=self.paquete.pk).update(publicado=False)
        for url in ["/datos/", self.visor, self.ver, self.ver + "assets/plotly.min.js"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_slug_inexistente_404(self):
        self.assertEqual(self.client.get("/datos/no-existe/").status_code, 404)
        self.assertEqual(self.client.get("/datos/ver/no-existe/").status_code, 404)

    def test_solo_metodos_seguros(self):
        for url in ["/datos/", self.visor, self.ver]:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url).status_code, 405)

    def test_sin_barra_final_redirige_solo_si_es_publico(self):
        r = self.client.get(f"/datos/ver/{SLUG}")
        self.assertRedirects(r, self.ver, fetch_redirect_response=False)
        Paquete.objects.filter(pk=self.paquete.pk).update(publico=False)
        self.assertEqual(self.client.get(f"/datos/ver/{SLUG}").status_code, 404)

    # --- listado ----------------------------------------------------------
    def test_listado_no_redirige_aunque_haya_uno_solo(self):
        r = self.client.get("/datos/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, TITULO)
        self.assertContains(r, "Indicadores económicos y sociales de la provincia.")
        self.assertContains(r, "Versión 1.3")
        self.assertContains(r, "Actualizado el")
        self.assertContains(r, "Se agregó el indicador de empleo registrado.")
        self.assertContains(r, f"/datos/ver/{SLUG}/miniatura.png")
        self.assertContains(r, f'href="/datos/{SLUG}/"')

    def test_listado_sin_novedades_no_muestra_el_bloque(self):
        otro = self.subir_datos(slug="otro-paquete", titulo="Otro", novedades="")
        self.assertEqual(otro.novedades, "")
        html = self.estado("/datos/")
        self.assertEqual(html.count("Novedades"), 1)  # solo la del primero

    def test_listado_ordena_del_mas_reciente_al_mas_antiguo(self):
        self.subir_datos(slug="viejo", titulo="Paquete viejo", dias=40)
        self.subir_datos(slug="nuevo", titulo="Paquete nuevo", dias=1)
        html = self.estado("/datos/")
        self.assertLess(html.index("Paquete nuevo"), html.index(TITULO))
        self.assertLess(html.index(TITULO), html.index("Paquete viejo"))

    def test_listado_no_muestra_privados_ni_despublicados(self):
        self.subir_datos(slug="privado", titulo="Paquete privado", publico=False)
        self.subir_datos(slug="oculto", titulo="Paquete oculto", publicado=False)
        html = self.estado("/datos/")
        self.assertIn(TITULO, html)
        self.assertNotIn("Paquete privado", html)
        self.assertNotIn("Paquete oculto", html)

    # --- visor ------------------------------------------------------------
    def test_visor_con_encabezado_botones_e_iframe(self):
        r = self.client.get(self.visor)
        self.assertContains(r, TITULO)
        self.assertContains(r, "Versión 1.3")
        self.assertContains(r, "Actualizado el")
        self.assertContains(r, "Indicadores económicos y sociales de la provincia.")
        self.assertContains(r, 'id="pantalla-completa"')
        self.assertContains(r, "Pantalla completa")
        self.assertContains(r, "Abrir en pestaña nueva")
        self.assertContains(r, f'src="/datos/ver/{SLUG}/"')
        self.assertContains(r, 'class="datos-visor"')
        # La página del sitio mantiene la CSP estricta (la de paquetes es solo para /datos/ver/)
        self.assertNotIn("unsafe-inline", r["Content-Security-Policy"])

    def test_visor_sin_descargas_ni_cerrar_sesion_ni_tablero_preparado(self):
        for sesion in (False, True):
            if sesion:
                self.client.force_login(self.admin)
            html = self.estado(self.visor)
            with self.subTest(sesion=sesion):
                self.assertNotIn("Cerrar sesión", html)
                self.assertNotIn("Tablero preparado para", html)
                self.assertNotIn("Descargas", html)
                self.assertNotIn("descargas/", html)
                self.assertNotIn("download", html.lower())
                self.assertNotIn(".xlsx", html)

    def test_visor_ocupa_la_pantalla_sin_doble_barra(self):
        css = Path(finders.find("sitio/css/sitio.css")).read_text(encoding="utf-8")
        self.assertRegex(css, r"\.datos-body\s*\{[^}]*height:\s*100dvh")
        self.assertRegex(css, r"\.datos-body\s*\{[^}]*overflow:\s*hidden")
        self.assertRegex(css, r"\.datos-marco\s*\{[^}]*flex:\s*1 1 auto")

    def test_visor_seo_y_redes(self):
        html = self.estado(self.visor)
        self.assertIn(f"<title>{TITULO} | ES & BI</title>", html)
        self.assertIn('<meta name="description" content="Indicadores económicos y sociales de la provincia.">', html)
        self.assertIn(f'<meta property="og:title" content="{TITULO}">', html)
        self.assertRegex(html, rf'<meta property="og:image" content="https?://[^"]+/datos/ver/{SLUG}/miniatura\.png">')
        self.assertRegex(html, rf'<link rel="canonical" href="https?://[^"]+/datos/{SLUG}/">')

    def test_visor_sin_miniatura_usa_la_imagen_del_sitio(self):
        archivos = archivos_base()
        del archivos["miniatura.png"]
        archivos["meta.json"] = archivos["meta.json"].replace("pbg-sde", "sin-mini")
        paquete = self.subir(archivos, carpeta="sin-mini", nombre="sin-mini.zip")
        Paquete.objects.filter(pk=paquete.pk).update(publico=True)
        html = self.estado("/datos/sin-mini/")
        self.assertNotIn("miniatura.png", html)
        self.assertIn("og_es_bi", html)

    # --- archivos ---------------------------------------------------------
    def test_archivos_permitidos_con_su_tipo(self):
        casos = {
            "": "text/html; charset=utf-8",
            "index.html": "text/html; charset=utf-8",
            "assets/plotly.min.js": "application/javascript; charset=utf-8",
            "assets/estilos.css": "text/css; charset=utf-8",
            "datos.json": "application/json",
            "assets/logo.svg": "image/svg+xml",
            "miniatura.png": "image/png",
            "assets/foto.jpg": "image/jpeg",
            "assets/fonts/archivo-latin-standard-normal.woff2": "font/woff2",
        }
        for ruta, tipo in casos.items():
            with self.subTest(ruta=ruta):
                r = self.client.get(self.ver + ruta)
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r["Content-Type"], tipo)
                self.assertNotIn("attachment", r.get("Content-Disposition", ""))

    def test_cabeceras_de_los_archivos(self):
        r = self.client.get(self.ver + "assets/plotly.min.js")
        self.assertEqual(r["Content-Security-Policy"], CSP_DATOS_PUBLICOS)
        self.assertEqual(r["Cache-Control"], "public, max-age=300")
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        self.assertNotIn("Access-Control-Allow-Origin", r)  # solo las fuentes
        self.assertEqual(r.contenido, b"console.log('plotly');")

    def test_csp_exacta_con_sandbox(self):
        self.assertEqual(CSP_DATOS_PUBLICOS, CSP_ESPERADA)
        r = self.client.get(self.ver)
        self.assertEqual(r["Content-Security-Policy"], CSP_ESPERADA)
        self.assertIn("sandbox allow-scripts allow-popups allow-popups-to-escape-sandbox", r["Content-Security-Policy"])
        self.assertNotIn("allow-same-origin", r["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'self'", r["Content-Security-Policy"])

    def test_cors_solo_en_las_fuentes_woff2(self):
        fuente = self.client.get(self.ver + "assets/fonts/archivo-latin-standard-normal.woff2")
        self.assertEqual(fuente["Access-Control-Allow-Origin"], "*")
        for ruta in ["", "assets/estilos.css", "datos.json", "miniatura.png"]:
            with self.subTest(ruta=ruta):
                self.assertNotIn("Access-Control-Allow-Origin", self.client.get(self.ver + ruta))

    def test_descargas_planillas_pdf_y_csv_dan_404(self):
        rutas = [
            "descargas/itae_sde.xlsx",
            "descargas/Cuarto%20Informe%20PBG_ITAE-SDE.pdf",
            "descargas/tabla.csv",
            "descargas/grafico.png",  # una extensión permitida, pero dentro de descargas/
            "Descargas/grafico.png",
            "tabla.csv",
            "assets/LICENSE-plotly.txt",
            "assets/no-existe.js",
        ]
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(self.ver + ruta).status_code, 404)

    def test_rutas_inseguras_no_salen_del_paquete(self):
        urls = [
            f"/datos/ver/{SLUG}/../../config/settings.py",
            f"/datos/ver/{SLUG}/assets/%2e%2e/%2e%2e/meta.json",
            f"/datos/ver/{SLUG}/assets%5Cplotly.min.js",
            f"/datos/ver/{SLUG}//etc/passwd.html",
            f"/datos/ver/{SLUG}/%00.js",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertIn(self.client.get(url).status_code, (404, 301, 302, 400))

    @unittest.skipIf(sys.platform.startswith("win"), "crear enlaces simbólicos en Windows requiere permisos")
    def test_enlace_simbolico_no_se_sirve(self):
        secreto = self.raiz / "secreto.html"
        secreto.write_text("secreto")
        os.symlink(secreto, self.paquete.directorio / "assets" / "trampa.html")
        self.assertEqual(self.client.get(self.ver + "assets/trampa.html").status_code, 404)

    def test_el_portal_privado_sigue_igual(self):
        # Que un paquete sea público no abre el portal: sigue pidiendo sesión y grupo.
        r = self.client.get(f"/portal/ver/{SLUG}/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith(reverse("portal:login")))
        self.assertEqual(self.client.get(f"/portal/tablero/{SLUG}/").status_code, 302)
        self.client.force_login(self.ajeno)
        self.assertEqual(self.client.get(f"/portal/ver/{SLUG}/").status_code, 404)
        r = self.client.get(f"/portal/ver/{SLUG}/descargas/itae_sde.xlsx")
        self.assertEqual(r.status_code, 404)
        # y el grupo del organismo sigue viendo su tablero con descargas
        self.paquete.grupos.add(self.otro_grupo)
        self.assertEqual(self.client.get(f"/portal/tablero/{SLUG}/").status_code, 200)
        self.assertEqual(self.client.get(f"/portal/ver/{SLUG}/descargas/itae_sde.xlsx").status_code, 200)


class MarcaPublicaTests(BaseDatos):
    def test_por_defecto_no_es_publico(self):
        paquete = self.subir()
        self.assertIs(paquete.publico, False)
        self.assertEqual(list(Paquete.publicos()), [])

    def test_version_nueva_conserva_la_marca(self):
        paquete = self.subir_datos()
        self.assertIs(paquete.publico, True)
        # Subida normal del mismo slug (el zip no trae la marca ni se la toca después):
        nuevo = self.subir(
            archivos_base({"slug": SLUG, "titulo": TITULO, "version": "1.4", "fecha": "2026-10-19"}),
            carpeta=SLUG, nombre="nueva.zip",
        )
        self.assertEqual(nuevo.pk, paquete.pk)
        paquete.refresh_from_db()
        self.assertIs(paquete.publico, True)
        self.assertEqual(paquete.version, "1.4")
        self.assertEqual(paquete.versiones.count(), 2)
        self.assertEqual(list(Paquete.publicos()), [paquete])

    def test_la_fecha_es_la_del_meta_json_de_la_version_vigente(self):
        paquete = self.subir_datos(dias=7)
        self.assertEqual(paquete.fecha_actualizacion, timezone.localdate() - timedelta(days=7))
        self.assertEqual(paquete.fecha_actualizacion, paquete.version_actual.fecha)


class MenuTests(BaseDatos):
    def pestana(self, html):
        return 'href="/datos/"' in html

    def test_sin_paquetes_publicos_no_hay_pestana(self):
        self.assertFalse(self.pestana(self.estado("/")))

    def test_con_un_paquete_privado_o_despublicado_no_hay_pestana(self):
        self.subir_datos(slug="privado", publico=False)
        self.subir_datos(slug="oculto", publicado=False)
        for url in ["/", "/cv/"]:
            with self.subTest(url=url):
                self.assertFalse(self.pestana(self.estado(url)))

    def test_con_un_paquete_publico_aparece_entre_servicios_y_contacto(self):
        self.subir_datos()
        html = self.estado("/")
        self.assertIn('href="/datos/"', html)
        self.assertLess(html.index(">SERVICIOS<"), html.index('href="/datos/"'))
        self.assertLess(html.index('href="/datos/"'), html.index(">CONTACTO<"))
        self.assertRegex(html, r'<a class="nav-link"[^>]*href="/datos/"[^>]*>DATOS')

    def test_aparece_en_todas_las_paginas_con_menu(self):
        self.subir_datos()
        for url in ["/", "/cv/", "/datos/", f"/datos/{SLUG}/"]:
            with self.subTest(url=url):
                self.assertTrue(self.pestana(self.estado(url)))

    def test_el_item_esta_dentro_del_menu_colapsable_del_celular(self):
        self.subir_datos()
        html = self.estado("/")
        colapsable = html[html.index('id="navbarNav"'):html.index("</nav>")]
        self.assertIn('href="/datos/"', colapsable)

    def test_el_item_enlaza_a_la_pagina_no_a_un_ancla(self):
        self.subir_datos()
        html = self.estado("/")
        self.assertNotRegex(html, r'href="[^"]*#datos"')

    def test_item_activo_en_la_seccion_datos(self):
        self.subir_datos()
        self.assertIn('aria-current="page"', self.estado("/datos/"))
        self.assertNotIn('aria-current="page"', self.estado("/"))

    def test_pastilla_nuevo_solo_dentro_de_los_15_dias(self):
        paquete = self.subir_datos(dias=15)
        self.assertIn("pastilla-nuevo", self.estado("/"))
        self.assertRegex(self.estado("/"), r"DATOS\s*<span class=\"badge[^\"]*pastilla-nuevo\">Nuevo</span>")
        self.subir_datos(dias=16)  # mismo slug: ahora la versión vigente tiene 16 días
        html = self.estado("/")
        self.assertTrue(self.pestana(html))
        self.assertNotIn("pastilla-nuevo", html)
        self.assertNotIn("Nuevo</span>", html)
        self.assertEqual(Paquete.objects.get(pk=paquete.pk).publico, True)

    def test_pastilla_usa_el_ultimo_paquete_publico_actualizado(self):
        self.subir_datos(slug="viejo", dias=60)
        self.assertNotIn("pastilla-nuevo", self.estado("/"))
        self.subir_datos(slug="nuevo", dias=2)
        self.assertIn("pastilla-nuevo", self.estado("/"))

    def test_un_paquete_privado_reciente_no_enciende_la_pastilla(self):
        self.subir_datos(slug="viejo", dias=60)
        self.subir_datos(slug="privado", dias=1, publico=False)
        self.assertNotIn("pastilla-nuevo", self.estado("/"))

    def test_sin_fecha_en_el_meta_hay_pestana_pero_no_pastilla(self):
        self.subir_datos(con_fecha=False)
        html = self.estado("/")
        self.assertTrue(self.pestana(html))
        self.assertNotIn("pastilla-nuevo", html)
        self.assertNotIn("aviso-datos", html)


class FranjaInicioTests(BaseDatos):
    def franja(self, html):
        """El HTML de la franja (vacío si no está)."""
        m = re.search(r'<div class="aviso-datos".*?</div>', html, re.S)
        return m.group(0) if m else ""

    def test_aparece_con_el_texto_y_el_enlace_pedidos(self):
        paquete = self.subir_datos(dias=3)
        html = self.estado("/")
        franja = self.franja(html)
        fecha = paquete.fecha_actualizacion.strftime("%d/%m/%Y")
        self.assertIn(f"Nuevos datos: {TITULO} · actualizado el {fecha} · Ver ahora", franja)
        self.assertIn("Nuevos datos · Ver", franja)  # versión corta del celular
        self.assertIn(f'href="/datos/{SLUG}/"', franja)
        self.assertIn(f'data-fecha="{paquete.fecha_actualizacion.isoformat()}"', franja)

    def test_es_accesible(self):
        self.subir_datos()
        franja = self.franja(self.estado("/"))
        self.assertIn('role="region"', franja)
        self.assertIn('aria-label="Aviso de datos nuevos"', franja)
        self.assertRegex(franja, r'<button type="button" class="aviso-datos__cerrar" aria-label="[^"]+">')
        self.assertIn("&times;", franja)

    def test_esta_justo_debajo_de_la_barra_de_navegacion(self):
        self.subir_datos()
        html = self.estado("/")
        self.assertLess(html.index("</nav>"), html.index('id="aviso-datos"'))
        self.assertLess(html.index('id="aviso-datos"'), html.index('<main id="contenido">'))
        entre = html[html.index("</nav>"):html.index('id="aviso-datos"')]
        self.assertNotIn("<section", entre)

    def test_respeta_la_csp_sin_js_ni_estilos_inline(self):
        self.subir_datos()
        r = self.client.get("/")
        html = r.content.decode()
        franja = self.franja(html)
        self.assertNotIn("script-src 'self' 'unsafe-inline'", r["Content-Security-Policy"])
        self.assertNotIn(" style=", franja)
        self.assertNotIn("onclick", html.lower())
        # todo <script> de la página tiene src (nada de JS inline)
        self.assertEqual(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", html), [])
        self.assertRegex(html, r'<script src="[^"]*/aviso_datos[^"]*\.js"></script>')

    def test_el_js_estatico_guarda_la_fecha_en_localstorage(self):
        ruta = finders.find("sitio/js/aviso_datos.js")
        self.assertIsNotNone(ruta)
        js = Path(ruta).read_text(encoding="utf-8")
        for texto in ("localStorage", "data-fecha", "aviso-datos__cerrar", "try {"):
            self.assertIn(texto, js)

    def test_se_muestra_hasta_los_15_dias_y_despues_desaparece(self):
        self.subir_datos(dias=15)
        self.assertTrue(self.franja(self.estado("/")))
        self.subir_datos(dias=16)
        self.assertEqual(self.franja(self.estado("/")), "")

    def test_no_aparece_sin_paquetes_publicos(self):
        self.assertEqual(self.franja(self.estado("/")), "")

    def test_no_aparece_con_un_paquete_privado_o_despublicado(self):
        self.subir_datos(slug="privado", dias=1, publico=False)
        self.subir_datos(slug="oculto", dias=1, publicado=False)
        self.assertEqual(self.franja(self.estado("/")), "")

    def test_solo_en_inicio(self):
        self.subir_datos(dias=1)
        self.assertTrue(self.franja(self.estado("/")))
        for url in ["/cv/", "/datos/", f"/datos/{SLUG}/"]:
            with self.subTest(url=url):
                self.assertNotIn("aviso-datos", self.estado(url))

    def test_muestra_titulo_y_fecha_del_ultimo_paquete_actualizado(self):
        self.subir_datos(slug="anterior", titulo="Paquete anterior", dias=10)
        nuevo = self.subir_datos(slug="reciente", titulo="Paquete reciente", dias=2)
        franja = self.franja(self.estado("/"))
        self.assertIn("Paquete reciente", franja)
        self.assertNotIn("Paquete anterior", franja)
        self.assertIn('href="/datos/reciente/"', franja)
        self.assertIn(nuevo.fecha_actualizacion.strftime("%d/%m/%Y"), franja)

    def test_los_15_dias_salen_de_settings(self):
        from django.conf import settings

        self.assertEqual(settings.DIAS_AVISO_DATOS, 15)
        self.subir_datos(dias=10)
        self.assertTrue(self.franja(self.estado("/")))
        with override_settings(DIAS_AVISO_DATOS=5):
            self.assertEqual(self.franja(self.estado("/")), "")
            self.assertNotIn("pastilla-nuevo", self.estado("/"))

    def test_tambien_se_ve_si_el_formulario_de_contacto_falla(self):
        # La vista de contacto vuelve a dibujar Inicio (400) con el mismo contexto.
        self.subir_datos()
        r = self.client.post("/contacto/", {"nombre": "", "email": "x", "mensaje": ""})
        self.assertEqual(r.status_code, 400)
        self.assertTrue(self.franja(r.content.decode()))

    def test_el_contexto_es_perezoso(self):
        # Las páginas que no usan DATOS (el admin, el portal) no pagan una consulta de más.
        from datos.context_processors import datos

        self.subir_datos()
        with self.assertNumQueries(0):
            datos(None)


class SitemapYRobotsTests(BaseDatos):
    def test_sitemap_incluye_publicos_y_excluye_privados(self):
        self.subir_datos()
        self.subir_datos(slug="privado", publico=False)
        self.subir_datos(slug="oculto", publicado=False)
        r = self.client.get("/sitemap.xml")
        self.assertEqual(r.status_code, 200)
        xml = r.content.decode()
        self.assertRegex(xml, r"<loc>https://[^<]+/datos/</loc>")
        self.assertRegex(xml, rf"<loc>https://[^<]+/datos/{SLUG}/</loc>")
        self.assertNotIn("/datos/privado/", xml)
        self.assertNotIn("/datos/oculto/", xml)
        self.assertIn("/cv/", xml)  # el resto del sitemap sigue igual

    def test_sitemap_sin_publicos_no_lista_datos(self):
        self.subir_datos(publico=False)
        xml = self.client.get("/sitemap.xml").content.decode()
        self.assertNotIn("/datos/", xml)

    def test_robots_permite_datos(self):
        r = self.client.get("/robots.txt")
        self.assertContains(r, "Allow: /datos/")
        self.assertNotContains(r, "Disallow: /datos")
        self.assertContains(r, "Disallow: /portal/")  # sigue igual


class AdminTests(BaseDatos):
    def setUp(self):
        super().setUp()
        self.publico = self.subir_datos()
        self.privado = self.subir_datos(slug="reservado", titulo="Paquete reservado", publico=False)
        self.client.force_login(self.admin)

    def test_casilla_libre_acceso_en_el_formulario(self):
        r = self.client.get(reverse("admin:portal_paquete_change", args=[self.publico.pk]))
        self.assertContains(r, "Libre acceso en /datos/")
        casilla = re.search(r'<input[^>]*name="publico"[^>]*>', r.content.decode())
        self.assertIsNotNone(casilla)
        self.assertIn("checked", casilla.group(0))

    def test_columna_publico_y_filtro(self):
        url = reverse("admin:portal_paquete_changelist")
        r = self.client.get(url)
        self.assertContains(r, "Público")
        self.assertContains(r, SLUG)
        self.assertContains(r, "reservado")
        solo_publicos = self.client.get(url, {"publico": "1"})
        self.assertContains(solo_publicos, SLUG)
        self.assertNotContains(solo_publicos, "reservado")
        solo_privados = self.client.get(url, {"publico": "0"})
        self.assertContains(solo_privados, "reservado")
        self.assertNotContains(solo_privados, f">{SLUG}<")

    def test_marcar_la_casilla_lo_publica_en_datos(self):
        self.assertEqual(self.client.get("/datos/reservado/").status_code, 404)
        Paquete.objects.filter(pk=self.privado.pk).update(publico=True)
        self.assertEqual(self.client.get("/datos/reservado/").status_code, 200)
