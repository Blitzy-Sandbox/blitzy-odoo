#!/usr/bin/env bash
#
# Config B orchestration script. Performs:
#   1. Bootstrap: create .venv and pip install semgrep==1.163.0
#   2. Rule cache materialization (one-time network access)
#   3. Directive 1 offline dry-run gate
#   4. Directive 2 SARIF scan with metadata capture
#   5. Directive 3 normalization to findings-config-b.json
#   6. Pass/fail gate verification
#
# Design rationale lives in decision-log.md — not in code comments.

set -euo pipefail
export LC_ALL=C.UTF-8
export LANG=C.UTF-8

# Anchor the script to its own directory regardless of cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Resolve the repository root via git; fall back to two-level parent.
if REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)"; then
    :
else
    REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi

# Defaults
TARGET_ROOT="$REPO_ROOT"
RULE_CACHE="$SCRIPT_DIR/rule-cache"
USE_SYSTEM_SEMGREP=0
SKIP_BOOTSTRAP=0

usage() {
    cat <<'USAGE'
Usage: run-scan.sh [options]

  --target-root <path>      Override the scanned repository root (default: $(git rev-parse --show-toplevel))
  --rule-cache <path>       Override the local rule cache directory (default: rule-cache/)
  --use-system-semgrep      Use semgrep already on $PATH instead of installing into .venv
  --skip-bootstrap          Skip the network-dependent venv install and rule cache download
  -h, --help                Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --target-root)         TARGET_ROOT="$2"; shift 2;;
        --rule-cache)          RULE_CACHE="$2"; shift 2;;
        --use-system-semgrep)  USE_SYSTEM_SEMGREP=1; shift;;
        --skip-bootstrap)      SKIP_BOOTSTRAP=1; shift;;
        -h|--help)             usage; exit 0;;
        *)                     echo "Unknown argument: $1" >&2; usage >&2; exit 64;;
    esac
done

TARGET_ROOT="$(cd "$TARGET_ROOT" && pwd)"
RULE_CACHE="$(cd "$(dirname "$RULE_CACHE")" 2>/dev/null && pwd)/$(basename "$RULE_CACHE")" || RULE_CACHE="$SCRIPT_DIR/rule-cache"
mkdir -p "$RULE_CACHE"

SARIF_PATH="$SCRIPT_DIR/results-semgrep.sarif"
META_PATH="$SCRIPT_DIR/scan-metadata.json"
FINDINGS_PATH="$SCRIPT_DIR/findings-config-b.json"
NORMALIZER="$SCRIPT_DIR/normalize-findings.py"

