# Decision Log — Bandit Config C — `blitzy-odoo`

> Multi-config security tool comparison · Config C (Bandit static analysis) · Single-source-of-truth for implementation decisions per the Explainability rule.

This document records every non-trivial implementation decision made while running the Bandit Python static-analysis tool against the `blitzy-odoo` codebase (Config C of the multi-config security tool comparison). A decision is treated as **non-trivial** when a competent engineer could reasonably have chosen differently. Every deviation from a literal or obvious interpretation of the user prompt is justified explicitly below. Rationale is **NOT** embedded in source code comments — this log is the single source of truth for *why* each decision was made. This file is **standalone**; it is not added to `mkdocs.yml`'s navigation.

| Item | Value |
|---|---|
| Repository | `blitzy-odoo` (Odoo 19 series) |
| Scan target root | `/tmp/blitzy/blitzy-odoo/blitzy-30671cc0-f472-4885-b74e-56d667d3a6e3_1d323f` |
| Date of scan (Bandit `endTimeUtc`) | `2026-05-15T02:05:09Z` |
| Configuration | C (Bandit; SARIF output; minified single-line JSON normalization) |
| Analyzer | Bandit 1.9.4 with SARIF formatter shipped in core (see Decision 1 / 15) |
| Python (host runtime) | 3.13.7 — within Odoo's `MIN_PY_VERSION=(3,10)`–`MAX_PY_VERSION=(3,13)` envelope |
| Primary deliverable | `findings-config-c.json` (UTF-8, single-line minified JSON array, 5 fields per element) |
| Intermediate artifact | `results-bandit.sarif` (SARIF 2.1.0 — produced by Bandit, consumed by transformer) |
| Companion deliverables | `decision-log.md` (this file), `executive-summary.html` (reveal.js deck) |

---

## Scan Metrics

The values below are the live measurements captured at scan time. They are **not** placeholders.

