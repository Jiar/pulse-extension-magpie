# Security and privacy

## Scope

This project is a local, read-only bridge from Magpie Allowances to Pulse. It starts on refresh and exits after producing one JSON line. It does not run a persistent server, collect telemetry, or upload account data.

The bridge accepts only HTTP URLs with a literal loopback IP address, an explicit port, and the exact `/v1/magpie/quotas` path. User information, query strings and fragments are rejected. System proxies and redirects are disabled. Requests time out after 8 seconds; input is limited to 2 MiB and output to 256 KiB including the newline. Oversized output produces a failure status rather than silently removing quota rows.

It does not read provider credentials, cookies, Keychain entries or API keys. Magpie remains responsible for authentication and fetching data from providers. The local HTTP API is trusted as the source of quota data; this project does not authenticate the process listening on the selected loopback port. Run only a Magpie instance you trust.

Provider switches filter what enters the Pulse report and average. The aggregate Magpie response still contains all accounts, and explicitly requesting `--details` shows hidden sources too. A visibility switch is not an access-control boundary. Account identifiers may appear in Pulse, terminal output and error messages supplied by Magpie.

Installed configuration and program files use owner-only permissions. The extension launcher runs Python in isolated mode. Install/update replaces files individually using temporary files; the entire directory update is not a multi-file transaction. If installation is interrupted, rerun the installer before refreshing Pulse.

## Reporting a vulnerability

Only the latest default-branch version is maintained. If the repository's **Security → Advisories → Report a vulnerability** option is available, use it for private reports:

https://github.com/Jiar/pulse-extension-magpie/security/advisories/new

If private reporting is unavailable, open a minimal issue asking the maintainer for a private channel. Do not publish exploit details, credentials or personal account data while arranging that channel. No response-time or remediation SLA is promised.

Include the affected commit, operating system and Python version, expected and observed behavior, and a minimal reproduction using fictional data. Ordinary installation or quota-mapping problems can be reported as public issues after removing personal data.

## Before sharing logs or images

Replace account names, email addresses, provider error text, balances, timestamps and local paths with invented examples. Never attach real `config.json`, raw endpoint responses, complete Pulse JSON reports, tokens or cookies. Repository demonstration images must be generated from the synthetic fixture rather than captured from personal accounts.
