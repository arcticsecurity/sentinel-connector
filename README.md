# Sentinel connector

## Introduction

Repository for everything related to the Arctic Security Microsoft Sentinel
connector.

The connector is an Azure Function App that polls the Arctic Security Early
Warning Service (EWS) "Customer Matched Data" API and ingests the events into a
Microsoft Sentinel (Log Analytics) workspace using the Azure Monitor Logs
Ingestion API.

The connector package is published as a GitHub release asset of this repository,
and the deployment template is versioned with the release tag. Customers deploy
the template into their own Azure subscription and point it at a published
package. The connector is currently marked as preview.

## Contents

- `Data Connectors/ArcticSecurityEwsConnector/`
    - Function App for the connector (`host.json`, `requirements.txt`)
    - `ArcticSecurityEwsConnector/` — the timer triggered function itself
    - `ArcticSecurityEwsConnector_API_FunctionApp.json` — Sentinel data
      connector definition (UI metadata, not used by the current deployment
      method)
    - `README.md` — connector specific notes
- `Analytic Rules/Arctic_Security_EWS_Analytics_Rules.json`
    - Four scheduled analytics rules (shared resource, high, medium, low)
- `Workbooks/Arctic_EWS_Workbook.workbook`
    - Sentinel workbook for visualizing the ingested data
