from django.conf import settings


def sitio(request):
    if settings.HOST_CANONICO:
        base = f"https://{settings.HOST_CANONICO}"
    else:
        base = request.build_absolute_uri("/").rstrip("/")
    return {"URL_BASE": base}
