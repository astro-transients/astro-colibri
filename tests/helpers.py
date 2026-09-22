"""
tests/helpers.py

Shared helpers for the API client tests.

Responses are real `requests.Response` objects, so `.json()` and `.text`
behave exactly as they do against the live API; only the session that sends
them is mocked.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

import requests

#: Shaped like a Firebase user ID (28 characters) and obviously fake.
FAKE_UID = "TESTuid00000000000000000000x"

NO_BODY = object()


def make_response(
    status: int = 200,
    body: Any = NO_BODY,
    *,
    text: Optional[str] = None,
    content_type: str = "application/json",
) -> requests.Response:
    """A `requests.Response` carrying `body` as JSON, or `text` verbatim."""
    response = requests.Response()
    response.status_code = status
    response.reason = "TEST"
    if body is not NO_BODY:
        response._content = json.dumps(body).encode("utf-8")
    else:
        response._content = (text or "").encode("utf-8")
    response.headers["Content-Type"] = content_type
    response.encoding = "utf-8"
    return response


def sent(session: Any) -> Tuple[str, str, Dict[str, Any]]:
    """`(method, url, keyword arguments)` of the last request sent."""
    args, kwargs = session.request.call_args
    return args[0], args[1], kwargs
