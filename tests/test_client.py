"""
tests/test_client.py

Unit tests for Client construction, user ID handling and transport.

The session is mocked; no request leaves the machine.

Run:
    pytest tests/test_client.py -v
"""

from __future__ import annotations

import math
from unittest.mock import patch

import pytest
import requests
from astrocolibri import Client, __version__
from astrocolibri.exceptions import (
    AstrocolibriAPIError,
    AstrocolibriConfigError,
    AstrocolibriTransportError,
)

from .helpers import FAKE_UID, sent

START = "2026-09-01T00:00:00Z"
END = "2026-09-02T00:00:00Z"


class TestUidResolution:
    def test_explicit_uid(self, session, respond):
        client = Client(uid="explicit-uid", session=session)
        respond(200, {"voevents": []})
        client.latest_transients(start=START, end=END)
        assert sent(session)[2]["json"]["uid"] == "explicit-uid"

    def test_env_var_used_when_uid_omitted(self, session, respond, monkeypatch):
        monkeypatch.setenv("ASTROCOLIBRI_UID", "env-uid")
        client = Client(session=session)
        respond(200, {"voevents": []})
        client.latest_transients(start=START, end=END)
        assert sent(session)[2]["json"]["uid"] == "env-uid"

    def test_explicit_uid_wins_over_env_var(self, session, respond, monkeypatch):
        monkeypatch.setenv("ASTROCOLIBRI_UID", "env-uid")
        client = Client(uid="explicit-uid", session=session)
        respond(200, {"voevents": []})
        client.latest_transients(start=START, end=END)
        assert sent(session)[2]["json"]["uid"] == "explicit-uid"

    def test_explicit_uid_is_stripped(self, session, respond):
        # A user ID pasted from the account page often carries whitespace.
        client = Client(uid="  pasted-uid \n", session=session)
        respond(200, {"voevents": []})
        client.latest_transients(start=START, end=END)
        assert sent(session)[2]["json"]["uid"] == "pasted-uid"

    def test_env_var_is_stripped(self, session, respond, monkeypatch):
        monkeypatch.setenv("ASTROCOLIBRI_UID", " env-uid ")
        client = Client(session=session)
        respond(200, {"voevents": []})
        client.latest_transients(start=START, end=END)
        assert sent(session)[2]["json"]["uid"] == "env-uid"

    @pytest.mark.parametrize("value", ["", "   "])
    def test_empty_explicit_uid_is_rejected(self, value):
        with pytest.raises(AstrocolibriConfigError, match="empty"):
            Client(uid=value)

    def test_empty_uid_error_links_the_account_page(self):
        with pytest.raises(AstrocolibriConfigError, match="astro-colibri.com/account"):
            Client(uid="")

    def test_non_string_uid_is_rejected(self):
        with pytest.raises(AstrocolibriConfigError, match="string"):
            Client(uid=12345)

    def test_empty_env_var_counts_as_unset(self, monkeypatch):
        monkeypatch.setenv("ASTROCOLIBRI_UID", "")
        assert Client().has_uid is False

    def test_no_uid_anywhere(self):
        assert Client().has_uid is False

    def test_has_uid(self):
        assert Client(uid=FAKE_UID).has_uid is True

    def test_env_var_is_read_at_construction(self, monkeypatch):
        client = Client()
        monkeypatch.setenv("ASTROCOLIBRI_UID", "set-too-late")
        assert client.has_uid is False

    def test_nothing_is_written_to_disk(self, session, respond, tmp_path, monkeypatch):
        # The user ID lives only in memory: no config file, no cache, no
        # dotfile, wherever the process happens to run.
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        with Client(uid=FAKE_UID, session=session) as client:
            respond(200, {"voevents": []})
            client.latest_transients(start=START, end=END)
        assert list(tmp_path.iterdir()) == []


class TestUidNeverLeaks:
    def test_repr_hides_uid(self, client):
        assert FAKE_UID not in repr(client)
        assert "uid=set" in repr(client)

    def test_repr_without_uid(self, anonymous_client):
        assert "uid=unset" in repr(anonymous_client)

    def test_transport_error_text_is_scrubbed(self, client, session):
        # requests puts the full URL, query string included, into its
        # exception text, and include_custom_events sends the uid there.
        session.request.side_effect = requests.ConnectionError(
            f"Max retries exceeded with url: /event?trigger_id=X&uid={FAKE_UID}"
        )
        with pytest.raises(AstrocolibriTransportError) as excinfo:
            client.get_event("X", include_custom_events=True)
        assert FAKE_UID not in str(excinfo.value)
        assert "<uid>" in str(excinfo.value)

    def test_transport_error_does_not_chain_the_original(self, client, session):
        # A chained exception is printed in full in tracebacks, uid and all.
        session.request.side_effect = requests.ConnectionError(f"url with {FAKE_UID}")
        with pytest.raises(AstrocolibriTransportError) as excinfo:
            client.get_event("X")
        assert excinfo.value.__cause__ is None
        assert excinfo.value.__suppress_context__ is True

    def test_api_error_message_is_scrubbed(self, client, respond):
        respond(500, {"message": f"failure while handling user {FAKE_UID}"})
        with pytest.raises(AstrocolibriAPIError) as excinfo:
            client.get_event("X")
        assert FAKE_UID not in str(excinfo.value)
        assert FAKE_UID not in excinfo.value.message

    @pytest.mark.parametrize(
        "encoded",
        [
            "odd+uid%2Fwith%2Bchars",  # form encoding: how requests builds query strings
            "odd%20uid%2Fwith%2Bchars",  # percent encoding
        ],
    )
    def test_encoded_uid_is_scrubbed(self, session, encoded):
        client = Client(uid="odd uid/with+chars", session=session)
        session.request.side_effect = requests.ConnectionError(
            f"url: /event?uid={encoded}"
        )
        with pytest.raises(AstrocolibriTransportError) as excinfo:
            client.get_event("X", include_custom_events=True)
        assert encoded not in str(excinfo.value)
        assert "<uid>" in str(excinfo.value)


