from django.utils.functional import SimpleLazyObject

from portal.models import Paquete


class EstadoDatos:
    """Qué hay de libre acceso en /datos/ (alimenta el menú y la franja de Inicio).

    Se consulta una sola vez por pedido y solo si alguna plantilla lo usa.
    """

    def __init__(self):
        self.ultimo = Paquete.publicos().first()  # el más recientemente actualizado

    @property
    def hay(self):
        """Hay al menos un paquete público y publicado: aparece la pestaña DATOS."""
        return self.ultimo is not None

    @property
    def nuevo(self):
        """El último se actualizó hace DIAS_AVISO_DATOS días o menos: pastilla "Nuevo" y franja."""
        return self.ultimo is not None and self.ultimo.es_reciente()


def datos(request):
    return {"DATOS": SimpleLazyObject(EstadoDatos)}
