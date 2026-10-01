"""
Configuración de gserelic.com.

Todo lo sensible o que cambia entre local y producción se lee de variables
de entorno (ver .env.example y README.md).
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(nombre, defecto=False):
    return os.environ.get(nombre, str(defecto)).strip().lower() in {"1", "true", "si", "sí", "yes"}


def env_list(nombre, defecto=""):
    return [x.strip() for x in os.environ.get(nombre, defecto).split(",") if x.strip()]


# En local se puede usar un archivo .env (no se versiona).
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "solo-para-desarrollo-local-no-usar-en-produccion"
    else:
        raise RuntimeError("Falta la variable de entorno DJANGO_SECRET_KEY.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
if os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
    ALLOWED_HOSTS.append(os.environ["RENDER_EXTERNAL_HOSTNAME"])

CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")

# Host canónico: las peticiones a los hosts listados en REDIRIGIR_A_CANONICO
# se redirigen con 301 a este host (gserelic.com -> www.gserelic.com).
HOST_CANONICO = os.environ.get("HOST_CANONICO", "")
REDIRIGIR_A_CANONICO = env_list("REDIRIGIR_A_CANONICO", "")

# Token para descargar respaldos desde un script (ver README). Vacío = deshabilitado.
RESPALDO_TOKEN = os.environ.get("RESPALDO_TOKEN", "").strip()

# Directorio de datos persistentes (disco de Render montado en /var/data).
# "or": una variable definida pero vacía (DATA_DIR= en el .env) también usa el valor por defecto.
DATA_DIR = Path(os.environ.get("DATA_DIR") or BASE_DIR / "datos_locales")
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    # Durante el build de Render el disco todavía no está montado y /var/data es de
    # solo lectura. El build (collectstatic) no usa la base, así que se sigue; al
    # arrancar, el disco ya está montado y la carpeta existe.
    pass

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "axes",
    "cuentas",
    "sitio",
    "portal",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "config.middleware.HostCanonicoMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "config.middleware.CabecerasSeguridadMiddleware",
    # axes debe ir al final
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "sitio.context_processors.sitio",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db.sqlite3",
        "OPTIONS": {
            # WAL mejora la concurrencia de lectura/escritura en SQLite.
            "init_command": "PRAGMA journal_mode=WAL;",
            "transaction_mode": "IMMEDIATE",
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Usuarios: el correo es el identificador --------------------------------
AUTH_USER_MODEL = "cuentas.Usuario"

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "portal:login"
LOGIN_REDIRECT_URL = "portal:inicio"
LOGOUT_REDIRECT_URL = "portal:login"

# --- Protección contra fuerza bruta (django-axes) ---------------------------
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1  # horas
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
# El formulario de login envía el correo en el campo "username".
AXES_USERNAME_FORM_FIELD = "username"
AXES_LOCKOUT_TEMPLATE = "portal/bloqueado.html"
# IP real del visitante detrás del proxy de Render: ver config/ip_cliente.py.
AXES_CLIENT_IP_CALLABLE = "config.ip_cliente.obtener_ip"
IP_CLIENTE_ENCABEZADO = os.environ.get("IP_CLIENTE_ENCABEZADO", "HTTP_X_FORWARDED_FOR").strip()
IP_CLIENTE_PROXIES = int(os.environ.get("IP_CLIENTE_PROXIES", "1"))

# --- Idioma y zona horaria --------------------------------------------------
LANGUAGE_CODE = "es-ar"
TIME_ZONE = "America/Argentina/Buenos_Aires"
USE_I18N = True
USE_TZ = True

# --- Archivos estáticos (CSS, JS, imágenes del sitio) -----------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
if "test" in sys.argv:
    # Los tests no requieren correr collectstatic.
    STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
# Archivos servidos en la raíz del dominio (/favicon.ico).
WHITENOISE_ROOT = BASE_DIR / "static_raiz"

# Medios PÚBLICOS (solo imágenes de fichas de proyectos del sitio).
MEDIA_URL = "/media/"
MEDIA_ROOT = DATA_DIR / "media_publica"

# Paquetes PRIVADOS del portal: nunca se sirven por una URL pública, solo por la
# vista protegida /portal/ver/ (sesión + grupo).
PAQUETES_ROOT = DATA_DIR / "paquetes_privados"
PAQUETE_MAX_BYTES = 50 * 1024 * 1024  # tamaño máximo descomprimido (y del zip subido)
PAQUETE_MAX_ARCHIVOS = 2000

DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# --- Correo ------------------------------------------------------------------
# En el plan free de Render los puertos SMTP están bloqueados: hace falta
# un plan pago (Starter) para que el formulario de contacto envíe.
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_TIMEOUT = 15
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "webmaster@localhost")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
CONTACTO_DESTINATARIOS = env_list("CONTACTO_DESTINATARIOS", EMAIL_HOST_USER)
# WhatsApp del sitio: solo dígitos, con código de país (ej. 5493851234567).
# Vacío = no se muestran los botones de WhatsApp.
WHATSAPP_NUMERO = "".join(c for c in os.environ.get("WHATSAPP_NUMERO", "") if c.isdigit())
# Si está definida, el formulario envía por Formspree (HTTPS) en lugar de SMTP.
FORMSPREE_ID = os.environ.get("FORMSPREE_ID", "").strip()

# --- Seguridad en producción -------------------------------------------------
X_FRAME_OPTIONS = "SAMEORIGIN"  # el portal mostrará paquetes en iframe del mismo origen
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 60 * 60 * 8  # 8 horas

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # HSTS: empezar con 1 hora; subir a 1 año cuando todo esté verificado.
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "3600"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

if "test" in sys.argv:
    # El cliente de tests usa HTTP: sin esto, todo respondería 301 a HTTPS.
    SECURE_SSL_REDIRECT = False
    # Salida limpia: varios tests simulan fallas a propósito (SMTP caído, Formspree sin red,
    # intentos de login fallidos); sus registros no son errores reales.
    AXES_VERBOSE = False
    LOGGING["root"]["level"] = "CRITICAL"
    LOGGING["loggers"] = {"django": {"level": "CRITICAL"}, "axes": {"level": "CRITICAL"}}
    STATIC_ROOT.mkdir(exist_ok=True)  # evita el aviso "No directory at: staticfiles"
    # Cifrado rápido SOLO en tests (los usuarios de prueba no son reales).
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
