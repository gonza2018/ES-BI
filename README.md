# gserelic.com — ES & BI

Sitio institucional de ES & BI y portal privado de clientes (`/portal/`), en Django 5.2.

| App | Qué hace |
|---|---|
| `cuentas` | Usuario con **correo como identificador** (sin username). |
| `sitio` | Web pública: inicio, quiénes somos, servicios (carrusel con ventanas "Conocer más"), proyectos, contacto, página personal `/cv/`, `robots.txt`, `sitemap.xml`. |
| `portal` | Login por correo y contraseña, protección contra fuerza bruta (django-axes) y **paquetes** (dashboards y sitios estáticos) privados por organismo. |
| `cfi_matriz` | *(Paso 3, pendiente)* App de carga de datos del CFI, con base propia. |

El admin está en **`/gestion/`** (no en `/admin/`).

## Variables de entorno

| Variable | Producción (Render) | Descripción |
|---|---|---|
| `DJANGO_SECRET_KEY` | **obligatoria** | Clave larga y aleatoria. Generar con `python -c "import secrets; print(secrets.token_urlsafe(50))"`. |
| `DJANGO_DEBUG` | `0` | `1` solo en local. |
| `DJANGO_ALLOWED_HOSTS` | `www.gserelic.com,gserelic.com` | El host `*.onrender.com` se agrega solo. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://www.gserelic.com,https://gserelic.com` | |
| `HOST_CANONICO` | `www.gserelic.com` | Host oficial del sitio. |
| `REDIRIGIR_A_CANONICO` | `gserelic.com` | Hosts que redirigen (301) al canónico. |
| `DATA_DIR` | `/var/data` | Punto de montaje del disco persistente: bases, archivos subidos y respaldos. |
| `WHATSAPP_NUMERO` | ej. `5493851234567` | Solo dígitos, con código de país (54), 9 y característica sin 0 ni 15. Vacía = sin botones de WhatsApp. |
| `FORMSPREE_ID` | `movwnndw` | Si está definida, el formulario envía por **Formspree** (HTTPS) y no usa SMTP. Funciona también en el plan free. |
| `EMAIL_HOST_USER` | tu cuenta de Gmail | Solo si no se usa Formspree. |
| `EMAIL_HOST_PASSWORD` | contraseña de aplicación | Solo si no se usa Formspree. |
| `DEFAULT_FROM_EMAIL` | igual a `EMAIL_HOST_USER` | Remitente de los correos del sitio. |
| `CONTACTO_DESTINATARIOS` | uno o varios correos, separados por coma | Quién recibe los mensajes del formulario. |
| `IP_CLIENTE_ENCABEZADO` | `HTTP_X_FORWARDED_FOR` (defecto) | De dónde sale la IP real del visitante. Confirmar con `/gestion/diagnostico-ip/`. |
| `IP_CLIENTE_PROXIES` | `1` (defecto) | Cuántas IPs contar desde la derecha en `X-Forwarded-For`. |
| `RESPALDO_TOKEN` | 40+ caracteres aleatorios | Permite que el script de Windows descargue respaldos. Vacío = deshabilitado. |
| `SECURE_HSTS_SECONDS` | `3600` al principio | Subir a `31536000` (1 año) cuando todo esté verificado. |

> **Correo:** con `FORMSPREE_ID` el formulario envía por HTTPS y funciona en cualquier plan. Sin ella usa SMTP,
> y el plan free de Render bloquea los puertos SMTP (25, 465 y 587). Si el envío falla, el sitio muestra un
> aviso y no se cae. Si en Formspree está activada la restricción por dominio, desactivarla: el envío sale
> desde el servidor, no desde el navegador.

