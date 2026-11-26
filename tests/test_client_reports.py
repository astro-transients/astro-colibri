"""
tests/test_client_reports.py

Unit tests for submit_observation_report and the personal API token.

Run:
    pytest tests/test_client_reports.py -v
"""

from __future__ import annotations

import pytest
from astrocolibri import Client
from astrocolibri.exceptions import (
    AstrocolibriAPIError,
    AstrocolibriAuthError,
    AstrocolibriConfigError,
    AstrocolibriNotFoundError,
)

from .helpers import FAKE_UID, sent

FAKE_TOKEN = "colibri_TESTtoken0000000000000000000000000000x"

DETECTION = {
    "observation_type": "detection",
    "filter": "r",
    "magnitude": 18.2,
    "magnitude_error": 0.1,
    "time_utc_mid": "2025-10-20T21:14:05Z",
}

CREATED = {
    "trigger_id": "1234",
    "source_name": "GRB 251020A",
    "observatory": "MYOBS",
    "report_id": "AC 2025abc_1",
    "observations": 1,
    "status": "created",
    "status_code": "200",
}


@pytest.fixture
def token_client(session):
    return Client(token=FAKE_TOKEN, session=session)


def submit(client, **overrides):
    arguments = {"source_name": "GRB 251020A", "observations": [DETECTION]}
    arguments.update(overrides)
    return client.submit_observation_report("myobs", **arguments)


class TestToken:
    def test_env_var_used_when_token_omitted(self, session, monkeypatch):
        monkeypatch.setenv("ASTROCOLIBRI_API_TOKEN", f"  {FAKE_TOKEN} ")
        assert Client(session=session).has_token is True

    def test_explicit_token_wins_over_env_var(self, session, respond, monkeypatch):
        monkeypatch.setenv("ASTROCOLIBRI_API_TOKEN", "colibri_other")
        respond(body=CREATED)

        submit(Client(token=FAKE_TOKEN, session=session))

        assert sent(session)[2]["headers"]["Authorization"] == f"Bearer {FAKE_TOKEN}"

    @pytest.mark.parametrize("value", ["", "   "])
    def test_empty_explicit_token_is_rejected(self, value):
        with pytest.raises(
            AstrocolibriConfigError, match="token was given but is empty"
        ):
            Client(token=value)

    def test_non_string_token_is_rejected(self):
        with pytest.raises(AstrocolibriConfigError, match="token must be a string"):
            Client(token=123)

    def test_no_token_anywhere(self):
        assert Client().has_token is False

    def test_repr_hides_token(self, token_client):
        assert FAKE_TOKEN not in repr(token_client)
        assert "token=set" in repr(token_client)

    def test_token_is_not_sent_on_other_requests(self, session, respond):
        respond(body={"trigger_id": "1234"})
        Client(uid=FAKE_UID, token=FAKE_TOKEN, session=session).get_event("1234")

        assert "Authorization" not in sent(session)[2]["headers"]

    def test_api_error_message_is_scrubbed(self, token_client, respond):
        respond(
            400, {"message": f"bad request from {FAKE_TOKEN}", "status_code": "400"}
        )

        with pytest.raises(AstrocolibriAPIError) as excinfo:
            submit(token_client)

        assert FAKE_TOKEN not in str(excinfo.value)
        assert "<token>" in str(excinfo.value)


class TestSubmit:
    def test_posts_the_report_with_the_token(self, token_client, session, respond):
        respond(body=CREATED)

        result = submit(
            token_client,
            trigger_id="1234",
            redshift=1.2,
            comments="Optical counterpart detected.",
            contact_name="Jane",
            contact_email="jane@obs.org",
            update_figure=True,
        )

        assert result == CREATED
        method, url, kwargs = sent(session)
        assert method == "POST"
        assert url == "https://astro-colibri.science/observation_report"
        assert kwargs["headers"]["Authorization"] == f"Bearer {FAKE_TOKEN}"
        assert kwargs["params"] is None
        assert kwargs["json"] == {
            "observatory": "MYOBS",
            "observation_category": "general_report",
            "update_figure": True,
            "trigger_id": "1234",
            "source_name": "GRB 251020A",
            "observations": [DETECTION],
            "redshift": 1.2,
            "comments": "Optical counterpart detected.",
            "contact": {"name": "Jane", "email": "jane@obs.org"},
        }

    def test_contact_is_left_to_the_api_by_default(
        self, token_client, session, respond
    ):
        respond(body=CREATED)

        submit(token_client)

        assert "contact" not in sent(session)[2]["json"]

    def test_unchanged_resubmission_is_returned(self, token_client, respond):
        respond(body={**CREATED, "status": "unchanged"})

        assert submit(token_client)["status"] == "unchanged"

    def test_missing_token_sends_nothing(self, client, session):
        with pytest.raises(AstrocolibriAuthError, match="ASTROCOLIBRI_API_TOKEN"):
            submit(client)
        session.request.assert_not_called()

    @pytest.mark.parametrize(
        "overrides, message",
        [
            ({"source_name": None}, "Name the event"),
            ({"source_name": " "}, "source_name must be a non-empty string"),
            ({"observations": DETECTION}, "list of dictionaries"),
            ({"observations": ["r=18.2"]}, r"observations\[0\] must be a dictionary"),
            (
                {"observations": [], "comments": " "},
                "observations, a redshift or comments",
            ),
            ({"redshift": -0.1}, "non-negative number"),
            ({"redshift": True}, "non-negative number"),
            ({"comments": 3}, "comments must be a string"),
            ({"update_figure": "yes"}, "update_figure"),
        ],
    )
    def test_invalid_arguments_send_nothing(
        self, token_client, session, overrides, message
    ):
        with pytest.raises(AstrocolibriConfigError, match=message):
            submit(token_client, **overrides)
        session.request.assert_not_called()

    def test_comments_alone_are_a_report(self, token_client, session, respond):
        respond(body=CREATED)

        submit(token_client, observations=None, comments="Observed, nothing found.")

        assert "observations" not in sent(session)[2]["json"]

    def test_rejected_token(self, token_client, respond):
        respond(
            401,
            {
                "code": "invalid_token",
                "message": "Invalid API token",
                "status_code": "401",
            },
        )

        with pytest.raises(AstrocolibriAuthError, match="create a new one in the app"):
            submit(token_client)

    def test_not_a_member(self, token_client, respond):
        respond(
            403,
            {
                "message": "you are not a member of this observatory",
                "status_code": "403",
            },
        )

        with pytest.raises(
            AstrocolibriAuthError, match="not a member of this observatory"
        ):
            submit(token_client)

    def test_unknown_event(self, token_client, respond):
        respond(
            404, {"message": "event 'GRB 251020A' was not found", "status_code": "404"}
        )

        with pytest.raises(AstrocolibriNotFoundError, match="was not found"):
            submit(token_client)

    def test_invalid_field_is_reported(self, token_client, respond):
        respond(
            400,
            {"message": "observations[0]: unknown field(s) mag", "status_code": "400"},
        )

        with pytest.raises(AstrocolibriAPIError, match="unknown field") as excinfo:
            submit(token_client)
        assert excinfo.value.status_code == 400

    def test_malformed_answer(self, token_client, respond):
        respond(body={"status": "created"})

        with pytest.raises(AstrocolibriAPIError, match="does not understand"):
            submit(token_client)
