"""Recibe todos los eventos, filtra localmente y hace pull HTTP sólo si corresponde."""

import argparse
import json

import httpx

from sismos.broker import connect, declare_city
from sismos.config import CITIES, City, api_url
from sismos.geo import distance_km, is_interested
from sismos.models import Earthquake, Notification


def emit(record: dict) -> None:
    print(json.dumps(record, ensure_ascii=False), flush=True)


def fetch_detail(client: httpx.Client, event: Notification) -> Earthquake:
    response = client.get(f"/sismos/{event.id}")
    response.raise_for_status()
    detail = Earthquake.model_validate_json(response.content)
    if detail.notification() != event:
        raise ValueError("El detalle no coincide con el ID y coordenadas del aviso")
    return detail


class Processor:
    def __init__(self, city: City, client: httpx.Client):
        self.city = city
        self.client = client

    def process(self, body: bytes) -> dict:
        event = Notification.model_validate_json(body)
        result = {"city": self.city.name, "event_id": event.id}
        distance = distance_km(self.city, event)
        result["distance_km"] = round(distance, 3)  # Sólo la salida se redondea.
        if is_interested(distance):
            detail = fetch_detail(self.client, event)
            result.update(action="detail", http_requested=True, detail=detail.model_dump(mode="json"))
        else:
            result.update(action="ignored", http_requested=False)
        return result


def make_callback(processor: Processor, output=emit):
    def callback(channel, method, properties, body):
        try:
            result = processor.process(body)
        except (ValueError, httpx.HTTPError) as exc:
            output({"city": processor.city.name, "action": "failed", "reason": str(exc)})
            # Se registra el error y se descarta esta copia para continuar con los demás avisos.
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return
        output(result)
        channel.basic_ack(delivery_tag=method.delivery_tag)

    return callback


def run(city_key: str) -> None:
    city = CITIES[city_key]
    connection = connect()
    try:
        channel = connection.channel()
        queue = declare_city(channel, city_key)
        channel.basic_qos(prefetch_count=1)
        with httpx.Client(base_url=api_url(), timeout=2.0, trust_env=False) as client:
            processor = Processor(city, client)
            channel.basic_consume(
                queue=queue,
                on_message_callback=make_callback(processor),
                auto_ack=False,
                exclusive=True,
            )
            emit({"city": city.name, "action": "ready", "queue": queue})
            channel.start_consuming()
    finally:
        if connection.is_open:
            connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Suscriptor de una ciudad")
    parser.add_argument("--city", choices=CITIES, required=True)
    args = parser.parse_args()
    try:
        run(args.city)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
