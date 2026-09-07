#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if (( EUID == 0 )); then
  echo 'Run this wrapper as your desktop user; it invokes sudo only for system files.' >&2
  exit 1
fi
if [[ " ${*} " != *' --uninstall '* ]]; then
  python3 tools/check_bindings.py "$@"
fi
sudo python3 tools/install.py --user "$(id -un)" "$@"
if [[ " ${*} " != *' --dry-run '* ]]; then
  hyprctl reload
  errors=$(hyprctl configerrors)
  if [[ -n ${errors//[[:space:]]/} ]]; then
    echo "$errors" >&2
    exit 1
  fi
fi