class TestTransport:
    def test_production_url_is_fixed(self, client, session, respond):
        respond(200, {"trigger_id": "X"})
        client.get_event("X")
        method, url, _ = sent(session)
        assert method == "GET"
        assert url == "https://astro-colibri.science/event"

    def test_user_agent_names_the_sdk(self, client, session, respond):
        respond(200, {"trigger_id": "X"})
        client.get_event("X")
        assert (
            sent(session)[2]["headers"]["User-Agent"]
            == f"astro-colibri-python/{__version__}"
        )

    def test_injected_session_settings_are_untouched(self, session, respond):
        session.headers = {"User-Agent": "my-pipeline/2.0"}
        client = Client(session=session)
        respond(200, {"trigger_id": "X"})
        client.get_event("X")
        assert session.headers == {"User-Agent": "my-pipeline/2.0"}
        assert sent(session)[2]["headers"]["User-Agent"].startswith(
            "astro-colibri-python/"
        )

    def test_accepts_json_for_json_endpoints(self, client, session, respond):
        respond(200, {"trigger_id": "X"})
        client.get_event("X")
        assert sent(session)[2]["headers"]["Accept"] == "application/json"

    def test_accepts_xml_for_voevent_export(self, client, session, respond):
        respond(200, text="<voe:VOEvent/>", content_type="application/xml")
        client.get_event_voevent("X")
        assert sent(session)[2]["headers"]["Accept"] == "application/xml"

    def test_default_timeout(self, client, session, respond):
        respond(200, {"trigger_id": "X"})
        client.get_event("X")
        assert sent(session)[2]["timeout"] == 30.0

    def test_constructor_timeout(self, session, respond):
        client = Client(timeout=5, session=session)
        respond(200, {"trigger_id": "X"})
        client.get_event("X")
        assert sent(session)[2]["timeout"] == 5.0

    def test_per_call_timeout_overrides(self, client, session, respond):
        respond(200, {"name": "Crab", "ra": 83.6, "dec": 22.0})
        client.get_source_summary("Crab", timeout=300)
        assert sent(session)[2]["timeout"] == 300.0

    @pytest.mark.parametrize("value", [0, -1, "30", True, math.inf, math.nan, None])
    def test_invalid_constructor_timeout(self, value):
        with pytest.raises(AstrocolibriConfigError, match="timeout"):
            Client(timeout=value)

    def test_invalid_per_call_timeout_sends_nothing(self, client, session):
        with pytest.raises(AstrocolibriConfigError, match="timeout"):
            client.get_event("X", timeout=0)
        session.request.assert_not_called()

    def test_default_session_does_not_retry(self):
        # Retrying could spend quota twice or re-trigger expensive
        # server-side processing, so the SDK's own session never retries.
        client = Client()
        adapter = client._session.get_adapter(Client.API_URL)
        assert adapter.max_retries.total == 0

    def test_failed_request_is_sent_exactly_once(self, client, session, respond):
        respond(500, {"message": "boom"})
        with pytest.raises(AstrocolibriAPIError):
            client.get_event("X")
        assert session.request.call_count == 1

    def test_timeout_is_sent_exactly_once(self, client, session):
        session.request.side_effect = requests.Timeout("slow")
        with pytest.raises(AstrocolibriTransportError):
            client.get_event("X")
        assert session.request.call_count == 1


class TestLifecycle:
    def test_close_closes_the_session_it_created(self):
        with patch("astrocolibri.client.requests.Session") as session_cls:
            client = Client()
            client.close()
        session_cls.return_value.close.assert_called_once()

    def test_close_leaves_an_injected_session_open(self, session):
        Client(session=session).close()
        session.close.assert_not_called()

    def test_context_manager_closes(self):
        with patch("astrocolibri.client.requests.Session") as session_cls:
            with Client():
                pass
        session_cls.return_value.close.assert_called_once()

    def test_context_manager_closes_on_exception(self):
        with patch("astrocolibri.client.requests.Session") as session_cls:
            with pytest.raises(RuntimeError):
                with Client():
                    raise RuntimeError("boom")
        session_cls.return_value.close.assert_called_once()

    def test_exit_does_not_swallow_exceptions(self, session):
        assert (
            Client(session=session).__exit__(RuntimeError, RuntimeError(), None)
            is False
        )
