# Conversación 003 - Validación de la tabla demands

## Usuario

> Estructurado de esta forma estaria correcto? "CREATE TABLE IF NOT EXISTS demands (
> &nbsp;&nbsp;&nbsp;&nbsp;id *BIGSERIAL* PRIMARY KEY,
> &nbsp;&nbsp;&nbsp;&nbsp;demand JSONB NOT NULL,
> &nbsp;&nbsp;&nbsp;&nbsp;demand_set JSONB NOT NULL,
> &nbsp;&nbsp;&nbsp;&nbsp;received_at *TIMESTAMPTZ* NOT NULL DEFAULT CURRENT_TIMESTAMP
> );"

## Asistente

Sí, la estructura es válida para PostgreSQL y permite guardar una demanda individual por fila. Solamente debes eliminar los asteriscos y las barras invertidas que provienen del formato Markdown. El SQL ejecutable sería:

```sql
CREATE TABLE IF NOT EXISTS demands (
    id BIGSERIAL PRIMARY KEY,
    demand JSONB NOT NULL,
    demand_set JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Cada columna tendría esta responsabilidad:

- `id`: identificador interno de la demanda, útil para `GET /history/{id}`.
- `demand`: objeto individual con `city`, `demand` y `unit`.
- `demand_set`: información del evento de origen, como `idpk`, `type`, `validUntil`, `metaContent` y `constraints`.
- `received_at`: instante en que tu sistema recibió el evento.

Por ejemplo, una fila podría guardar:

```json
// demand
{
  "city": "Los Santos",
  "demand": 10223,
  "unit": "GW"
}
```

```json
// demand_set
{
  "idpk": "550e8400-e29b-41d4-a716-446655440000",
  "type": "demand-set",
  "validUntil": "2026-12-12T00:00:00Z",
  "metaContent": "...",
  "constraints": {}
}
```

Evitaría repetir dentro de `demand_set` el arreglo completo `packageBody.demands`, porque cada fila ya representa una demanda individual y esa repetición aumentaría innecesariamente el tamaño de la tabla.

Hay dos detalles que debes considerar:

1. Si un evento contiene varias demandas, todas deberían recibir exactamente el mismo `received_at`. Lo más seguro es generar ese timestamp una vez en `master` y enviarlo explícitamente en todos los `INSERT`, en vez de depender del valor por defecto para cada fila.
2. Como `idpk` queda dentro de `demand_set`, la base de datos no impide fácilmente procesar dos veces el mismo evento. Puedes controlar la duplicación desde la aplicación o agregar una columna separada para el identificador del evento.

Si quieres mantener esta solución sencilla, agregaría al menos índices para los filtros principales:

```sql
CREATE INDEX IF NOT EXISTS idx_demands_city
ON demands ((demand->>'city'));

CREATE INDEX IF NOT EXISTS idx_demands_received_at
ON demands (received_at);

CREATE INDEX IF NOT EXISTS idx_demands_valid_until
ON demands ((demand_set->>'validUntil'));
```

Así como está, el modelo es correcto para una implementación pequeña: individualiza las demandas, conserva la información del evento y entrega un ID interno para cada registro. La principal concesión es que repite `demand_set` cuando un evento contiene varias ciudades.