## Desarrollo local (Windows, PowerShell)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # completar DJANGO_DEBUG=1; el correo sale por consola
python manage.py migrate
python manage.py createsuperuser   # pide correo y contraseña
python manage.py runserver
```

- Sitio: http://127.0.0.1:8000/ · Portal: http://127.0.0.1:8000/portal/ · Admin: http://127.0.0.1:8000/gestion/
- Tests: `python manage.py test`
- Los datos locales quedan en `datos_locales/` (no se versiona).

## Migración desde el sitio Flask (repositorio ES-BI)

En la PC, dentro del clon del repositorio (PowerShell):

```powershell
cd ES-BI
git checkout main
git pull
git checkout -b migracion-django
git rm -r --quiet app.py Procfile requirements.txt templates static
Expand-Archive ..\gserelic_django.zip -DestinationPath ..\tmp_django
Copy-Item ..\tmp_django\gserelic\* . -Recurse -Force
Remove-Item ..\tmp_django -Recurse -Force
git add .
git commit -m "Migración del sitio de Flask a Django"
git push -u origin migracion-django
```

`main` no se toca: el sitio actual sigue online hasta que se una la rama.

### Servicio de prueba en Render (gratis)

*New → Web Service* → repositorio `ES-BI`, rama **`migracion-django`**, plan **Free**.
Build `bash build.sh`, Start `bash start.sh`, y solo estas variables:
`DJANGO_SECRET_KEY` (una nueva), `FORMSPREE_ID=movwnndw`, y para poder entrar al admin
`DJANGO_SUPERUSER_EMAIL` y `DJANGO_SUPERUSER_PASSWORD` (el plan free no tiene *Shell*; el usuario se crea al arrancar).
Sin disco y sin `HOST_CANONICO`: los datos de prueba se borran en cada deploy, y está bien así.

### Pasar a producción

1. Probar todo en el servicio de prueba.
2. En el servicio actual: plan Starter, disco en `/var/data`, variables de la tabla de arriba y comandos de Build/Start.
3. Unir `migracion-django` en `main` (Pull Request en GitHub). Render despliega solo.
4. Borrar el servicio de prueba.

## Despliegue en Render

Servicio web existente, configurado así:

| Campo | Valor |
|---|---|
| Plan | **Starter** (no se duerme y permite SMTP) |
| Runtime | Python 3 (versión en `.python-version`) |
| Build Command | `bash build.sh` |
| Start Command | `bash start.sh` |
| Disco | 1 GB, montado en `/var/data` |
| Variables | las de la tabla de arriba |

`start.sh` corre las migraciones al arrancar, porque el disco no está disponible durante el build.

**Dominios:** en Render → *Settings → Custom Domains* tienen que estar `www.gserelic.com` y `gserelic.com`,
los dos con certificado verificado. En GoDaddy, los registros DNS que indique Render para cada uno.
El sitio redirige `gserelic.com` → `https://www.gserelic.com`.

**Primer usuario administrador:** en Render → *Shell*: `python manage.py createsuperuser`, o bien definir
`DJANGO_SUPERUSER_EMAIL` y `DJANGO_SUPERUSER_PASSWORD` y redeployar (después borrar esas dos variables).

## Portal: grupos, usuarios y paquetes

Todo se hace en `/gestion/`. La regla es simple: **cada organismo es un grupo**; un usuario ve
los paquetes de sus grupos; el superusuario ve todo.

### Crear un grupo (uno por organismo)
*Autenticación y autorización* → **Grupos** → *Agregar*. Nombre, por ejemplo `DGEyC SDE` o `CFI`.
No hace falta marcar permisos: los grupos solo se usan para decidir quién ve cada paquete.

> Truco: si el nombre del grupo es **igual** al `organismo` de `meta.json` (sin importar mayúsculas),
> el paquete se le asigna solo la primera vez que se sube. `pbg-sde` trae
> `"organismo": "DGEyC Santiago del Estero"`; si el grupo se llama `DGEyC SDE`, hay que asignarlo a mano.

### Crear un usuario
*Cuentas de usuario* → **Usuarios** → *Agregar*: correo, **nombre** (el portal saluda con el primero),
organismo, contraseña (10+ caracteres) y su grupo. No hay registro público ni recuperación de contraseña
por correo: si alguien la olvida, se la cambiás desde su ficha (*formulario* de contraseña).

