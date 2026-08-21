# Arctic Security EWS Sentinel connector

Azure Function App that polls the Arctic Security EWS "Customer Matched Data"
API and ingests the events into a Microsoft Sentinel workspace with the Azure
Monitor Logs Ingestion API.

Deployment instructions, the data model and the release process are documented
in the [repository README](../../README.md).

- Connector type: REST API polling with an Azure Function
- Provider: `ArcticSecurity`
- Appliance: `Ews`

## Contents

- `ArcticSecurityEwsConnector/` — the function
    - `__init__.py` — timer trigger entry point, event to record mapping
    - `ews.py` — EWS API client, paging and token handling
    - `data_collector.py` — uploads records with the Logs Ingestion API
    - `state_manager.py` — stores the paging token in Azure Files
    - `function.json` — timer trigger binding
- `host.json` — Functions host configuration
- `requirements.txt` — runtime dependencies
- `.funcignore` — files excluded from Visual Studio Code deployments
- `ArcticSecurityEwsConnector_API_FunctionApp.json` — Sentinel data connector
  definition (UI metadata, not used by the current deployment method)

## Application settings

| Setting | Description |
| --- | --- |
| `AzureWebJobsStorage` | Storage account connection string; also holds the paging token. |
| `DCE_ENDPOINT` | Logs ingestion endpoint of the data collection endpoint. |
| `DCR_RULE_ID` | Immutable ID of the data collection rule. |
| `DCR_STREAM_NAME` | Stream name, `Custom-ArcticSecurityEws_CL`. |
| `EWS_URL` | EWS API URL including `apikey`. |

All of them are required; the function fails on startup if any is missing.
Authentication to Azure uses the Function App's managed identity, so no
workspace ID or key is needed.

## Event mapping

`map_events_to_records()` converts EWS events into records of the form
`{"TimeGenerated": ..., "RawData": {...}}`. Timestamps are normalized to the
format expected by Log Analytics, `asn` is converted to an integer, `latitude`
and `longitude` to floats, and spaces in field names are replaced with
underscores. The complete event stays available in the `RawData` column, and the
data collection rule projects selected fields into named columns.

Events are not normalized into
[ASIM](https://learn.microsoft.com/azure/sentinel/normalization) schemas.
