import json
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import UUID

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from psycopg.rows import dict_row


load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://energyshark:energyshark@localhost:5432/energyshark",
)


def connect_to_database():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def create_table():
    schema_path = Path(__file__).parent.parent / "database" / "schema.sql"

    with connect_to_database() as connection:
        connection.execute(schema_path.read_text(encoding="utf-8"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    create_table()
    yield

app = FastAPI(lifespan=lifespan)


def valid_utc_date(value):
    if not isinstance(value, str):
        return False

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0
    except ValueError:
        return False


def valid_demand(demand):
    if not isinstance(demand, dict):
        return False

    value = demand.get("demand")
    return (
        isinstance(demand.get("city"), str)
        and bool(demand["city"])
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isinstance(demand.get("unit"), str)
        and bool(demand["unit"])
    )


def valid_event(event):
    try:
        UUID(event["idpk"])
        body = event["packageBody"]
        demands = body["demands"]
        cities = [demand["city"] for demand in demands]

        return (
            event["type"] == "demand-set"
            and isinstance(demands, list)
            and bool(demands)
            and all(valid_demand(demand) for demand in demands)
            and len(cities) == len(set(cities))
            and valid_utc_date(body["validUntil"])
            and isinstance(body["metaContent"], str)
            and isinstance(body["constraints"], dict)
            and ("timestamp" not in event or valid_utc_date(event["timestamp"]))
        )
    except (KeyError, TypeError, ValueError):
        return False


def split_event(event):
    body = event["packageBody"]
    demand_set = {
        **event,
        "packageBody": {
            key: value for key, value in body.items() if key != "demands"
        },
    }
    return body["demands"], demand_set


def format_demand(row):
    return {
        "id": row["id"],
        **row["demand"],
        "demandSet": row["demand_set"],
        "receivedAt": row["received_at"],
    }


def save_event(event):
    query = """
        INSERT INTO demands (demand, demand_set, received_at)
        VALUES (%s::jsonb, %s::jsonb, %s)
        RETURNING id
    """
    demands, demand_set = split_event(event)
    received_at = datetime.now(timezone.utc)
    demand_ids = []

    with connect_to_database() as connection:
        for demand in demands:
            row = connection.execute(
                query,
                (json.dumps(demand), json.dumps(demand_set), received_at),
            ).fetchone()
            demand_ids.append(row["id"])

    return {"demandIds": demand_ids, "receivedAt": received_at}


def find_demand(demand_id):
    with connect_to_database() as connection:
        row = connection.execute(
            "SELECT * FROM demands WHERE id = %s", (demand_id,)
        ).fetchone()

    return None if row is None else format_demand(row)


def is_date(value):
    try:
        date.fromisoformat(value)
        return len(value) == 10
    except (TypeError, ValueError):
        return False


def add_time_filter(conditions, values, expression, value):
    if is_date(value):
        conditions.append(
            f"(({expression})::timestamptz AT TIME ZONE 'UTC')::date = %s::date"
        )
    else:
        conditions.append(f"({expression})::timestamptz = %s::timestamptz")
    values.append(value)


#Filtros a condiciones para la EDD
def add_filters(query_parameters):
    conditions = []
    values = []
    text_fields = {
        "code": "demand ->> 'code'",
        "city": "demand ->> 'city'",
        "demand": "demand ->> 'demand'",
        "unit": "demand ->> 'unit'",
        "idpk": "demand_set ->> 'idpk'",
        "msgId": "demand_set ->> 'msgId'",
        "type": "demand_set ->> 'type'",
        "metaContent": "demand_set -> 'packageBody' ->> 'metaContent'",
    }

    for field, value in query_parameters.items():
        if field in ("page", "limit"):
            continue
        if field == "id":
            conditions.append("id::text = %s")
            values.append(value)
        elif field in text_fields:
            conditions.append(text_fields[field] + " = %s")
            values.append(value)
        elif field == "timestamp":
            add_time_filter(conditions, values, "demand_set ->> 'timestamp'", value)
        elif field == "validUntil":
            add_time_filter(
                conditions,
                values,
                "demand_set -> 'packageBody' ->> 'validUntil'",
                value,
            )
        elif field == "receivedAt":
            add_time_filter(conditions, values, "received_at", value)
        elif field == "constraints":
            conditions.append(
                "demand_set -> 'packageBody' -> 'constraints' = %s::jsonb"
            )
            values.append(value)

    return conditions, values


#Lista de demandas individuales
def list_demands(page, limit, query_parameters):
    conditions, values = add_filters(query_parameters)
    query = "SELECT * FROM demands"

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY received_at DESC, id DESC LIMIT %s OFFSET %s"
    values.extend([limit, (page - 1) * limit])

    with connect_to_database() as connection:
        rows = connection.execute(query, values).fetchall()

    return [format_demand(row) for row in rows]


#Check de salud
@app.get("/health")
def health():
    try:
        with connect_to_database() as connection:
            connection.execute("SELECT 1")
        return {"status": "ok"}
    except psycopg.Error as error:
        raise HTTPException(status_code=503, detail="Database unavailable") from error



@app.get("/history")
def history(
    request: Request,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
):
    return {
        "page": page,
        "limit": limit,
        "results": list_demands(page, limit, request.query_params),
    }


@app.get("/history/{demand_id}")
def history_detail(demand_id: int):
    demand = find_demand(demand_id)

    if demand is None:
        raise HTTPException(status_code=404, detail="Demand not found")

    return demand

#Post para nuevos registros
@app.post("/events", status_code=201)
def create_event(event: dict):
    if not valid_event(event):
        raise HTTPException(status_code=400, detail="Invalid demand-set")

    try:
        return save_event(event)
    except psycopg.errors.UniqueViolation as error:
        raise HTTPException(status_code=409, detail="demand-set already exists") from error
