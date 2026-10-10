from pathlib import Path

from pydantic import TypeAdapter

from sismos.config import DATA_FILE
from sismos.models import Earthquake


def load_catalog(path: Path = DATA_FILE) -> dict[str, Earthquake]:
    records = TypeAdapter(list[Earthquake]).validate_json(path.read_bytes())
    catalog = {event.id: event for event in records}
    if len(catalog) != len(records):
        raise ValueError("El catálogo contiene identificadores repetidos")
    return catalog
