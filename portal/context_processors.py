from .marca import contexto_marca, es_neutro


def marca(request):
    """Variables de marca para las plantillas del portal (fuera del portal no consulta la base)."""
    if not request.path.startswith("/portal/"):
        return {}
    return contexto_marca(es_neutro(request))
