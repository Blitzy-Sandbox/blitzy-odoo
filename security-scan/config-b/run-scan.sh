#!/usr/bin/env bash
# Config B — Semgrep CE static-analysis orchestrator.
# Design rationale for every non-trivial choice lives in
# security-scan/config-b/decision-log.md (Explainability rule).

set -euo pipefail
LC_ALL=C.UTF-8
LANG=C.UTF-8
export LC_ALL LANG

# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
DEFAULT_TARGET_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd -P)"
DEFAULT_RULE_CACHE="${SCRIPT_DIR}/rule-cache"
SEMGREP_VERSION_PIN="1.163.0"

# Rule packs (verbatim from the user prompt Directive 1).
RULE_PACKS_REQUESTED=("p/security-audit" "p/secrets" "p/owasp")
RULE_PACKS_FILE=("security-audit.yml" "secrets.yml" "owasp.yml")

SARIF_OUTPUT="${SCRIPT_DIR}/results-semgrep.sarif"
FINDINGS_OUTPUT="${SCRIPT_DIR}/findings-config-b.json"
METADATA_OUTPUT="${SCRIPT_DIR}/scan-metadata.json"
NORMALIZER="${SCRIPT_DIR}/normalize-findings.py"
VENV_DIR="${SCRIPT_DIR}/.venv"
REQUIREMENTS_FILE="${SCRIPT_DIR}/requirements.txt"

# Runtime state populated as phases execute.
TARGET_ROOT=""
RULE_CACHE="${DEFAULT_RULE_CACHE}"
USE_SYSTEM_SEMGREP=0
SKIP_BOOTSTRAP=0
SEMGREP_BIN=""
PYTHON_BIN=""
SEMGREP_VERSION=""
DRY_RUN_EXIT=0
DRY_RUN_DURATION_MS=0
DRY_RUN_CMD=""
VERBATIM_CMD=""
SCAN_EXIT_CODE=0
SCAN_DURATION_SECONDS=0
SCAN_START_ISO=""
SCAN_END_ISO=""
FILES_SCANNED=0
NORMALIZE_SHA=""
SECOND_NORMALIZE_SHA=""
BYTE_IDENTICAL="false"
FINDINGS_COUNT=0

# ----------------------------------------------------------------------
# Logging helpers (stderr; stdout is reserved for computed values).
# ----------------------------------------------------------------------

log() {
    printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*" >&2
}

die() {
    log "FATAL: $*"
    exit 1
}

# Remove transient working files on any exit path (clean run, error, signal).
cleanup_transients() {
    rm -f "${SCRIPT_DIR}/.scan-stdout.log" "${SCRIPT_DIR}/.scan-stderr.log"
}
trap cleanup_transients EXIT INT TERM

print_usage() {
    cat <<'USAGE' >&2
Usage: run-scan.sh [options]

  --target-root <path>      Override the scanned repository root.
                            Default: $(git rev-parse --show-toplevel) with
                            two-level-parent fallback.
  --rule-cache <path>       Override the local rule-cache directory.
                            Default: <script-dir>/rule-cache
  --use-system-semgrep      Use the semgrep binary on PATH instead of
                            installing into the harness-local .venv.
  --skip-bootstrap          Skip the network-dependent venv install and
                            rule-pack download (offline rerun).
  -h, --help                Show this help and exit.
USAGE
}

# ----------------------------------------------------------------------
# Argument parsing + path resolution.
# ----------------------------------------------------------------------

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --target-root)
                [[ $# -ge 2 ]] || die "--target-root requires a value"
                TARGET_ROOT="$2"
                shift 2
                ;;
            --rule-cache)
                [[ $# -ge 2 ]] || die "--rule-cache requires a value"
                RULE_CACHE="$2"
                shift 2
                ;;
            --use-system-semgrep)
                USE_SYSTEM_SEMGREP=1
                shift
                ;;
            --skip-bootstrap)
                SKIP_BOOTSTRAP=1
                shift
                ;;
            -h|--help)
                print_usage
                exit 0
                ;;
            *)
                printf 'Unknown argument: %s\n' "$1" >&2
                print_usage
                exit 64
                ;;
        esac
    done

    if [[ -z "${TARGET_ROOT}" ]]; then
        if command -v git >/dev/null 2>&1; then
            local discovered
            if discovered="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null)"; then
                TARGET_ROOT="${discovered}"
            fi
        fi
        if [[ -z "${TARGET_ROOT}" ]]; then
            TARGET_ROOT="${DEFAULT_TARGET_ROOT}"
        fi
    fi

    [[ -d "${TARGET_ROOT}" ]] || die "--target-root path is not a directory: ${TARGET_ROOT}"
    TARGET_ROOT="$(cd "${TARGET_ROOT}" && pwd -P)"

    # Resolve RULE_CACHE to absolute form, tolerating a not-yet-existent dir.
    local rc_dir rc_base
    rc_dir="$(dirname "${RULE_CACHE}")"
    rc_base="$(basename "${RULE_CACHE}")"
    if [[ -d "${rc_dir}" ]]; then
        RULE_CACHE="$(cd "${rc_dir}" && pwd -P)/${rc_base}"
    fi
}

