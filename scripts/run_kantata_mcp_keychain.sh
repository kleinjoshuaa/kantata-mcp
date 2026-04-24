#!/usr/bin/env bash
# Load Kantata access token from macOS Keychain, then start kantata-mcp (stdio).
# See README → "MCP server" → macOS Keychain wrapper.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MCP_BIN="${KANTATA_MCP_PATH:-$REPO_ROOT/.venv/bin/kantata-mcp}"
SERVICE="${KANTATA_KEYCHAIN_SERVICE:-kantata-mcp-access-token}"

if [[ ! -x "$MCP_BIN" ]]; then
  echo "kantata-mcp not found or not executable: $MCP_BIN" >&2
  echo "Set KANTATA_MCP_PATH to your .venv/bin/kantata-mcp" >&2
  exit 1
fi

if [[ -z "${KANTATA_ACCESS_TOKEN:-}" ]]; then
  if ! KANTATA_ACCESS_TOKEN="$(security find-generic-password -a "$USER" -s "$SERVICE" -w 2>/dev/null)"; then
    echo "Could not read Keychain item (-a $USER -s $SERVICE). Create it with:" >&2
    echo "  security add-generic-password -U -a \"$USER\" -s \"$SERVICE\" -w" >&2
    echo "(paste token at Password prompt; omit -w to be prompted securely)" >&2
    exit 1
  fi
  export KANTATA_ACCESS_TOKEN
fi

exec "$MCP_BIN" "$@"
