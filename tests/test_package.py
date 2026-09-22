"""
tests/test_package.py

Public-surface and packaging checks for the astro-colibri SDK.

These guard the parts a published library cannot get wrong quietly: the
exported names, the advertised topic list, the version users see, the
promise that no Producer is reachable from this package, and the fixed
production host of the API client.
"""

from __future__ import annotations

import builtins
import inspect
import re
from pathlib import Path

import astrocolibri

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _pyproject_version() -> str:
    """Read [project] version without needing tomllib (Python 3.9 support)."""
    text = PYPROJECT.read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "no version found in pyproject.toml"
    return match.group(1)


class TestPublicSurface:
    def test_all_exports_are_importable(self):
        # A name in __all__ that does not resolve breaks `from astrocolibri
        # import *` for every user, and only shows up after release.
        for name in astrocolibri.__all__:
            assert hasattr(astrocolibri, name), f"__all__ exports missing {name}"

    def test_documented_entry_points_are_exported(self):
        for name in (
            "Consumer",
            "Client",
            "TOPICS",
            "OPTIONAL_PARAMETERS",
            "__version__",
        ):
            assert name in astrocolibri.__all__

    def test_no_producer_is_reachable(self):
        # The package deliberately ships consumption only; publishing stays
        # inside the broker application. Catch a Producer leaking in.
        assert not hasattr(astrocolibri, "Producer")
        assert not any("producer" in name.lower() for name in astrocolibri.__all__)


class TestTopics:
    EXPECTED = [
        "astrocolibri.all.JSON",
        "astrocolibri.all.VOEvent",
        "astrocolibri.important.JSON",
        "astrocolibri.important.VOEvent",
        "astrocolibri.heartbeat",
    ]

    def test_topics_match_the_documented_set(self):
        # These strings are published in the README and on the API doc page.
        # Renaming one silently breaks every user's subscribe() call.
        assert astrocolibri.TOPICS == self.EXPECTED

    def test_topics_have_no_duplicates(self):
        assert len(astrocolibri.TOPICS) == len(set(astrocolibri.TOPICS))

    def test_broker_test_topic_is_not_a_public_stream(self):
        # The broker routes test traffic to a dedicated "test" topic, kept
        # outside the astrocolibri.* namespace. It must never be advertised
        # here, or ordinary users would consume test events as real alerts.
        assert "test" not in astrocolibri.TOPICS
        assert all(t.startswith("astrocolibri.") for t in astrocolibri.TOPICS)


class TestExceptionHierarchy:
    def test_every_error_subclasses_the_base(self):
        # The docs promise a single `except AstrocolibriError` catches all.
        from astrocolibri import (
            AstrocolibriAPIError,
            AstrocolibriAuthError,
            AstrocolibriConfigError,
            AstrocolibriDecodeError,
            AstrocolibriError,
            AstrocolibriKafkaError,
            AstrocolibriNotFoundError,
            AstrocolibriRateLimitError,
            AstrocolibriTransportError,
        )

        for exc in (
            AstrocolibriAuthError,
            AstrocolibriConfigError,
            AstrocolibriKafkaError,
            AstrocolibriDecodeError,
            AstrocolibriAPIError,
            AstrocolibriNotFoundError,
            AstrocolibriRateLimitError,
            AstrocolibriTransportError,
        ):
            assert issubclass(exc, AstrocolibriError)

    def test_specific_api_errors_are_api_errors(self):
        # `except AstrocolibriAPIError` must also catch a miss or a quota stop.
        from astrocolibri import (
            AstrocolibriAPIError,
            AstrocolibriNotFoundError,
            AstrocolibriRateLimitError,
        )

        assert issubclass(AstrocolibriNotFoundError, AstrocolibriAPIError)
        assert issubclass(AstrocolibriRateLimitError, AstrocolibriAPIError)

    def test_base_error_subclasses_exception(self):
        from astrocolibri import AstrocolibriError

        assert issubclass(AstrocolibriError, Exception)


class TestClientSurface:
    def test_api_url_is_the_production_https_host(self):
        assert astrocolibri.Client.API_URL == "https://astro-colibri.science"

    def test_host_cannot_be_overridden(self):
        # The public SDK only talks to production. Encoded like the missing
        # Producer: a base_url parameter would be an invitation to point the
        # SDK at unofficial endpoints.
        parameters = set(inspect.signature(astrocolibri.Client.__init__).parameters)
        assert not parameters & {"base_url", "url", "host", "api_url", "endpoint"}

    def test_no_public_parameter_shadows_a_builtin(self):
        # `filter=` or `format=` would shadow builtins inside user code that
        # forwards keyword arguments.
        shadowed = []
        for name, method in inspect.getmembers(astrocolibri.Client, inspect.isfunction):
            if name.startswith("_") and name != "__init__":
                continue
            for parameter in inspect.signature(method).parameters:
                if parameter != "self" and hasattr(builtins, parameter):
                    shadowed.append(f"{name}({parameter}=)")
        assert shadowed == []

    def test_optional_parameters_match_the_api(self):
        # The API accepts exactly these; anything else is rejected client-side.
        assert astrocolibri.OPTIONAL_PARAMETERS == ("gw_contours", "archive")


class TestVersion:
    def test_version_matches_pyproject(self):
        # The version lives in both _version.py and pyproject.toml. If they
        # drift, users get a wheel whose __version__ lies about itself.
        assert astrocolibri.__version__ == _pyproject_version()

    def test_version_is_pep440_ish(self):
        assert re.fullmatch(
            r"\d+\.\d+\.\d+([._-]?(a|b|rc|dev|post)\d*)?", astrocolibri.__version__
        ), f"unexpected version string: {astrocolibri.__version__}"