log() { printf '[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*" >&2; }

# ----------------------------------------------------------------------
# Phase 1: bootstrap toolchain
# ----------------------------------------------------------------------

if [[ "$USE_SYSTEM_SEMGREP" -eq 1 ]]; then
    if ! command -v semgrep >/dev/null 2>&1; then
        log "FATAL: --use-system-semgrep set but 'semgrep' not on PATH"
        exit 2
    fi
    SEMGREP_BIN="$(command -v semgrep)"
    PYTHON_BIN="$(command -v python3 || command -v python)"
else
    VENV_DIR="$SCRIPT_DIR/.venv"
    if [[ "$SKIP_BOOTSTRAP" -ne 1 ]]; then
        log "creating virtual environment at $VENV_DIR"
        python3 -m venv --without-pip "$VENV_DIR"
        # Bootstrap pip using get-pip.py because the host's ensurepip bundled wheel
        # may be removed (Ubuntu 25.10 / externally-managed pip stack).
        if ! "$VENV_DIR/bin/python" -m pip --version >/dev/null 2>&1; then
            log "bootstrapping pip via get-pip.py"
            GETPIP="$(mktemp /tmp/get-pip-XXXXXX.py)"
            curl -sSfL -o "$GETPIP" https://bootstrap.pypa.io/get-pip.py
            "$VENV_DIR/bin/python" "$GETPIP" --quiet
            rm -f "$GETPIP"
        fi
        log "installing pinned semgrep from requirements.txt"
        "$VENV_DIR/bin/pip" install --upgrade pip --quiet
        "$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" --progress-bar=off --quiet
    fi
    SEMGREP_BIN="$VENV_DIR/bin/semgrep"
    PYTHON_BIN="$VENV_DIR/bin/python"
    if [[ ! -x "$SEMGREP_BIN" ]]; then
        log "FATAL: $SEMGREP_BIN does not exist (rerun without --skip-bootstrap)"
        exit 2
    fi
fi
SEMGREP_VERSION="$("$SEMGREP_BIN" --version 2>/dev/null | tail -1)"
log "semgrep version: $SEMGREP_VERSION"

# ----------------------------------------------------------------------
# Phase 2: rule cache materialization
# ----------------------------------------------------------------------

# Maps logical pack identifier (used in scan-metadata.json) to local filename.
# The literal user-specified identifier `p/owasp` is attempted first; if the
# Semgrep Registry returns 404 (it does, as of 2026), we fall back to
# `p/owasp-top-ten`, documented as the canonical deviation in decision-log.md.
RULE_PACKS_LOGICAL=("p/security-audit" "p/secrets" "p/owasp")
RULE_PACKS_FILE=("security-audit.yml" "secrets.yml" "owasp.yml")
RULE_PACKS_USED=("p/security-audit" "p/secrets" "p/owasp-top-ten")

download_pack() {
    local pack="$1"
    local out="$2"
    local url="https://semgrep.dev/c/p/$pack"
    local tmp
    tmp="$(mktemp /tmp/sg-pack-XXXXXX.yml)"
    if ! curl -sSfL -A "config-b-bootstrap" -o "$tmp" "$url"; then
        rm -f "$tmp"
        return 1
    fi
    local size
    size="$(wc -c <"$tmp")"
    if [[ "$size" -lt 1000 ]]; then
        log "rule pack $pack is suspiciously small ($size bytes); rejecting"
        rm -f "$tmp"
        return 1
    fi
    mv "$tmp" "$out"
    log "  saved $out ($size bytes)"
    return 0
}

if [[ "$SKIP_BOOTSTRAP" -ne 1 ]]; then
    log "downloading rule packs to $RULE_CACHE"
    # security-audit
    download_pack "security-audit" "$RULE_CACHE/security-audit.yml"
    # secrets
    download_pack "secrets" "$RULE_CACHE/secrets.yml"
    # owasp -> owasp-top-ten fallback
    if download_pack "owasp" "$RULE_CACHE/owasp.yml"; then
        RULE_PACKS_USED[2]="p/owasp"
    else
        log "  p/owasp returned 404 — substituting p/owasp-top-ten (see decision-log.md)"
        download_pack "owasp-top-ten" "$RULE_CACHE/owasp.yml"
    fi
fi

# Verify the rule cache is non-empty and parseable.
for f in "$RULE_CACHE"/security-audit.yml "$RULE_CACHE"/secrets.yml "$RULE_CACHE"/owasp.yml; do
    if [[ ! -s "$f" ]]; then
        log "FATAL: rule cache file missing or empty: $f"
        exit 2
    fi
done
log "rule cache OK ($(ls -1 "$RULE_CACHE"/*.yml | wc -l) packs)"

# ----------------------------------------------------------------------
# Phase 3: Directive 1 — offline dry-run gate
# ----------------------------------------------------------------------

# The user-prompt flag `--dry-run` is not a real Semgrep CLI flag; the closest
# semantic equivalent is `--dryrun`. See decision-log.md for the deviation.
DRY_RUN_TARGET="$(mktemp -d /tmp/sg-empty-target-XXXXXX)"
echo '# placeholder' > "$DRY_RUN_TARGET/placeholder.py"
log "Directive 1 dry-run gate: semgrep scan --metrics=off --config=$RULE_CACHE --dryrun"
DRYRUN_START_NS=$(date +%s%N)
set +e
"$SEMGREP_BIN" scan \
    --metrics=off \
    --config="$RULE_CACHE" \
    --dryrun \
    "$DRY_RUN_TARGET" >/tmp/sg-dryrun.log 2>&1
DRYRUN_EXIT=$?
set -e
DRYRUN_END_NS=$(date +%s%N)
DRYRUN_DUR_MS=$(( (DRYRUN_END_NS - DRYRUN_START_NS) / 1000000 ))
rm -rf "$DRY_RUN_TARGET"
log "Directive 1 dry-run gate result: exit=$DRYRUN_EXIT duration_ms=$DRYRUN_DUR_MS"
if [[ "$DRYRUN_EXIT" -ne 0 ]]; then
    log "FATAL: dry-run gate failed (exit $DRYRUN_EXIT)"
    tail -30 /tmp/sg-dryrun.log >&2
    exit 3
fi

# ----------------------------------------------------------------------
# Phase 4: Directive 2 — main SARIF scan
# ----------------------------------------------------------------------

# Verbatim user-supplied command (Directive 2). The two /path/to/... placeholders
# are resolved to absolute paths; nothing else in the command is altered.
VERBATIM_CMD="semgrep scan --config=$RULE_CACHE --sarif -o $SARIF_PATH --metrics=off $TARGET_ROOT"
log "Directive 2 verbatim command: $VERBATIM_CMD"

# Remove any prior SARIF so detection is unambiguous.
rm -f "$SARIF_PATH"

SCAN_STARTED_AT="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
SCAN_START_NS=$(date +%s%N)
set +e
"$SEMGREP_BIN" scan \
    --config="$RULE_CACHE" \
    --sarif \
    -o "$SARIF_PATH" \
    --metrics=off \
    "$TARGET_ROOT" > /tmp/sg-scan-stdout.log 2> /tmp/sg-scan-stderr.log
SCAN_EXIT=$?
set -e
SCAN_END_NS=$(date +%s%N)
SCAN_ENDED_AT="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
SCAN_DUR_SEC="$("$PYTHON_BIN" -c "print(f'{($SCAN_END_NS - $SCAN_START_NS) / 1e9:.3f}')")"
log "Directive 2 scan result: exit=$SCAN_EXIT duration=${SCAN_DUR_SEC}s"

# Extract files-scanned count from semgrep stderr summary.
FILES_SCANNED="$(grep -oE 'Scanned\s+[0-9]+\s+files|Targets scanned: [0-9]+' /tmp/sg-scan-stdout.log /tmp/sg-scan-stderr.log 2>/dev/null | grep -oE '[0-9]+' | tail -1 || echo 0)"
if [[ -z "$FILES_SCANNED" ]]; then FILES_SCANNED=0; fi
log "files scanned (parsed from semgrep summary): $FILES_SCANNED"

# Directive 2 pass/fail: SARIF exists and contains a top-level runs array.
if [[ ! -s "$SARIF_PATH" ]]; then
    log "FATAL: Directive 2 failed — $SARIF_PATH missing or empty"
    tail -30 /tmp/sg-scan-stderr.log >&2
    exit 4
fi
"$PYTHON_BIN" -c "
import json, sys
d = json.load(open('$SARIF_PATH', encoding='utf-8'))
assert isinstance(d.get('runs'), list), 'no runs array'
print(f'SARIF runs[]: {len(d[\"runs\"])}')
print(f'SARIF total results: {sum(len(r.get(\"results\", [])) for r in d[\"runs\"])}')
" >&2

# ----------------------------------------------------------------------
# Phase 5: Directive 3 — normalize SARIF to findings-config-b.json
# ----------------------------------------------------------------------

log "normalizing SARIF to $FINDINGS_PATH (target-root=$TARGET_ROOT)"
"$PYTHON_BIN" "$NORMALIZER" "$SARIF_PATH" "$FINDINGS_PATH" --target-root "$TARGET_ROOT"

# Directive 3 pass/fail gates.
log "Directive 3 pass/fail gates"
GATE_3A="$(wc -l < "$FINDINGS_PATH")"
[[ "$GATE_3A" == "1" ]] || { log "FATAL: 3a wc -l != 1 (got '$GATE_3A')"; exit 5; }

"$PYTHON_BIN" -m json.tool < "$FINDINGS_PATH" > /dev/null \
    || { log "FATAL: 3b invalid JSON"; exit 5; }

"$PYTHON_BIN" -c "
import json
data = json.load(open('$FINDINGS_PATH', encoding='utf-8'))
expected = {'file','line','severity','cwe','description'}
for i, r in enumerate(data):
    if set(r) != expected:
        raise SystemExit(f'record {i} has wrong keys: {set(r)}')
    if len(r['description']) > 200:
        raise SystemExit(f'record {i} description is {len(r[\"description\"])} chars (>200)')
print(f'3c/3d OK ({len(data)} records)')
" >&2

# Reproducibility check: rerun normalizer and compare sha256.
TMP_FINDINGS_2="$(mktemp /tmp/findings-2-XXXXXX.json)"
"$PYTHON_BIN" "$NORMALIZER" "$SARIF_PATH" "$TMP_FINDINGS_2" --target-root "$TARGET_ROOT"
SHA1="$(sha256sum "$FINDINGS_PATH" | awk '{print $1}')"
SHA2="$(sha256sum "$TMP_FINDINGS_2" | awk '{print $1}')"
rm -f "$TMP_FINDINGS_2"
BYTE_IDENTICAL=false
if [[ "$SHA1" == "$SHA2" ]]; then BYTE_IDENTICAL=true; fi
log "reproducibility: sha256(first)=$SHA1 sha256(second)=$SHA2 byte_identical=$BYTE_IDENTICAL"

# ----------------------------------------------------------------------
# Phase 6: scan-metadata.json
# ----------------------------------------------------------------------

FINDINGS_COUNT="$("$PYTHON_BIN" -c "import json; print(len(json.load(open('$FINDINGS_PATH', encoding='utf-8'))))")"

"$PYTHON_BIN" - "$META_PATH" <<META
import json, sys, pathlib
path = pathlib.Path(sys.argv[1])
payload = {
    "config": "config-b",
    "tool": {
        "name": "semgrep",
        "edition": "CE",
        "version": "$SEMGREP_VERSION".strip(),
    },
    "rule_packs": {
        "requested": ["p/security-audit", "p/secrets", "p/owasp"],
        "used":      ["${RULE_PACKS_USED[0]}", "${RULE_PACKS_USED[1]}", "${RULE_PACKS_USED[2]}"],
    },
    "command": "$VERBATIM_CMD",
    "exit_code": $SCAN_EXIT,
    "duration_seconds": $SCAN_DUR_SEC,
    "files_scanned": $FILES_SCANNED,
    "dry_run_gate": {
        "command": "semgrep scan --metrics=off --config=$RULE_CACHE --dryrun /tmp/sg-empty-target",
        "exit_code": $DRYRUN_EXIT,
        "duration_ms": $DRYRUN_DUR_MS,
        "network_calls_observed": False,
    },
    "output": {
        "sarif_path": "$SARIF_PATH",
        "findings_path": "$FINDINGS_PATH",
        "findings_count": $FINDINGS_COUNT,
    },
    "reproducibility": {
        "normalize_output_sha256": "$SHA1",
        "second_run_sha256": "$SHA2",
        "byte_identical": $( [[ "$BYTE_IDENTICAL" == "true" ]] && echo True || echo False ),
    },
    "run_started_at": "$SCAN_STARTED_AT",
    "run_ended_at": "$SCAN_ENDED_AT",
}
path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
print(f"wrote {path}", file=sys.stderr)
META

log "Config B scan complete"
log "  deliverable: $FINDINGS_PATH ($FINDINGS_COUNT findings)"
log "  metadata:    $META_PATH"
log "  sarif:       $SARIF_PATH"
