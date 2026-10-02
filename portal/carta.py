"""Carta de acceso en PDF (A4, sin logos). Texto base: templates/portal/mensajes/carta_acceso.txt.

Si existe la firma manuscrita (settings.FIRMA_ARCHIVO, en el disco privado), va sobre el nombre,
con 4,5 cm de ancho. Si no existe, va solo el texto de la firma.
"""
import io
from pathlib import Path

from PIL import Image as PILImage
from xml.sax.saxutils import escape

import qrcode
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify
from reportlab.lib.enums import TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]

ANCHO_FIRMA = 4.5 * cm
# Copia de la firma que va DENTRO del PDF: a propósito pobre para copiar y reutilizar.
# ~220 px de ancho a 4,5 cm son unos 125 ppp: se ve bien en pantalla e impresa a tamaño
# carta, pero extraída del PDF no sirve para un documento de calidad.
FIRMA_PDF_ANCHO_PX = 220
FIRMA_PDF_CALIDAD_JPEG = 60


def fecha_en_letras(fecha):
    return f"{fecha.day} de {MESES[fecha.month - 1]} de {fecha.year}"


def imagen_qr(texto):
    """PNG (bytes) del código QR del texto."""
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
    qr.add_data(texto)
    qr.make(fit=True)
    buffer = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buffer, format="PNG")
    return buffer.getvalue()


def firma_para_pdf(ruta):
    """Copia degradada de la firma para insertar en el PDF (bytes JPEG, ancho, alto).

    - Baja resolución (FIRMA_PDF_ANCHO_PX).
    - Sin transparencia: va sobre fondo blanco, así no se puede pegar limpia sobre otro documento.
    - JPEG con compresión visible de cerca (artefactos alrededor del trazo).
    El original queda solo en el disco privado del servidor.
    """
    with PILImage.open(ruta) as original:
        original = original.convert("RGBA")
        fondo = PILImage.new("RGB", original.size, "white")
        fondo.paste(original, mask=original.getchannel("A"))
        alto = max(1, round(fondo.height * FIRMA_PDF_ANCHO_PX / fondo.width))
        chica = fondo.resize((FIRMA_PDF_ANCHO_PX, alto), PILImage.Resampling.BILINEAR)
    salida = io.BytesIO()
    chica.save(salida, format="JPEG", quality=FIRMA_PDF_CALIDAD_JPEG, subsampling=2, optimize=True)
    salida.seek(0)
    return salida, chica.width, chica.height


def nombre_archivo(paquete, usuario):
    return f"Acceso_{paquete.slug}_{slugify(usuario.apellido) or 'usuario'}.pdf"


def _estilos():
    base = ParagraphStyle("base", fontName="Times-Roman", fontSize=11.5, leading=16, alignment=TA_JUSTIFY)
    return {
        "base": base,
        "derecha": ParagraphStyle("derecha", parent=base, alignment=TA_RIGHT),
        "destinatario": ParagraphStyle("dest", parent=base, alignment=0, leading=15),
        "enlace": ParagraphStyle("enlace", parent=base, fontName="Courier", fontSize=9.5, leading=12,
                                 alignment=0, wordWrap="CJK"),
        "firma": ParagraphStyle("firma", parent=base, alignment=1, leading=15),
    }


def generar_carta(usuario, paquete, enlace, fecha=None):
    """Devuelve los bytes del PDF."""
    fecha = fecha or timezone.localdate()
    e = _estilos()
    historia = [
        Paragraph(escape(f"{settings.CARTA_CIUDAD}, {fecha_en_letras(fecha)}"), e["derecha"]),
        Spacer(1, 1.0 * cm),
    ]

    destinatario = [usuario.destinatario]
    if usuario.organismo:
        destinatario.append(usuario.organismo)
    destinatario.append("S / D")
    historia += [Paragraph("<br/>".join(escape(x) for x in destinatario), e["destinatario"]), Spacer(1, 0.8 * cm)]

    texto = render_to_string("portal/mensajes/carta_acceso.txt", {"usuario": usuario, "paquete": paquete})
    for parrafo in [p.strip() for p in texto.split("\n\n") if p.strip()]:
        if parrafo == "[[ENLACE]]":
            qr = Image(io.BytesIO(imagen_qr(enlace)), width=3.6 * cm, height=3.6 * cm)
            bloque = [
                Paragraph("Para acceder, ingrese al siguiente enlace o escanee el código QR:", e["base"]),
                Spacer(1, 0.25 * cm),
                Paragraph(escape(enlace), e["enlace"]),
            ]
            tabla = Table([[bloque, qr]], colWidths=[11.2 * cm, 4.0 * cm])
            tabla.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 12),
            ]))
            historia += [tabla, Spacer(1, 0.4 * cm)]
        else:
            historia += [Paragraph(escape(" ".join(parrafo.split())), e["base"]), Spacer(1, 0.35 * cm)]

    historia.append(Spacer(1, 1.2 * cm))
    firma = []
    ruta_firma = Path(settings.FIRMA_ARCHIVO)
    if ruta_firma.is_file():
        datos, ancho, alto = firma_para_pdf(ruta_firma)
        firma.append(Image(datos, width=ANCHO_FIRMA, height=ANCHO_FIRMA * alto / ancho))
    firma.append(Paragraph(f"{escape(settings.FIRMA_NOMBRE)}<br/>{escape(settings.FIRMA_MATRICULA)}", e["firma"]))
    tabla_firma = Table([[None, firma]], colWidths=[8.2 * cm, 7.0 * cm])
    tabla_firma.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "CENTER"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    historia.append(tabla_firma)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=2.7 * cm, rightMargin=2.7 * cm, topMargin=2.5 * cm, bottomMargin=2.5 * cm,
        title=f"Acceso al tablero «{paquete.titulo}»", author=settings.FIRMA_NOMBRE,
    )
    doc.build(historia)
    return buffer.getvalue()
