"""
tests/test_errors.py

Unit tests for how API failures surface as exceptions.

The API does not signal errors consistently. Status codes arrive as ints or
as strings, some errors are serialized under HTTP 200, and a missing user
ID, an unknown one and an exhausted quota each look different. The client
folds all of that into a small exception hierarchy; these tests pin the
mapping.

Run:
    pytest tests/test_errors.py -v
"""

from __future__ import annotations

from datetime import datetime

import pytest
import requests
from astrocolibri.exceptions import (
    AstrocolibriAPIError,
    AstrocolibriAuthError,
    AstrocolibriError,
    AstrocolibriNotFoundError,
    AstrocolibriRateLimitError,
    AstrocolibriTransportError,
)

START = "2026-09-01T00:00:00Z"
END = "2026-09-02T00:00:00Z"
RATE_LIMITED = "Rate limit exceeded. Renewal at 2026-09-13T08:00:00"


def search(client):
    return client.latest_transients(start=START, end=END)


class TestStatusMapping:
    def test_401(self, client, respond):
        respond(
            401,
            {"message": "Unauthorized: please provide a valid uid", "status_code": 401},
        )
        with pytest.raises(AstrocolibriAuthError, match="please provide a valid uid"):
            search(client)

    def test_403_unknown_user_points_at_the_account_page(self, client, respond):
        # What a mistyped user ID looks like.
        respond(403, {"message": "User does not exist", "status_code": 403})
        with pytest.raises(AstrocolibriAuthError) as excinfo:
            search(client)
        assert "User does not exist" in str(excinfo.value)
        assert "astro-colibri.com/account" in str(excinfo.value)

    def test_404(self, client, respond):
        respond(404, {"message": "not found", "status_code": "404"})
        with pytest.raises(AstrocolibriNotFoundError) as excinfo:
            search(client)
        assert excinfo.value.status_code == 404
        assert excinfo.value.endpoint == "/latest_transients"

    def test_429_carries_the_reset_time(self, client, respond):
        respond(429, {"message": RATE_LIMITED, "status_code": 429})
        with pytest.raises(AstrocolibriRateLimitError) as excinfo:
            search(client)
        assert excinfo.value.reset_time == datetime(2026, 9, 13, 8, 0, 0)
        assert excinfo.value.status_code == 429

    def test_429_reset_time_in_str_datetime_form(self, client, respond):
        # The API builds the message with str(datetime): a space separator
        # and microseconds.
        message = "Rate limit exceeded. Renewal at 2026-09-13 08:00:00.123456"
        respond(429, {"message": message, "status_code": 429})
        with pytest.raises(AstrocolibriRateLimitError) as excinfo:
            search(client)
        assert excinfo.value.reset_time == datetime(2026, 9, 13, 8, 0, 0, 123456)

    def test_429_without_a_parseable_time(self, client, respond):
        respond(429, {"message": "Too many requests", "status_code": 429})
        with pytest.raises(
            AstrocolibriRateLimitError, match="Too many requests"
        ) as excinfo:
            search(client)
        assert excinfo.value.reset_time is None

    def test_500(self, client, respond):
        respond(500, {"message": "Internal error"})
        with pytest.raises(AstrocolibriAPIError, match="Internal error") as excinfo:
            search(client)
        assert type(excinfo.value) is AstrocolibriAPIError
        assert excinfo.value.status_code == 500

    def test_message_and_formatting(self, client, respond):
        respond(400, {"message": "Invalid filter format : missing field 'type'"})
        with pytest.raises(AstrocolibriAPIError) as excinfo:
            search(client)
        assert excinfo.value.message == "Invalid filter format : missing field 'type'"
        assert str(excinfo.value) == (
            "[HTTP 400] /latest_transients: Invalid filter format : missing field 'type'"
        )

    def test_non_json_error_body(self, client, respond):
        respond(502, text="<html>Bad Gateway</html>", content_type="text/html")
        with pytest.raises(AstrocolibriAPIError, match="Bad Gateway") as excinfo:
            search(client)
        assert excinfo.value.status_code == 502

    def test_empty_error_body_falls_back_to_the_reason(self, client, respond):
        respond(503, text="")
        with pytest.raises(AstrocolibriAPIError, match="TEST"):
            search(client)


