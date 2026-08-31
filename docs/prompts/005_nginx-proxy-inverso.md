# Conversación 005 - Función de Nginx

## Usuario

> puedes expliacarme para que srve nginx

## Asistente

Nginx sirve como **puerta de entrada** entre Internet y tu aplicación `master`. En este proyecto cumple principalmente la función de **proxy inverso**.

El recorrido de una solicitud sería:

```text
Usuario
  │
  │ https://tu-dominio.cl/history
  ▼
Nginx en la EC2
  │
  │ http://localhost:8000/history
  ▼
Contenedor master
```

Cuando alguien visita tu dominio, la solicitud llega primero a Nginx mediante el puerto 80 para HTTP o el 443 para HTTPS. Nginx recibe esa solicitud y la reenvía internamente a FastAPI, que está expuesto en el puerto `8000` de la EC2.

Esto entrega varias ventajas:

- Permite usar el dominio sin escribir `:8000` en la dirección.
- Puede manejar el certificado HTTPS de Let's Encrypt.
- Puede redirigir automáticamente las solicitudes HTTP hacia HTTPS.
- Oculta la conexión directa con el servidor Uvicorn.
- Centraliza configuraciones como límites de tamaño, encabezados y tiempos de espera.
- En proyectos mayores puede repartir solicitudes entre varias instancias de `master`.

Una configuración inicial podría ser:

```nginx
server {
    listen 80;
    server_name api.ejemplo.cl;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

La línea más importante es:

```nginx
proxy_pass http://127.0.0.1:8000;
```

Esta le indica a Nginx que reenvíe las solicitudes al puerto que Docker publica para `master`:

```yaml
master:
  ports:
    - "8000:8000"
```

Nginx no necesita comunicarse con `connector` ni con PostgreSQL. Solamente dirige las solicitudes públicas hacia `master`. `connector` y la base de datos permanecen como componentes internos.

En esta entrega, Nginx debe instalarse directamente en la instancia EC2, fuera de Docker. Los contenedores siguen siendo administrados por Docker Compose, mientras Nginx funciona como un servicio del sistema operativo de la EC2.

## Usuario

> y como funciona la certificacion de https, cual es su utilidad me refiero y porque idealmente necesita ser periodica

## Asistente

Un certificado HTTPS permite que el navegador compruebe que está comunicándose con el dominio correcto y que la información viaja cifrada. HTTPS es HTTP protegido mediante TLS.

Cuando una persona entra a:

```text
https://api.ejemplo.cl
```

ocurre, de forma simplificada, lo siguiente:

1. El cliente se conecta a Nginx mediante el puerto 443.
2. Nginx presenta el certificado asociado a `api.ejemplo.cl`.
3. El cliente verifica que el certificado corresponde al dominio, que no está vencido y que fue emitido por una autoridad confiable.
4. El cliente y Nginx acuerdan claves temporales para cifrar la comunicación.
5. A partir de ese momento, las solicitudes y respuestas viajan cifradas.

El certificado aporta tres propiedades principales:

- **Autenticidad:** ayuda a comprobar que el servidor pertenece realmente al dominio visitado.
- **Confidencialidad:** evita que alguien que intercepte el tráfico pueda leer fácilmente su contenido.
- **Integridad:** permite detectar si los datos fueron alterados durante el trayecto.

Let's Encrypt actúa como autoridad certificadora y entrega certificados sin costo. Una herramienta como Certbot demuestra que controlas el dominio, solicita el certificado y configura Nginx para utilizarlo.

Los certificados no son permanentes: tienen una fecha de expiración. Esto limita el tiempo durante el cual un certificado o una clave comprometida podrían seguir siendo aceptados y obliga a renovar periódicamente la validación del dominio.

Por esa razón se ejecuta regularmente una comprobación de renovación. No significa que Certbot genere un certificado nuevo en cada revisión. Normalmente comprueba cuánto tiempo de vigencia queda y solamente lo renueva cuando se aproxima su vencimiento.

El flujo sería:

```text
Temporizador periódico
        │
        ▼
certbot renew
        │
        ├── Certificado aún vigente -> no hace cambios
        │
        └── Próximo a expirar -> solicita uno nuevo
                                  y recarga Nginx
```

Si no se automatiza este proceso y el certificado vence, los navegadores mostrarán una advertencia de seguridad y los clientes podrían rechazar la conexión. La API seguiría ejecutándose internamente, pero su acceso HTTPS dejaría de ser confiable.

En tu entrega se solicita comprobar la expiración automáticamente dos veces al día. En una instancia Ubuntu esto suele quedar administrado por un temporizador de `systemd` instalado junto con Certbot. Puedes revisar su estado con:

```bash
systemctl status certbot.timer
systemctl list-timers | grep certbot
```

Y puedes probar el proceso sin consumir una renovación real mediante:

```bash
sudo certbot renew --dry-run
```

La renovación periódica, por tanto, no cambia continuamente el cifrado de tu aplicación: garantiza que Nginx siempre disponga de un certificado válido antes de que el anterior expire.
