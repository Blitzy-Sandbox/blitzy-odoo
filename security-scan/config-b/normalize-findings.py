#!/usr/bin/env python3
"""Config B — SARIF → five-field minified-JSON findings normalizer.

Per user prompt Directive 3 (preserved verbatim), the output schema is:

    [{"file":"<relative path>","line":<integer>,"severity":"<critical|high|medium|low>","cwe":"<CWE-ID>","description":"<max 200 chars>"},...]

Rationale for every non-trivial decision lives in security-scan/config-b/decision-log.md (Explainability rule).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SEVERITY_MAP: dict[str, str] = {
    "error": "critical",
    "warning": "high",
    "note": "medium",
    "info": "low",
}

LAST_RESORT_SEVERITY: str = "medium"

DESCRIPTION_MAX_CHARS: int = 200

CWE_INFERENCE_TABLE: tuple[tuple[str, str], ...] = (
    ("hard-coded credential", "CWE-798"),
    ("hard-coded password", "CWE-798"),
    ("hard-coded api key", "CWE-798"),
    ("hard-coded api-key", "CWE-798"),
    ("hard-coded secret", "CWE-798"),
    ("hard-coded token", "CWE-798"),
    ("hardcoded credential", "CWE-798"),
    ("hardcoded password", "CWE-798"),
    ("hardcoded api key", "CWE-798"),
    ("hardcoded api-key", "CWE-798"),
    ("hardcoded secret", "CWE-798"),
    ("hardcoded token", "CWE-798"),
    ("server-side request forgery", "CWE-918"),
    ("server-side template injection", "CWE-1336"),
    ("cross-site request forgery", "CWE-352"),
    ("cross-site scripting", "CWE-79"),
    ("cross site scripting", "CWE-79"),
    ("xml external entity", "CWE-611"),
    ("os command injection", "CWE-78"),
    ("command injection", "CWE-78"),
    ("shell injection", "CWE-78"),
    ("sql injection", "CWE-89"),
    ("nosql injection", "CWE-943"),
    ("ldap injection", "CWE-90"),
    ("xpath injection", "CWE-643"),
    ("code injection", "CWE-94"),
    ("template injection", "CWE-1336"),
    ("path traversal", "CWE-22"),
    ("directory traversal", "CWE-22"),
    ("insecure deserialization", "CWE-502"),
    ("unsafe deserialization", "CWE-502"),
    ("open redirect", "CWE-601"),
    ("authentication bypass", "CWE-287"),
    ("missing authorization", "CWE-862"),
    ("broken access control", "CWE-284"),
    ("cors misconfiguration", "CWE-942"),
    ("insecure cookie", "CWE-614"),
    ("certificate verification disabled", "CWE-295"),
    ("verify=false", "CWE-295"),
    ("weak random", "CWE-338"),
    ("insecure random", "CWE-338"),
    ("weak hash", "CWE-328"),
    ("weak cipher", "CWE-327"),
    ("weak crypto", "CWE-327"),
    ("broken crypto", "CWE-327"),
    ("race condition", "CWE-362"),
    ("integer overflow", "CWE-190"),
    ("clickjacking", "CWE-1021"),
    ("ssrf", "CWE-918"),
    ("ssti", "CWE-1336"),
    ("xxe", "CWE-611"),
    ("xss", "CWE-79"),
    ("csrf", "CWE-352"),
    ("md5", "CWE-327"),
    ("sha1", "CWE-327"),
)

CWE_NORMALIZE_RE: re.Pattern[str] = re.compile(r"(?i)\bCWE[-_:\s]*0*([0-9]+)\b")

CWE_UNKNOWN: str = "CWE-Unknown"


def load_sarif(path: Path) -> dict:
    """Load a SARIF v2.1.0 document with explicit UTF-8 decoding.

    Validates that the top-level object contains a runs[] array
    (Directive 2 pass/fail precondition). Raises ValueError on
    structural failure; UnicodeDecodeError on non-UTF-8 bytes.
    """
    with path.open("r", encoding="utf-8", errors="strict") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("SARIF root must be a JSON object")
    runs = data.get("runs")
    if not isinstance(runs, list):
        raise ValueError("SARIF missing top-level 'runs' array")
    return data


def index_rules(run: dict) -> dict[str, dict]:
    """Build a mapping rule_id -> rule_object from run.tool.driver.rules.

    Keys are both the rule's "id" and "name" fields so result.ruleId
    lookups can find the rule via either form.
    """
    rules_by_id: dict[str, dict] = {}
    driver = (run.get("tool") or {}).get("driver") or {}
    rules = driver.get("rules") or []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rid = rule.get("id")
        rname = rule.get("name")
        if isinstance(rid, str) and rid and rid not in rules_by_id:
            rules_by_id[rid] = rule
        if isinstance(rname, str) and rname and rname not in rules_by_id:
            rules_by_id[rname] = rule
    return rules_by_id



def severity_for(result: dict, rule: dict | None) -> str:
    """Apply error->critical, warning->high, note->medium, info->low with fallbacks.

    Fallback chain (in order):
      1. result.level
      2. rule.defaultConfiguration.level
      3. rule.properties.severity (Semgrep places severity here when level is absent)
      4. LAST_RESORT_SEVERITY ('medium')

    Each last-resort fallback is logged to stderr with the rule ID so operators
    can audit the gap between SARIF emission and the closed enum.
    """
    level = result.get("level")
    if isinstance(level, str):
        key = level.strip().lower()
        if key in SEVERITY_MAP:
            return SEVERITY_MAP[key]

    if isinstance(rule, dict):
        default_cfg = rule.get("defaultConfiguration") or {}
        default_level = default_cfg.get("level") if isinstance(default_cfg, dict) else None
        if isinstance(default_level, str):
            key = default_level.strip().lower()
            if key in SEVERITY_MAP:
                return SEVERITY_MAP[key]

        props = rule.get("properties") or {}
        if isinstance(props, dict):
            rule_sev = props.get("severity")
            if isinstance(rule_sev, str):
                key = rule_sev.strip().lower()
                if key in SEVERITY_MAP:
                    return SEVERITY_MAP[key]
                if key in {"critical", "high", "medium", "low"}:
                    return key

    sys.stderr.write(
        "normalize-findings: severity fallback to "
        f"'{LAST_RESORT_SEVERITY}' for ruleId={result.get('ruleId', '?')!r} "
        "(SARIF level + rule metadata both omit severity)\n"
    )
    return LAST_RESORT_SEVERITY


def _normalize_cwe(raw: object) -> str | None:
    """Normalize a single CWE input to the canonical form 'CWE-<n>'.

    Accepts heterogeneous inputs:
      - 'CWE-79', 'cwe-079', 'CWE_89', 'cwe: 22'
      - bare integer ('79' or 79)
      - composite strings ("CWE-22: Improper Limitation of a Pathname...")
    Returns None when no CWE token is recoverable.
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        n = int(raw)
        return f"CWE-{n}" if n >= 0 else None
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    m = CWE_NORMALIZE_RE.search(s)
    if m:
        return f"CWE-{int(m.group(1))}"
    if s.isdigit():
        return f"CWE-{int(s)}"
    return None


