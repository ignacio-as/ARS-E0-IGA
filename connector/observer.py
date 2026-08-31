import os
from dotenv import load_dotenv
import json
import requests
from pathlib import Path
import pika
import ssl
import time


load_dotenv()
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "broker.iic2173.org")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT"))
RABBITMQ_VIRTUAL_HOST = os.getenv("RABBITMQ_VIRTUAL_HOST", "energy")
RABBITMQ_USER = os.getenv("RABBITMQ_USER")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE")
MASTER_URL = os.getenv("MASTER_URL")
HEALTH_FILE = Path("/tmp/connector-ready")


def send_to_master(body):
    event = json.loads(body.decode("utf-8"))
    return requests.post(MASTER_URL, json=event, timeout=10)


def on_message(channel, method, properties, body):
    try:
        print(body.decode("utf-8"), flush=True)
        response = send_to_master(body)

        #Todo en orden
        if response.status_code in [200, 201, 409]:
            #Aviso a Rabbit que todo esta en orden
            channel.basic_ack(delivery_tag=method.delivery_tag)
            print("Evento recibido correctamente por master.")

        elif response.status_code >= 500:
            print("Error en el Master", response.status_code)
            time.sleep(5)
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

        else:
            print("Master rechazo el evento:", response.status_code)
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    except (json.JSONDecodeError, UnicodeDecodeError):
        print("El mensaje recibido no es un JSON valido.")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    except requests.RequestException as error:
        print("No fue posible enviar el evento a master:", error)
        time.sleep(5)
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def connect_to_rabbitmq():
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
    ssl_context = ssl.create_default_context() #NA como se crea?

    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        virtual_host=RABBITMQ_VIRTUAL_HOST,
        credentials=credentials,
        ssl_options=pika.SSLOptions(ssl_context, RABBITMQ_HOST),
    )
    return pika.BlockingConnection(parameters)


def start_observer():
    HEALTH_FILE.unlink(missing_ok=True)

    while True:
        try:
            print("Conectando con RabbitMQ")
            connection = connect_to_rabbitmq()
            channel = connection.channel()
            #Un mensajito a la vez:
            channel.basic_qos(prefetch_count=1)

            channel.basic_consume(
                queue=RABBITMQ_QUEUE,
                on_message_callback=on_message,
                auto_ack=False, #Aun no todo en orden
                )
            HEALTH_FILE.touch()
            print("Esperando mensajes..")
            channel.start_consuming()


        except pika.exceptions.AMQPError as error:
            HEALTH_FILE.unlink(missing_ok=True) #Ya no estoy sano
            print("--Problema al establecer conexion--", error)
            print("Nuevo intento en 5 segundos...")
            time.sleep(5)

        #mejor para interrunpcion
        except KeyboardInterrupt:
            HEALTH_FILE.unlink(missing_ok=True)
            print("Observer detenido.")
            break



if __name__ == "__main__":
    start_observer()
