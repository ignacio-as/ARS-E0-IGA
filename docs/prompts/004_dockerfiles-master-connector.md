# Conversación 004 - Dockerfile de master y connector

## Usuario

> Chat para los dockerfile, puedes ayudarme con la creación del de conector y master

## Asistente

Claro. Suponiendo que tu proyecto tiene las carpetas `master`, `connector` y `database` en la raíz, puedes comenzar con dos Dockerfile sencillos basados en Python 3.11.

Para `master/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY master/requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY master ./master
COPY database ./database

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "master.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Este contenedor:

- Instala las dependencias de FastAPI y PostgreSQL.
- Copia el código de `master`.
- Copia `database` para que la aplicación pueda acceder al archivo `schema.sql`.
- Ejecuta Uvicorn escuchando en todas las interfaces del contenedor.

Para `connector/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY connector/requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY connector .

CMD ["python", "observer.py"]
```

Este segundo contenedor instala las dependencias de RabbitMQ y ejecuta el proceso permanente encargado de consumir mensajes.

Estos Dockerfile asumen que Docker Compose utiliza la raíz del proyecto como contexto de construcción. La configuración correspondiente debería verse aproximadamente así:

```yaml
services:
  master:
    build:
      context: .
      dockerfile: master/Dockerfile

  connector:
    build:
      context: .
      dockerfile: connector/Dockerfile
```

No copiaría el archivo `.env` dentro de ninguna imagen. Las credenciales y direcciones deben entregarse a los contenedores mediante `environment` o `env_file` en Docker Compose.

Esta sería una primera versión funcional de ambos archivos. Antes de la entrega todavía habría que agregar un `HEALTHCHECK` a cada contenedor. Para `master` puede consultar un endpoint `/health`; para `connector` puedes comprobar un archivo de estado actualizado por el proceso o verificar que el proceso siga ejecutándose. También conviene agregar un `.dockerignore` para evitar copiar `.env`, `.git`, archivos temporales y credenciales al contexto de construcción.

## Usuario

> como seria el HEALTHCHECK

## Asistente

Para `master`, lo más claro es crear un endpoint `/health` que compruebe también la conexión con PostgreSQL. Por ejemplo, en FastAPI:

```python
from fastapi import HTTPException
import psycopg


@app.get("/health")
def health():
    try:
        with connect_to_database() as connection:
            connection.execute("SELECT 1")
        return {"status": "ok"}
    except psycopg.Error as error:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from error
```

Luego debes instalar `curl` y agregar el `HEALTHCHECK` al `master/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY master/requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY master ./master
COPY database ./database

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail http://localhost:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "master.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

En el caso de `connector`, no necesitas crear un servidor HTTP solamente para comprobar su salud. Una opción sencilla es que `observer.py` cree un archivo cuando logra conectarse y lo elimine cuando pierde la conexión:

```python
from pathlib import Path


HEALTH_FILE = Path("/tmp/connector-ready")


def start_observer():
    HEALTH_FILE.unlink(missing_ok=True)

    while True:
        try:
            connection = connect_to_rabbitmq()
            channel = connection.channel()
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(
                queue=RABBITMQ_QUEUE,
                on_message_callback=on_message,
                auto_ack=False,
            )

            HEALTH_FILE.touch()
            channel.start_consuming()

        except pika.exceptions.AMQPError as error:
            HEALTH_FILE.unlink(missing_ok=True)
            print("Conexión perdida:", error)
            time.sleep(5)
```

Su `connector/Dockerfile` podría quedar así:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY connector/requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY connector .

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD test -f /tmp/connector-ready || exit 1

CMD ["python", "observer.py"]
```

Con esto, `master` estará saludable solamente cuando su API y la base de datos respondan. `connector` estará saludable cuando haya establecido la conexión con RabbitMQ y se encuentre listo para consumir. Es importante eliminar el archivo si la conexión se interrumpe; de lo contrario, Docker podría seguir marcando el contenedor como saludable aunque ya no estuviera conectado.

## Usuario

> ayudame a entender, uno sube a git y lluego a la ec2 el pyoyecto como datos vacios, luego docker compose genera las imagenes y de ellas los contenedores vivos?

## Asistente

Sí, esa es la idea general. Al repositorio Git subes el **código y la configuración reproducible**, pero no los datos reales, credenciales ni archivos secretos.

El flujo sería:

```text
Tu computador
    │
    │ git push
    ▼
Repositorio Git
    │
    │ git clone / git pull
    ▼
Instancia EC2
    │
    │ docker compose up --build -d
    ▼
Imágenes Docker
    │
    ▼