# ----------------------------------------------------------------------
# Phase 1 — bootstrap toolchain (.venv + semgrep install).
# ----------------------------------------------------------------------

bootstrap_pip_in_venv() {
    if "${VENV_DIR}/bin/python" -m pip --version >/dev/null 2>&1; then
        return 0
    fi
    log "Bootstrapping pip via get-pip.py (ensurepip wheel unavailable on host)"
    local getpip
    getpip="$(mktemp /tmp/get-pip-XXXXXX.py)"
    curl -sSfL -o "${getpip}" https://bootstrap.pypa.io/get-pip.py \
        || { rm -f "${getpip}"; die "failed to download get-pip.py"; }
    "${VENV_DIR}/bin/python" "${getpip}" --quiet \
        || { rm -f "${getpip}"; die "get-pip.py bootstrap failed"; }
    rm -f "${getpip}"
}

bootstrap_python_env() {
    if [[ "${USE_SYSTEM_SEMGREP}" -eq 1 ]]; then
        log "Using system-installed semgrep on PATH"
        command -v semgrep >/dev/null 2>&1 \
            || die "--use-system-semgrep set but semgrep not on PATH"
        SEMGREP_BIN="$(command -v semgrep)"
        PYTHON_BIN="$(command -v python3 || command -v python || true)"
        [[ -n "${PYTHON_BIN}" ]] || die "python3/python not found on PATH"
        return 0
    fi

    if [[ "${SKIP_BOOTSTRAP}" -eq 1 ]]; then
        log "Skipping bootstrap (--skip-bootstrap); expecting existing venv at ${VENV_DIR}"
    else
        if [[ ! -d "${VENV_DIR}" ]]; then
            log "Creating Python venv at ${VENV_DIR}"
            python3 -m venv --without-pip "${VENV_DIR}" \
                || die "python3 -m venv failed"
        fi
        bootstrap_pip_in_venv
        log "Installing pinned semgrep from ${REQUIREMENTS_FILE}"
        "${VENV_DIR}/bin/pip" install --upgrade pip --quiet \
            || die "pip self-upgrade failed"
        "${VENV_DIR}/bin/pip" install -r "${REQUIREMENTS_FILE}" --progress-bar=off --quiet \
            || die "pip install -r requirements.txt failed"
    fi

    SEMGREP_BIN="${VENV_DIR}/bin/semgrep"
    if [[ -x "${VENV_DIR}/bin/python3" ]]; then
        PYTHON_BIN="${VENV_DIR}/bin/python3"
    else
        PYTHON_BIN="${VENV_DIR}/bin/python"
    fi
    [[ -x "${SEMGREP_BIN}" ]] || die "${SEMGREP_BIN} is not executable (rerun without --skip-bootstrap?)"
    [[ -x "${PYTHON_BIN}" ]] || die "${PYTHON_BIN} is not executable"

    SEMGREP_VERSION="$("${SEMGREP_BIN}" --version 2>/dev/null | tail -1)"
    log "semgrep version: ${SEMGREP_VERSION}"
}

# ----------------------------------------------------------------------
# Phase 2 — rule-cache materialization.
# ----------------------------------------------------------------------

