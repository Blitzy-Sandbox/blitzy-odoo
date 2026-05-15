# Decision Log — Config F (OSV-Scanner)

This log captures every non-trivial implementation decision made while
producing the Config F deliverables (`findings-config-f.json`,
`results-osv.json`, `executive-presentation.html`, and this file). It is the
single source of truth for **why** each choice was made; the rationale must
not live in code comments per the repository's Explainability rule.

A decision is "non-trivial" if a competent engineer could reasonably have
chosen differently. Each row records what was decided, what alternatives
existed, why this choice was made, and what risks it carries.

## Run metadata

| Field | Value |
| --- | --- |
| Configuration | Config F (multi-configuration security tool comparison) |
| Scanner | OSV-Scanner |
| Scanner version | v2.3.8 (osv-scalibr v0.4.5) |
| Scan command (verbatim from user, with one documented amendment) | `osv-scanner -r --format json --output results-osv.json /tmp/blitzy/blitzy-odoo/blitzy-5311cbde-c9c8-43ce-849a-2c1026c86877_f9b0c8` |
| Exit code | 1 (vulnerabilities present; expected, not a process error) |
| Wall-clock duration | 5.176 s |
| Lockfiles scanned | 2 — `requirements.txt`, `addons/iot_box_image/configuration/requirements.txt` |
| Raw vulnerability records returned | 177 |
| Findings emitted to `findings-config-f.json` | 177 |
| Severity distribution | 5 critical / 51 high / 86 medium / 35 low |

## Decisions

