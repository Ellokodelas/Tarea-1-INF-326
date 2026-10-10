"""Pruebas de contratos, API, selección geográfica y tratamiento de entregas."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from geographiclib.geodesic import Geodesic
from pydantic import ValidationError

from sismos.api import app
from sismos.broker import declare_city
from sismos.catalog import load_catalog
from sismos.config import CITIES, EXCHANGE
from sismos.geo import distance_km, is_interested
from sismos.models import Notification
from sismos.publisher import publish
from sismos.subscriber import Processor, fetch_detail, make_callback

CATALOG = load_catalog()
EXPECTED = {
    "csn-385245": {"coquimbo", "valparaiso", "concepcion"},
    "demo-arica": {"arica"},
    "demo-coquimbo": {"coquimbo", "valparaiso"},
    "demo-valparaiso": {"coquimbo", "valparaiso", "concepcion"},
    "demo-concepcion": {"valparaiso", "concepcion"},
    "demo-punta-arenas": {"punta_arenas"},
    "demo-lejano": set(),
}


def notification(event_id="demo-valparaiso"):
    return CATALOG[event_id].notification()


def detail_response(event_id="demo-valparaiso"):
    return httpx.Response(200, json=CATALOG[event_id].model_dump(mode="json"))


def client_for(handler):
    return httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler))


def test_api_returns_full_detail_and_no_post():
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/sismos/csn-385245")
            assert response.status_code == 200
            assert response.json() == CATALOG["csn-385245"].model_dump(mode="json")
            assert (await client.get("/health")).json() == {"status": "ok"}
            assert (await client.get("/sismos/no-existe")).status_code == 404
            assert (await client.post("/sismos/csn-385245", json={})).status_code == 405

    asyncio.run(scenario())


def test_minimal_notification_and_amqp_publication():
    event = notification()
    assert set(event.model_dump()) == {"id", "latitude", "longitude"}
    channel = Mock()
    publish(channel, event)
    kwargs = channel.basic_publish.call_args.kwargs
    assert json.loads(kwargs["body"]) == event.model_dump()
    assert kwargs["exchange"] == EXCHANGE
    assert kwargs["mandatory"] is True
    assert kwargs["properties"].delivery_mode == 2


@pytest.mark.parametrize("patch", [
    {"latitude": 91.0}, {"longitude": -181.0}, {"latitude": float("nan")},
    {"longitude": float("inf")}, {"latitude": "-33.0"}, {"latitude": True},
    {"id": "../bad"}, {"magnitude": 4.5},
])
def test_rejects_invalid_events(patch):
    data = {**notification().model_dump(), **patch}
    with pytest.raises(ValidationError):
        Notification.model_validate(data)


def test_rejects_missing_coordinates():
    with pytest.raises(ValidationError):
        Notification.model_validate({"id": "x"})


@pytest.mark.parametrize("distance,expected", [
    (0.0, True), (499.999, True), (500.0, False), (500.001, False),
])
def test_strict_500_km_boundary(distance, expected):
    assert is_interested(distance) is expected


@pytest.mark.parametrize("distance,expected", [(499.999, True), (500.001, False)])
def test_geodesic_near_boundary(distance, expected):
    city = CITIES["valparaiso"]
    target = Geodesic.WGS84.Direct(city.latitude, city.longitude, 0, distance * 1000)
    event = Notification(id="boundary", latitude=target["lat2"], longitude=target["lon2"])
    calculated = distance_km(city, event)
    assert calculated == pytest.approx(distance, abs=1e-8)
    assert is_interested(calculated) is expected


def test_zero_and_reference_distance():
    assert distance_km(CITIES["arica"], notification("demo-arica")) == 0
    # Un grado sobre el ecuador WGS84: aproximadamente 111.31949 km.
    city = type(CITIES["arica"])("Origen", 0.0, 0.0)
    assert distance_km(city, Notification(id="ref", latitude=0.0, longitude=1.0)) == pytest.approx(111.31949, abs=1e-5)


@pytest.mark.parametrize("event_id,expected_cities", EXPECTED.items())
def test_all_five_subscribers_only_pull_if_interested(event_id, expected_cities):
    for city_key, city in CITIES.items():
        requests = []

        def handler(request):
            requests.append(request)
            return detail_response(event_id)

        with client_for(handler) as client:
            result = Processor(city, client).process(notification(event_id).model_dump_json().encode())
        interested = city_key in expected_cities
        assert result["action"] == ("detail" if interested else "ignored")
        assert result["http_requested"] is interested
        assert len(requests) == int(interested)
        if interested:
            assert requests[0].url.path == f"/sismos/{event_id}"


def test_republishing_an_event_repeats_the_demo():
    handler = Mock(side_effect=lambda request: detail_response())
    with client_for(handler) as client:
        processor = Processor(CITIES["valparaiso"], client)
        body = notification().model_dump_json().encode()
        assert processor.process(body)["action"] == "detail"
        assert processor.process(body)["action"] == "detail"
    assert handler.call_count == 2


def test_timeout_is_reported_without_retrying():
    handler = Mock(side_effect=httpx.ReadTimeout("simulado"))
    with client_for(handler) as client, pytest.raises(httpx.ReadTimeout):
        fetch_detail(client, notification())
    assert handler.call_count == 1


@pytest.mark.parametrize("status", [404, 503])
def test_http_errors_are_reported_without_retrying(status):
    handler = Mock(return_value=httpx.Response(status))
    with client_for(handler) as client, pytest.raises(httpx.HTTPStatusError):
        fetch_detail(client, notification())
    assert handler.call_count == 1


@pytest.mark.parametrize("response", [httpx.Response(200, content=b"invalid json"), detail_response("demo-arica")])
def test_invalid_or_inconsistent_http_detail_is_rejected(response):
    with client_for(lambda request: response) as client, pytest.raises(ValueError):
        fetch_detail(client, notification())


@pytest.mark.parametrize("body", [b"not json", b'{"id":"bad"}'])
def test_bad_message_is_discarded_without_http(body):
    handler = Mock()
    channel = Mock()
    with client_for(handler) as client:
        callback = make_callback(Processor(CITIES["arica"], client), Mock())
        callback(channel, SimpleNamespace(delivery_tag=42), None, body)
    handler.assert_not_called()
    channel.basic_ack.assert_not_called()
    channel.basic_nack.assert_called_once_with(delivery_tag=42, requeue=False)


def test_http_failure_is_discarded_and_next_event_is_processed():
    channel = Mock()
    output = Mock()
    responses = iter([httpx.Response(503), detail_response()])
    with client_for(lambda request: next(responses)) as client:
        processor = Processor(CITIES["valparaiso"], client)
        callback = make_callback(processor, output)
        body = notification().model_dump_json().encode()
        callback(channel, SimpleNamespace(delivery_tag=7), None, body)
        callback(channel, SimpleNamespace(delivery_tag=8), None, body)
    assert [call.args[0]["action"] for call in output.call_args_list] == ["failed", "detail"]
    channel.basic_nack.assert_called_once_with(delivery_tag=7, requeue=False)
    channel.basic_ack.assert_called_once_with(delivery_tag=8)


def test_success_acknowledges_after_processing():
    channel = Mock()
    output = Mock()
    with client_for(lambda request: detail_response()) as client:
        callback = make_callback(Processor(CITIES["valparaiso"], client), output)
        callback(channel, SimpleNamespace(delivery_tag=9), None, notification().model_dump_json().encode())
    assert output.call_args.args[0]["action"] == "detail"
    channel.basic_ack.assert_called_once_with(delivery_tag=9)
    channel.basic_nack.assert_not_called()


def test_topology_has_five_distinct_bound_queues():
    channel = Mock()
    queues = [declare_city(channel, city) for city in CITIES]
    assert len(set(queues)) == 5
    assert channel.queue_declare.call_count == 5
    bound_queues = {call.kwargs["queue"] for call in channel.queue_bind.call_args_list}
    assert bound_queues == set(queues)
    assert all(call.kwargs["durable"] for call in channel.queue_declare.call_args_list)


def test_catalog_rejects_duplicate_ids(tmp_path):
    path = tmp_path / "duplicate.json"
    record = CATALOG["demo-arica"].model_dump(mode="json")
    path.write_text(json.dumps([record, record]), encoding="utf-8")
    with pytest.raises(ValueError, match="repetidos"):
        load_catalog(path)