def infer_cwe(text: str) -> str | None:
    """Deterministic keyword-based CWE inference.

    Walks CWE_INFERENCE_TABLE in declared order (longest, most-specific phrases
    first) and returns the first matching CWE ID. Matching is a case-insensitive
    substring test. Returns None when no keyword matches.
    """
    if not text or not isinstance(text, str):
        return None
    haystack = text.lower()
    for needle, cwe in CWE_INFERENCE_TABLE:
        if needle in haystack:
            return cwe
    return None


def cwe_for(result: dict, rule: dict | None) -> str:
    """Resolve a finding's CWE.

    Lookup order:
      1. rule.properties.cwe (string, list, or numeric)
      2. rule.properties.cwes, .cwe_id, .cwe2022-top25, .cwe2021-top25
      3. rule.properties.tags items that begin with 'CWE-<n>'
      4. result.taxa[] entries whose toolComponent.name == 'CWE'
      5. infer_cwe() on result.message.text + rule short/full/help text + rule id/name
      6. 'CWE-Unknown' (logged to stderr)
    """
    rule_id = result.get("ruleId", "?")

    if isinstance(rule, dict):
        props = rule.get("properties") or {}
        if isinstance(props, dict):
            primary = props.get("cwe")
            normalized = _first_normalized_cwe(primary)
            if normalized:
                return normalized

            for alt_key in ("cwes", "cwe_id", "cwe2022-top25", "cwe2021-top25"):
                normalized = _first_normalized_cwe(props.get(alt_key))
                if normalized:
                    return normalized

            tags = props.get("tags")
            if isinstance(tags, list):
                for tag in tags:
                    if isinstance(tag, str) and "cwe" in tag.lower():
                        normalized = _normalize_cwe(tag)
                        if normalized:
                            return normalized

        for tax in result.get("taxa") or []:
            if not isinstance(tax, dict):
                continue
            comp = tax.get("toolComponent") or {}
            if isinstance(comp, dict) and str(comp.get("name", "")).upper() == "CWE":
                normalized = _normalize_cwe(tax.get("id"))
                if normalized:
                    return normalized

    message_text = ""
    msg = result.get("message")
    if isinstance(msg, dict):
        candidate = msg.get("text")
        if isinstance(candidate, str):
            message_text = candidate

    rule_text_parts: list[str] = []
    if isinstance(rule, dict):
        for key in ("shortDescription", "fullDescription", "help"):
            v = rule.get(key)
            if isinstance(v, dict):
                t = v.get("text")
                if isinstance(t, str):
                    rule_text_parts.append(t)
        for key in ("name", "id"):
            v = rule.get(key)
            if isinstance(v, str):
                rule_text_parts.append(v.replace("-", " ").replace("_", " ").replace(".", " "))

    inferred = infer_cwe(" ".join([message_text, *rule_text_parts]))
    if inferred:
        return inferred

    snippet = message_text[:80]
    sys.stderr.write(
        f"normalize-findings: CWE fallback to {CWE_UNKNOWN!r} for "
        f"ruleId={rule_id!r} message={snippet!r}\n"
    )
    return CWE_UNKNOWN


