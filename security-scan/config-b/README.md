# Config B — Semgrep CE Static-Analysis Harness

Read-only static analysis of `blitzy-odoo` using Semgrep Community Edition with three cached registry rule packs, producing a five-field minified JSON findings export.

---

## Purpose

This folder is **Config B** of the multi-configuration security tool comparison. It scans the `blitzy-odoo` codebase (everything under the repository root) using Semgrep CE with three named registry rule packs cached locally — `p/security-audit`, `p/secrets`, and `p/owasp` — and produces a single deliverable `findings-config-b.json` in the format mandated by the user prompt (minified, single-line, UTF-8 JSON array; exactly five fields per record; severity in `{critical,high,medium,low}`; description ≤200 characters; `[]` for zero findings). The harness is offline-by-default after a one-time bootstrap, telemetry-free (`--metrics=off`), and produces byte-identical reruns. **No file outside `security-scan/config-b/` is modified.**

Sibling configurations of the comparison (Config A, Config C, …) live in `security-scan/config-a/`, `security-scan/config-c/`, etc., and do not share any state with this directory.

---

## Prerequisites

- **Python 3.10 or later** (Semgrep CE requires it). Verify: `python3 --version`.
- **POSIX shell** (Bash). Verify: `bash --version`.
- **Network access** during the one-time bootstrap phase (rule-pack download). Subsequent runs are offline.
- **About 200 MB of free disk space** for the `.venv/` and `rule-cache/` directories.

The harness installs Semgrep into an isolated virtual environment under `security-scan/config-b/.venv/` so it never touches the project's root `requirements.txt` or the Odoo runtime environment.

---

## Quickstart

```bash
# From the repository root:
./security-scan/config-b/run-scan.sh

# The harness will:
#   1. Create security-scan/config-b/.venv/ and install semgrep==1.163.0.
#   2. Materialize the three rule packs into security-scan/config-b/rule-cache/.
#   3. Run the Directive 1 offline dry-run gate.
#   4. Execute the Directive 2 SARIF scan.
#   5. Capture exit code, wall-clock duration, and total files scanned into scan-metadata.json.
#   6. Normalize SARIF to the five-field array in findings-config-b.json.
#   7. Verify every Directive 3 pass/fail gate.

# Re-running offline once the cache is populated:
./security-scan/config-b/run-scan.sh --skip-bootstrap

# Re-running with a system-installed Semgrep:
./security-scan/config-b/run-scan.sh --use-system-semgrep

# Scanning a different target root:
./security-scan/config-b/run-scan.sh --target-root /path/to/another-checkout
```

### Optional flags

| Flag | Default | Purpose |
| --- | --- | --- |
| `--target-root <path>` | `$(git rev-parse --show-toplevel)` | Override the scanned repository root. |
| `--rule-cache <path>` | `security-scan/config-b/rule-cache` | Override the local rule cache directory. |
| `--use-system-semgrep` | off | Skip the `.venv/` install and use the `semgrep` already on `$PATH` (must be CE 1.163.0 for byte-identical output). |
| `--skip-bootstrap` | off | Assume the rule cache is already populated (fully offline rerun). |
| `-h`, `--help` | — | Show usage and exit. |

---

## The exact scan command (preserved verbatim from the user prompt, Directive 2)

```bash
semgrep scan --config=/path/to/local-rules --sarif -o results-semgrep.sarif --metrics=off /path/to/blitzy-odoo
```

In Config B, the two `/path/to/...` placeholders resolve to:

- `/path/to/local-rules` → `security-scan/config-b/rule-cache` (the local materialization of `p/security-audit`, `p/secrets`, and `p/owasp`).
- `/path/to/blitzy-odoo` → the absolute path of the repository root (auto-detected as `$(git rev-parse --show-toplevel)` by `run-scan.sh`, overridable with `--target-root`).

No other flags are added or removed. `run-scan.sh` echoes the resolved command to stderr before executing it so an operator can independently verify wire-level fidelity.

---

## Output schema (`findings-config-b.json`)

The deliverable is a **minified, single-line, UTF-8 JSON array**. Each finding is exactly five fields. For zero findings, the file content is the two bytes `[]`.

```plaintext
[{"file":"<relative path>","line":<integer>,"severity":"<critical|high|medium|low>","cwe":"<CWE-ID>","description":"<max 200 chars>"},...]
```

