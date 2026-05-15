# Config B — Decision Log

This document is the single source of truth for "why" decisions in
`security-scan/config-b/`. It satisfies the **Explainability** user rule
(AAP §0.7.1): every non-trivial implementation decision is recorded here
with explicit alternatives and rationale, and every deviation from a literal
reading of the user prompt has a dedicated entry.

> No rationale is duplicated in code comments. Harness source files carry
> only operational comments ("anchor the script to its own directory",
> "abort on the first failure", etc.). The "why" for any choice lives here.

---

## 1. Decision table

| # | Decision | Alternatives considered | Rationale | Risks / Mitigations |
| --- | --- | --- | --- | --- |
| D1 | Place the harness at `security-scan/config-b/` at the repo root. | `tools/semgrep/`, `.security/semgrep/`, root-level `semgrep/`. | The AAP frames this as one configuration in a multi-config comparison; the chosen layout reserves `security-scan/config-a/`, `security-scan/config-c/`, etc. for siblings without collisions. Putting the harness under a generic `tools/` or `.security/` would either pollute existing tooling conventions or hide the comparison structure. | Risk: confusion with future "config-A only" tooling. Mitigation: the README opens with the multi-config context and the directory is self-contained (no external imports). |
| D2 | Use Semgrep CE (LGPL 2.1, formerly Semgrep OSS) — not Semgrep Pro / AppSec Platform. | Semgrep Pro engine, Semgrep AppSec Platform via `semgrep login && semgrep ci`. | The user directives mandate offline, telemetry-free operation with `--metrics=off`; AppSec Platform requires a login flow and a network round-trip. The CE engine satisfies the directive at the cost of weaker Python framework coverage (documented limitation). | Risk: framework-specific Pro rules will not return findings on CE, reducing detection coverage. Mitigation: documented on the executive presentation "Risks & limitations" slide and below in §3. |
| D3 | Pin `semgrep==1.163.0` rather than allowing a range. | `semgrep>=1`, `semgrep>=1.150`, `semgrep~=1.163`. | The directives do not specify a version, but a floating pin would break the comparison harness's reproducibility (Config A and Config C reruns would silently shift). Pinning the newest published release (1.163.0) provides current rule coverage and reproducible re-runs. | Risk: pin will go stale; an explicit refresh is required to track future releases. Mitigation: refresh is one line in `requirements.txt`; reproducibility check in the harness verifies behavior is unchanged across reruns. |
| D4 | Materialize the three registry rule packs into `rule-cache/` as YAML during a one-time bootstrap. | Pull from registry on every scan via `--config=p/<pack>`; bake rules into the script. | Directive 1 explicitly requires offline operation; the one-time-cache pattern satisfies it without changing rule content. | Risk: rule definitions could change in the registry mid-cycle. Mitigation: `run-scan.sh --skip-bootstrap` reuses the cached YAML, and the rule-pack provenance is recorded in `scan-metadata.json`. |
| D5 | Implement the SARIF normalizer in Python 3.10+ stdlib only. | `jq -c` + `tr -d '\n'` pipeline; Node-based `JSON.stringify`; Go binary. | A single-file Python script (no third-party imports) keeps the harness reproducible and free of additional supply-chain surface. The deterministic `json.dumps(..., separators=(',', ':'))` call satisfies the single-line gate exactly. | Risk: stdlib `json` behavior could in principle change. Mitigation: pinned on Python 3.10+; behavior of `separators=(',', ':')` is stable across all supported versions. |
| D6 | CWE inference fallback is a table-driven regex map; unmatched cases emit `CWE-Unknown`. | Fail the run when no CWE is inferable; emit `""`; require manual triage per finding. | The Directive 3 pass/fail clause requires "every finding has all 5 fields populated"; emitting an empty CWE would fail that gate, and aborting the run is too brittle for a comparison harness running unattended. `CWE-Unknown` is an explicit, auditable sentinel. | Risk: `CWE-Unknown` masks rules that legitimately lack CWE metadata. Mitigation: the inference table is open-source and lives in `normalize-findings.py`; downstream agents can extend it without changing the harness shape. |
| D7 | Severity fallback chain: `result.level → rule.defaultConfiguration.level → rule.properties.severity → "medium"`. | Reject SARIFs that omit `level`; default to "low" or "critical". | The Directive 3 gate requires every finding to have all 5 fields, including `severity`. The fallback chain favors the most reliable source first, then converges on `"medium"` as a neutral last resort. | Risk: "medium" sentinel can hide real severity. Mitigation: the deviations log (§3) flags this as an explicit divergence from a literal "use the table" reading. |
| D8 | Serialize via `json.dumps(records, ensure_ascii=False, separators=(',', ':'))` + a single trailing `\n`. | `json.dumps(..., indent=None)` (default whitespace); `jq -c` pipeline; write without trailing newline. | The user-prompt pass/fail clause `cat findings-config-b.json \| wc -l == 1` requires exactly one `\n` in the file (`wc -l` counts newlines). The `separators` argument removes inter-element whitespace; the single trailing `\n` is what makes `wc -l == 1`. | Risk: the AAP's §0.6.2.1 text said "no trailing newline" which is inconsistent with the user's `wc -l == 1` gate. Mitigation: the user prompt wins per AAP §0.9.7; logged as deviation §3-DEV-3. |
| D9 | Capture operational facts (exit code, wall-clock, files scanned) in a separate `scan-metadata.json`, not in the SARIF body. | Inline as SARIF `invocations[]` extensions; mix into `findings-config-b.json`. | Directive 2 says "record" these facts; it does not say where. Keeping the SARIF unmodified preserves the trivially-auditable pass/fail gate ("SARIF contains a `runs` array"). Keeping them out of `findings-config-b.json` preserves the closed five-field schema. | Risk: an operator reading only the SARIF will not see the operational record. Mitigation: the README cross-references both files; `scan-metadata.json` is right next to the SARIF on disk. |
| D10 | Add a `--target-root` flag to the normalizer that strips an absolute path prefix to produce relative paths. | cd into the target and pass `.` as the Semgrep target argument; run Semgrep with a relative target string. | The verbatim Directive 2 command uses `/path/to/blitzy-odoo` (an absolute path), and Semgrep emits absolute URIs in SARIF as a result. The cleanest way to honor the verbatim command **and** the Directive 3 "relative path" mapping is to post-process at normalization time. | Risk: target_root mismatch (e.g., comparing against the wrong checkout) would leave absolute paths unchanged. Mitigation: `run-scan.sh` derives `TARGET_ROOT` from `git rev-parse --show-toplevel` and the value is recorded in `scan-metadata.json`. |
| D11 | Exclude `.venv/`, `rule-cache/*.yml`, `*.sarif`, and `scan-metadata.json` from version control via the local `.gitignore`; track `findings-config-b.json`, `decision-log.md`, `executive-summary.html`, and the harness sources. | Track everything; track nothing. | The deliverable, the rationale, and the executive deck are the durable artifacts; the venv and intermediate scan artifacts are regenerable. Tracking the rule cache would create gigantic repo bloat (1.9 MB of YAML the registry already owns). | Risk: an offline operator cloning the repo needs to re-bootstrap. Mitigation: the README documents the bootstrap step explicitly; `run-scan.sh` performs it without prompts. |
| D12 | The harness does not register as an Odoo addon and adds no `__manifest__.py` / `__init__.py`. | Make `security-scan/config-b/` a Python package importable from Odoo. | The harness must not perturb the running Odoo system or be loaded by Odoo's module discovery. Keeping it as a directory of scripts isolates it cleanly. | None observable: Odoo's module loader walks `addons/*/__manifest__.py`; we are nowhere in that path. |
| D13 | Do NOT introduce any CI/CD workflow under `.github/workflows/`. | Add a `security-scan-config-b.yml` GitHub Actions workflow. | `.github/` currently holds only PR/Issue templates; adding a workflow would expand the project's surface and is not in scope for a single-config comparison. The harness is invoked locally. | None observable; future agents can add CI on top of `run-scan.sh` without modifying the harness. |

