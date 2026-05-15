# Config B — Semgrep CE Static Analysis Harness

This directory holds **Config B** of a multi-configuration security tool
comparison run against the `blitzy-odoo` repository. It produces a single
deliverable file, `findings-config-b.json`, that contains a minified, single-line,
UTF-8 JSON array of normalized findings. Nothing in the `blitzy-odoo` source tree
is modified by this harness — the scan is read-only.

> Sibling configurations of the comparison (Config A, Config C, …) live in
> `security-scan/config-a/`, `security-scan/config-c/`, etc., and do not share
> any state with this directory.

---

## 1. Prerequisites

| Requirement | Version | Notes |
| --- | --- | --- |
| Operating system | Linux or macOS (POSIX) | Bash assumed. |
| Python | 3.10 or later | Required by Semgrep CE 1.163.0 (supports 3.10–3.14). |
| `bash` | Any POSIX-compliant Bash | `run-scan.sh` uses `set -euo pipefail`. |
| Network access | One-time during bootstrap | Required only to download Semgrep from PyPI and the three rule packs from the Semgrep Registry. After `rule-cache/` is populated, subsequent runs are offline. |
| Disk space | ~500 MB | For the Semgrep wheel, its transitive dependencies in `.venv/`, the rule cache, and intermediate scan artifacts. |

The harness installs Semgrep into an isolated virtual environment under
`security-scan/config-b/.venv/` so it never touches the project's root
`requirements.txt` or the Odoo runtime environment.

---

## 2. Quickstart

From the repository root:

```bash
bash security-scan/config-b/run-scan.sh
```

The script performs the following steps and aborts on the first failure:

1. **Bootstrap.** Creates `.venv/` and installs `semgrep==1.163.0`.
2. **Rule cache materialization.** Downloads `p/security-audit`, `p/secrets`, and
   `p/owasp` from the Semgrep Registry into `rule-cache/` as YAML.
3. **Offline dry-run gate (Directive 1 pass/fail).** Runs
   `semgrep scan --metrics=off --config=security-scan/config-b/rule-cache --dry-run`
   and asserts exit 0.
4. **SARIF scan (Directive 2).** Runs the verbatim user-supplied command and
   records exit code, wall-clock duration, and the total number of files
   scanned into `scan-metadata.json`.
5. **Normalize (Directive 3).** Runs `normalize-findings.py` against the SARIF
   to emit `findings-config-b.json`.
6. **Validate gates.** Asserts the deliverable is a single line, valid JSON,
   has the closed 5-field schema, and contains no description exceeding 200
   characters.
7. **Reproducibility check.** Re-runs the normalizer and confirms a
   byte-identical output (recorded under `scan-metadata.reproducibility`).

### 2.1 Optional flags

| Flag | Default | Purpose |
| --- | --- | --- |
| `--target-root <path>` | `$(git rev-parse --show-toplevel)` | Override the scanned repo root. |
| `--rule-cache <path>` | `security-scan/config-b/rule-cache` | Override the local rule cache directory. |
| `--use-system-semgrep` | off | Skip the venv installation and use the `semgrep` already on `$PATH` (must be CE 1.163.0 for byte-identical output). |
| `--skip-bootstrap` | off | Assume the rule cache is already populated (fully offline rerun). |

---

## 3. Verbatim user command (Directive 2)

The SARIF-generating invocation is preserved character-for-character from the
user prompt. The two `/path/to/...` placeholders are resolved at runtime by
`run-scan.sh` and printed to stderr before execution so the operator can
verify wire-level fidelity:

```bash
semgrep scan --config=/path/to/local-rules --sarif -o results-semgrep.sarif --metrics=off /path/to/blitzy-odoo
```

`/path/to/local-rules` resolves to the absolute path of `rule-cache/` and
`/path/to/blitzy-odoo` resolves to the absolute path of the repository root.

---

## 4. Output schema (Directive 3)

The deliverable `findings-config-b.json` is a JSON array of objects, each
object having exactly five fields in this key order:

```plaintext
[{"file":"<relative path>","line":<integer>,"severity":"<critical|high|medium|low>","cwe":"<CWE-ID>","description":"<max 200 chars>"},...]
```

Field mapping:

| Field | Source |
| --- | --- |
| `file` | SARIF location (relative path), i.e. `result.locations[0].physicalLocation.artifactLocation.uri`. |
| `line` | SARIF region start line, coerced to integer. |
| `severity` | Mapping table `error→critical, warning→high, note→medium, info→low`. |
| `cwe` | Rule metadata CWE ID. If absent, the most specific CWE inferable from the rule description (table-driven). Otherwise `CWE-Unknown` (see `decision-log.md`). |
| `description` | SARIF message text, truncated to 200 characters. |

When zero findings are produced, the file is the literal two-byte content `[]`.

---

## 5. Pass/fail gates

| Gate | Source | Verification |
| --- | --- | --- |
| Directive 1 — offline operation | User prompt | Inside `run-scan.sh`: `semgrep scan --metrics=off --config=security-scan/config-b/rule-cache --dry-run` exits 0 with no network calls. |
| Directive 2 — SARIF emission | User prompt | `python -c "import json; d=json.load(open('results-semgrep.sarif')); assert isinstance(d.get('runs'), list)"`. |
| Directive 3a — single line | User prompt + AAP §0.1.2.3, §0.5.4.2, §0.6.2.1 | The file contains zero newline bytes (no embedded, no trailing): `[ "$(tr -dc '\n' < findings-config-b.json \| wc -c)" = "0" ]`. For an empty result set, the file is exactly the two bytes `[]`: `[ "$(wc -c < findings-config-b.json)" = "2" ]` when the payload is `[]`. See `decision-log.md` DEV-3 for the resolution of the AAP-vs-user-prompt tension around `wc -l`. |
| Directive 3b — valid JSON | User prompt | `python -m json.tool < findings-config-b.json > /dev/null`. |
| Directive 3c — five fields | User prompt | All objects have exactly `{file, line, severity, cwe, description}`. |
| Directive 3d — description ≤ 200 chars | User prompt | All `description` strings have `len(...) <= 200`. |
| Explainability rule | User rule | `decision-log.md` exists with decision table, traceability matrix, and deviations log. |
| Executive Presentation rule | User rule | `executive-summary.html` opens in any modern browser, contains 12–18 `<section>` elements, and uses the pinned CDN versions. |

---

## 6. Outputs produced

| File | Tracked in git? | Description |
| --- | --- | --- |
| `findings-config-b.json` | yes | **THE deliverable.** Minified, single-line JSON array. |
| `results-semgrep.sarif` | no (gitignored) | Intermediate SARIF v2.1.0 emitted by Semgrep. |
| `scan-metadata.json` | no (gitignored) | Operational record: exit code, duration, files scanned, Semgrep version, rule-pack list, reproducibility evidence. |
| `decision-log.md` | yes | Explainability rule deliverable. |
| `executive-summary.html` | yes | Executive Presentation rule deliverable. |
| `rule-cache/*.yml` | no (gitignored) | Locally materialized registry rule packs. |
| `.venv/` | no (gitignored) | Isolated Python environment. |

---

## 7. Troubleshooting

- **`semgrep: command not found` after install.** The script auto-activates
  `.venv/`. If you skipped that, source it manually:
  `source security-scan/config-b/.venv/bin/activate`.
- **Rule pack download fails.** The bootstrap phase requires network access.
  Once successful, future runs can pass `--skip-bootstrap`.
- **Dry-run gate fails with network calls.** Re-run with `--metrics=off`
  already on the command; if it still fails, inspect the rule cache for empty
  or malformed YAML and rerun bootstrap.
- **Wheel install fails on Python 3.14+.** Semgrep CE 1.163.0 supports up to
  3.14; if you are on a newer Python, install Python 3.13 alongside and
  re-invoke the harness with `PYTHON=python3.13 bash run-scan.sh`.

---

## 8. Repository state assumptions

The harness assumes it is invoked from inside a checkout of `blitzy-odoo`
that has not been modified. Adding, removing, or modifying files between the
scan and a re-scan will (legitimately) change the SARIF contents and therefore
the deliverable; that is expected and is not a reproducibility violation.

For a deeper account of design decisions, alternatives considered, and any
deviations from a literal reading of the user prompt, see
[`decision-log.md`](./decision-log.md).
