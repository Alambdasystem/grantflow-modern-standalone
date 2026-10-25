# Independent baseline build

Verified October 25, 2026, before readiness changes.

- Repository: https://github.com/Alambdasystem/grantflow-modern-standalone (private).
- Authenticated owner confirmed by GitHub connector and CLI: `Alambdasystem`. No account switch.
- Root baseline: `4054e692a4111cc283342a088a7da7468c1079d2`, branch `main`, no parent commits/history inherited.
- An independent remote clone of `main` was clean before/after build.
- `docker compose config --quiet`: PASS.
- Backend image: `gfm-fresh-main-backend:4054e69`, observed image ID `sha256:957e375d5279c467171094c58529ae219880a17325a00bfd0b49d3e5eb57d9c5`.
- Frontend image: `gfm-fresh-main-frontend:4054e69`, observed image ID `sha256:5ea897c38cf85e80073a9192b362804d5124e9320bd618ccfae7e73fdfd1a547`.
- Frontend compilation, type checking and route generation passed.

These were independent image builds using unique tags, not service replacements. All COPY inputs came from the clone; package, browser and font downloads used internet access. No original environment/database/account store, private evidence or model cache was needed to build. Baseline build success does not claim byte-for-byte rebuilds of floating base/transitive/OS downloads; readiness work records/pins those inputs separately.

The official Gitleaks v8.30.1 Windows archive was checksum verified. The staged baseline secret scan passed with redacted reporting. Private audit/runtime files and production-targeted inspection/launch scripts were excluded; documentation images were recaptured from synthetic lab records. Original project remotes, accounts and services were not changed.
