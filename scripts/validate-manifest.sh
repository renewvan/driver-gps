#!/usr/bin/env bash
# Validates manifest.json against the hub's node-manifest schema.
#   scripts/validate-manifest.sh <schema.json> [manifest.json]
# CI fetches the schema from renewvan/hub at the ref pinned in
# .github/workflows/test.yml. The schema forbids `version` and `host_serial`
# (both are stamped at runtime), so a hand-edited version fails here.
set -euo pipefail

schema="${1:?usage: validate-manifest.sh <schema.json> [manifest.json]}"
manifest="${2:-$(dirname "$0")/../manifest.json}"

npx --yes ajv-cli@5 validate -s "$schema" -d "$manifest" --strict=false