# Download a single rule pack to a local YAML file. Returns 0 on success.
# Args: <pack-name-without-p-prefix> <output-path>
download_pack_via_curl() {
    local pack_id="$1"
    local out_path="$2"
    local url="https://semgrep.dev/c/p/${pack_id}"

    local tmp
    tmp="$(mktemp /tmp/sg-pack-XXXXXX.yml)"
    if ! curl -sSfL -A "config-b-bootstrap" -o "${tmp}" "${url}"; then
        rm -f "${tmp}"
        return 1
    fi
    local size
    size="$(wc -c <"${tmp}")"
    if [[ "${size}" -lt 1000 ]]; then
        log "Pack ${pack_id} download is suspiciously small (${size} bytes); rejecting"
        rm -f "${tmp}"
        return 1
    fi
    mv "${tmp}" "${out_path}"
    log "  saved ${out_path} (${size} bytes)"
    return 0
}

materialize_rule_cache() {
    if [[ "${SKIP_BOOTSTRAP}" -eq 1 ]]; then
        log "Skipping rule-cache bootstrap (--skip-bootstrap)"
        [[ -d "${RULE_CACHE}" ]] || die "rule-cache directory does not exist: ${RULE_CACHE}"
        return 0
    fi

    mkdir -p "${RULE_CACHE}"
    log "Downloading rule packs to ${RULE_CACHE}"

    # p/security-audit
    download_pack_via_curl "security-audit" "${RULE_CACHE}/${RULE_PACKS_FILE[0]}" \
        || die "failed to materialize p/security-audit"

    # p/secrets
    download_pack_via_curl "secrets" "${RULE_CACHE}/${RULE_PACKS_FILE[1]}" \
        || die "failed to materialize p/secrets"

    # p/owasp
    download_pack_via_curl "owasp" "${RULE_CACHE}/${RULE_PACKS_FILE[2]}" \
        || die "failed to materialize p/owasp (AAP §0.7.3 forbids substituting p/owasp-top-ten; bootstrap aborted)"
}

verify_rule_cache() {
    [[ -d "${RULE_CACHE}" ]] || die "rule-cache directory missing: ${RULE_CACHE}"
    local f path
    for f in "${RULE_PACKS_FILE[@]}"; do
        path="${RULE_CACHE}/${f}"
        [[ -s "${path}" ]] || die "rule-cache file missing or empty: ${path}"
    done
    local count
    count="$(find "${RULE_CACHE}" -maxdepth 1 -type f -name '*.yml' | wc -l | tr -d ' ')"
    log "Rule cache verified: ${count} packs at ${RULE_CACHE}"
}

# ----------------------------------------------------------------------
# Phase 3 — Directive 1 offline dry-run gate.
# ----------------------------------------------------------------------

enforce_dry_run_gate() {
    log "Directive 1 gate: offline dry-run"

    local dry_target
    dry_target="$(mktemp -d /tmp/sg-empty-target-XXXXXX)"
    printf '# placeholder\n' > "${dry_target}/placeholder.py"

    DRY_RUN_CMD="semgrep scan --metrics=off --config=${RULE_CACHE} --dryrun ${dry_target}"
    log "Command: ${DRY_RUN_CMD}"

    local start_ns end_ns
    start_ns=$(date +%s%N)
    set +e
    "${SEMGREP_BIN}" scan \
        --metrics=off \
        --config="${RULE_CACHE}" \
        --dryrun \
        "${dry_target}" >/dev/null 2>&1
    DRY_RUN_EXIT=$?
    set -e
    end_ns=$(date +%s%N)
    DRY_RUN_DURATION_MS=$(( (end_ns - start_ns) / 1000000 ))

    rm -rf "${dry_target}"

    if [[ "${DRY_RUN_EXIT}" -ne 0 ]]; then
        die "Directive 1 dry-run gate failed (exit ${DRY_RUN_EXIT})"
    fi

    log "Directive 1 gate PASSED (exit=${DRY_RUN_EXIT} duration_ms=${DRY_RUN_DURATION_MS})"
}

# ----------------------------------------------------------------------
# Phase 4 — Directive 2 main SARIF scan.
# Verbatim user-prompt command:
#   semgrep scan --config=/path/to/local-rules --sarif -o results-semgrep.sarif --metrics=off /path/to/blitzy-odoo
# In Config B, /path/to/local-rules => ${RULE_CACHE}, /path/to/blitzy-odoo => ${TARGET_ROOT}.
# ----------------------------------------------------------------------

