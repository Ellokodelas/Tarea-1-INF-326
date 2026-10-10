from fastapi import FastAPI, HTTPException

from sismos.catalog import load_catalog
from sismos.models import Earthquake

app = FastAPI(title="Datos de sismos - INF326", version="1.0.0")
CATALOG = load_catalog()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/sismos/{event_id}", response_model=Earthquake)
def get_earthquake(event_id: str) -> Earthquake:
    event = CATALOG.get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Sismo no encontrado")
    return event