- Para quitar el acceso: desmarcar **Activo** (no borrar: se pierde el registro de último acceso).
- La columna **last login** muestra cuándo entró por última vez (si el evaluador abrió el portal).
- Bloqueado por intentos fallidos (5 → 1 hora): *Axes → Access attempts* → borrar su registro,
  o `python manage.py axes_reset`.

### Subir un paquete nuevo
*Portal de clientes* → **Paquetes** → **Subir paquete (.zip)** → elegir el zip → *Subir y publicar*.

El sistema controla que tenga `index.html` y `meta.json`, que no haya rutas con `..`, rutas absolutas
ni enlaces simbólicos, que no pese más de 50 MB descomprimido y que no traiga archivos ejecutables de
servidor (`.py`, `.php`, `.sh`…). Si algo falla, lo dice y no guarda nada.

Después de subirlo, en su ficha: **Grupos con acceso** → pasar el grupo a la derecha → *Guardar*.
Hasta que tenga un grupo, solo lo ve el superusuario.

### Actualizar un paquete (versión nueva)
Subir el zip nuevo igual que arriba (o desde la ficha: **Subir nueva versión (.zip)**). Si el `slug`
de `meta.json` ya existe, se publica la versión nueva y **la anterior queda en el historial** (abajo
en la ficha). Los grupos asignados se conservan. `meta.json` manda: título, estado, versión, fecha y
descripción se actualizan con lo que traiga.

**Volver a una versión anterior:** *Versiones de paquetes* → tildar la versión → acción
*Volver a esta versión* → *Ir*.

### Despublicar, cambiar estado o borrar
- **Despublicar** (ocultarlo sin borrarlo): en la ficha, desmarcar **Publicado**; o en la lista,
  tildar y elegir la acción *Despublicar*. El superusuario lo sigue viendo, con la etiqueta *No publicado*.
- **Cambiar el estado** (borrador / en revisión / aprobado) sin subir otro zip: campo **Estado** en la ficha.
- **Borrar**: botón *Eliminar* de la ficha. Borra también sus archivos del disco (todas las versiones).

### Cómo se sirve (para la próxima persona que toque el código)
- `/portal/` grilla · `/portal/tablero/<slug>/` página con el iframe, descargas y pantalla completa ·
  `/portal/ver/<slug>/` y `/portal/ver/<slug>/<ruta>` archivos del paquete.
- Cada archivo pasa por la vista protegida: sin sesión → login; grupo incorrecto → 404 (no revela que existe).
- Solo se sirven `.html .js .css .json .woff2 .png .jpg .jpeg .svg` y, como descarga, `.xlsx .pdf .csv`.
  Cualquier otra extensión da 404 (por eso las licencias `.txt` de un paquete no se sirven).
- Los archivos de paquetes llevan su propia CSP (`config/middleware.py`, `CSP_PAQUETES`) y
  `Cache-Control: private, max-age=300`. El resto del sitio mantiene la CSP estricta.
- **Los zips de paquetes nunca van al repositorio** (es público): `.gitignore` excluye `*.zip`.
  Para probar con el paquete real: `PAQUETE_REAL=C:\ruta\pbg-sde.zip python manage.py test portal`.

## Mensajes del formulario de contacto

Cada mensaje se **guarda primero** en la base y **después** se intenta el aviso por correo
(Formspree o SMTP). Si el aviso falla, el visitante igual ve "Mensaje enviado" y el mensaje no se pierde.

`/gestion/` → *Sitio público* → **Mensajes de contacto**:
- Los no leídos se filtran con *Por leído → No*. Abrir un mensaje lo marca como leído.
- La columna *aviso por correo enviado* muestra si te llegó el correo. Si no, el campo *error del aviso*
  dice por qué (por ejemplo, el motivo que da Formspree).
- Acción **Reintentar el aviso por correo**: seleccionar mensajes → elegir la acción → *Ir*.

