import reflex as rx

# Configuración de la aplicación
class PortafolioConfig(rx.Config):
    pass

config = PortafolioConfig(
    app_name="portafolio",
    db_url="sqlite:///portafolio.db",
    env=rx.Env.DEV,
)

# Página de inicio
def index() -> rx.Component:
    return rx.container(
        rx.heading("¡Hola, soy [Tu Nombre]!", size="2xl"),
        rx.text("Bienvenido a mi portafolio. Aquí encontrarás información sobre mí y mis proyectos."),
        rx.button("Ver proyectos", on_click="/projects"),
    )

# Página "Sobre mí"
def about() -> rx.Component:
    return rx.container(
        rx.heading("Sobre mí", size="xl"),
        rx.text("Aquí puedes escribir sobre tu experiencia, habilidades y formación."),
    )

# Página de proyectos
def projects() -> rx.Component:
    return rx.container(
        rx.heading("Mis Proyectos", size="xl"),
        rx.text("Aquí puedes listar tus proyectos con enlaces y descripciones."),
    )

# Página de contacto
def contact() -> rx.Component:
    return rx.container(
        rx.heading("Contacto", size="xl"),
        rx.text("Puedes enviarme un mensaje completando el siguiente formulario."),
        rx.input(placeholder="Tu nombre"),
        rx.input(placeholder="Tu correo"),
        rx.textarea(placeholder="Tu mensaje"),
        rx.button("Enviar"),
    )

# Configuración de las rutas
app = rx.App()
app.add_page(index, route="/")
app.add_page(about, route="/about")
app.add_page(projects, route="/projects")
app.add_page(contact, route="/contact")

# Ejecutar la aplicación
if __name__ == "__main__":
    app.compile()