| Field | Source | Notes |
| --- | --- | --- |
| `file` | SARIF `result.locations[0].physicalLocation.artifactLocation.uri` | Relative path emitted by Semgrep. |
| `line` | SARIF `result.locations[0].physicalLocation.region.startLine` | Integer. |
| `severity` | SARIF `result.level` mapped via `error→critical, warning→high, note→medium, info→low` | Falls back through rule `defaultConfiguration.level` and rule `properties.severity` to `"medium"`; see `decision-log.md` DEV-6 for fallback rationale. |
| `cwe` | Rule `properties.cwe` (first if list); else `infer_cwe(message)`; else `"CWE-Unknown"` | Normalized to `CWE-<n>`. See `decision-log.md` DEV-5. |
| `description` | SARIF `result.message.text` | Truncated to 200 Unicode characters (no ellipsis). |

---

## Pass/fail gates

The harness enforces every gate below. Each is verified inside `run-scan.sh`; the run aborts on the first failure with a non-zero exit code.

| Gate | Verification command (executed inside `run-scan.sh`) |
| --- | --- |
| Directive 1 — offline operation | `semgrep scan --metrics=off --config=security-scan/config-b/rule-cache --dryrun <empty-target>` exits 0 with no network calls. (The CLI flag is `--dryrun` rather than the user-prompt-literal `--dry-run`; see `decision-log.md` DEV-2.) |
| Directive 2 — SARIF emission | `python -c "import json,sys; d=json.load(open('results-semgrep.sarif')); assert isinstance(d.get('runs'), list)"` exits 0. |
| Directive 3a — single line | `tr -dc '\n' < findings-config-b.json \| wc -c` returns `0` (no newline bytes anywhere). For the empty-result baseline `wc -c < findings-config-b.json` returns `2` (the file is exactly the two bytes `[]`). This is the AAP-aligned formulation of the user-prompt-literal `wc -l == 1` gate; see `decision-log.md` DEV-3. |
| Directive 3b — valid JSON | `python -m json.tool < findings-config-b.json > /dev/null` exits 0. |
| Directive 3c — five fields | `python -c "import json; data=json.load(open('findings-config-b.json')); assert all(set(r)=={'file','line','severity','cwe','description'} for r in data)"` exits 0. |
| Directive 3d — description ≤200 chars | `python -c "import json; data=json.load(open('findings-config-b.json')); assert all(len(r['description'])<=200 for r in data)"` exits 0. |
| Explainability rule | `decision-log.md` has decision table, traceability matrix, deviations section. |
| Executive Presentation rule | `executive-summary.html` is self-contained, has 12–18 `<section>` elements, every section carries ≥1 non-text visual, CDNs pinned to exact versions (reveal.js 5.1.0, Mermaid 11.4.0, Lucide 0.460.0). |

---

## File inventory

### Static (committed to version control)

| File | Purpose |
| --- | --- |
| `README.md` | This file. Operator entry point. |
| `requirements.txt` | Pinned harness dependency: `semgrep==1.163.0`. |
| `run-scan.sh` | Orchestration entrypoint; performs install → cache → dry-run gate → SARIF scan → normalize → verify. |
| `normalize-findings.py` | SARIF → five-field JSON normalizer (Python 3.10+ stdlib only). |
| `findings-config-b.json` | **THE deliverable.** Minified single-line UTF-8 JSON array of normalized findings. |
| `decision-log.md` | Explainability rule deliverable: decision table, traceability matrix, deviations log. |
| `executive-summary.html` | Executive Presentation rule deliverable: single self-contained reveal.js deck. |
| `.gitignore` | Excludes regenerable runtime outputs from version control. |

### Runtime-generated (in `.gitignore`)

| File | Generator | Purpose |
| --- | --- | --- |
| `.venv/` | `run-scan.sh` | Isolated Python environment with `semgrep==1.163.0`. |
| `rule-cache/security-audit.yml` | `run-scan.sh` bootstrap | Local materialization of registry pack `p/security-audit`. |
| `rule-cache/secrets.yml` | `run-scan.sh` bootstrap | Local materialization of registry pack `p/secrets`. |
| `rule-cache/owasp.yml` | `run-scan.sh` bootstrap | Local materialization of registry pack `p/owasp`. If the registry cannot serve `p/owasp`, the harness aborts per AAP §0.7.3 rather than substituting another pack. |
| `results-semgrep.sarif` | `semgrep scan` | Raw SARIF v2.1.0 output (intermediate). |
| `scan-metadata.json` | `run-scan.sh` | Operational record: exit code, wall-clock duration, files scanned, etc. |