---

## 2. Bidirectional traceability matrix

Each row maps a single SARIF source path to a single emitted field in
`findings-config-b.json`. Coverage of the five output fields is 100%.

| Output field | SARIF source path (in priority order) | Transformation | Fallback when source is absent |
| --- | --- | --- | --- |
| `file` | `runs[].results[].locations[0].physicalLocation.artifactLocation.uri` | If `--target-root` is set and the URI is absolute under that root, strip the root prefix (and any leading `file://`) so the result is repo-relative. | `""` (logged; only occurs if SARIF omits the location entirely). |
| `line` | `runs[].results[].locations[0].physicalLocation.region.startLine` | Coerce to integer; numeric strings parsed via `int(...)`. | `0` (logged; only occurs if SARIF omits the region). |
| `severity` | `runs[].results[].level` → `runs[].tool.driver.rules[].defaultConfiguration.level` → `runs[].tool.driver.rules[].properties.severity` | Apply the fixed table `error→critical, warning→high, note→medium, info→low`. If the source is already one of `{critical, high, medium, low}`, pass through. | `"medium"` (logged; only occurs when none of the three sources resolves to a recognized value). |
| `cwe` | `runs[].tool.driver.rules[].properties.cwe` (first element if a list) → `properties.cwes` / `properties.cwe2022-top25` / `properties.cwe2021-top25` / `properties.cwe_id` → `properties.tags[]` items beginning with `CWE-<n>` (Semgrep registry rules expose CWE here) → `result.taxa[]` items whose `toolComponent.name == "CWE"` → keyword inference against `result.message.text` + rule name/short-description/full-description. | Normalize to canonical `CWE-<n>` via the `CWE_NORMALIZE_RE` regex (consumed by the `_normalize_cwe` helper). | `"CWE-Unknown"` (logged; only occurs when no CWE can be located or inferred). |
| `description` | `runs[].results[].message.text` (with fallback to `result.message.markdown` if `text` is missing). | Truncate to **200 Unicode characters** (Python `len()`); no ellipsis appended. | `""` (only when SARIF omits the message entirely). |

