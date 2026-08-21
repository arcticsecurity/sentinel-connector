"""
Azure function for Arctic Security Ews data connector to Azure Sentinel.

https://learn.microsoft.com/en-us/azure/azure-monitor/logs/logs-ingestion-api-overview

TODO:
- mapping event keys to property names
  "The property name can contain only letters, numbers, and the underscore (_) character."
"""

import os
import logging
import time
from functools import cache
from dataclasses import dataclass
from typing import Mapping, Iterable, Optional, Callable, Any

import azure.functions as func
from azure.identity import DefaultAzureCredential
from dateutil.parser import isoparse

from .state_manager import StateManager
from .data_collector import post_data
from .ews import load_events

logger = logging.getLogger(__name__)


@dataclass
class Config:
    storage: str
    dce_endpoint: str
    dcr_rule_id: str
    dcr_stream_name: str
    ews_url: str

    @classmethod
    def from_env(cls, env):
        return cls(
            storage=env["AzureWebJobsStorage"],
            dce_endpoint=env["DCE_ENDPOINT"],
            dcr_rule_id=env["DCR_RULE_ID"],
            dcr_stream_name=env["DCR_STREAM_NAME"],
            ews_url=env["EWS_URL"],
        )


@cache
def load_config():
    """Load config from environment."""
    return Config.from_env(os.environ)


def load_token(state: StateManager) -> Optional[str]:
    """Load token from storage."""
    token = state.get()
    logger.debug(f"Loaded {token=}")
    return token


def save_token(state: StateManager, token: Optional[str]) -> None:
    """Save token into storage."""
    if token is None:
        return

    state.post(token)
    logger.debug(f"Saved {token=}")


@dataclass
class Field:
    name: str
    convert: Callable[[Any], Any] = lambda x: x


def default_convert(value: Any) -> Any:
    if isinstance(value, (list, dict, str, int, float, bool)) or value is None:
        return value

    if isinstance(value, (set, tuple)):
        return list(value)

    return str(value)


def _build_ts(v):
    """Convert timestamp to a format recognized by sentinel."""
    try:
        dt = isoparse(v)
    except (ValueError, TypeError):
        return None
    else:
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# Event fields that need explicit conversion into records
event_fields = {
    "observation time": Field("observation_time", _build_ts),
    "source time": Field("source_time", _build_ts),
    "first seen": Field("first_seen", _build_ts),
    "asn": Field("asn", int),
    "latitude": Field("latitude", float),
    "longitude": Field("longitude", float),
}


def map_events_to_records(events: Iterable[Mapping]) -> Iterable[Mapping]:
    """Map events into log analytics records."""
    return list(filter(None, (event_to_record(e) for e in events)))


def event_to_record(event: Mapping) -> Mapping:
    """Map one event into a log analytics record.

    Wraps all fields into RawData (dynamic) to match DCR stream declaration.
    """
    raw = dict(create_record(k, v) for k, v in event.items())
    return {
        "TimeGenerated": raw.get("observation_time", ""),
        "RawData": raw,
    }


def create_record(key, value):
    """Create record from key, value pair."""
    default_field = Field(key.replace(" ", "_"), convert=default_convert)
    field = event_fields.get(key, default_field)

    try:
        v = field.convert(value)
    except Exception as e:
        logger.warning(f"Error converting {key=} {value=}: {e}")
        v = str(value)

    return field.name, v


@cache
def get_credential():
    return DefaultAzureCredential()


def insert_records(records: Iterable[Mapping], config: Config):
    """Insert records into log analytics."""
    post_data(
        config.dce_endpoint,
        config.dcr_rule_id,
        config.dcr_stream_name,
        get_credential(),
        records,
    )


@cache
def get_state(connection_str):
    return StateManager(connection_str)


def main(mytimer: func.TimerRequest) -> None:
    """Azure function entry point."""
    # Configure logging (TODO: make this work)
    # https://learn.microsoft.com/en-us/azure/developer/python/sdk/azure-sdk-logging
    logging.getLogger().setLevel(logging.DEBUG)

    if mytimer.past_due:
        logger.info("The timer is past due!")

    ts = time.monotonic()

    config = load_config()
    state = get_state(config.storage)
    token = load_token(state)

    more_available = True
    n = 0
    n_inserts = 0
    last_saved_token: Optional[str] = None

    while more_available:
        prev_token = token
        events, token, more_available = load_events(config.ews_url, token)

        # load_events failed: retry if data, otherwise stop
        if events is None:
            if more_available:
                continue
            break

        # Always save the "next poll" token when it changes
        # (paging => x-last-token, final => x-last-inserted-token)
        if token is not None and token != last_saved_token:
            save_token(state, token)
            last_saved_token = token

        # No events: don't ingest, but avoid infinite loop if token didn't advance
        if not events:
            if token == prev_token:
                logger.info(
                    "No events returned and token did not advance; stopping loop."
                )
                break
            continue

        records = map_events_to_records(events)
        insert_records(records, config)

        n_inserts += 1
        n += len(records)

    duration = time.monotonic() - ts
    logger.info(
        f"Inserted {n} records ({n_inserts}) in {duration:.1f}s, new token: {token}"
    )