def _first_normalized_cwe(value: object) -> str | None:
    """Return the first normalizable CWE from a scalar or list value."""
    if value is None:
        return None
    if isinstance(value, list):
        for item in value:
            normalized = _normalize_cwe(item)
            if normalized:
                return normalized
        return None
    return _normalize_cwe(value)



def description_for(result: dict) -> str:
    """Read result.message.text and truncate to DESCRIPTION_MAX_CHARS Unicode chars.

    Truncation is performed on Unicode code points (Python str length), not bytes.
    No ellipsis is appended (the full 200-character budget is preserved).
    When the SARIF result omits message.text entirely, an empty string is emitted
    and the fallback is logged to stderr with the rule ID.
    """
    msg = result.get("message")
    text: str | None = None
    if isinstance(msg, dict):
        candidate = msg.get("text")
        if isinstance(candidate, str):
            text = candidate
        else:
            markdown = msg.get("markdown")
            if isinstance(markdown, str):
                text = markdown
    elif isinstance(msg, str):
        text = msg

    if text is None:
        sys.stderr.write(
            "normalize-findings: description fallback (empty) for "
            f"ruleId={result.get('ruleId', '?')!r}\n"
        )
        return ""

    if len(text) > DESCRIPTION_MAX_CHARS:
        return text[:DESCRIPTION_MAX_CHARS]
    return text


def _make_relative(uri: str, target_root: str | None) -> str:
    """Rewrite an absolute SARIF URI to a path relative to target_root.

    Strips an optional 'file://' scheme prefix. If target_root is not a prefix
    of the URI, returns the URI unchanged.
    """
    if not uri or not target_root:
        return uri
    candidate = uri
    if candidate.startswith("file://"):
        candidate = candidate[len("file://"):]
    root = target_root.rstrip("/")
    if root and candidate.startswith(root + "/"):
        return candidate[len(root) + 1:]
    if candidate == root:
        return ""
    return uri


