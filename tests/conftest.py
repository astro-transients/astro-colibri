"""
tests/conftest.py

Fixtures for the API client tests.

The transport is always mocked: a MagicMock stands in for the
`requests.Session`. Nothing here points the client at another host; the
production URL is fixed by design.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from astrocolibri import Client

from .helpers import FAKE_UID, NO_BODY, make_response


@pytest.fixture(autouse=True)
def _isolate_uid_env(monkeypatch):
    """A real ASTROCOLIBRI_UID in the developer's shell must not leak into tests."""
    monkeypatch.delenv("ASTROCOLIBRI_UID", raising=False)


@pytest.fixture
def session():
    return MagicMock(name="requests.Session")


@pytest.fixture
def client(session):
    return Client(uid=FAKE_UID, session=session)


@pytest.fixture
def anonymous_client(session):
    return Client(session=session)


@pytest.fixture
def respond(session):
    """Set the response the next request receives."""

    def _respond(
        status=200, body=NO_BODY, *, text=None, content_type="application/json"
    ):
        session.request.return_value = make_response(
            status, body, text=text, content_type=content_type
        )
        return session.request.return_value

    return _respond
