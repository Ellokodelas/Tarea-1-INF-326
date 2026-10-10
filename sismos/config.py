import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class City:
    name: str
    latitude: float
    longitude: float


CITIES = {
    "arica": City("Arica", -18.4746, -70.29792),
    "coquimbo": City("Coquimbo", -29.95332, -71.33947),
    "valparaiso": City("Valparaíso", -33.036, -71.62963),
    "concepcion": City("Concepción", -36.82699, -73.04977),
    "punta_arenas": City("Punta Arenas", -53.16282, -70.90922),
}
RADIUS_KM = 500.0
EXCHANGE = "sismos.eventos.v1"
DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "sismos.json"


def amqp_url() -> str:
    return os.getenv("AMQP_URL", "amqp://sismos:sismos_demo@localhost:5672/%2F")


def api_url() -> str:
    return os.getenv("API_URL", "http://localhost:8000").rstrip("/")


def queue_name(city: str) -> str:
    return f"sismos.{city}"
