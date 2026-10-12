# Security and credentials

Model credentials are read only from environment variables named in a model configuration. Do not place API tokens in configuration files, shell history, issue reports, run artifacts, or commits.

Use an interactive hidden prompt when practical:

```bash
read -s "P2SF_API_TOKEN?API token: "
export P2SF_API_TOKEN
echo
```

M5 uses a host-side proxy so the upstream credential is not mounted into the agent container. Before publishing a new run, search its artifacts for authorization headers and secrets and rotate any credential that may have been exposed.