- [`deployment_template.json`](https://github.com/arcticsecurity/sentinel-connector/blob/main/deployment_template.json)
    - ARM template that deploys all required Azure resources
- `create_connector_zip.sh`
    - Builds the deployable Function App ZIP package
- `bump_version.sh`
    - Sets the release version and keeps the documentation in step with it
- `VERSION`
    - Release version; changing it triggers a release from CI
- `LICENSE`
    - MIT license
- `SECURITY.md`
    - How to report security issues

## How it works

- The function runs on a timer trigger, once per minute
  (`ArcticSecurityEwsConnector/function.json`).
- On each run it reads a paging token from Azure Files and requests events from
  the EWS API. On the first run, when no token exists, it starts from 7 days
  back.
- Paging follows the API response headers: while `x-next-token` is present the
  run continues with `x-last-token`, and the final page stores
  `x-last-inserted-token` as the starting point for the next run.
- The token is stored in the Function App's own storage account, in the file
  share `funcstatemarkershare`, file `funcstatemarkerfile`. Deleting that file
  makes the next run start from 7 days back again.
- If the API rejects the stored token as invalid, the connector resets the token
  and retries.
- Each event is converted into a record of the form
  `{"TimeGenerated": ..., "RawData": {...}}`. Timestamps are normalized, `asn`
  is converted to an integer, `latitude` and `longitude` to floats, and spaces
  in field names are replaced with underscores.
- Records are uploaded with the Logs Ingestion API to the data collection
  endpoint. The data collection rule then projects the most relevant fields out
  of `RawData` into named columns of the `ArcticSecurityEws_CL` table.
- Authentication to Azure uses the Function App's system assigned managed
  identity, which must hold the **Monitoring Metrics Publisher** role on the
  data collection rule.

## Deployment

### What the template creates

`deployment_template.json` deploys, into the selected resource group:

- a storage account for the Function App (also used for the paging token)
- a data collection endpoint (`<function name>-dce`)
- the custom table `ArcticSecurityEws_CL` in the workspace (30 day retention,
  Analytics plan)
- a data collection rule (`<function name>-dcr`, `kind: Direct`) with the stream
  `Custom-ArcticSecurityEws_CL` and the KQL transformation that populates the
  table columns
- a Linux Function App (`python|3.12`) with a system assigned managed identity,
  running the connector from the package URL
  (`WEBSITE_RUN_FROM_PACKAGE`)
- optionally, the **Monitoring Metrics Publisher** role assignment on the data
  collection rule for the Function App identity

### Prerequisites

- An Azure subscription with a Log Analytics workspace that has Microsoft
  Sentinel enabled.
- The workspace can be in any resource group or subscription. The template
  creates the custom table in the workspace itself, so you also need permissions
  to create resources in the resource group that holds the workspace.
- Permissions to create resources in that resource group. Assigning the role
  automatically additionally requires **Owner** or **User Access
  Administrator**; without those permissions, deploy with
  `AssignDcrRoleToFunctionIdentity` set to `false` and assign the role manually.
- The EWS "Customer Matched Data" API URL, including its `apikey` query
  parameter.
- Note that running the Function App and ingesting the data are billable Azure
  services.

### Step 1 — Get the EWS API URL

1. Log in to the Arctic EWS portal.
2. Go to the **Configuration** tab and enable the **Customer Matched Data** API
   if it is not already enabled.
3. Use the link icon next to the activation switch to copy the API URL.

The URL contains an API key and must be treated as a secret.

### Step 2 — Get the package URL

The connector package is published as a release asset of this repository. Use a
version specific URL so that the deployed code does not change unexpectedly:

```
https://github.com/arcticsecurity/sentinel-connector/releases/download/v0.8.0/ArcticSecurityEwsConnector.zip
```

The URL is read by Azure anonymously when the Function App starts, so it has to
be publicly reachable.

### Step 3 — Deploy the template

The deployment template lives in this repository and is tagged with each
release. Use the tag that matches the package version from step 2, so that the
template and the deployed code belong together.

The simplest way is to let the portal load the template directly from the tag:

```
https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Farcticsecurity%2Fsentinel-connector%2Fv0.8.0%2Fdeployment_template.json
```

The URL is the raw address of `deployment_template.json` at the tag,
percent-encoded. Change the tag in it to deploy a different version.

The template can also be pasted in by hand:

1. Open
   [Deploy a custom template](https://portal.azure.com/#create/Microsoft.Template)
   in the Azure portal and select **Build your own template in the editor**.
2. Paste the contents of
   [`deployment_template.json`](https://github.com/arcticsecurity/sentinel-connector/blob/v0.8.0/deployment_template.json)
   at the matching tag into the editor and save.

Then, with either method:

3. Select the subscription, resource group and region for the connector
   resources. They do not have to be the same as the workspace; the data
   collection endpoint and rule are always created in the workspace region, as
   Azure Monitor requires.
4. Fill in the parameters and start the deployment.

### Parameters

| Parameter | Required | Description |
| --- | --- | --- |
| `FunctionName` | no | Name prefix for the created resources. Defaults to `EWSconnect`. A unique suffix is appended automatically. |
| `EwsUrl` | yes | The EWS Customer Matched Data API URL from step 1, including `apikey`. |
| `WorkspaceResourceId` | yes | Full resource ID of the Log Analytics workspace, `/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.OperationalInsights/workspaces/<workspace>`. See below for how to find it. |
| `PackageUrl` | yes | Public URL of the connector ZIP from step 2. |
| `AssignDcrRoleToFunctionIdentity` | no | Defaults to `true`. Set to `false` if you do not have permissions to create role assignments; the **Monitoring Metrics Publisher** role must then be granted manually on the data collection rule. |

#### Finding the workspace resource ID

`WorkspaceResourceId` is the full ARM path of the workspace, not the GUID
labelled **Workspace ID** on the workspace Overview page. That GUID identifies
the workspace to the older agent-based APIs and is not accepted here.

In the portal, open the Log Analytics workspace and either select **JSON View**
on the Overview page, or open **Settings > Properties** and copy **Resource ID**.
With the Azure CLI:

```sh
az monitor log-analytics workspace show \
    --resource-group RESOURCE-GROUP --name WORKSPACE-NAME --query id -o tsv
```

### Step 4 — Verify

Data should appear within several minutes of the deployment. In the workspace,
run:

```kusto
ArcticSecurityEws_CL
| sort by TimeGenerated desc
| take 10
```

Newly created resources and tables can take a few minutes to become visible in
the portal.

## Analytics rules and workbook

These are deployed separately, after the connector is in place.

- **Analytics rules**: deploy `Analytic Rules/Arctic_Security_EWS_Analytics_Rules.json`
  as a custom template. It takes a single `workspace` parameter, the name of the
  Log Analytics workspace. It creates four scheduled rules that run hourly and
  create incidents: *EWS Shared Resource* (informational), *EWS High*,
  *EWS Medium* and *EWS Low*.
- **Workbook**: in Sentinel, go to **Workbooks**, choose **Add workbook**, open
  the advanced editor and paste the contents of
  `Workbooks/Arctic_EWS_Workbook.workbook`, then save it.

## Data model

Events are ingested into the custom table `ArcticSecurityEws_CL`.

- `TimeGenerated` (datetime) — observation time of the event
- `RawData` (dynamic) — the complete event as received from the EWS API
- Extracted columns: `category`, `description`, `domain_name`, `event_type`,
  `ip`, `issue_description`, `issue_scope`, `issue_validation`,
  `malware_family`, `match_description`, `port`, `related_domain_name`,
  `reverse_dns`, `service`, `shared_resource`, `source_time`, `tracking_id`,
  `urgency`, `vulnerability`, `weakness`, `x509_subject_cn`

Fields that are not extracted into columns remain available inside `RawData`,
for example `RawData.confidence`. To extract more fields into columns, both the
table schema and the `transformKql` of the data collection rule in
`deployment_template.json` need to be updated.

## Application settings

The template configures these automatically. They are listed here for manual
deployments and troubleshooting.

| Setting | Description |
| --- | --- |
| `AzureWebJobsStorage` | Storage account connection string; also holds the paging token. |
| `DCE_ENDPOINT` | Logs ingestion endpoint of the data collection endpoint. |
| `DCR_RULE_ID` | Immutable ID of the data collection rule. |
| `DCR_STREAM_NAME` | Stream name, `Custom-ArcticSecurityEws_CL`. |
| `EWS_URL` | EWS API URL including `apikey`. |

`EWS_URL` is a secret. It can be stored in Azure Key Vault and referenced with
the `@Microsoft.KeyVault(SecretUri=...)` syntax instead of a plain value.

The connector authenticates to Azure with the managed identity of the Function
App, so no workspace keys are needed.

## Development

### Environment

- Python 3.12, as pinned in `.python-version`. This is also the runtime version
  of the Function App, and the last Python version available for Linux
  Consumption plan apps.
- `zip` is required for building the package.
- Development tooling is installed with `pip install -r requirements-dev.txt`.

### Checks

CI runs the same checks that can be run locally:

```sh
ruff check .
ruff format --check .
git ls-files '*.sh' | xargs shellcheck
git ls-files '*.yml' '*.yaml' | xargs yamllint -s \
    -d "{extends: default, rules: {line-length: disable}}"
./bump_version.sh --check
```

`./bump_version.sh --check` verifies that the release tags referenced in the
documentation match `VERSION`.

### Building the package

```sh
./create_connector_zip.sh [output-name.zip]
```

The script validates the contents of the function directory, installs the
dependencies of `requirements.txt` for Python 3.12 on linux/x86-64 into
`.python_packages/lib/site-packages`, and writes
`Data Connectors/ArcticSecurityEwsConnector/ArcticSecurityEwsConnector.zip`.
Set `PYTHON_BIN` if the Python 3.12 interpreter is not on the path as
`python3.12`.

The built ZIP is not committed to the repository; CI builds it on every run and
attaches it to the release.

### Running locally

Deployment from Visual Studio Code is supported for development. Create
`local.settings.json` with the application settings listed above, sign in with
`az login` so that `DefaultAzureCredential` can obtain a token, and make sure
that the identity has the **Monitoring Metrics Publisher** role on the data
collection rule.

## Releasing

1. Set the new version:

   ```sh
   ./bump_version.sh 0.4.0
   ```

   The script writes `VERSION` and updates the release tag references in the
   documentation, so that they stay in step with the version being released.
2. Commit the changes and merge them to `main`.

CI builds the package, and when the version does not yet have a matching tag it
creates the tag `v<version>` and a GitHub release with
`ArcticSecurityEwsConnector.zip` attached, with release notes generated from the
merged pull requests.

The tag also versions `deployment_template.json`, which is read from the
repository at the tag rather than attached to the release.

The package asset URL is what customers use as `PackageUrl`. Existing
deployments are not updated automatically; upgrading means updating the
`PackageUrl` application setting of the Function App and restarting it. If the
template changed between versions, the deployment has to be run again with the
new template instead.

## Troubleshooting

- **No data in the workspace.** Check the Function App logs in Application
  Insights. Verify `EWS_URL`, and that the API is enabled in the EWS portal.
- **Upload failures or 403 errors.** The managed identity is most likely missing
  the **Monitoring Metrics Publisher** role on the data collection rule.
- **The table does not appear.** New resources can take several minutes to show
  up. If it is not on the workspace main page, check **All resources**.
- **Re-ingesting data.** Deleting `funcstatemarkerfile` from the
  `funcstatemarkershare` file share in the Function App storage account makes
  the connector start again from 7 days back.

## Notes

- The custom table is created with 30 day retention; adjust it in the workspace
  if longer retention is needed.

## License

MIT, see [LICENSE](LICENSE).
