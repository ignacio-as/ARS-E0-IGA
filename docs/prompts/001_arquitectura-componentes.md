# Conversación 001 - Separación de componentes

## Usuario

> Chat esta mi primera entrega de mi ramo de Aquitectura de sistemas de software, tengo una idea de la separacion de los componentes connectos, master y la BDD separados en tres entornos de docker distintos en una ec2. Pero aclarame a grandes rasgos si me equivoco?

## Asistente

Tu idea general es correcta, con una precisión: no serían necesariamente tres “entornos Docker”, sino tres **servicios o contenedores separados**, ejecutándose dentro de la misma instancia EC2 y administrados mediante Docker Compose.

La separación esperada sería:

- `connector`: mantiene la conexión con RabbitMQ, consume los eventos y los envía a `master` mediante HTTP POST. Debe funcionar permanentemente y reconectarse si pierde la conexión con el broker.
- `master`: contiene la API web. Recibe los eventos del `connector`, los guarda en la base de datos y expone endpoints como `GET /history` y `GET /history/{id}`.
- Base de datos: PostgreSQL o MongoDB en un contenedor independiente. Solamente `master` debería acceder directamente a ella.

Los tres pueden estar en una sola EC2. `connector` y `master` deben compartir una red interna de Docker; normalmente la base de datos también se conecta a esa red para que `master` pueda encontrarla por su nombre de servicio. No necesitas una EC2 distinta para cada componente.

El flujo principal quedaría así:

```text
RabbitMQ externo -> connector -> HTTP POST -> master -> base de datos
                                         ^
Internet -> dominio -> Nginx en la EC2 --|
```

Un detalle importante es que Nginx debe instalarse directamente en la EC2, fuera de Docker, y actuar como proxy inverso hacia `master`. Además, cada contenedor debe tener su propio `HEALTHCHECK`.

Por lo tanto, tu planteamiento va bien encaminado: una EC2, tres contenedores separados y una red Docker compartida. El principal ajuste conceptual es llamarlos servicios o contenedores, no tres entornos Docker independientes.

## Usuario

> y sobre connector, podrias darme una carcasa vacia con la estructura principal que deberia tener

## Asistente

Sí. Asumiendo que usarás Python, una carcasa clara para `connector` podría separar la conexión con RabbitMQ, el envío HTTP y la configuración:

```text
connector/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── rabbitmq.py
│   ├── master_client.py
│   └── healthcheck.py
├── Dockerfile
└── requirements.txt
```

`app/config.py` centraliza la configuración obtenida desde variables de entorno:

```python
import os


class Settings:
    rabbitmq_host = os.getenv("RABBITMQ_HOST", "")
    rabbitmq_port = int(os.getenv("RABBITMQ_PORT", "5671"))
    rabbitmq_user = os.getenv("RABBITMQ_USER", "")
    rabbitmq_password = os.getenv("RABBITMQ_PASSWORD", "")
    rabbitmq_queue = os.getenv("RABBITMQ_QUEUE", "")
    master_url = os.getenv("MASTER_URL", "http://master:8000/events")


settings = Settings()
```

`app/master_client.py` se responsabiliza únicamente de comunicarse con `master`:

```python
import requests

from app.config import settings


def send_event(event: dict) -> bool:
    """Envía un evento a master y retorna True solamente si fue aceptado."""
    response = requests.post(settings.master_url, json=event, timeout=10)
    return 200 <= response.status_code < 300
```

`app/rabbitmq.py` contiene la conexión, el consumo y la decisión de confirmar o rechazar mensajes:

```python
import json

from app.master_client import send_event


def create_connection():
    """Crea y retorna una conexión configurada con RabbitMQ."""
    # TODO: construir credenciales y parámetros SSL con pika
    raise NotImplementedError


def process_message(channel, method, properties, body):
    """Procesa un mensaje recibido desde RabbitMQ."""
    try:
        event = json.loads(body)

        if send_event(event):
            channel.basic_ack(delivery_tag=method.delivery_tag)
        else:
            channel.basic_nack(
                delivery_tag=method.delivery_tag,
                requeue=True,
            )
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Un mensaje inválido no debería bloquear infinitamente la cola.
        channel.basic_nack(
            delivery_tag=method.delivery_tag,
            requeue=False,
        )


def consume_forever():
    """Se conecta a la cola y comienza el consumo permanente."""
    connection = create_connection()
    channel = connection.channel()

    # TODO: configurar basic_qos y basic_consume
    # TODO: iniciar channel.start_consuming()
```

`app/main.py` mantiene vivo el proceso e implementa la reconexión:

```python
import logging
import time

from app.rabbitmq import consume_forever


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    retry_seconds = 5

    while True:
        try:
            consume_forever()
        except KeyboardInterrupt:
            logger.info("Connector detenido")
            break
        except Exception:
            logger.exception(
                "Conexión interrumpida; reintentando en %s segundos",
                retry_seconds,
            )
            time.sleep(retry_seconds)


if __name__ == "__main__":
    main()
```

`app/healthcheck.py` puede comprobar que el proceso principal continúe operativo mediante un archivo actualizado periódicamente o mediante una comprobación del proceso. Por ahora puedes dejar su contrato preparado:

```python
def is_healthy() -> bool:
    """Retorna si el ciclo principal del connector sigue operativo."""
    # TODO: comprobar un heartbeat escrito por el proceso principal
    return False


if __name__ == "__main__":
    raise SystemExit(0 if is_healthy() else 1)
```

Las dependencias mínimas en `requirements.txt` serían:

```text
pika
requests
```

Esta carcasa deja pendientes deliberadamente la configuración TLS de RabbitMQ, la validación del evento, el `HEALTHCHECK` real y la política detallada de reintentos. La regla más importante es confirmar el mensaje con `basic_ack` únicamente después de que `master` responda exitosamente; así evitas perder eventos si la API o la base de datos están temporalmente caídas.