Conviene entrar a revisar cada tanto, sobre todo hasta confirmar que los avisos llegan bien.
Los mensajes tienen datos personales de quien escribe: borrar los que ya no hagan falta.

## Fichas de proyectos (sitio público)

`/gestion/` → *Proyectos*: título, organismo, año, resumen opcional, imagen y texto alternativo.
Solo se muestran las marcadas como **Publicado**. Si no hay ninguna, la sección no aparece.
**No cargar datos sensibles**: esto es público.

## Respaldos

Hay dos capas, y la segunda es la que protege si se pierde el disco de Render.

**1. Snapshots de Render (automáticos).** Render hace un snapshot del disco cada 24 horas y lo guarda
al menos 7 días. Se restaura desde *Disks* en el panel del servicio, pero solo el disco **completo**:
todo lo que cambió después del snapshot se pierde. Sirve ante un error reciente, no como archivo
histórico, y vive en la misma plataforma.

**2. Copia fuera de Render (la hacés vos).** `/gestion/respaldo/` genera un `.tar.gz` consistente
(bases SQLite copiadas con la API de backup, imágenes públicas y paquetes privados) y lo descarga.

- **A mano:** entrar al admin como superusuario y abrir `https://www.gserelic.com/gestion/respaldo/`.
- **Automático en Windows:** `scripts\descargar_respaldo.ps1`.
  1. Generar un token: `python -c "import secrets; print(secrets.token_urlsafe(40))"`.
  2. Cargarlo en Render como `RESPALDO_TOKEN`.
  3. En la PC, una sola vez:
     `[Environment]::SetEnvironmentVariable("GSERELIC_RESPALDO_TOKEN", "<token>", "User")`
  4. Probar: `powershell -ExecutionPolicy Bypass -File scripts\descargar_respaldo.ps1`
     (guarda en `Documentos\Respaldos_gserelic`, conserva los 12 últimos).
  5. Programador de tareas → *Crear tarea básica* → semanal → *Iniciar un programa*:
     `powershell.exe` con argumentos `-ExecutionPolicy Bypass -File "C:\ruta\ES-BI\scripts\descargar_respaldo.ps1"`.

Además, `python manage.py respaldar` (desde *Shell* en Render) crea el mismo archivo en
`DATA_DIR/respaldos/` y conserva los 5 últimos. Ese queda en el mismo disco: no reemplaza la copia externa.

**Restaurar:** descomprimir el `.tar.gz`; `bases/db.sqlite3` va a `DATA_DIR/`, y `media_publica/` y
`paquetes_privados/` a `DATA_DIR/` con el mismo nombre.

## Seguridad

**IP del visitante y bloqueo por intentos fallidos.** El bloqueo es por usuario + IP. La IP se toma del
último proxy de confianza contando desde la derecha de `X-Forwarded-For` (lo de la izquierda lo puede
inventar el cliente). Después de cada cambio de infraestructura, entrar como superusuario a
`/gestion/diagnostico-ip/` y verificar que la IP calculada coincida con tu IP pública.
Si no coincide, ajustar `IP_CLIENTE_ENCABEZADO` / `IP_CLIENTE_PROXIES` según lo que muestre esa página.

**Riesgo aceptado: los paquetes corren con la sesión del usuario.** Los dashboards se muestran en un
iframe del **mismo origen** y ejecutan JavaScript inline. Un paquete malicioso podría actuar con la
sesión de quien lo mira: leer otras páginas del portal y, si quien lo mira es **superusuario**, usar
el admin. Es aceptable mientras **solo se suban paquetes propios** (los arma el Claude de dashboards y
los subís vos). Recomendación práctica: revisar cada paquete antes de subirlo y no abrirlo desde el
portal con la sesión de superusuario si viene de otra fuente.
**Si algún día sube paquetes un tercero**, hay que servirlos desde un subdominio aparte
(por ejemplo `paquetes.gserelic.com`), que no comparte la sesión del portal.

## Pendiente

- **Paso 3:** app `cfi_matriz` con base propia.
