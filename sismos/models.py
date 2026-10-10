"""Contratos compartidos; el evento AMQP contiene sólo lo necesario para filtrar."""

from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]
EventId = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Notification(Contract):
    id: EventId
    latitude: Latitude
    longitude: Longitude


class Magnitude(Contract):
    value: Annotated[float, Field(ge=-5, le=12)]
    type: Annotated[str, Field(min_length=1, max_length=20)]


class Earthquake(Contract):
    id: EventId
    occurred_at: AwareDatetime
    latitude: Latitude
    longitude: Longitude
    depth_km: Annotated[float, Field(ge=0, le=1000)]
    magnitude: Magnitude
    reference: str
    source: str
    source_url: str | None = None
    simulated: bool

    def notification(self) -> Notification:
        return Notification(id=self.id, latitude=self.latitude, longitude=self.longitude)