class TestHierarchy:
    @pytest.mark.parametrize(
        "cls", [AstrocolibriNotFoundError, AstrocolibriRateLimitError]
    )
    def test_api_error_subclasses(self, cls):
        assert issubclass(cls, AstrocolibriAPIError)

    @pytest.mark.parametrize(
        "cls", [AstrocolibriAPIError, AstrocolibriTransportError, AstrocolibriAuthError]
    )
    def test_everything_is_an_astrocolibri_error(self, cls):
        assert issubclass(cls, AstrocolibriError)


class TestErrorEnvelopes:
    def test_status_code_as_a_string(self, client, respond):
        respond(400, {"message": "bad request", "status_code": "400"})
        with pytest.raises(AstrocolibriAPIError) as excinfo:
            search(client)
        assert excinfo.value.status_code == 400

    def test_error_tuple_under_http_200(self, client, respond):
        # GET /latest_transients answers a refused request this way (#978):
        # the Flask error tuple serialized as a JSON array, under HTTP 200.
        respond(
            200,
            [
                {
                    "message": "Unauthorized: please provide a valid uid",
                    "status_code": 401,
                },
                401,
            ],
        )
        with pytest.raises(AstrocolibriAuthError, match="please provide a valid uid"):
            search(client)

    def test_rate_limit_tuple_under_http_200(self, client, respond):
        respond(200, [{"message": RATE_LIMITED, "status_code": 429}, 429])
        with pytest.raises(AstrocolibriRateLimitError) as excinfo:
            search(client)
        assert excinfo.value.reset_time == datetime(2026, 9, 13, 8, 0, 0)

    def test_error_dict_under_http_200(self, client, respond):
        respond(200, {"message": "bad request", "status_code": "500"})
        with pytest.raises(AstrocolibriAPIError, match="bad request"):
            client.get_event("X")

    def test_a_pair_of_events_is_not_an_envelope(self, client, respond):
        events = [{"trigger_id": "A", "ra": 1.0}, {"trigger_id": "B", "ra": 2.0}]
        respond(200, events)
        assert client.get_events(["A", "B"]) == events

    def test_a_result_with_a_message_field_is_not_an_envelope(self, client, respond):
        # Only bodies made of nothing but envelope keys count as errors.
        payload = {"voevents": [], "message": "no entries found", "status_code": 404}
        respond(200, payload)
        assert search(client) == payload


class TestMalformedResponses:
    def test_non_json_success_body(self, client, respond):
        respond(200, text="<html>maintenance</html>", content_type="text/html")
        with pytest.raises(AstrocolibriAPIError, match="does not understand"):
            search(client)

    def test_long_bodies_are_truncated(self, client, respond):
        respond(200, text="x" * 10_000, content_type="text/plain")
        with pytest.raises(AstrocolibriAPIError) as excinfo:
            search(client)
        assert len(str(excinfo.value)) < 500


class TestTransportErrors:
    def test_timeout(self, client, session):
        session.request.side_effect = requests.Timeout("read timed out")
        with pytest.raises(AstrocolibriTransportError, match="timed out after 30 s"):
            search(client)

    def test_connection_error(self, client, session):
        session.request.side_effect = requests.ConnectionError(
            "Name or service not known"
        )
        with pytest.raises(
            AstrocolibriTransportError, match="Name or service not known"
        ):
            search(client)

    def test_ssl_error(self, client, session):
        session.request.side_effect = requests.exceptions.SSLError(
            "certificate verify failed"
        )
        with pytest.raises(
            AstrocolibriTransportError, match="certificate verify failed"
        ):
            search(client)

    def test_transport_error_is_not_an_api_error(self, client, session):
        session.request.side_effect = requests.ConnectionError("down")
        with pytest.raises(AstrocolibriTransportError) as excinfo:
            search(client)
        assert not isinstance(excinfo.value, AstrocolibriAPIError)