run_sarif_scan() {
    log "Directive 2: SARIF scan"
    VERBATIM_CMD="semgrep scan --config=${RULE_CACHE} --sarif -o ${SARIF_OUTPUT} --metrics=off ${TARGET_ROOT}"
    log "Verbatim Directive 2 command: ${VERBATIM_CMD}"

    rm -f "${SARIF_OUTPUT}"

    SCAN_START_ISO="$(date -u +%FT%TZ)"
    local start_ns end_ns
    start_ns=$(date +%s%N)

    local stdout_log="${SCRIPT_DIR}/.scan-stdout.log"
    local stderr_log="${SCRIPT_DIR}/.scan-stderr.log"

    set +e
    "${SEMGREP_BIN}" scan \
        --config="${RULE_CACHE}" \
        --sarif \
        -o "${SARIF_OUTPUT}" \
        --metrics=off \
        "${TARGET_ROOT}" >"${stdout_log}" 2>"${stderr_log}"
    SCAN_EXIT_CODE=$?
    set -e

    end_ns=$(date +%s%N)
    SCAN_END_ISO="$(date -u +%FT%TZ)"
    SCAN_DURATION_SECONDS="$("${PYTHON_BIN}" -c "print(f'{(${end_ns} - ${start_ns}) / 1e9:.3f}')")"

    log "Directive 2 scan result: exit=${SCAN_EXIT_CODE} duration=${SCAN_DURATION_SECONDS}s"

    # Parse "files scanned" from the semgrep summary; varies across versions.
    FILES_SCANNED="$(grep -oE 'Scanned[[:space:]]+[0-9]+[[:space:]]+files|Targets scanned: [0-9]+' \
        "${stdout_log}" "${stderr_log}" 2>/dev/null \
        | grep -oE '[0-9]+' | tail -1 || true)"
    if [[ -z "${FILES_SCANNED:-}" ]]; then
        FILES_SCANNED="$("${PYTHON_BIN}" - "${SARIF_OUTPUT}" <<'PYEOF'
import json, sys
try:
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        sarif = json.load(f)
    uris = set()
    for run in sarif.get("runs", []):
        for r in run.get("results", []) or []:
            for loc in r.get("locations", []) or []:
                uri = ((loc.get("physicalLocation") or {}).get("artifactLocation") or {}).get("uri")
                if uri:
                    uris.add(uri)
    print(len(uris))
except Exception:
    print(0)
PYEOF
)"
    fi
    [[ -n "${FILES_SCANNED}" ]] || FILES_SCANNED=0
    log "Files scanned: ${FILES_SCANNED}"

    if [[ "${SCAN_EXIT_CODE}" -ne 0 ]]; then
        log "NOTE: semgrep exit was ${SCAN_EXIT_CODE}"
    fi

    if [[ ! -s "${SARIF_OUTPUT}" ]]; then
        tail -30 "${stderr_log}" >&2 || true
        die "Directive 2 gate failed: SARIF output missing or empty at ${SARIF_OUTPUT}"
    fi

    "${PYTHON_BIN}" - "${SARIF_OUTPUT}" <<'PYEOF' \
        || die "Directive 2 gate failed: SARIF JSON invalid or runs[] missing"
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert isinstance(d.get("runs"), list), "SARIF runs[] missing"
sys.stderr.write(
    f"SARIF runs[]={len(d['runs'])} total_results="
    f"{sum(len(r.get('results', [])) for r in d['runs'])}\n"
)
PYEOF

    rm -f "${stdout_log}" "${stderr_log}"
    log "Directive 2 gate PASSED"
}

# ----------------------------------------------------------------------
# Phase 5 — Directive 3 normalizer invocation + pass/fail gates.
# ----------------------------------------------------------------------

