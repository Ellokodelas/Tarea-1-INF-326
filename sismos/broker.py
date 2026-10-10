"""Conexión y topología RabbitMQ; una cola independiente por ciudad."""

import time

import pika

from sismos.config import CITIES, EXCHANGE, amqp_url, queue_name


def connect(attempts: int = 15) -> pika.BlockingConnection:
    parameters = pika.URLParameters(amqp_url())
    parameters.heartbeat = 120
    parameters.socket_timeout = 5
    parameters.blocked_connection_timeout = 30
    for attempt in range(attempts):
        try:
            return pika.BlockingConnection(parameters)
        except pika.exceptions.AMQPConnectionError:
            if attempt + 1 == attempts:
                raise
            time.sleep(2)
    raise RuntimeError("No se pudo conectar al broker")


def declare_exchange(channel) -> None:
    channel.exchange_declare(exchange=EXCHANGE, exchange_type="fanout", durable=True)


def declare_city(channel, city: str) -> str:
    if city not in CITIES:
        raise ValueError(f"Ciudad desconocida: {city}")
    queue = queue_name(city)
    declare_exchange(channel)
    channel.queue_declare(queue=queue, durable=True)
    channel.queue_bind(exchange=EXCHANGE, queue=queue)
    return queue


def main() -> None:
    connection = connect()
    try:
        channel = connection.channel()
        for city in CITIES:
            declare_city(channel, city)
        print("Topología lista: fanout y una cola para cada una de las cinco ciudades.", flush=True)
    finally:
        if connection.is_open:
            connection.close()


if __name__ == "__main__":
    main()
