"""Check a Streamlit entrypoint or the liveness of an already running demo.

Run AppTest without credentials: the target page executes its normal code.
HTTP liveness does not prove app correctness.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen


def check_health(base_url: str, timeout: float = 15) -> None:
    try:
        parsed = urlsplit(base_url)
        # Accessing hostname/port validates malformed bracketed hosts and
        # ports that urlsplit parses lazily.
        hostname = parsed.hostname
        _port = parsed.port
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Use an HTTP(S) base URL without credentials, query or fragment"
        ) from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Use an HTTP(S) base URL without credentials, query or fragment"
        )
    url = base_url.rstrip("/") + "/_stcore/health"
    try:
        with urlopen(url, timeout=timeout) as response:
            if response.status != 200 or response.read(128).strip() != b"ok":
                raise ValueError(
                    "Streamlit health response must be HTTP 200 with body ok"
                )
    except (URLError, TimeoutError, OSError) as exc:
        # Avoid logging URLs, headers, response payloads or credentials.
        raise ValueError("Streamlit health request failed") from exc


def check_app(entrypoint: Path, timeout: float = 30) -> None:
    if not entrypoint.is_file():
        raise ValueError("Streamlit entrypoint is missing; merge the Dashboard first")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(entrypoint), default_timeout=timeout).run()
    if app.exception:
        raise ValueError(
            "Streamlit app raised an exception; inspect locally without secrets"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--url", help="Check an existing server; does not execute the page"
    )
    group.add_argument("--entrypoint", type=Path, default=Path("streamlit_app.py"))
    args = parser.parse_args()
    try:
        if args.url:
            check_health(args.url)
            print(
                "PASS: Streamlit server liveness (not data freshness or UI acceptance)"
            )
        else:
            check_app(args.entrypoint)
            print("PASS: Streamlit initial page executed without exceptions")
    except (ValueError, ImportError, RuntimeError) as exc:
        # AppTest timeout details can contain page output; keep CLI failure generic.
        if isinstance(exc, ValueError):
            parser.exit(1, f"FAIL: {exc}\n")
        parser.exit(1, "FAIL: Streamlit dependency or execution failure\n")


if __name__ == "__main__":
    main()