---

## Operational metadata (`scan-metadata.json`)

`run-scan.sh` writes this sibling JSON file to capture the three operational facts Directive 2 requires (exit code, wall-clock duration, total files scanned) without modifying the SARIF body.

Example shape:

```
{
  "config": "config-b",
  "tool": {"name": "semgrep", "edition": "CE", "version": "1.163.0"},
  "rule_packs": ["p/security-audit", "p/secrets", "p/owasp"],
  "command": "semgrep scan --config=<rule-cache> --sarif -o results-semgrep.sarif --metrics=off <repo-root>",
  "exit_code": 0,
  "duration_seconds": 123.45,
  "files_scanned": 12345,
  "dry_run_gate": {"command": "...", "exit_code": 0, "duration_ms": 0, "network_calls_observed": false},
  "output": {
    "sarif_path": "results-semgrep.sarif",
    "findings_path": "findings-config-b.json",
    "findings_count": 0
  },
  "reproducibility": {
    "normalize_output_sha256": "<hex>",
    "second_run_sha256": "<hex>",
    "byte_identical": true
  },
  "run_started_at": "2025-01-01T00:00:00Z",
  "run_ended_at":   "2025-01-01T00:02:03Z"
}
```

Field notes:

- `rule_packs` is a flat array of the verbatim identifiers from Directive 1 (`p/security-audit`, `p/secrets`, `p/owasp`). AAP §0.7.3 forbids substitution, so the harness aborts on registry failure rather than rewriting this list.
- `dry_run_gate.network_calls_observed: false` is the Directive 1 evidence.
- `reproducibility.byte_identical: true` confirms that re-running the normalizer against the same SARIF produces the same `findings-config-b.json` byte-for-byte.

---

## Troubleshooting

| Symptom | Likely cause | Resolution |
| --- | --- | --- |
| `pip install semgrep==1.163.0` fails with "no matching distribution" | Python < 3.10 or unsupported platform | Verify `python3 --version` is 3.10 or later; on macOS use Homebrew Python; on Windows use WSL. |
| Bootstrap fails downloading a rule pack | One-time network access to `semgrep.dev` blocked, or registry transient error | Re-run without `--skip-bootstrap`; ensure outbound HTTPS to `semgrep.dev` during bootstrap. Once successful, future runs can pass `--skip-bootstrap`. |
| Dry-run gate exits non-zero with "config not found" | `rule-cache/` is empty or partial | Re-run without `--skip-bootstrap` to repopulate the cache. |
| Main scan exits non-zero with "syntax error" | Semgrep parser error on a malformed file | Check stderr for the offending file; the scan continues past parse errors but logs them. |
| `wc -l < findings-config-b.json` returns `0` | File has no trailing newline (Config B convention) | This is **expected**; see `decision-log.md` DEV-3. The "single line" gate is enforced semantically (no embedded newlines), not by trailing-LF count. The gate command in `run-scan.sh` uses `tr -dc '\n' \| wc -c == 0`. |
| Findings file shows `"CWE-Unknown"` for some records | Rule metadata omits CWE AND no keyword inference matched | This is the documented fallback (see `decision-log.md` DEV-5). The rule ID is logged to stderr each time so operators can audit. |
| Findings file shows `"severity": "medium"` for some records | SARIF result-level + rule-level severity both absent | Last-resort fallback (see `decision-log.md` DEV-6). |
| Wheel install fails on Python 3.14+ | Semgrep CE 1.163.0 supports up to 3.14 only | If you are on a newer Python, install Python 3.13 alongside and re-invoke the harness with `PYTHON=python3.13 ./run-scan.sh`. |
| `semgrep: command not found` after install | `.venv/` not activated in the current shell | The script auto-activates `.venv/`. If you skipped that, source it manually: `source security-scan/config-b/.venv/bin/activate`. |

---

## Related deliverables

- **`decision-log.md`** — Single source of truth for "why" decisions in Config B. Required reading before modifying any harness behavior. Contains the decision table, the bidirectional SARIF → findings traceability matrix, and the enumerated deviations from a literal reading of the user prompt (DEV-2 through DEV-8; DEV-1 is RETIRED but the identifier is preserved for historical cross-references).
- **`executive-summary.html`** — Non-technical leadership-facing reveal.js deck. Open in any modern browser; no build steps and no local file dependencies.
