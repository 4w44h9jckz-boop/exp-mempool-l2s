#!/usr/bin/env bash
# Every tracked text file this repository wrote is ASCII only. LICENSE is exempt.
#
# Reads `git ls-files`, so run it after `git add`: an untracked file is invisible to it.

set -euo pipefail
cd "$(dirname "$0")/.."

status=0
while IFS= read -r -d '' file; do
  case "$file" in
    LICENSE) continue ;;
  esac
  if LC_ALL=C grep -n -P '[^\x00-\x7F]' "$file" >/dev/null 2>&1; then
    echo "non-ASCII characters in $file:"
    LC_ALL=C grep -n -P '[^\x00-\x7F]' "$file" | head -5
    status=1
  fi
done < <(git ls-files -z -- '*.md' '*.py' '*.json' '*.sh' '*.yml' '*.txt' 'Makefile')

if [ "$status" -eq 0 ]; then
  echo "ascii: ok"
fi
exit "$status"
