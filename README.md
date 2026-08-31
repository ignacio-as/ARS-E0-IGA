# EnergyShark - E0

API desarrollada en Python con FastAPI que recibe eventos y los almacena en PostgreSQL, recibiendo información a través de un connector, de igual forma desarrollado en Python.

## Dominio:
**www.ars-iga-e0.lat**
**ars-iga-e0.lat**


## Método de acceso al servidor
- **Dominio:** [https://www.ars-iga-e0.lat/](https://www.ars-iga-e0.lat/)
- **Acceso SSH:**
```bash
chmod 400 "key-e0.pem"
ssh -i "key-e0.pem" ubuntu@ec2-100-50-204-88.compute-1.amazonaws.com
```
Key-e0.pem en Canvas


## Ejecución
1. `env_empty_example.txt` es la base del `.env` (Rellenar con las credenciales correctas).
2. Levantar los servicios:
```bash
docker compose up --build -d
```
La API queda disponible internamente en `http://localhost:8000` en el ec2.

Endpoints principales:

- `GET /history`
- `GET /history?page=1&limit=25`
- `GET /history/{id}`
- `POST /events`
- `GET /health`



## Requisitos
### Funcionales

- **Logrado:** RF1: Para visualizar el historial debe estar en https://www.ars-iga-e0.lat/history
- **Logrado:** RF2
- **Logrado:** RF3
- **Logrado:** RF4

### No Funcionales
- **Logrado:** RNF1
- **Logrado:** RNF2
- **Logrado:** RNF3
- **Logrado:** RNF4 
- **Logrado:** RNF5
- **Logrado:** RNF6
- **Logrado:** RNF7

### No Funcionales Compose
- **Logrado:** RNF1
- **Logrado:** RNF2
- **Logrado:** RNF3

### Parte variable (HTTPs)
- **Logrado:** RNF1
- **Logrado:** RNF22
- **Logrado:** RNF3

### Parte variable (HTTPs)
- **No Trabajado:**

## Tecnologías
- Python y FastAPI
- PostgreSQL
