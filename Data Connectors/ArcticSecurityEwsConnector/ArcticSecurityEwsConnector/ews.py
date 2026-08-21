"""
Communicate with the Arctic Security Ews
"""

import logging
from typing import Tuple, Iterable, Mapping, Optional

import requests
from requests.adapters import HTTPAdapter, Retry

retry_codes = (500, 502, 503, 504)
retry = Retry(
    total=10,
    backoff_factor=1,
    status_forcelist=retry_codes,
)
adapter = HTTPAdapter(max_retries=retry)
session = requests.Session()
session.mount("http://", adapter)
session.mount("https://", adapter)
logger = logging.getLogger(__name__)


def load_events(
    url: str,
    token: Optional[str],
    limit: Optional[int] = None,
) -> Tuple[Iterable[Mapping], Optional[str], bool]:
    """Load events from ews.

    The Log Ingestion API SDK handles chunking (1 MB per API call).
    https://learn.microsoft.com/en-us/azure/azure-monitor/logs/logs-ingestion-api-overview
    """
    # url manipulation here assumes there is at least one query parameter (apikey)
    assert "?" in url

    # If token given, use it - otherwise start from 7 days ago (somewhat arbitrary choice)
    if token:
        url += f"&token={token}"
    else:
        url += f"&start=-{7 * 24 * 3600}"

    if limit is not None:
        url += f"&limit={limit}"

    logger.debug(f"Load events from {url=}")
    resp = session.get(url)

    if resp.status_code == 200:
        events = resp.json()
        more_available = "x-next-token" in resp.headers
        last_inserted = resp.headers.get("x-last-inserted-token")
        last_token = resp.headers.get("x-last-token")

        if more_available:
            token = last_token
            logger.debug(
                f"Loaded {len(events)} events succesfully, {token=}, {more_available=}"
            )
        else:
            token = last_inserted
            logger.debug(
                f"Loaded {len(events)} events, end of pages or no data.  {token=}, {more_available=}"
            )
    else:
        if _is_invalid_token_error(resp):
            logger.warning(f"Invalid token {token}, reset it and retry")
            events, token, more_available = None, None, True
        else:
            events, token, more_available = None, None, False
            logger.warning(f"Error loading events {resp=} {resp.text=}")
    return events, token, more_available


def _is_invalid_token_error(resp):
    """Check whether error is due to invalid token."""
    if resp.status_code != 400:
        return False

    try:
        for error in resp.json()["errors"]:
            if error["key"] == "token" and error["message"].startswith("Invalid token"):
                return True
    except Exception:
        return False

    return False