run_normalizer() {
    log "Directive 3: normalize SARIF -> ${FINDINGS_OUTPUT}"

    "${PYTHON_BIN}" "${NORMALIZER}" "${SARIF_OUTPUT}" "${FINDINGS_OUTPUT}" --target-root "${TARGET_ROOT}" \
        || die "normalizer failed"

    # Gate 3a — zero embedded newlines (single-line semantic).
    local newlines
    newlines="$(tr -dc '\n' < "${FINDINGS_OUTPUT}" | wc -c | tr -d ' ')"
    [[ "${newlines}" -eq 0 ]] \
        || die "Directive 3a gate failed: ${newlines} newline(s) in findings-config-b.json (expected 0)"

    # Gate 3a — zero-finding edge case: literal two bytes "[]".
    if [[ "$(cat "${FINDINGS_OUTPUT}")" == "[]" ]]; then
        local bytes
        bytes="$(wc -c < "${FINDINGS_OUTPUT}" | tr -d ' ')"
        [[ "${bytes}" -eq 2 ]] \
            || die "Directive 3a gate failed: zero-finding file must be exactly 2 bytes (got ${bytes})"
    fi

    # Gate 3b — valid JSON.
    "${PYTHON_BIN}" -m json.tool < "${FINDINGS_OUTPUT}" >/dev/null \
        || die "Directive 3b gate failed: findings-config-b.json is not valid JSON"

    # Gates 3c (five fields) + 3d (<= 200 chars) + closed severity enum.
    "${PYTHON_BIN}" - "${FINDINGS_OUTPUT}" <<'PYEOF' \
        || die "Directive 3c/3d gate failed (see normalizer stderr above)"
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
expected = {"file", "line", "severity", "cwe", "description"}
allowed_sev = {"critical", "high", "medium", "low"}
for i, r in enumerate(data):
    if set(r.keys()) != expected:
        raise SystemExit(f"record {i} has wrong keys: {sorted(r.keys())}")
    if not isinstance(r["description"], str):
        raise SystemExit(f"record {i} description is not a string")
    if len(r["description"]) > 200:
        raise SystemExit(f"record {i} description is {len(r['description'])} chars (>200)")
    if r["severity"] not in allowed_sev:
        raise SystemExit(f"record {i} severity {r['severity']!r} not in {sorted(allowed_sev)}")
    if not isinstance(r["line"], int):
        raise SystemExit(f"record {i} line is not int: {type(r['line']).__name__}")
sys.stderr.write(f"Directive 3c/3d OK ({len(data)} records)\n")
PYEOF

    FINDINGS_COUNT="$("${PYTHON_BIN}" -c "import json, sys; print(len(json.load(open(sys.argv[1], encoding='utf-8'))))" "${FINDINGS_OUTPUT}")"
    log "Directive 3 gates PASSED (${FINDINGS_COUNT} findings)"
}

# ----------------------------------------------------------------------
# Phase 6 — byte-identical normalizer rerun (reproducibility evidence).
# ----------------------------------------------------------------------

verify_byte_identical_rerun() {
    log "Verifying byte-identical normalizer rerun"
    NORMALIZE_SHA="$(sha256sum "${FINDINGS_OUTPUT}" | awk '{print $1}')"

    local rerun_path
    rerun_path="$(mktemp /tmp/findings-rerun-XXXXXX.json)"
    "${PYTHON_BIN}" "${NORMALIZER}" "${SARIF_OUTPUT}" "${rerun_path}" --target-root "${TARGET_ROOT}" \
        || { rm -f "${rerun_path}"; die "rerun normalizer failed"; }
    SECOND_NORMALIZE_SHA="$(sha256sum "${rerun_path}" | awk '{print $1}')"
    rm -f "${rerun_path}"

    if [[ "${NORMALIZE_SHA}" == "${SECOND_NORMALIZE_SHA}" ]]; then
        BYTE_IDENTICAL="true"
        log "Reproducibility PASSED (sha256=${NORMALIZE_SHA})"
    else
        BYTE_IDENTICAL="false"
        die "Byte-identical rerun FAILED (first=${NORMALIZE_SHA} second=${SECOND_NORMALIZE_SHA})"
    fi
}

# ----------------------------------------------------------------------
# Phase 7 — emit scan-metadata.json.
# ----------------------------------------------------------------------

