# Security policy

Report vulnerabilities privately through GitHub's private vulnerability reporting for this repository. Do not put
credentials, personal data or exploit details in a public issue.

## Scope

- The project simulates trading on public market data. It has no order, wallet or exchange-key code.
- Secrets (the Cloudflare deploy token) live outside the repository, in the operator's home directory, and are never
  committed or printed. CI scans the history for common credential patterns.
- In scope: secret exposure, code execution through data or dependencies, unsafe CI workflows, and anything that
  could make the published pages show data that is not the system's own.
