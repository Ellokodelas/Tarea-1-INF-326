"""Reproduce hechos del catálogo precargado; nunca registra sismos por HTTP."""

import argparse
import json
import math

import pika

from sismos.broker import connect, declare_exchange
from sismos.catalog import load_catalog
from sismos.config import EXCHANGE
from sismos.models import Notification


def publish(channel, event: Notification) -> None:
    channel.basic_publish(
        exchange=EXCHANGE,
        routing_key="",
        body=event.model_dump_json().encode("utf-8"),
        properties=pika.BasicProperties(
            content_type="application/json",
            content_encoding="utf-8",
            delivery_mode=2,
        ),
        mandatory=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Publicar notificaciones mínimas de sismos")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--id", help="Identificador del catálogo")
    selection.add_argument("--all", action="store_true", help="Publicar todo el catálogo")
    parser.add_argument("--interval", type=float, default=0.3, help="Segundos entre eventos")
    args = parser.parse_args()
    if not math.isfinite(args.interval) or args.interval < 0:
        parser.error("--interval debe ser finito y mayor o igual a cero")
    catalog = load_catalog()
    if args.id is not None and args.id not in catalog:
        parser.error(f"ID desconocido. Disponibles: {', '.join(catalog)}")
    events = list(catalog.values()) if args.all else [catalog[args.id]]
    connection = connect()
    try:
        channel = connection.channel()
        declare_exchange(channel)
        channel.confirm_delivery()
        for index, event in enumerate(events):
            notification = event.notification()
            publish(channel, notification)
            print(json.dumps({"action": "published", **notification.model_dump()}), flush=True)
            if index + 1 < len(events):
                connection.sleep(args.interval)
    finally:
        if connection.is_open:
            connection.close()


if __name__ == "__main__":
    main()