Contenedores en ejecución
```

En Git normalmente guardarías:

- El código Python de `master` y `connector`.
- Los dos Dockerfile.
- `docker-compose.yml`.
- `requirements.txt`.
- `schema.sql`.
- Una plantilla como `.env.example`, sin valores secretos.
- La configuración de Nginx que solicita la entrega.

No deberías subir:

- El archivo `.env` real.
- Contraseñas de PostgreSQL o RabbitMQ.
- Claves de AWS.
- El archivo `.pem` de la instancia EC2.
- Datos generados por la base de datos.

En EC2 clonas el repositorio y creas manualmente el `.env` con las credenciales correctas. Después ejecutas:

```bash
docker compose up --build -d
```

Docker Compose realiza varias tareas:

1. Lee `docker-compose.yml`.
2. Construye la imagen de `master` usando `master/Dockerfile`.
3. Construye la imagen de `connector` usando `connector/Dockerfile`.
4. Descarga la imagen oficial de PostgreSQL si todavía no existe localmente.
5. Crea la red interna y los volúmenes declarados.
6. Crea e inicia los contenedores `master`, `connector` y `database`.

Una **imagen** es una plantilla inmutable que contiene el código, las dependencias y el comando de inicio. Un **contenedor** es una instancia viva de esa imagen, es decir, el proceso que realmente está ejecutándose.

La base de datos inicialmente estaría vacía, salvo por las tablas creadas mediante `schema.sql`. Cuando lleguen eventos, PostgreSQL guardará los registros en un **volumen Docker**. Ese volumen debe declararse en Compose:

```yaml
services:
  database:
    image: postgres:17-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

Gracias al volumen, los datos sobreviven si recreas o actualizas el contenedor de PostgreSQL. Sin él, podrías perder la información al eliminar el contenedor.

Cuando cambies el código, el ciclo habitual será:

```bash
git pull
docker compose up --build -d
```

Esto reconstruye las imágenes que cambiaron y recrea sus contenedores. El volumen de PostgreSQL permanece, por lo que los eventos almacenados no deberían desaparecer. Nginx es la excepción de esta arquitectura: según el enunciado, se instala y configura directamente en la EC2, fuera de Docker, para dirigir el tráfico del dominio hacia `master`.

## Usuario

> ¿puedes listarme de forma sencilla los comandos mas importante de compose y su utilidad?

## Asistente

Claro. Estos son los comandos de Docker Compose que probablemente utilizarás con mayor frecuencia. Debes ejecutarlos desde la carpeta que contiene `docker-compose.yml`.

```bash
docker compose up -d
```

Crea e inicia los servicios en segundo plano. Si las imágenes ya existen, las reutiliza.

```bash
docker compose up --build -d
```

Reconstruye las imágenes y luego inicia los servicios. Es el comando habitual después de cambiar código, dependencias o un Dockerfile.

```bash
docker compose ps
```

Muestra los contenedores del proyecto, su estado y si están saludables.

```bash
docker compose logs
```

Muestra los registros de todos los servicios.

```bash
docker compose logs -f
```

Sigue mostrando los registros en tiempo real. Puedes salir con `Ctrl+C` sin detener los contenedores.

```bash
docker compose logs -f master
docker compose logs -f connector
docker compose logs -f database
```

Muestra solamente los registros del servicio indicado.

```bash
docker compose stop
```

Detiene los contenedores sin eliminarlos.

```bash
docker compose start
```

Vuelve a iniciar contenedores que fueron detenidos con `stop`.

```bash
docker compose restart
```

Reinicia todos los servicios. También puedes reiniciar uno solo, por ejemplo:

```bash
docker compose restart connector
```

```bash
docker compose down
```

## Usuario

> Puedes ayudarme con una guia inicial con la estructura del compose y explicame cada parte y como se forma la red interna

## Asistente

Sí. Una estructura inicial de `docker-compose.yml` para `database`, `master` y `connector` podría ser:

```yaml
services:
  database:
    image: postgres:17-alpine
    container_name: database
    environment:
      POSTGRES_DB: energyshark
      POSTGRES_USER: energyshark
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U energyshark -d energyshark"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - energyshark_net
    restart: unless-stopped

  master:
    build:
      context: .
      dockerfile: master/Dockerfile
    container_name: master
    environment:
      DATABASE_URL: postgresql://energyshark:${POSTGRES_PASSWORD}@database:5432/energyshark
    ports:
      - "8000:8000"
    depends_on:
      database:
        condition: service_healthy
    networks:
      - energyshark_net
    restart: unless-stopped

  connector:
    build:
      context: .
      dockerfile: connector/Dockerfile
    container_name: connector
    env_file:
      - .env
    environment:
      MASTER_URL: http://master:8000/events
    depends_on:
      master:
        condition: service_healthy
    networks:
      - energyshark_net
    restart: unless-stopped

volumes:
  postgres_data:

networks:
  energyshark_net:
    driver: bridge
```

