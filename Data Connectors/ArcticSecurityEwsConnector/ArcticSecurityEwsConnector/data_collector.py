"""
Communicate with the Log Ingestion API

https://learn.microsoft.com/en-us/azure/azure-monitor/logs/logs-ingestion-api-overview
"""

import logging
from typing import Iterable, Mapping

from azure.core.exceptions import HttpResponseError
from azure.monitor.ingestion import LogsIngestionClient

logger = logging.getLogger(__name__)


def post_data(
    endpoint: str,
    rule_id: str,
    stream_name: str,
    credential,
    records: Iterable[Mapping],
):
    """
    Post data to log analytics via the Log Ingestion API.
    """
    logger.info(f"Post {len(records)} records via Log Ingestion API")

    failed_logs = []

    def on_error(error):
        logger.warning(f"Log chunk failed to upload: {error.error}")
        failed_logs.extend(error.failed_logs)

    client = LogsIngestionClient(endpoint=endpoint, credential=credential)
    try:
        client.upload(
            rule_id=rule_id,
            stream_name=stream_name,
            logs=records,
            on_error=on_error,
        )
    except HttpResponseError as e:
        logger.error(f"Upload failed: {e}")
        return

    if failed_logs:
        logger.warning(f"{len(failed_logs)} log entries failed to upload")
    else:
        logger.info(f"Posted {len(records)} records successfully")
