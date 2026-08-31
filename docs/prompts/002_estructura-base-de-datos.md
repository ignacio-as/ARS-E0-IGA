# Conversación 002 - Estructura de la base de datos

## Usuario

> Chat, sobre la creación de la base de datos para el proyecto de arquitectura, como corresponderia una estructura para la base de datos en la que quiero individualizar las demandas

## Asistente

Si quieres individualizar las demandas, te conviene separar el **evento recibido** de las **demandas que vienen dentro de su arreglo**. La relación sería de uno a muchos: un evento puede contener varias demandas, pero cada demanda pertenece a un solo evento.

Una estructura razonable en PostgreSQL sería:

```text
demand_events (1) ──────── (N) demands
```

La tabla `demand_events` conserva la información común del mensaje:

```sql
CREATE TABLE demand_events (
    id UUID PRIMARY KEY,
    idpk UUID NOT NULL UNIQUE,
    type VARCHAR(50) NOT NULL,
    valid_until TIMESTAMPTZ,
    meta_content JSONB,
    constraints_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_event JSONB NOT NULL
);
```

La tabla `demands` crea un registro independiente para cada ciudad:

```sql
CREATE TABLE demands (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL,
    city VARCHAR(255) NOT NULL,
    demand NUMERIC NOT NULL,
    unit VARCHAR(20) NOT NULL,
    CONSTRAINT fk_demands_event
        FOREIGN KEY (event_id)
        REFERENCES demand_events(id)
        ON DELETE CASCADE
);
```

Por ejemplo, si RabbitMQ entrega un evento con tres elementos dentro de `packageBody.demands`, guardarías:

- Un registro en `demand_events`.
- Tres registros en `demands`, todos asociados al mismo `event_id`.

El campo `idpk` evita almacenar dos veces el mismo evento. El campo `id` de `demands` funciona como identificador interno para consultar una demanda mediante `GET /history/{id}`. `received_at` debe ser generado por tu aplicación o por la base de datos al recibir el evento, no tomado desde RabbitMQ.

También conservaría el mensaje completo en `raw_event`. Aunque algunos datos estén separados en columnas, esto evita perder propiedades nuevas o información que después necesites recuperar.

Para facilitar las búsquedas y filtros, puedes agregar índices:

```sql
CREATE INDEX idx_demands_city ON demands(city);
CREATE INDEX idx_demands_unit ON demands(unit);
CREATE INDEX idx_events_received_at ON demand_events(received_at);
CREATE INDEX idx_events_valid_until ON demand_events(valid_until);
```

Al consultar `/history`, harías un `JOIN` entre ambas tablas para devolver cada demanda junto con los datos de su evento. Además, aplicarías la paginación directamente en SQL con `LIMIT` y `OFFSET`, evitando cargar todo el historial en memoria.

## Usuario

> Puedo "comprimir info" como demand JSONB ya que ya tiene esos atributos?

## Asistente

Sí, puedes guardar cada demanda como `JSONB`, aunque sería más preciso llamarlo **agrupar o encapsular sus atributos**, porque `JSONB` no implica necesariamente que ocupe menos espacio.

Por ejemplo, podrías tener:

```sql
CREATE TABLE demands (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL,
    demand JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Y el campo `demand` contendría:

```json
{
  "city": "New New york",
  "demand": 1013.123,
  "unit": "GW"
}
```

Seguirías teniendo una fila por cada demanda, por lo que cada una conservaría un `id` interno propio. Sus propiedades se pueden filtrar con operadores de PostgreSQL:

```sql
SELECT *
FROM demands
WHERE demand->>'city' = 'New New york';
```

Para valores numéricos debes convertir el texto al tipo correspondiente:

```sql
SELECT *
FROM demands
WHERE (demand->>'demand')::numeric > 1000;
```

También puedes crear índices para los filtros más usados:

```sql
CREATE INDEX idx_demands_city
ON demands ((demand->>'city'));

CREATE INDEX idx_demands_value
ON demands (((demand->>'demand')::numeric));

CREATE INDEX idx_demands_jsonb
ON demands USING GIN (demand);
```

Es una alternativa válida y flexible, especialmente si los atributos de una demanda podrían cambiar. Su desventaja es que la base de datos no valida con tanta facilidad que `city`, `demand` y `unit` existan y tengan siempre el tipo correcto; esa validación tendría que realizarla principalmente tu aplicación.

No guardaría dentro de cada fila una copia completa del evento con todo el arreglo de demandas, porque repetirías mucha información. Mantendría el evento original una sola vez en una tabla `demand_events` y asociaría cada fila mediante `event_id`. De esa forma obtienes simultáneamente flexibilidad con `JSONB`, demandas individualizadas y conservación íntegra del evento recibido.