### `services`

Dentro de esta sección se declaran los contenedores que componen la aplicación. En este caso son `database`, `master` y `connector`.

### `database`

```yaml
image: postgres:17-alpine
```

Utiliza una imagen oficial ya construida de PostgreSQL. No necesitas crear un Dockerfile propio para la base de datos.

```yaml
environment:
  POSTGRES_DB: energyshark
  POSTGRES_USER: energyshark
  POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
```

Configura el nombre de la base, el usuario y la contraseña. `${POSTGRES_PASSWORD}` se obtiene del archivo `.env`; no debes escribir la contraseña directamente en Compose ni subirla a Git.

```yaml
volumes:
  - postgres_data:/var/lib/postgresql/data
```

Conecta el volumen persistente `postgres_data` con la carpeta donde PostgreSQL almacena sus archivos. Así los datos sobreviven a la recreación del contenedor.

El `healthcheck` ejecuta `pg_isready` dentro del contenedor y permite saber cuándo PostgreSQL está realmente listo para recibir conexiones.

### `master`

```yaml
build:
  context: .
  dockerfile: master/Dockerfile
```

Indica que la imagen debe construirse desde tu código. El contexto es la raíz del proyecto, por lo que el Dockerfile puede copiar tanto `master` como `database`.

```yaml
DATABASE_URL: postgresql://energyshark:${POSTGRES_PASSWORD}@database:5432/energyshark
```

La palabra `database` después de `@` no es una dirección externa: es el nombre del servicio de PostgreSQL. Docker lo resuelve automáticamente a la IP interna de ese contenedor.

```yaml
ports:
  - "8000:8000"
```

El primer `8000` es el puerto de la EC2 y el segundo es el puerto dentro del contenedor. Esto permite que Nginx, instalado en la EC2, dirija las solicitudes hacia `localhost:8000`.

`depends_on` espera a que `database` esté saludable antes de iniciar `master`.

### `connector`

El `env_file` entrega al contenedor las variables de RabbitMQ guardadas localmente en `.env`.

```yaml
MASTER_URL: http://master:8000/events
```

Aquí `master` también es un nombre DNS interno creado por Docker. `connector` no necesita conocer la IP del otro contenedor ni publicar ningún puerto hacia Internet.

Su `depends_on` espera a que el `HEALTHCHECK` de `master` indique que la API está lista.

### Red interna

```yaml
networks:
  energyshark_net:
    driver: bridge
```

Cuando ejecutas `docker compose up`, Compose crea una red privada de tipo `bridge` y conecta a ella los tres contenedores porque cada servicio incluye:

```yaml
networks:
  - energyshark_net
```

Dentro de esa red, Docker proporciona resolución DNS usando los nombres de los servicios:

```text
connector -> http://master:8000/events
master    -> database:5432
```

Las IP internas pueden cambiar cuando se recrean los contenedores, pero los nombres `master` y `database` se mantienen. Por eso debes utilizar nombres de servicio y no direcciones IP fijas.

Compose también crea automáticamente una red predeterminada si no declaras `networks`. Declararla de forma explícita no es obligatoria para este caso, pero hace más clara la arquitectura y permite controlar qué servicios pueden comunicarse.

Finalmente, `restart: unless-stopped` hace que Docker intente reiniciar un contenedor si su proceso termina, excepto cuando tú lo detienes manualmente. Esto complementa, pero no reemplaza, la lógica de reconexión que debe existir dentro de `connector`.

Detiene y elimina los contenedores y la red creada por Compose. No elimina los volúmenes persistentes por defecto, por lo que los datos de PostgreSQL se conservan.

```bash
docker compose build
```

Construye las imágenes sin iniciar los contenedores.

```bash
docker compose exec master bash
```

Abre una terminal dentro de un contenedor que ya está ejecutándose. Las imágenes `slim` podrían no incluir Bash; en ese caso puedes usar:

```bash
docker compose exec master sh
```

```bash
docker compose config
```

Valida y muestra la configuración final de Compose, incluyendo las variables sustituidas. Debes tener cuidado al compartir su salida porque podría mostrar valores procedentes del `.env`.

Existe además este comando:

```bash
docker compose down -v
```

Este sí elimina también los volúmenes del proyecto. En tu caso borraría los datos persistidos por PostgreSQL, por lo que no deberías usarlo en EC2 salvo que realmente quieras reiniciar la base de datos desde cero.

Para el trabajo cotidiano, los cuatro más importantes serán:

```bash
docker compose up --build -d
docker compose ps
docker compose logs -f
docker compose down
```