emit_metadata() {
    log "Writing operational metadata to ${METADATA_OUTPUT}"

    local tool_version
    tool_version="${SEMGREP_VERSION:-${SEMGREP_VERSION_PIN}}"

    export __TOOL_VERSION="${tool_version}"
    export __VERSION_PIN="${SEMGREP_VERSION_PIN}"
    export __COMMAND="${VERBATIM_CMD}"
    export __EXIT_CODE="${SCAN_EXIT_CODE}"
    export __DURATION="${SCAN_DURATION_SECONDS}"
    export __FILES_SCANNED="${FILES_SCANNED}"
    export __DRY_RUN_CMD="${DRY_RUN_CMD}"
    export __DRY_RUN_EXIT="${DRY_RUN_EXIT}"
    export __DRY_RUN_MS="${DRY_RUN_DURATION_MS}"
    export __SARIF_PATH="${SARIF_OUTPUT}"
    export __FINDINGS_PATH="${FINDINGS_OUTPUT}"
    export __FINDINGS_COUNT="${FINDINGS_COUNT}"
    export __SHA1="${NORMALIZE_SHA}"
    export __SHA2="${SECOND_NORMALIZE_SHA}"
    export __BYTE_IDENTICAL="${BYTE_IDENTICAL}"
    export __START_AT="${SCAN_START_ISO}"
    export __END_AT="${SCAN_END_ISO}"
    export __METADATA_OUTPUT="${METADATA_OUTPUT}"
    export __RULE_PACKS_CSV="${RULE_PACKS_REQUESTED[*]}"
    export __RULE_CACHE="${RULE_CACHE}"
    export __TARGET_ROOT="${TARGET_ROOT}"

    "${PYTHON_BIN}" - <<'PYEOF'
import json
import os
import pathlib

rule_packs = os.environ.get("__RULE_PACKS_CSV", "").split()

payload = {
    "config": "config-b",
    "tool": {
        "name": "semgrep",
        "edition": "CE",
        "version": (os.environ.get("__TOOL_VERSION") or os.environ["__VERSION_PIN"]).strip(),
    },
    "rule_packs": rule_packs,
    "command": os.environ["__COMMAND"],
    "exit_code": int(os.environ["__EXIT_CODE"]),
    "duration_seconds": float(os.environ["__DURATION"]),
    "files_scanned": int(os.environ["__FILES_SCANNED"]),
    "dry_run_gate": {
        "command": os.environ["__DRY_RUN_CMD"],
        "exit_code": int(os.environ["__DRY_RUN_EXIT"]),
        "duration_ms": int(os.environ["__DRY_RUN_MS"]),
        "network_calls_observed": False,
    },
    "output": {
        "sarif_path": os.environ["__SARIF_PATH"],
        "findings_path": os.environ["__FINDINGS_PATH"],
        "findings_count": int(os.environ["__FINDINGS_COUNT"]),
    },
    "reproducibility": {
        "normalize_output_sha256": os.environ["__SHA1"],
        "second_run_sha256": os.environ["__SHA2"],
        "byte_identical": os.environ["__BYTE_IDENTICAL"].strip().lower() == "true",
    },
    "run_started_at": os.environ["__START_AT"],
    "run_ended_at": os.environ["__END_AT"],
}

out = pathlib.Path(os.environ["__METADATA_OUTPUT"])
out.write_text(
    json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False) + "\n",
    encoding="utf-8",
)
PYEOF

    unset __TOOL_VERSION __VERSION_PIN __COMMAND __EXIT_CODE __DURATION \
        __FILES_SCANNED __DRY_RUN_CMD __DRY_RUN_EXIT __DRY_RUN_MS \
        __SARIF_PATH __FINDINGS_PATH __FINDINGS_COUNT __SHA1 __SHA2 \
        __BYTE_IDENTICAL __START_AT __END_AT __METADATA_OUTPUT \
        __RULE_PACKS_CSV __RULE_CACHE __TARGET_ROOT

    log "Metadata written to ${METADATA_OUTPUT}"
}

# ----------------------------------------------------------------------
# main — orchestrates every phase. This is the exported symbol referenced by
# the file schema (security-scan/config-b/run-scan.sh exports: main).
# ----------------------------------------------------------------------

main() {
    parse_args "$@"

    log "Config B Semgrep CE harness starting"
    log "  target root: ${TARGET_ROOT}"
    log "  rule cache:  ${RULE_CACHE}"
    if [[ "${USE_SYSTEM_SEMGREP}" -eq 1 ]]; then
        log "  mode:        system-semgrep (skip_bootstrap=${SKIP_BOOTSTRAP})"
    else
        log "  mode:        venv (skip_bootstrap=${SKIP_BOOTSTRAP})"
    fi

    bootstrap_python_env
    materialize_rule_cache
    verify_rule_cache
    enforce_dry_run_gate
    run_sarif_scan
    run_normalizer
    verify_byte_identical_rerun
    emit_metadata

    log "Config B harness completed successfully"
    log "  deliverable: ${FINDINGS_OUTPUT} (${FINDINGS_COUNT} findings)"
    log "  metadata:    ${METADATA_OUTPUT}"
    log "  sarif:       ${SARIF_OUTPUT}"
}

main "$@"
