#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/config.local.env" ]]; then
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/config.local.env"
fi
python3 "$SCRIPT_DIR/local-puller.py" "$@"