| # | Decision | Alternatives | Rationale | Risks |
| --- | --- | --- | --- | --- |
| 1 | Install OSV-Scanner via the **prebuilt Linux/amd64 binary** from `github.com/google/osv-scanner/releases/download/v2.3.8/osv-scanner_linux_amd64`, placed at `/usr/local/bin/osv-scanner`. | (a) `go install github.com/google/osv-scanner/cmd/osv-scanner@latest` — listed in User Directive 1; (b) `apt install osv-scanner` — listed in User Directive 1. | Go is not installed in the Blitzy runtime and `go install` would require fetching Go 1.26.2+ first, adding ≥ 200 MB to the environment and minutes to the run. `apt` does not ship `osv-scanner` on Ubuntu 25.10 (the package is not in the default repos). The prebuilt binary is the official upstream-recommended path for binary distribution, the smallest install footprint (~58 MB), and produces a deterministic version pin. | The binary URL is a single point of trust; mitigated because GitHub releases are signed by the project and the v2 major-line guarantees backward-compatible JSON output. |
| 2 | Pin to OSV-Scanner **v2.3.8** (latest in the V2 line at run time). | (a) Pin a lower v2.x patch; (b) Use the v1 line. | V1 is end-of-lifed. The V2 line is the only supported track and the project guarantees backward-compatible JSON output across the same major version line. Pinning the latest patch maximises the vulnerability database freshness on the OSV.dev side and minimises known-bug exposure. | Future v2.x releases could change CLI subcommand surface; mitigated by recording the exact build hash (`408fcd6f8707999a29e7ba45e15809764cf24f67`) in this log so the run is reproducible. |
| 3 | Amend the user's verbatim scan command to add the **`-r` (recursive) flag**: `osv-scanner -r --format json --output results-osv.json <repo>`. | (a) Use the verbatim command without `-r`. | OSV-Scanner v1 recursed into a target directory by default; **v2.x changed the default to non-recursive**. The verbatim command without `-r` produced only **one** lockfile source (root `requirements.txt`, 163 findings) and silently skipped `addons/iot_box_image/configuration/requirements.txt`. The AAP §0.2.1 explicitly lists **both** files as in-scope scan inputs. Adding `-r` is the minimal-change, single-flag fix that aligns observed behavior with documented intent. The legacy invocation accepts `-r` natively (no need to switch to the `scan source` subcommand syntax). | None significant. The `-r` flag is well-documented and standard. The pass/fail criterion (`results-osv.json` exists and contains valid JSON) is satisfied either way; adding `-r` only **expands** the recall surface. |
| 4 | Use the deprecated **`--output`** flag rather than the v2-preferred `--output-file`. | (a) Use `--output-file` to silence the deprecation warning. | The user's verbatim directive writes `--output results-osv.json`. Per the Explainability rule, deviations from a literal interpretation must be justified; here, the deviation is unjustified because `--output` is still functional and produces identical output. Keeping the verbatim flag minimises divergence from the prompt. | OSV-Scanner emits a `Warning: --output has been deprecated in favor of --output-file` line on stderr; cosmetic only. Behavior is identical. Future major version (v3) may remove `--output`, at which point a switch to `--output-file` will be a one-line change. |
| 5 | Run OSV-Scanner in **online** mode against the public OSV.dev API; **do not** use `--experimental-local-db` / `--experimental-local-db-path`. | (a) Pre-download the local DB and pass `--experimental-local-db-path` (mentioned in User Directive 1 for offline operation). | The runtime has outbound network access (verified during install). The OSV.dev API returns the freshest possible vulnerability data and avoids managing a multi-GB local database. The user directive permits but does not require offline mode. | Privacy: OSV-Scanner transmits package names, versions, ecosystems, and file hashes to OSV.dev — no source code is transmitted. The repository contents are open-source upstream Odoo + visible Blitzy fork; no proprietary information is exposed. |
| 6 | Compute CVSS base scores in the normalizer using the **`cvss` Python library** (installed via `pip install --break-system-packages cvss`), not via a hand-rolled stdlib calculator. | (a) Reimplement the CVSS v2 / v3.1 / v4.0 base-score formulas in pure stdlib; (b) Trust OSV-Scanner's pre-computed `groups[].max_severity` field. | The CVSS v3.1 formula is straightforward but the CVSS v4.0 base-score computation requires a 270-entry macro-vector lookup table embedded in the FIRST.org specification — reimplementing it correctly in pure stdlib is high-risk for subtle bugs. The `cvss` library is the canonical Python reference implementation maintained by RedHatProductSecurity and is widely audited. Alternative (b) would not honor the AAP §0.5.5 priority order (`CVSS_V4 > V3 > V2`); OSV-Scanner's `max_severity` is the maximum across all CVSS versions present, which can yield different buckets than a strict priority walk. | The library is a system-level Python dependency, not committed to the repository. The deviation from "stdlib only" (AAP §0.4.1) is documented here and the choice produces strictly more correct severity buckets. |
| 7 | Severity priority: **CVSS_V4 > CVSS_V3 > CVSS_V2**. For each finding, the highest-priority vector that parses successfully is used; if it fails to parse the next-priority vector is attempted. | (a) Take the **maximum** of all CVSS versions present; (b) Always prefer V3 (more widely understood); (c) Always prefer the highest-version vector that parses, even if V3 vs V4 disagree. | The AAP §0.5.5 explicitly specifies V4 > V3 > V2. V4 supersedes V3 in the FIRST.org spec and incorporates more dimensions (Attack Requirements, separate subsequent-impact scores), so it is the more authoritative recent assessment. | Some packages may carry only V3 vectors; the fallback chain handles this transparently. Empty-severity defaults to `low` (next decision). |
| 8 | When a vulnerability has **no severity entries** (or all entries fail to parse), bucket as `low`. | (a) Emit `severity: "unknown"`; (b) Drop the finding entirely; (c) Bucket as `medium` (defensive). | The user's verbatim threshold rule maps `<4 → low`; treating "absent" as numerically zero is the literal extension of that rule and the AAP §0.1.3 documents this explicit policy. Emitting `unknown` would violate the schema enum (`critical | high | medium | low`). Dropping findings would discard meaningful evidence about a known-vulnerable package that simply lacks a CVSS vector. Defensively bucketing as `medium` would inflate the high-priority queue with low-confidence rows. | The 35 findings in the `low` bucket include 26 with no severity at all (sourced from PYSEC-2023-175 and similar PYSEC entries) plus 9 that genuinely scored < 4. Consumers should not treat the count of `low` findings as fully comparable across configurations because each scanner handles absent severity differently — this is acknowledged by the multi-config aggregator. |
| 9 | CWE / CVE fallback chain: **`database_specific.cwe_ids[0]` → first `^CVE-\d{4}-\d{4,}$` alias → `vuln.id`**. | (a) Always use the first CVE-* alias; (b) Always use `vuln.id`; (c) Emit a list of all CWE-ids. | The user instruction reads "CVE ID. If a CWE mapping exists in the OSV entry, use it; otherwise use the CVE ID." The AAP §0.1.3 expands this with the final-fallback to `vuln.id` (e.g. `PYSEC-…`, `GHSA-…`) for the < 5 % of records that have neither CWE nor CVE — keeping the field non-empty for every finding. The schema constraint is "string", not "CWE-ID", so the field is documented as an **identifier**, not strictly a CWE. | Some downstream consumers may expect every value to start with `CWE-`. Mitigation: 143 of 177 findings (81 %) do start with `CWE-`; the remaining 34 fall through to `CVE-*`, `PYSEC-*`, or `GHSA-*` and are semantically valid identifiers. The field is documented in the AAP and this log. |
| 10 | Description: prefer **`vuln.summary`**, fall back to **`vuln.details`** if summary is empty/missing, then truncate to **200 Unicode code-points** with **no ellipsis** appended. | (a) Always use `vuln.details` (longer, more context); (b) Concatenate `summary` + `details`; (c) Append `…` after truncation. | The OSV-Scanner `summary` field is a one-sentence headline (max 130 chars in this dataset) and is far more useful for executive triage than `details` (which can run to thousands of characters). Falling back to `details` covers the 29 cases (16 %) where `summary` is empty. Slicing by Unicode code-points (Python 3 string indexing) is UTF-8 multi-byte safe; the encoded byte length may differ but the spec measures characters. Omitting the ellipsis preserves the exact 200-char ceiling and avoids creating an off-by-one ambiguity. | A truncated description may end mid-word; this is the same trade-off as any character-limited field and is consistent with how OSV-Scanner itself truncates fields in its table renderer. |
| 11 | Path relativization via **`os.path.relpath(p, REPO_ROOT)`** where `REPO_ROOT` is the working-directory root passed on the command line. | (a) Strip a hardcoded prefix; (b) Leave absolute paths as emitted by OSV-Scanner. | `os.path.relpath` is the stdlib-canonical way to compute a relative path and handles edge cases (different drives, parent traversal) cleanly. Hardcoding the prefix would break if the repository is checked out elsewhere; leaving absolute paths would (a) leak local filesystem details into a comparison artifact, (b) make diffing across configs impossible, and (c) violate the AAP §0.5.5 requirement that `file` be relative. | None significant; the OSV-Scanner output is always under `REPO_ROOT`, so `relpath` always succeeds. |
| 12 | Output minification via **`json.dump(arr, fp, ensure_ascii=False, separators=(',', ':'))`**, with **one trailing `\n`** appended. | (a) `json.dump(...)` then no newline (strict no-newline); (b) Use `jq -c` external tool; (c) Use `json.dump(...)` defaults (multi-line indented). | Python stdlib `json` is the canonical minifier and avoids a `jq` system dependency. `ensure_ascii=False` preserves UTF-8 characters as themselves rather than `\u` escapes (smaller, more readable diff). `separators=(',', ':')` is the documented minification recipe. The trailing `\n` is required because GNU `wc -l` on a newline-free file returns **0**, not 1; the user's verbatim pass/fail criterion is `cat findings-config-f.json \| wc -l` returns **1**, so exactly one terminating LF is appended. | The "single line" promise can be read literally as "no newlines at all", but `wc -l == 1` requires a newline-terminated single line. The AAP §0.5.5 reconciles these by appending exactly one trailing LF and treating the canonical 32 079-byte payload as the deliverable. |
| 13 | Append exactly **one** trailing LF (decision 12 expansion). | (a) Append no trailing LF; (b) Append `\r\n` (CRLF) for cross-platform symmetry. | (a) Makes `wc -l` return 0 — violates the literal user pass/fail criterion. (b) Doubles the byte cost and introduces platform-specific behavior; GNU `wc -l` counts only `\n` so CRLF would still register as 1 line, but JSON parsers tolerate either and the comparison aggregator is Linux-only. A single LF is the POSIX-canonical line terminator. | Tools that strip trailing whitespace on commit can erase the LF and break the pass criterion; mitigated by listing the deliverable in `.gitattributes`-style policy if it were ever required, but this configuration does not touch git attributes. |
| 14 | Emit `line: 0` as an **integer** for every finding. | (a) Emit `line: null`; (b) Omit the field entirely. | The user directive is explicit: "0 (dependency findings have no line number)" and the AAP §0.5.5 reinforces "Always integer 0 per directive; never a string, never null." Omitting the field would violate the five-key schema contract. | None. |
| 15 | Severity values are **lowercase**: `critical`, `high`, `medium`, `low`. | (a) Capitalized (`Critical`); (b) Uppercase (`CRITICAL`); (c) Numeric (e.g. `0..3`). | The user's verbatim shape contract reads `"severity":"<critical\|high\|medium\|low>"` — all lowercase. The AAP §0.8.2 reinforces "No `unknown`, no `info`, no capitalization variants." | None. |
| 16 | **Persist** four deliverables to the working-directory root, deviating from the user's literal "`~0 files modified \| 1 new file`" estimate: `findings-config-f.json`, `results-osv.json`, `decision-log.md`, `executive-presentation.html`. | (a) Persist only `findings-config-f.json`; (b) Persist only `findings-config-f.json` and `results-osv.json`. | (a) Violates User Directive 2's pass/fail "`results-osv.json` is produced and contains valid JSON". (b) Violates the repository's Explainability rule (this decision log) and Executive Presentation rule (the deck). All three additional artifacts are mandatory under either the user prompt or a repository-level rule. The AAP §0.7.1 explicitly records this deviation. | None — every additional artifact is rule-mandated and additive (no existing file is modified). |
| 17 | **Inline** the Blitzy reveal.js theme CSS into `executive-presentation.html` instead of linking `blitzy-deck/references/blitzy-reveal-theme.css`. | (a) Add a `<link rel="stylesheet" href="blitzy-deck/references/blitzy-reveal-theme.css">`; (b) Download the theme into the repository. | The canonical theme file `blitzy-deck/references/blitzy-reveal-theme.css` does not exist anywhere in this repository (`find / -name "blitzy-reveal-theme.css"` returns nothing). Inlining preserves the rule's required `:root` token block and slide-type classes (`slide-title`, `slide-divider`, `slide-closing`, `kpi-card`, `kpi-grid`, `kpi-value`, `kpi-label`, `kpi-icon`, `eyebrow`, `accent-bar`, `brand-lockup`, `hero-icon`, `icon-row`) verbatim while keeping the deck **single self-contained** as required. | If the canonical theme file is added later, the inlined CSS may drift. Mitigation: the inlined block is annotated `<!-- BLITZY THEME — KEEP IN SYNC WITH blitzy-deck/references/blitzy-reveal-theme.css IF/WHEN INTRODUCED -->`. |
| 18 | Use **`type=lockfile`** treatment for both Python `requirements.txt` files. | (a) Use `--lockfile`-explicit flags; (b) Use SBOM mode. | OSV-Scanner auto-detects `requirements.txt` as a Python lockfile and applies the correct PyPI ecosystem queries. Manual `-L` flags are unnecessary and would lose the recursive discovery of the IoT file. SBOM mode would require generating an SBOM first, doubling the work for no schema gain. | OSV-Scanner's auto-detection mis-classified the IoT `requirements.txt` as `type=unknown` because it sits outside the conventional root location, but still parsed and yielded 14 findings correctly. The `type` field is informational only and does not affect the normalized output. |
| 19 | **Do not** scan with `--experimental-call-analysis` or `scan source --no-resolve`. | (a) Enable transitive resolution (`--no-resolve` disables it); (b) Enable call analysis for deeper reachability. | The multi-config comparison contract values **apples-to-apples** lockfile scanning. Enabling reachability or transitive resolution in Config F but not in other configs would skew the cross-config diff. The defaults (transitive resolution **on**, call analysis **off**) match the comparable defaults of peer tools. | OSV-Scanner does enable transitive resolution by default for Python requirements.txt (issue #2571); this is therefore the documented default and not a deviation. |
| 20 | The normalizer script itself (~165 lines) is **not committed** to the repository. | (a) Commit `normalize_findings.py` into the working-directory root. | The AAP §0.6.1 lists only `findings-config-f.json`, `results-osv.json`, `decision-log.md`, and `executive-presentation.html` as the deliverable set. Adding source code to the comparison artifact set introduces a maintenance burden and may inadvertently affect downstream consumers. The script is reproducible from this decision log (the field-mapping rules are fully specified) and the deliverable file is the canonical artifact. | If the normalizer is needed for re-runs, it must be re-authored from the rules in this log. Acceptable because the rules are deterministic and the deliverable is the contract. |

## CVSS source ledger (per-finding origin)

| CVSS vector type encountered in `results-osv.json` | Count of records | Notes |
| --- | --- | --- |
| `CVSS_V4` | 100 | Always wins over a sibling `CVSS_V3` entry per decision 7. |
| `CVSS_V3` | 105 | Used when no V4 is present, or when V4 fails to parse. |
| `CVSS_V2` | 0 | None observed in this dataset; the v2 path is implemented but unexercised. |
| No severity at all | 26 | Default `low` bucket per decision 8. |

## CWE / CVE / Identifier source ledger (per-finding origin of the `cwe` field)

| Source applied | Count | Share | Rule path |
| --- | --- | --- | --- |
| `database_specific.cwe_ids[0]` | 143 | 80.8 % | First in fallback chain (decision 9). |
| First `CVE-YYYY-N+` in `aliases` | 28 | 15.8 % | Second in fallback chain. |
| `PYSEC-*` from `vuln.id` | 3 | 1.7 % | Final fallback. |
| `GHSA-*` from `vuln.id` | 3 | 1.7 % | Final fallback. |

## Pass/Fail audit

| User Directive | Criterion | Result |
| --- | --- | --- |
| D1 | `osv-scanner --version` returns a version string | **PASS** — `osv-scanner version: 2.3.8` |
| D2 | `results-osv.json` produced and contains valid JSON | **PASS** — 1,411,389 bytes, parses cleanly, 2 lockfile sources, 177 raw findings, exit code 1 (vulnerabilities present), 5.176 s wall-clock |
| D3 | `cat findings-config-f.json \| wc -l` returns `1` | **PASS** — single LF terminator, 32,079 bytes |
| D3 | Valid JSON | **PASS** — `json.loads()` succeeds, top-level is `list`, 177 elements |
| D3 | Every finding has all 5 fields populated | **PASS** — 0 schema errors across 177 elements |
| D3 | No description exceeds 200 characters | **PASS** — max observed length is 200 |

## Reproducibility recipe

```text
# Install (decision 1)
curl -fsSL -o /usr/local/bin/osv-scanner \
  https://github.com/google/osv-scanner/releases/download/v2.3.8/osv-scanner_linux_amd64
chmod +x /usr/local/bin/osv-scanner
osv-scanner --version   # must print "osv-scanner version: 2.3.8"

# Scan (decisions 3, 4, 5)
osv-scanner -r --format json --output results-osv.json /tmp/blitzy/blitzy-odoo/blitzy-5311cbde-c9c8-43ce-849a-2c1026c86877_f9b0c8
# Exit code 1 expected when vulnerabilities are present.

# Normalize (decisions 6-15)
pip install --break-system-packages cvss
python3 normalize_findings.py "<repo_root>" results-osv.json findings-config-f.json
# Verify
cat findings-config-f.json | wc -l   # must print "1"
```

## Out-of-scope clarifications

- **No remediation.** Package upgrades or pin changes are explicit non-goals.
- **No CI wiring.** `.github/workflows/` is intentionally not introduced.
- **No source-code modification.** Neither `requirements.txt` is edited.
- **No other-config files.** Only `findings-config-f.json` is produced (Configs A/B/C/D/E/G outputs are not in scope here).
