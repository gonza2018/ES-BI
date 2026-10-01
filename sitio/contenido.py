"""Textos de la sección Servicios. Editar acá para cambiar tarjetas y ventanas "Conocer más"."""

SERVICIOS = [
    {
        "id": "consultoria",
        "titulo": "Consultoría Económico Financiera",
        "imagen": "sitio/img/consultoria_economico_financiera.jpg",
        "alt": "Tablet con gráficos de análisis financiero",
        "resumen": "La complejidad volátil de las variables macroeconómicas genera inquietud y curiosidad sobre las medidas económicas.",
        "texto": (
            "La complejidad volátil de las variables macroeconómicas genera inquietud y curiosidad sobre las "
            "medidas económicas tomadas por los policy makers. Es siempre valorada la opinión profesional sobre "
            "los argumentos político-económicos de los funcionarios gubernamentales."
        ),
    },
    {
        "id": "proyectos",
        "titulo": "Evaluación de Proyectos",
        "imagen": "sitio/img/evaluacion_de_proyectos.jpg",
        "alt": "Equipo revisando documentos y gráficos junto a una computadora",
        "resumen": "Formulación y evaluación de proyectos públicos y privados, de la demanda al impacto social.",
        "texto": (
            "Formulación y evaluación de proyectos públicos y privados: estudios de mercado, tamaño y localización "
            "del proyecto, inversiones, financiamiento, rentabilidad y balanza de divisas, estimación de la demanda "
            "(privada y social), proyección de la oferta y de las curvas de costos (privados y sociales), "
            "estimación de impactos e incidencia de programas sociales."
        ),
    },
    {
        "id": "transferencia",
        "titulo": "Estudio de Precios de Transferencia",
        "imagen": "sitio/img/precios_de_transferencia.jpg",
        "alt": "Contenedores de carga apilados en un puerto",
        "resumen": "Asesoramiento para su operatoria de exportación e importación con empresas del exterior.",
        "texto": (
            "Brindamos asesoramiento para su operatoria de exportación o importación con empresas del exterior, "
            "evaluando las actividades y funciones desarrolladas por su compañía, los riesgos asumidos y los activos "
            "utilizados en el ejercicio de dichas funciones. Generamos informes con las justificaciones del análisis "
            "de las operaciones sujetas a la normativa, para transacciones con sujetos vinculados o radicados en "
            "países no cooperantes y PJBONT. Incluye formularios F2668, F4501, F8096, F8097 e Informe Maestro."
        ),
    },
    {
        "id": "encuestas",
        "titulo": "Encuestas e Investigaciones Sociales",
        "imagen": "sitio/img/encuesta_investigaciones_sociales.jpg",
        "alt": "Personas revisando gráficos impresos de resultados de una encuesta",
        "resumen": "Encuestas bien diseñadas y cuidadosamente analizadas para la toma de decisiones.",
        "texto": (
            "Nos especializamos en crear encuestas bien diseñadas y cuidadosamente analizadas que brindan "
            "información para la toma de decisiones. Contamos con un equipo de encuestadores y analistas con amplia "
            "experiencia en investigación y relevamiento de temas económicos, sociales y políticos. Realizamos "
            "estudios de mercado, de opinión pública, diagnóstico de coyuntura, clima social, evaluación de "
            "impacto, marketing político y análisis electoral."
        ),
    },
    {
        "id": "datos",
        "titulo": "Análisis de Bases de Datos",
        "imagen": "sitio/img/analisis_bases_de_datos.jpg",
        "alt": "Manos escribiendo código en una computadora portátil",
        "resumen": "Análisis de datos estructurados y no estructurados con forecasting y machine learning.",
        "texto": (
            "La cantidad de información disponible para el estudio de fenómenos económicos y sociales hace "
            "indispensable el conocimiento de habilidades para su manejo. Ofrecemos análisis de datos e información "
            "tanto estructurada como no estructurada, a través del dominio de forecasting, machine learning y "
            "deep learning."
        ),
    },
    {
        "id": "espacial",
        "titulo": "Econometría Espacial",
        "imagen": "sitio/img/econometria_espacial.jpg",
        "alt": "Mapa temático con el porcentaje de hogares con necesidades básicas insatisfechas por zona",
        "resumen": "Patrones espaciales y clústers con significancia estadística a partir de información geográfica.",
        "texto": (
            "Al observar los diferentes elementos contenidos en una capa de información geográfica se identifican "
            "patrones, distribuciones o agrupaciones de entidades que responden a una lógica. El estudio de los "
            "patrones espaciales a través de las nuevas tecnologías permite explicar la formación de clústers con "
            "significancia estadística."
        ),
    },
]


def en_grupos(lista, n):
    return [lista[i : i + n] for i in range(0, len(lista), n)]


SERVICIOS_EN_DIAPOSITIVAS = en_grupos(SERVICIOS, 2)
