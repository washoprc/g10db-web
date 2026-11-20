#!/usr/bin/env bash
# 旧 PHP ツリー (washoprc/g10db または docker-g10db の g10db/) から
# GroupList / TableList / Ha_coef / NL を取り込む。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LEGACY="${1:-}"

if [[ -z "$LEGACY" ]]; then
  echo "Usage: $0 /path/to/g10db" >&2
  echo "  expected: \$LEGACY/G10DB/{GroupList,TableList}.inf" >&2
  echo "            \$LEGACY/TekeTekeKun/{Ha_coef,NL}/" >&2
  exit 1
fi

G10DB="$LEGACY/G10DB"
TEKE="$LEGACY/TekeTekeKun"

if [[ ! -d "$G10DB" && -d "$LEGACY/g10db/G10DB" ]]; then
  G10DB="$LEGACY/g10db/G10DB"
  TEKE="$LEGACY/g10db/TekeTekeKun"
fi

mkdir -p "$ROOT/config/Ha_coef" "$ROOT/config/NL"

if [[ -f "$G10DB/GroupList.inf" || -f "$G10DB/TableList.inf" ]]; then
  inputs=()
  [[ -f "$G10DB/GroupList.inf" ]] && inputs+=("$G10DB/GroupList.inf")
  [[ -f "$G10DB/TableList.inf" ]] && inputs+=("$G10DB/TableList.inf")
  python3 "$ROOT/scripts/convertInf.py" "${inputs[@]}" -o "$ROOT/config"
fi

if [[ -d "$TEKE/Ha_coef" ]]; then
  rsync -a --delete --exclude 'README.md' "$TEKE/Ha_coef/" "$ROOT/config/Ha_coef/"
  echo "synced Ha_coef"
fi

if [[ -d "$TEKE/NL" ]]; then
  rsync -a --delete --exclude 'README.md' "$TEKE/NL/" "$ROOT/config/NL/"
  echo "synced NL"
fi

echo "done. review config/ and commit."