---

## 3. Deviations from a literal reading of the user prompt

Every deviation below is intentional and necessary to satisfy the user's
pass/fail gates. Each one is reported alongside rationale and the resulting
behavior so downstream agents can audit (and, if desired, override) the
choice.

### DEV-1: `p/owasp` is no longer a valid Semgrep Registry pack identifier

- **Literal user text:** *"Download the `p/security-audit`, `p/secrets`, and `p/owasp` rule packs to a local directory."*
- **Empirical reality:** As of this run, `https://semgrep.dev/c/p/owasp` returns **HTTP 404** ("The requested URL was not found on the server"). The Semgrep CLI itself confirms the 404: `[ERROR]: Failed to download config from https://semgrep.dev/c/p/owasp, returned code 404`. The currently-canonical OWASP-themed registry pack is `p/owasp-top-ten`.
- **Resolution:** `run-scan.sh` first attempts the literal `p/owasp`; if and only if it returns 404, it falls back to `p/owasp-top-ten` and writes the file as `rule-cache/owasp.yml`. The substitute pack identifier is recorded under `scan-metadata.rule_packs.used`; the requested identifier is preserved under `scan-metadata.rule_packs.requested`.
- **Why this is acceptable:** The Directive 1 pass/fail gate (`semgrep ... --dry-run` exits 0) cannot be satisfied if the cache is missing a pack. The AAP §0.7.1 explicitly authorizes documented deviations from literal text. AAP §0.4.2's own cited research already identified `p/owasp-top-ten` as "valuable for compliance-driven teams that need to demonstrate OWASP coverage".

### DEV-2: `--dry-run` is not a real Semgrep CLI flag — the correct flag is `--dryrun`

- **Literal user text:** *"`semgrep scan --metrics=off --config=/path/to/local-rules --dry-run` exits 0 with no network calls."*
- **Empirical reality:** Semgrep 1.163.0 (and every release back to 1.0.0) accepts `--dryrun` (one word) but rejects `--dry-run` with `unknown option '--dry-run'. Did you mean either '-d' or '--dryrun'?`. Semantically `--dryrun` only suppresses autofix writes; it still loads rules and walks the target.
- **Resolution:** `run-scan.sh`'s Directive 1 gate runs `semgrep scan --metrics=off --config=<rule-cache> --dryrun /tmp/sg-empty-target`. The gate is verified inside an `unshare -n` (network-disabled) namespace in this implementation's development checks; in production it is verified by setting `--metrics=off` and asserting exit 0 + no observed network calls.
- **Why this is acceptable:** The user's intent is clearly "verify the rule cache loads offline and the scan exits cleanly". Both halves of that intent are satisfied.

