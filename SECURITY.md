# Security policy

## Reporting a vulnerability

Please report security issues in this connector to
[product-security@arcticsecurity.com](mailto:product-security@arcticsecurity.com) instead of
opening a public issue.

Include enough detail to reproduce the issue, such as the affected version, the
steps taken and the observed result. We will confirm the report and let you know
how we plan to address it.

## Supported versions

Fixes are released in the latest version. See the
[releases](https://github.com/arcticsecurity/sentinel-connector/releases) for
the available versions.

## Handling of credentials

The `EWS_URL` application setting contains an API key, and the deployment
template writes it into the Function App configuration. Do not include it in
issue reports, logs or pull requests. It can be stored in Azure Key Vault and
referenced from the application setting instead.
