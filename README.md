# Switch runtime diagnostic build

Standalone build integration and host tests for the public, MIT-licensed NaGaa95/genshinimpact_nx wrapper. This repository contains diagnostic patches and fixtures, not game files, APKs, proprietary libraries, credentials or private runtime logs. It does not include the development repository history.

## Reproducible inputs

The workflow pins upstream source to 6406b23c5a862b38dfa581facd93c5624a4a6c25, the devkitPro container by SHA-256, and the public Mesa SDK artifact with its SHA-256 verification. GitHub's ephemeral workflow token is used only to retrieve that public SDK. No private-repository access token is needed. SDK artifact expiry can require reviewed replacement of the pinned dependency.

Push or manually run Build standalone wrapper memory hub. The workflow reconstructs the wrapper, runs host ASan/UBSan fixtures, builds ARM64 and checks linked call paths. Successful runs retain the NRO, ELF and build evidence for seven days. Download the NRO from the workflow artifact; do not rename an older binary as a newer build. Compilation and host tests do not establish Switch compatibility or that the white-screen closure is fixed.

## Diagnostic scope

Fatal shims publish static reasons before best-effort tracing, restore registered calling-thread host TLS, and preserve host abort. Render probing is bounded but cannot interrupt an entered call. The observer and crash logs remain dependent on synchronous SD/stdio; missing records cannot identify a fault. No protection or authentication changes are implemented by this build integration.

## Licensing

The included MIT notice credits upstream contributors. Preserve existing notices when copying code. Upstream source is fetched at build time and retains its own notices. The integration additions are made available under the same MIT terms. Third-party SDK components retain their respective licenses. No rights to proprietary game content are conveyed.
