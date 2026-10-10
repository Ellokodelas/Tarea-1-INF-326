from geographiclib.geodesic import Geodesic

from sismos.config import City, RADIUS_KM
from sismos.models import Notification


def distance_km(city: City, event: Notification) -> float:
    """Distancia superficial entre ciudad y epicentro sobre el elipsoide WGS84."""
    result = Geodesic.WGS84.Inverse(
        city.latitude, city.longitude, event.latitude, event.longitude
    )
    return result["s12"] / 1000.0


def is_interested(distance: float) -> bool:
    # No redondear antes de comparar: exactamente 500 km queda fuera.
    return distance < RADIUS_KM
