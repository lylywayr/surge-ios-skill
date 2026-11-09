#!/bin/sh
# Sync Surge's bundled official skill docs from a Mac (Surge.app installed).
#   sync_upstream.sh <host>          fetch + show diff, changes nothing  (SSH alias of a Mac with Surge)
#   sync_upstream.sh <host> --apply  also replace references/command-reference.md
#                                    (upstream text, with §1.1 swapped for the Minis note below)
# Upstream SKILL.md is never applied automatically: read it and merge relevant changes by hand.
set -eu
HOST=; APPLY=0
for a in "$@"; do case "$a" in --apply) APPLY=1;; *) HOST="$a";; esac; done
[ -n "$HOST" ] || { echo "usage: $0 <ssh-host> [--apply]" >&2; exit 2; }
SRC=/Applications/Surge.app/Contents/Resources/Skills/surge
SKILL="$(cd "$(dirname "$0")/.." && pwd)"
OUT=/tmp/surge-upstream
rm -rf "$OUT"; mkdir -p "$OUT"
scp -q -o BatchMode=yes -o ConnectTimeout=10 "$HOST:$SRC/SKILL.md" "$HOST:$SRC/references/command-reference.md" "$OUT/"
ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST" /Applications/Surge.app/Contents/Applications/surge-cli version | head -1 > "$OUT/VERSION"
python3 - "$OUT/command-reference.md" "$OUT/adapted.md" <<'PY'
import sys
t=open(sys.argv[1]).read()
s=t.index("### 1.1 Basic format"); e=t.index("### 1.2 Response envelope",s)
note='''### 1.1 Basic format (Minis)

> Synced from the Surge-bundled skill; only this subsection is Minis-specific.
> `/usr/local/bin/surge-cli` is a Python client talking to the Surge iOS External Controller.

```bash
surge-cli [--remote host:port] [--password-stdin] [--raw] <command> [args...]
```

- Default controller `127.0.0.1:6170`. Password from `--password-stdin` or `SURGE_CLI_PASSWORD`; never in argv.
- Prefer `--raw` for exact controller JSON; human formatting exists only for common commands. Unknown commands are passed through to the controller.
- `--check <path>` uploads that file to Surge's online validator (`services.nssurge.com`); there is no local parser in iSH. Redact secrets first; never upload the active profile implicitly.
- `lsp`, interactive mode, `plugin validate|pack` are macOS-only and not available here.

'''
open(sys.argv[2],'w').write(t[:s]+note+t[e:])
PY
diff -u "$SKILL/references/command-reference.md" "$OUT/adapted.md" > "$OUT/command-reference.diff" || true
echo "upstream: $(cat "$OUT/VERSION")  dir: $OUT"
echo "command-reference.md: $(grep -c '^[+-][^+-]' "$OUT/command-reference.diff" || true) changed lines (see command-reference.diff)"
if [ "$APPLY" = 1 ]; then
  cp "$OUT/adapted.md" "$SKILL/references/command-reference.md"
  printf '%s, synced %s\n' "$(cat "$OUT/VERSION")" "$(date +%F)" > "$SKILL/references/UPSTREAM_VERSION"
  echo "applied command-reference.md"
fi
echo "SKILL.md: diff against previous upstream is not kept; read $OUT/SKILL.md for new workflows"