def record_for(
    result: dict,
    rules_by_id: dict[str, dict],
    target_root: str | None = None,
) -> dict:
    """Assemble the five-field record in canonical key order.

    Canonical key order: file, line, severity, cwe, description.
    Python 3.7+ guarantees dict insertion order; downstream serialization with
    json.dumps preserves this order in the output.

    When target_root is provided and the SARIF URI is an absolute path beneath
    it, the prefix is stripped so the deliverable contains a repository-relative
    path (Directive 3 'relative path' requirement).
    """
    rule_id = result.get("ruleId")
    rule: dict | None = None
    if isinstance(rule_id, str) and rule_id in rules_by_id:
        rule = rules_by_id[rule_id]

    locations = result.get("locations") or []
    file_uri = ""
    start_line = 0
    if locations and isinstance(locations[0], dict):
        phys = locations[0].get("physicalLocation") or {}
        if isinstance(phys, dict):
            artifact = phys.get("artifactLocation") or {}
            if isinstance(artifact, dict):
                uri_raw = artifact.get("uri")
                if isinstance(uri_raw, str):
                    file_uri = uri_raw
            region = phys.get("region") or {}
            if isinstance(region, dict):
                sl = region.get("startLine")
                if isinstance(sl, int):
                    start_line = sl
                elif isinstance(sl, str):
                    try:
                        start_line = int(sl)
                    except ValueError:
                        start_line = 0

    if target_root and file_uri:
        file_uri = _make_relative(file_uri, target_root)

    if not file_uri:
        sys.stderr.write(
            "normalize-findings: location fallback (empty file) for "
            f"ruleId={rule_id!r}\n"
        )
    if start_line == 0:
        sys.stderr.write(
            "normalize-findings: region fallback (line=0) for "
            f"ruleId={rule_id!r}\n"
        )

    return {
        "file": file_uri,
        "line": start_line,
        "severity": severity_for(result, rule),
        "cwe": cwe_for(result, rule),
        "description": description_for(result),
    }


def main(argv: list[str]) -> int:
    """Orchestrate SARIF -> five-field minified-JSON normalization.

    Exit codes:
      0  success
      2  input SARIF not found
      3  SARIF load failure (JSON parse, encoding, or structural)
      4  schema violation in an emitted record
      5  description length violation in an emitted record
      6  severity enum violation in an emitted record
    """
    parser = argparse.ArgumentParser(
        prog="normalize-findings.py",
        description=(
            "SARIF v2.1.0 -> five-field minified-JSON findings normalizer "
            "for Config B."
        ),
        add_help=True,
    )
    parser.add_argument(
        "input_sarif",
        help="Path to the Semgrep SARIF v2.1.0 input file.",
    )
    parser.add_argument(
        "output_json",
        help="Path to write the minified single-line UTF-8 findings JSON.",
    )
    parser.add_argument(
        "--target-root",
        dest="target_root",
        default=None,
        help=(
            "Absolute path of the scanned repository root. When set, any "
            "SARIF URI beginning with this prefix is rewritten to a path "
            "relative to that root (Directive 3 'relative path' requirement)."
        ),
    )
    args = parser.parse_args(argv)

    in_path = Path(args.input_sarif).resolve()
    out_path = Path(args.output_json).resolve()

    if not in_path.is_file():
        sys.stderr.write(
            f"normalize-findings: input SARIF not found: {in_path}\n"
        )
        return 2

    target_root: str | None = args.target_root
    if target_root:
        target_root = str(Path(target_root).resolve())

    try:
        sarif = load_sarif(in_path)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError, OSError) as exc:
        sys.stderr.write(
            f"normalize-findings: failed to load SARIF: {exc}\n"
        )
        return 3

    records: list[dict] = []
    for run in sarif.get("runs") or []:
        if not isinstance(run, dict):
            continue
        rules_by_id = index_rules(run)
        results = run.get("results") or []
        for result in results:
            if not isinstance(result, dict):
                continue
            records.append(record_for(result, rules_by_id, target_root=target_root))

    expected_keys = {"file", "line", "severity", "cwe", "description"}
    allowed_severities = {"critical", "high", "medium", "low"}
    for idx, rec in enumerate(records):
        if set(rec.keys()) != expected_keys:
            sys.stderr.write(
                f"normalize-findings: schema check failed for record {idx}: "
                f"keys={sorted(rec.keys())}\n"
            )
            return 4
        if not isinstance(rec["description"], str) or len(rec["description"]) > DESCRIPTION_MAX_CHARS:
            sys.stderr.write(
                f"normalize-findings: description length check failed for record {idx}: "
                f"len={len(rec.get('description', ''))}\n"
            )
            return 5
        if rec["severity"] not in allowed_severities:
            sys.stderr.write(
                f"normalize-findings: severity enum check failed for record {idx}: "
                f"severity={rec['severity']!r}\n"
            )
            return 6

    payload_text = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    payload_bytes = (payload_text + "\n").encode("utf-8")
    out_path.write_bytes(payload_bytes)

    sys.stderr.write(
        f"normalize-findings: wrote {len(records)} records to {out_path} "
        f"({len(payload_bytes)} bytes)\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
