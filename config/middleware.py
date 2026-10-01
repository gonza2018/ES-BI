from django.conf import settings
from django.http import HttpResponsePermanentRedirect


class HostCanonicoMiddleware:
    """Redirige gserelic.com -> www.gserelic.com (301), conservando ruta y query."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        canonico = settings.HOST_CANONICO
        host = request.get_host().split(":")[0].lower()
        if canonico and host in settings.REDIRIGIR_A_CANONICO:
            return HttpResponsePermanentRedirect(f"https://{canonico}{request.get_full_path()}")
        return self.get_response(request)


# CSP estricta para el sitio público y el portal.
# Las páginas de paquetes del portal (Paso 2) definirán su propia CSP.
CSP_ESTRICTA = "; ".join(
    [
        "default-src 'self'",
        "img-src 'self' data:",
        "style-src 'self'",
        "script-src 'self'",
        "font-src 'self'",
        "frame-src 'self'",
        "frame-ancestors 'self'",
        "form-action 'self'",
        "base-uri 'self'",
        "object-src 'none'",
    ]
)


# CSP de los archivos de paquetes (/portal/ver/...). Probada con pbg-sde v1.1: todo local
# (Plotly y fuentes en assets/), JS y estilos inline, sin 'unsafe-eval' ni CDNs.
# El sitio público y el portal conservan la CSP estricta de arriba.
CSP_PAQUETES = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "frame-ancestors 'self'",
        "object-src 'none'",
        "base-uri 'self'",
    ]
)


class CabecerasSeguridadMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # El admin de Django usa estilos inline: no se le aplica la CSP estricta.
        if not request.path.startswith("/gestion/"):
            response.headers.setdefault("Content-Security-Policy", CSP_ESTRICTA)
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response