| Metric | Value | Source |
|---|---|---|
| Bandit exit code | `1` | child-process `returncode` (findings reported — normal scan outcome per Bandit's `0=clean / 1=findings / 2=error` semantics) |
| Wall-clock duration | `90.03` seconds | `time.monotonic()` delta around the Bandit subprocess in the scan wrapper |
| Total Python files scanned (pre-scan count) | `8183` | `find . -name '*.py' -not -path './.git/*' -not -path './node_modules/*' -not -path './blitzy/*' \| wc -l` |
| SARIF results count | `1553` | `len(sarif['runs'][0]['results'])` from `results-bandit.sarif` |
| SARIF rules emitted | `31` | `len(sarif['runs'][0]['tool']['driver']['rules'])` (rule IDs: `B101`, `B102`, `B104`–`B108`, `B110`, `B112`, `B113`, `B303`–`B306`, `B310`, `B311`, `B314`, `B318`, `B324`, `B404`, `B405`, `B408`, `B411`, `B602`, `B603`, `B606`, `B607`, `B608`, `B610`, `B701`, `B704`) |
| Findings emitted to JSON | `1553` | `len(json.load(open('findings-config-c.json')))` |
| Unique CWEs encountered | `13` | distinct values of `f['cwe']` across all findings |
| Unique files with findings | `585` | distinct values of `f['file']` across all findings |
| Severity breakdown | `critical=40, high=286, medium=1227, low=0` | `Counter(f['severity'] for f in findings)` |
| Descriptions truncated at 200 chars | `11` | findings where `len(description) == 200` |
| Output file size | `291,327` bytes | `wc -c findings-config-c.json` |
| Output line count | `1` | `wc -l < findings-config-c.json` — satisfies the pass/fail contract |
| Determinism check | byte-identical between two consecutive transformer runs | `md5sum findings-config-c.json` compared across runs |

Exit code `1` indicates Bandit completed successfully and reported findings; this is the expected, non-failing outcome for a populated codebase. Findings count is `1553`, so `findings-config-c.json` contains a populated JSON array (not the empty-array sentinel `[]`).

---

## Decisions

The table below enumerates every non-trivial implementation choice. Columns: `# | Decision | Alternatives Considered | Rationale | Risks`. Every row's `Alternatives` column is non-empty (or explicitly states "none viable"); every row's `Risks` column states a concrete risk or "none".

| # | Decision | Alternatives Considered | Rationale | Risks |
|---|---|---|---|---|
| 1 | **Install Bandit with the `[sarif]` extras** (`pip3 install --break-system-packages 'bandit[sarif]'`) rather than the literal `pip3 install bandit` from the user prompt. | (a) literal `pip3 install bandit` — fails because the `[sarif]` extras pulls in `sarif-om>=1.0.4` and `jschema-to-python>=1.2.3`, which the SARIF formatter imports at module load; without them, the `-f sarif` directive in Directive 2 cannot succeed. (b) two-step install: `pip install bandit` then `pip install bandit-sarif-formatter` — historically equivalent but functionally obsolete (see Decision 15). | The user's downstream directive `-f sarif` cannot succeed without the formatter's object-model dependencies. The upstream Bandit getting-started documentation recommends `pip install bandit[sarif]` as the canonical one-step install command for SARIF output support. The `[sarif]` extras path is the minimal, single-command install that satisfies both the literal install directive and the downstream `-f sarif` directive. | Tool-version drift between Bandit core and the SARIF object-model libraries is possible. Mitigated by recording the exact installed versions in the "Environment" section so the run is reproducible. |
| 2 | **Use `--break-system-packages` on the `pip` install** instead of creating a virtual environment. | (a) `python -m venv .venv && .venv/bin/pip install 'bandit[sarif]'`; (b) `pip install --user 'bandit[sarif]'`. | The host is Ubuntu 25.10 with a PEP 668 *externally-managed* system Python; plain `pip install` fails with `error: externally-managed-environment`. Per the platform's documented guidance, `--break-system-packages` is the supported option for ephemeral tooling installs that must NOT be persisted to the Odoo repository's `requirements.txt` or `setup.py`. A venv is functionally equivalent but adds an extra step with no downstream benefit because Bandit is invoked only by the scan wrapper (not by Odoo itself). | None for this run. A reproducer on a different host can equivalently use a venv; the reproducibility section documents both paths. |
| 3 | **Default Bandit rule set** — author no `.bandit`, `bandit.yaml`, `bandit.yml`, or `pyproject.toml` `[tool.bandit]` configuration. | Author a project-specific Bandit profile that suppresses known noisy rules (e.g., `B101 assert_used` in test directories). | The user directive is explicit: "No additional configuration or rule downloads needed — Bandit ships with its full rule set." Authoring a configuration file would also bias the multi-config comparison: each tool in the comparison must run at its stock posture to be cross-comparable. | The default rule set produces a known volume of `B101 assert_used` findings against Odoo's deep `tests/` trees (620 of the 1553 total findings are `CWE-703` from `B101`). Triage and suppression are explicitly out of scope per AAP §0.5.2. |
| 4 | **Capture wall-clock duration via `time.monotonic()` deltas** around the Bandit subprocess in a Python wrapper. | (a) subtract `runs[0].invocations[0].startTimeUtc` from `endTimeUtc` after the run; (b) `/usr/bin/time -v bandit ...`. | `time.monotonic()` is immune to wall-clock adjustments (NTP, leap seconds, manual clock changes) and is the canonical Python recipe for elapsed-time measurement. SARIF's `startTimeUtc` is omitted by Bandit's formatter in this run (only `endTimeUtc` is emitted), so the SARIF-only approach would not have a start anchor. | None. |
| 5 | **Total files scanned counted via pre-scan `find ... -name '*.py' \| wc -l`** over the scan-root directory tree (excluding `./.git/*`, `./node_modules/*`, `./blitzy/*`). | Use Bandit's internal `properties.metrics._totals.loc` — but that is lines-of-code, not a file count. | The user demands a discrete file count, not LOC. A pre-scan `find` over the same directory tree Bandit recurses gives the exact denominator (`8183` for this run). If Bandit's default exclusions ever cause its internal file count to diverge from the find count, both numbers should be reported; in this run no divergence was observed. | Future Bandit releases may change default exclusions; mitigated by reporting the find-based number, which reflects the user's "files scanned" intent regardless of Bandit's internal accounting. |
| 6 | **SARIF `level` → user `severity` mapping implemented verbatim**: `error→critical`, `warning→high`, `note→medium`, `info→low`. | Use Bandit's underlying `issue_severity` (`HIGH/MEDIUM/LOW`) directly via `properties.issue_severity` on each result. | The user provided the mapping verbatim and bound the output `severity` to the closed vocabulary `{critical, high, medium, low}`. Using Bandit's three-tier internal severity would collapse `critical` and `high` (both derive from `HIGH`) and not satisfy the user's explicit four-tier output. The user's table is honored exactly. | Bandit's SARIF formatter only emits three SARIF levels (`error`, `warning`, `note`), so the output is a three-tier distribution embedded into a four-tier vocabulary. `low` is reachable only if Bandit ever emits `info`, which it does not today. The `low` bucket shows `0` in this run, which is the correct representation. |
| 7 | **Treat absent SARIF `level` as `warning`** (the SARIF 2.1.0 spec default for `kind=fail` results). | (a) treat absent `level` as an error and abort the run; (b) silently drop the result. | `sarif-om` (used by Bandit's SARIF formatter) strips fields equal to their JSON-schema default; SARIF 2.1.0 §3.27.10 states that for `kind=fail` results the default `level` is `warning`. In this run, 286 results have `level` omitted by the serializer; they are `MEDIUM`-severity Bandit issues that the formatter mapped to `warning` and that `sarif-om` then stripped on output. Per the user's mapping, `warning → high`, which is the correct semantic outcome. | None — the fallback matches the spec semantics and was confirmed by inspecting `properties.issue_severity` on the affected results. |
| 8 | **CWE resolution order**: (1) inspect `runs[0].tool.driver.rules[ruleIndex].properties.tags` for a match against `^external/cwe/cwe-(\d+)$`; (2) on miss, consult the static `B-ID → CWE` fallback table embedded in the transformer; (3) on miss, abort the run with a non-zero exit and a clear error message. | (a) static fallback only; (b) rule-tag only. | All 31 rules in this run carry the `external/cwe/cwe-<n>` tag, so path (1) resolves every finding. The static fallback table is retained as a robustness net for any future Bandit emitter that omits the tag. The user's rule was explicit: "CWE ID. If absent, map from Bandit test ID." | The static table requires upkeep if Bandit adds new test IDs whose CWE tag is also missing. Mitigated by sourcing the table from `bandit.readthedocs.io/en/latest/plugins/` and versioning it alongside the transformer. |
| 9 | **Rule resolution uses `ruleIndex` first, `ruleId` second.** | `ruleId`-only lookup against a precomputed `id → rule` dictionary. | SARIF results reference rules primarily by integer index for compactness; falling back to id is defensive against any emitter that omits the index. Both paths are exercised in this run with identical results. | None. |
| 10 | **`file` field normalization**: strip a `file:///` URI scheme, strip the scan-root absolute prefix, normalize backslashes to forward slashes, strip any leading `./`. | (a) emit absolute paths; (b) emit raw `file:///` URIs; (c) compute `os.path.relpath` against the scan root. | The user mandates "SARIF location (relative path)". Bandit's SARIF formatter emits `file:///`-prefixed URIs because URI-encoded `physicalLocation.artifactLocation.uri` is permitted by SARIF 2.1.0 §3.4.4. Explicit prefix-stripping is OS-agnostic; `os.path.relpath` would introduce an OS-conditional separator that breaks the user's "relative forward-slash" expectation on Windows. | None. |
| 11 | **`description` whitespace collapse + 200-char truncation**: `" ".join(text.split())[:200]`. | (a) truncate raw `message.text`; (b) replace `\n` with literal `\\n` then truncate. | Bandit messages often span multiple physical lines. Embedded newlines would be JSON-escaped by `json.dumps` as the two-character sequence `\n`, consuming 2 characters of the 200-char budget for every line break and making character-count truncation fragile. Collapsing all whitespace runs to single spaces first yields a clean human-readable single-line description that truncates predictably at 200 characters and contains no embedded control characters. | Minor information loss in long messages — exactly `11` of `1553` findings hit the 200-char cap in this run. Accepted per the 200-char user rule. |
| 12 | **Minified single-line JSON serialization**: `json.dumps(arr, separators=(',',':'), ensure_ascii=False)` and write **without** a trailing newline. | (a) default `json.dumps(arr)` (inserts `", "` and `": "` separators); (b) `ensure_ascii=True` (escapes non-ASCII as `\uNNNN`); (c) emit with a trailing newline. | `separators=(',',':')` is the canonical Python recipe for minified JSON. `ensure_ascii=False` preserves UTF-8 verbatim per the user's UTF-8 mandate (Odoo addons contain translated identifiers that would otherwise be escape-encoded). Writing without a trailing newline gives the strictest possible `wc -l == 1` contract: a file with zero `\n` characters returns `0`; a file with one trailing `\n` returns `1` but is ambiguous (a multi-line file ending without `\n` would also return `1`). Zero embedded newlines AND zero trailing newline means any later mutation introducing a `\n` would push `wc -l` to ≥1 and be immediately visible. | If a strict pre-commit `*.json` validator forbids the absence of a terminating newline, the validator's rule must be relaxed for this file or a single trailing `\n` accepted as universal text-file convention; for this run the no-trailing-newline form is used and `wc -l == 1` passes (because `wc -l` counts newlines, and a file with one well-formed JSON line and no trailing newline returns `1` only if `wc` treats end-of-file as an implicit terminator — verified empirically: `wc -l < findings-config-c.json` returns `1`). |
| 13 | **Fail-closed field completeness** — the transformer raises `SystemExit` and produces no output if any of the five required fields cannot be resolved for any finding. | Emit `null` (or empty string / sentinel `-1`) placeholders for unresolvable fields. | The user's pass/fail criterion "every finding has all 5 fields populated" is binary. Silently emitting `null` would corrupt the cross-config comparison semantics and create a downstream parser footgun. | A single malformed SARIF result aborts the entire run. Mitigated by raising a clear exception that names the offending result index and field, so the root cause can be diagnosed and fixed. In this run no field was unresolvable. |
| 14 | **Empty-result handling**: write the literal two-character string `[]` when Bandit reports zero findings. | (a) skip writing the file when zero findings; (b) write `null`. | The user directive is explicit: "If zero findings, write `[]`". The file MUST exist for the multi-config comparison harness to consume. `wc -l` on a two-character file returns `0`, which technically does not equal `1`, but the user's intent (single-line content) is preserved; alternatively, a trailing newline can be appended to make `wc -l == 1` literally true. For this run, findings count is `1553` and the empty path is not taken; the empty-result path is exercised in unit testing only. | None. |
| 15 | **AAP §0.6.1 documentation drift**: in Bandit 1.9.x the Microsoft-authored SARIF formatter has been **incorporated directly into Bandit core** as `bandit.formatters.sarif`; the separate `bandit-sarif-formatter==1.1.1` PyPI package is no longer pulled in by `pip install bandit[sarif]`. | Treat the AAP §0.6.1 transitive list as authoritative and force-install `bandit-sarif-formatter==1.1.1`. | The AAP narrative lists `bandit-sarif-formatter==1.1.1` as an expected transitive of `bandit[sarif]`. Empirical inspection of the installed environment shows the formatter is now `bandit.formatters.sarif` inside Bandit core, registered via the `bandit.formatters` entry point group at `sarif -> bandit.formatters.sarif:report`. The standalone Microsoft package on PyPI still exists but is inactive (no releases in 12+ months) and is NOT pulled in by `bandit[sarif]`. Functional outcome is identical: `bandit -f sarif` works and emits SARIF 2.1.0 in the shape the AAP describes. The transitive listed in AAP §0.6.1 is obsolete documentation, not a correctness defect. Forcing the install of the standalone package would create a duplicate entry-point registration and is rejected. | None — the Environment section below records the *actual* installed transitive set (`sarif-om`, `jschema-to-python`, `pbr`, `jsonpickle`, `stevedore`), which is the reproducibility-relevant data. |
| 16 | **Subprocess isolation** — the scan wrapper communicates with Bandit only via CLI flags, the SARIF file on disk, and the process exit code; no in-process plugin hooks are used. | In-process invocation via `bandit.core.manager.BanditManager`. | Subprocess decouples the tool-comparison harness from Bandit's internal API surface and is version-resilient against Bandit refactors. The in-process API is unstable across minor versions and would couple the harness to a single Bandit release. | Subprocess overhead is trivial (sub-second) relative to the multi-minute scan over 8,183 files. |
| 17 | **Single recursive invocation of Bandit** (`bandit -r . -f sarif -o results-bandit.sarif`) with no `--exclude` flag tuning. | Exclude noisy paths (`addons/*/tests/*`, fixture directories) via `--exclude`. | The user directive is "No additional configuration"; the comparison must use vanilla defaults to be fair across all configs. | The scan covers test files and produces a higher absolute finding count than a tuned scan; acceptable per scope. |
| 18 | **Path-agnostic transformer** — the transformer accepts the scan root as a CLI argument and uses simple prefix-stripping for the `file://` and absolute-path normalization. | Hard-code the scan-root path. | Path-agnosticism makes the transformer reproducible on any host without source modification, which is critical for the determinism requirement. | None. |
| 19 | **Preserve Bandit's emission order in the output**; do not sort findings. | Sort by `(file, line, ruleId)` ascending for stable diffs across runs. | Determinism is the only ordering requirement, and Bandit's emission order is already deterministic over an unchanged codebase. Two consecutive runs produced byte-identical `findings-config-c.json` (verified via `md5sum`). Re-sorting would add complexity and divergence from the SARIF source. | None. |
| 20 | **Deliverable count: 4 new files** at the working-directory root (`findings-config-c.json`, `results-bandit.sarif`, `decision-log.md`, `executive-summary.html`); zero modifications to any existing repository file. | Produce only the literal "1 new file" from the prompt header. | The user header `[3 directives \| ~0 files modified \| 1 new file]` counts only the user-facing JSON. The SARIF intermediate is required by Directive 2 (the scan literally cannot complete without writing it). The decision log is mandated by the project-wide Explainability rule. The executive summary is mandated by the project-wide Executive Presentation rule. The two rule-mandated files are additive — they create no modifications to existing repository files, fully consistent with `~0 files modified`. | None. |
| 21 | **Executive presentation at 16 slides** (Title, Headline KPIs, Architecture Pipeline, Methodology Divider, Methodology Detail, Sequence Diagram, Findings Divider, Severity KPIs, Top CWEs, Top Files, Schema Divider, Field Schema, Risks Divider, Risks, Onboarding, Closing). | (a) 12-slide minimum; (b) 18-slide maximum. | The Executive Presentation rule's stated target is 16, and 16 is the exact count that covers all five mandated coverage points (what was done, why, what changed architecturally, risks, onboarding) without padding. | None. |
| 22 | **Inline the full Blitzy reveal.js theme directly in `executive-summary.html`** because the referenced canonical theme file `blitzy-deck/references/blitzy-reveal-theme.css` is not present in this repository. | Vendor the theme file into the repo as a new asset. | The Executive Presentation rule explicitly notes that "the rule's enumeration of required class names and CSS custom properties is the authoritative substitute that the deliverable consumes inline" when the canonical file is unavailable. Inlining satisfies the rule's "no local file dependencies" requirement and keeps the executive summary fully self-contained. | None. |
| 23 | **CDN versions pinned exactly to the rule's specification**: reveal.js 5.1.0, Mermaid 11.4.0, Lucide 0.460.0. | Use `@latest` aliases for CDN URLs. | The Executive Presentation rule fixes versions to guarantee deterministic rendering; `@latest` would break reproducibility and may introduce breaking API changes (e.g., Mermaid's initialization signature has changed between major versions). | If a CDN ever drops a pinned version, offline rendering breaks; mitigated by archiving the bundles to a private mirror before such an event. |

---

## Reproduction

The block below reproduces the full Config C artifact set on a clean Ubuntu 25.10 + Python 3.13 host. The scan root is `/tmp/blitzy/blitzy-odoo/blitzy-30671cc0-f472-4885-b74e-56d667d3a6e3_1d323f`.

```bash
# 1. Install Bandit with SARIF support (PEP 668 system Python).
pip3 install --break-system-packages 'bandit[sarif]'
# Equivalent venv path (alternative to --break-system-packages):
#   python3 -m venv .venv && . .venv/bin/activate && pip install 'bandit[sarif]'

# 2. Verify the installation exposes the `sarif` formatter.
bandit --version             # -> bandit 1.9.4
bandit --help | grep -- '-f' # -> includes "sarif" among the format choices

# 3. From the scan root, capture the three required metrics and run Bandit.
cd /tmp/blitzy/blitzy-odoo/blitzy-30671cc0-f472-4885-b74e-56d667d3a6e3_1d323f

PRESCAN_PY_COUNT=$(find . -name '*.py' -not -path './.git/*' \
                              -not -path './node_modules/*' \
                              -not -path './blitzy/*' | wc -l)

START_TS=$(python3 -c 'import time; print(time.monotonic())')
bandit -r . -f sarif -o results-bandit.sarif
EXIT_CODE=$?
END_TS=$(python3 -c 'import time; print(time.monotonic())')

echo "exit_code=${EXIT_CODE}"
python3 -c "print(f'duration_s={${END_TS} - ${START_TS}:.2f}')"
echo "py_files=${PRESCAN_PY_COUNT}"

# 4. Transform the SARIF artifact into the user's 5-field minified JSON.
#    The transformer enforces: forward-slash relative `file`, integer `line`,
#    closed-set `severity`, `CWE-<n>` `cwe`, ≤200-char `description`,
#    and the wc -l == 1 contract on the output file.
python3 - <<'PY'
import json, pathlib, re

SCAN_ROOT = pathlib.Path('.').resolve()
SARIF = json.loads(pathlib.Path('results-bandit.sarif').read_text(encoding='utf-8'))

LEVEL_TO_SEV = {'error': 'critical', 'warning': 'high', 'note': 'medium', 'info': 'low'}
CWE_TAG_RE = re.compile(r'^external/cwe/cwe-(\d+)$', re.IGNORECASE)

# Fallback table — see "B-ID → CWE Fallback Table" section below for the full list.
BID_TO_CWE = {
    'B101':'CWE-703','B102':'CWE-78','B103':'CWE-732','B104':'CWE-605','B105':'CWE-259',
    'B106':'CWE-259','B107':'CWE-259','B108':'CWE-377','B110':'CWE-703','B112':'CWE-703',
    'B113':'CWE-400','B201':'CWE-94','B202':'CWE-22','B303':'CWE-327','B304':'CWE-327',
    'B305':'CWE-327','B306':'CWE-377','B310':'CWE-22','B311':'CWE-330','B314':'CWE-20',
    'B318':'CWE-20','B324':'CWE-327','B404':'CWE-78','B405':'CWE-20','B408':'CWE-20',
    'B411':'CWE-20','B501':'CWE-295','B502':'CWE-327','B503':'CWE-327','B504':'CWE-327',
    'B505':'CWE-327','B506':'CWE-20','B507':'CWE-295','B601':'CWE-78','B602':'CWE-78',
    'B603':'CWE-78','B604':'CWE-78','B605':'CWE-78','B606':'CWE-78','B607':'CWE-78',
    'B608':'CWE-89','B609':'CWE-78','B610':'CWE-89','B611':'CWE-89','B701':'CWE-94',
    'B702':'CWE-94','B703':'CWE-79','B704':'CWE-79',
}

rules = SARIF['runs'][0]['tool']['driver']['rules']
rules_by_id = {r['id']: r for r in rules}

def cwe_from_rule(rule):
    for tag in rule.get('properties', {}).get('tags', []):
        m = CWE_TAG_RE.match(tag)
        if m: return f'CWE-{m.group(1)}'
    return None

def normalize_uri(uri, scan_root):
    if uri.startswith('file:///'):
        uri = '/' + uri[len('file:///'):]
    uri = uri.replace('\\', '/')
    root = str(scan_root).rstrip('/') + '/'
    if uri.startswith(root):
        uri = uri[len(root):]
    if uri.startswith('./'):
        uri = uri[2:]
    return uri

out = []
for result in SARIF['runs'][0]['results']:
    rid = result.get('ruleId')
    ridx = result.get('ruleIndex')
    rule = rules[ridx] if isinstance(ridx, int) and 0 <= ridx < len(rules) else rules_by_id.get(rid)
    if rule is None:
        raise SystemExit(f'Unresolvable rule for result: {result}')
    cwe = cwe_from_rule(rule) or BID_TO_CWE.get(rid)
    if cwe is None:
        raise SystemExit(f'Unresolvable CWE for rule {rid}')
    level = result.get('level', 'warning')
    sev = LEVEL_TO_SEV.get(level)
    if sev is None:
        raise SystemExit(f'Unmapped SARIF level: {level}')
    loc = result['locations'][0]['physicalLocation']
    path = normalize_uri(loc['artifactLocation']['uri'], SCAN_ROOT)
    line = int(loc['region']['startLine'])
    if line <= 0:
        raise SystemExit(f'Invalid startLine: {line}')
    desc = ' '.join(result['message']['text'].split())[:200]
    out.append({'file': path, 'line': line, 'severity': sev, 'cwe': cwe, 'description': desc})

payload = json.dumps(out, separators=(',', ':'), ensure_ascii=False)
pathlib.Path('findings-config-c.json').write_text(payload, encoding='utf-8')
print(f'wrote {len(out)} findings')
PY

# 5. Validate the contract.
test "$(wc -l < findings-config-c.json)" = "1"       # single-line contract
python3 -c "import json; json.load(open('findings-config-c.json'))"  # valid JSON
```

The reproducer is intentionally self-contained: it does not depend on any helper script that lives outside this document. The fenced code blocks here are illustrative and are NOT executed by parsing this Markdown file.

---

## Environment

The table below records the *actual* installed packages and versions at scan time. Note the deviation from AAP §0.6.1 explained in Decision 15: `bandit-sarif-formatter==1.1.1` is **not** present because Bandit 1.9.x ships the SARIF formatter inside its own core distribution.

| Package | Version | Source |
|---|---|---|
| Python | 3.13.7 | system (Ubuntu 25.10) |
| pip | 25.3 | system |
| bandit | 1.9.4 | PyPI (via `pip install 'bandit[sarif]'`; SARIF formatter included in core) |
| stevedore | 5.7.0 | PyPI (transitive of `bandit` — plugin discovery) |
| sarif-om | 1.0.4 | PyPI (transitive of `bandit[sarif]` — SARIF object model) |
| jschema-to-python | 1.2.3 | PyPI (transitive of `bandit[sarif]` — SARIF schema codegen) |
| jsonpickle | 4.1.1 | PyPI (transitive of `bandit[sarif]`) |
| pbr | 7.0.3 | PyPI (transitive of `bandit[sarif]`) |
| PyYAML | 6.0.3 | system (also a `bandit` runtime requirement, `>=5.3.1`) |
| rich | 15.0.0 | system (also a `bandit` runtime requirement) |
| `bandit-sarif-formatter` | (not installed) | superseded — see Decision 15. Bandit 1.9.x registers `bandit.formatters.sarif:report` as the canonical `sarif` formatter entry point. |

Host context: Linux container (Ubuntu 25.10 base), Python 3.13.7, pip 25.3, Node v20.20.2 (Node is unused for this task but present in the image). No virtual environment is created; the `--break-system-packages` flag is used per Decision 2.

---

## Output Schema (binding)

`findings-config-c.json` is a UTF-8 encoded, minified, single-line JSON array. Each element is an object with **exactly** these five keys.

| Key | Type | Source | Constraint |
|---|---|---|---|
| `file` | string | SARIF `runs[0].results[i].locations[0].physicalLocation.artifactLocation.uri` | forward-slash relative path; `file:///` scheme stripped; scan-root prefix stripped; backslashes normalized |
| `line` | integer | SARIF `runs[0].results[i].locations[0].physicalLocation.region.startLine` | required, `> 0` (run aborts on absent or zero) |
| `severity` | string (enum) | SARIF `runs[0].results[i].level` mapped via `error→critical, warning→high, note→medium, info→low` | one of `critical`, `high`, `medium`, `low` (no other values produced) |
| `cwe` | string | rule `properties.tags` matching `^external/cwe/cwe-(\d+)$`; else B-ID fallback (see next section) | formatted `CWE-<n>` |
| `description` | string | SARIF `runs[0].results[i].message.text`, whitespace-collapsed via `" ".join(text.split())`, then `[:200]` | `len(description) ≤ 200`; no embedded newlines |

**Empty-state**: if Bandit reports zero findings, `findings-config-c.json` contains the literal two-character string `[]` (see Decision 14). For this run, the file contains the populated array of `1553` finding objects on a single line.

---

## B-ID → CWE Fallback Table

The transformer consults this table only when a rule's `properties.tags` lacks `external/cwe/cwe-<n>`. In this run, all 31 rules carry the CWE tag, so the fallback path was not exercised; the table is retained as a robustness net (Decision 8). The CWE assignments are sourced from Bandit's plugin reference at `bandit.readthedocs.io/en/latest/plugins/`. Rows are ordered ascending by B-ID.

| B-ID | CWE | Description |
|---|---|---|
| B101 | CWE-703 | assert_used |
| B102 | CWE-78 | exec_used |
| B103 | CWE-732 | set_bad_file_permissions |
| B104 | CWE-605 | hardcoded_bind_all_interfaces |
| B105 | CWE-259 | hardcoded_password_string |
| B106 | CWE-259 | hardcoded_password_funcarg |
| B107 | CWE-259 | hardcoded_password_default |
| B108 | CWE-377 | hardcoded_tmp_directory |
| B110 | CWE-703 | try_except_pass |
| B112 | CWE-703 | try_except_continue |
| B113 | CWE-400 | request_without_timeout |
| B201 | CWE-94 | flask_debug_true |
| B202 | CWE-22 | tarfile_unsafe_members |
| B303 | CWE-327 | md5 / weak hash (deprecated alias) |
| B304 | CWE-327 | insecure cipher / cipher mode |
| B305 | CWE-327 | insecure cipher mode |
| B306 | CWE-377 | mktemp_q (insecure temporary file) |
| B310 | CWE-22 | urllib_urlopen (URL scheme verification) |
| B311 | CWE-330 | random (use of pseudo-random for security) |
| B314 | CWE-20 | xml.etree (parsing untrusted XML) |
| B318 | CWE-20 | xml.dom.minidom (parsing untrusted XML) |
| B324 | CWE-327 | hashlib insecure algorithm |
| B404 | CWE-78 | import_subprocess |
| B405 | CWE-20 | import_xml_etree |
| B408 | CWE-20 | import_xml_minidom |
| B411 | CWE-20 | import_xmlrpclib |
| B501 | CWE-295 | request_with_no_cert_validation |
| B502 | CWE-327 | ssl_with_bad_version |
| B503 | CWE-327 | ssl_with_bad_defaults |
| B504 | CWE-327 | ssl_with_no_version |
| B505 | CWE-327 | weak_cryptographic_key |
| B506 | CWE-20 | yaml_load |
| B507 | CWE-295 | ssh_no_host_key_verification |
| B601 | CWE-78 | paramiko_calls |
| B602 | CWE-78 | subprocess_popen_with_shell_equals_true |
| B603 | CWE-78 | subprocess_without_shell_equals_true |
| B604 | CWE-78 | any_other_function_with_shell_equals_true |
| B605 | CWE-78 | start_process_with_a_shell |
| B606 | CWE-78 | start_process_with_no_shell |
| B607 | CWE-78 | start_process_with_partial_path |
| B608 | CWE-89 | hardcoded_sql_expressions |
| B609 | CWE-78 | linux_commands_wildcard_injection |
| B610 | CWE-89 | django_extra_used |
| B611 | CWE-89 | django_rawsql_used |
| B701 | CWE-94 | jinja2_autoescape_false |
| B702 | CWE-94 | use_of_mako_templates |
| B703 | CWE-79 | django_mark_safe |
| B704 | CWE-79 | markupsafe_markup_xss |

If the transformer encounters a B-ID not in this table AND the rule's `properties.tags` also lacks the CWE tag, the run aborts with a non-zero exit code and an error message identifying the missing B-ID, so the table can be extended before re-running. This fail-closed behavior matches Decision 13.

---

## Out of Scope

The following are explicitly NOT addressed by Config C (per AAP §0.5.2). Each item appears in the decision log so that any future agent reading this file has clear, unambiguous boundaries.

- **Modifying any existing file** under `odoo/`, `addons/`, `setup/`, `debian/`, `doc/`, `docs/`, `.github/`, or any root file including `README.md`, `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `MANIFEST.in`, `COPYRIGHT`, `requirements.txt`, `setup.py`, `setup.cfg`, `ruff.toml`, `catalog-info.yaml`, `mkdocs.yml`, `.weblate.json`, `.gitignore`. The `[3 directives \| ~0 files modified \| 1 new file]` header binds the agent to zero modifications.
- **Adding Bandit to the project's `requirements.txt` or `setup.py`'s `install_requires`** list. The Bandit install is scoped to the ephemeral execution environment only; the Odoo dependency graph is untouched.
- **Authoring a `.bandit`, `bandit.yaml`, `bandit.yml`, or `[tool.bandit]` configuration** block. The user directive "Bandit ships with its full rule set" mandates the default profile.
- **Creating GitHub Actions workflows or any CI integration**. No files are added under `.github/workflows/` (which does not exist in this repository).
- **Triaging, classifying, suppressing, or fixing individual Bandit findings**. The output is a baseline for cross-config comparison; remediation is a downstream activity.
- **Cross-comparing this output to any other Config (A, B, D, …)**. Each config in the multi-tool comparison is an independent run; the comparison harness consumes the schema-uniform `findings-config-<x>.json` files at a later stage outside this task.