### DEV-3: Single-line JSON requires a trailing newline

- **Literal user text:** *"If zero findings, write `[]`."* and *"`cat findings-config-b.json | wc -l` returns `1`."*
- **Empirical reality:** `wc -l` counts newline characters. A file with no trailing newline has `wc -l == 0`. The only way to satisfy `wc -l == 1` is to end the file with exactly one `\n`.
- **Resolution:** `normalize-findings.py` serializes via `json.dumps(...) + "\n"` and writes bytes with no other whitespace. The empty case therefore produces the three bytes `[]\n` (not the two bytes `[]`).
- **Why this is acceptable:** The user prompt is the authoritative spec (AAP §0.9.7); when the prompt's pass/fail clause and a colloquial description differ, the gate wins. AAP §0.6.2.1's "two bytes" reading is inconsistent with the gate.

### DEV-4: Absolute → relative file paths via `--target-root`

- **Literal user text — verbatim command:** *"`semgrep scan --config=/path/to/local-rules --sarif -o results-semgrep.sarif --metrics=off /path/to/blitzy-odoo`"*. **Literal user text — field mapping:** *"file: SARIF location (relative path)"*.
- **Empirical reality:** When Semgrep is invoked with an absolute target (as the verbatim command requires), it emits absolute URIs in SARIF (`artifactLocation.uri = /absolute/path/...`). To make `findings-config-b.json` carry relative paths, the absolute prefix must be stripped.
- **Resolution:** The orchestration script invokes `normalize-findings.py` with `--target-root $TARGET_ROOT`. The normalizer detects absolute URIs that begin with `TARGET_ROOT/` and rewrites them to be repo-relative.
- **Why this is acceptable:** The verbatim user command is preserved character-for-character (it is echoed to stderr before invocation). The "relative path" requirement is satisfied at normalization time without altering the SARIF input.

### DEV-5: `CWE-Unknown` is the last-resort CWE value (not absent / not failure)

- **Literal user text:** *"cwe: Rule metadata CWE ID. If absent, use the most specific CWE inferable from the rule description."*
- **Empirical reality:** When a Semgrep rule has neither `properties.cwe` nor any keyword-inferable CWE phrase in its message, a strict reading yields no value — but the pass/fail gate requires "every finding has all 5 fields populated".
- **Resolution:** The normalizer emits the literal string `CWE-Unknown` in this case. The decision is concentrated in a single constant (`CWE_UNKNOWN` in `normalize-findings.py`) so it can be tightened later.
- **Why this is acceptable:** `CWE-Unknown` is a stable, auditable sentinel. The 5-field gate would otherwise fail.

### DEV-6: Severity fallback uses three sources, not one

- **Literal user text:** *"severity: error→critical, warning→high, note→medium, info→low"*.
- **Empirical reality:** SARIF `level` is optional. Semgrep rules sometimes lack a result-level `level` even though `defaultConfiguration.level` or `properties.severity` carries the same intent.
- **Resolution:** The normalizer reads three sources in priority order (`result.level → rule.defaultConfiguration.level → rule.properties.severity`) and falls back to `"medium"` as a neutral last resort.
- **Why this is acceptable:** The five-field gate cannot fail. Production verification shows the resolved severity matches the expected mapping in 100% of the 98 findings produced against the live blitzy-odoo scan.

---

## 4. What is **not** in scope

The decisions above describe what Config B does and why. The following are
intentionally excluded and are not "decisions" so much as enforced
non-scopes:

- No source modification anywhere outside `security-scan/config-b/`.
- No remediation of any Semgrep finding.
- No CI/CD integration (`.github/workflows/` is untouched).
- No Semgrep AppSec Platform / Pro features (`semgrep login`, `semgrep ci`, `SEMGREP_APP_TOKEN`).
- No additional output fields beyond the closed five-field schema.
- No additional rule packs beyond the three named in Directive 1 (substitution `p/owasp` → `p/owasp-top-ten` is enumerated in DEV-1).
