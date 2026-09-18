"""Ensure liveness rejects login pages and failed/unreachable servers."""

import subprocess
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import pytest

from scripts.check_demo import check_app, check_health


@pytest.mark.parametrize("status,body", [(200, b"ok"), (200, b"ok\n")])
def test_health_accepts_streamlit(status, body):
    response = BytesIO(body)
    response.status = status
    with patch("scripts.check_demo.urlopen", return_value=response) as request:
        check_health("https://demo.streamlit.app/")
    request.assert_called_once_with(
        "https://demo.streamlit.app/_stcore/health", timeout=15
    )


@pytest.mark.parametrize("status,body", [(200, b"<html>login</html>"), (503, b"ok")])
def test_health_rejects_false_positives(status, body):
    response = BytesIO(body)
    response.status = status
    with (
        patch("scripts.check_demo.urlopen", return_value=response),
        pytest.raises(ValueError),
    ):
        check_health("https://demo.streamlit.app")


def test_health_hides_network_error_details():
    with (
        patch("scripts.check_demo.urlopen", side_effect=URLError("private detail")),
        pytest.raises(ValueError, match="^Streamlit health request failed$"),
    ):
        check_health("https://demo.streamlit.app")


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "https://user:pass@host", "https://host?key=value"]
)
def test_health_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        check_health(url)


def test_health_rejects_malformed_url_without_leaking_parser_details():
    with pytest.raises(ValueError, match=r"^Use an HTTP\(S\) base URL") as error:
        check_health("https://[bad")
    assert "bad" not in str(error.value)


def test_missing_entrypoint_is_not_ready():
    missing_entrypoint = Path(__file__).with_name("__missing_streamlit_entrypoint__.py")
    assert not missing_entrypoint.exists()
    with pytest.raises(ValueError, match="entrypoint is missing"):
        check_app(missing_entrypoint)


def test_entrypoint_smoke_works_when_started_outside_repository():
    repository = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(repository / "scripts" / "check_demo.py"),
            "--entrypoint",
            str(repository / "streamlit_app.py"),
        ],
        cwd=repository.parent,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == 0, result.stderr
