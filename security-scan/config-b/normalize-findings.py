#!/usr/bin/env python3
# normalize-findings.py — deterministic SARIF -> Config B findings normalizer.
#
# Public contract:
#   usage: normalize-findings.py <input-sarif> <output-json>
#
# Output format (Directive 3, verbatim user template):
#   [{"file":"<relative path>","line":<integer>,"severity":"<critical|high|medium|low>","cwe":"<CWE-ID>","description":"<max 200 chars>"},...]
#
# Field sourcing:
#   file        SARIF location: runs[].results[].locations[0].physicalLocation.artifactLocation.uri
#               If --target-root is supplied and the URI is absolute under that
#               root, the prefix is stripped so the output is a relative path
#               (Directive 3 requires "SARIF location (relative path)").
#   line        SARIF region: runs[].results[].locations[0].physicalLocation.region.startLine (int)
#   severity    runs[].results[].level mapped error->critical, warning->high, note->medium, info->low.
#               Fallback chain: rule defaultConfiguration.level -> rule properties.severity -> "medium".
#   cwe         rule properties.cwe (first element if a list) normalized to "CWE-<n>".
#               If absent, infer from rule message via keyword table. Else "CWE-Unknown".
#   description result.message.text truncated to 200 Unicode characters; no ellipsis appended.
#
# Serialization is exactly:
#   json.dumps(records, ensure_ascii=False, separators=(",", ":"))
# written as bytes followed by exactly one trailing '\n'. The trailing newline is
# what makes `wc -l < findings-config-b.json` return 1 (the user-prompt
# pass/fail gate). For zero findings the file content is the three bytes `[]\n`.
#
# Determinism: result iteration preserves SARIF emission order. No sorting, no
# de-duplication, no rule-grouping is applied. Re-running on an unchanged SARIF
# produces a byte-identical output (verified by run-scan.sh sha256 comparison).
#
# Design rationale lives in decision-log.md, not in code comments.

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SEVERITY_MAP = {
    "error": "critical",
    "warning": "high",
    "note": "medium",
    "info": "low",
}
SEVERITY_FALLBACK = "medium"
DESCRIPTION_MAX_CHARS = 200
CWE_UNKNOWN = "CWE-Unknown"

# Table-driven CWE inference. Order matters: the first matching pattern wins.
# Patterns are case-insensitive whole-word-ish substrings on the result message.
# This table is the single source of truth for the inference fallback; the
# decision log enumerates the rationale for each entry.
CWE_INFERENCE_TABLE: list[tuple[str, str]] = [
    # SQL & NoSQL injection
    (r"\bsql\s*injection\b", "CWE-89"),
    (r"\bsqli\b", "CWE-89"),
    (r"\bnosql\s*injection\b", "CWE-943"),
    # Command / OS injection
    (r"\bcommand\s*injection\b", "CWE-78"),
    (r"\bos\s*command\s*injection\b", "CWE-78"),
    (r"\bshell\s*injection\b", "CWE-78"),
    # Code injection / eval
    (r"\bcode\s*injection\b", "CWE-94"),
    (r"\beval\(\)?\s*(usage|of\s*untrusted|injection)?", "CWE-95"),
    # XSS
    (r"\b(?:reflected|stored|dom)?\s*xss\b", "CWE-79"),
    (r"\bcross[\s-]*site\s*scripting\b", "CWE-79"),
    # CSRF
    (r"\bcsrf\b", "CWE-352"),
    (r"\bcross[\s-]*site\s*request\s*forgery\b", "CWE-352"),
    # Path traversal
    (r"\bpath\s*traversal\b", "CWE-22"),
    (r"\bdirectory\s*traversal\b", "CWE-22"),
    (r"\.\./", "CWE-22"),
    # SSRF / open redirect
    (r"\bssrf\b", "CWE-918"),
    (r"\bserver[\s-]*side\s*request\s*forgery\b", "CWE-918"),
    (r"\bopen\s*redirect\b", "CWE-601"),
    # Hardcoded secrets / credentials
    (r"\bhard[\s-]*coded\s*(?:secret|password|credential|token|key|api[\s-]*key)\b", "CWE-798"),
    (r"\b(detected|leaked)\s+(?:secret|password|token|api[\s-]*key|access[\s-]*key)\b", "CWE-798"),
    (r"\bsecret\s+in\s+code\b", "CWE-798"),
    # Deserialization
    (r"\b(?:insecure|unsafe)\s*deserializ", "CWE-502"),
    (r"\bpickle\b", "CWE-502"),
    (r"\byaml\.load\b", "CWE-502"),
    # XXE
    (r"\bxxe\b", "CWE-611"),
    (r"\bxml\s*external\s*entity\b", "CWE-611"),
    # Weak / broken crypto
    (r"\b(weak|broken|insecure)\s+(crypto|cipher|hash|random)\b", "CWE-327"),
    (r"\bmd5\b", "CWE-327"),
    (r"\bsha1\b", "CWE-327"),
    (r"\becb\s+mode\b", "CWE-327"),
    (r"\bdes\s+(?:cipher|encryption)\b", "CWE-327"),
    # Weak random
    (r"\binsecure\s+random\b", "CWE-338"),
    (r"\bmath\.random\b", "CWE-338"),
    # TLS / cert verification
    (r"\b(?:tls|ssl)\s+(?:certificate)?\s*verification\s+disabled\b", "CWE-295"),
    (r"\bverify\s*=\s*false\b", "CWE-295"),
    # Auth / authz
    (r"\bauthentication\s+bypass\b", "CWE-287"),
    (r"\bmissing\s+authorization\b", "CWE-862"),
    (r"\bbroken\s+access\s+control\b", "CWE-284"),
    # Sensitive data
    (r"\b(?:logging|exposed)\s+(?:secret|password|credential|sensitive)\b", "CWE-532"),
    (r"\binsecure\s+cookie\b", "CWE-614"),
    (r"\b(?:missing|insecure)\s+(?:httponly|secure)\s+(?:flag|attribute)\b", "CWE-1004"),
    # Headers / CORS
    (r"\bcors\s+misconfiguration\b", "CWE-942"),
    (r"\bopen\s+cors\b", "CWE-942"),
    # SSRF aliases
    (r"\bblind\s+ssrf\b", "CWE-918"),
    # LDAP injection
    (r"\bldap\s+injection\b", "CWE-90"),
    # XPath injection
    (r"\bxpath\s+injection\b", "CWE-643"),
    # Template injection
    (r"\b(?:server[\s-]*side\s+)?template\s+injection\b", "CWE-1336"),
    (r"\bssti\b", "CWE-1336"),
    # Race conditions
    (r"\brace\s+condition\b", "CWE-362"),
    # Integer issues
    (r"\binteger\s+overflow\b", "CWE-190"),
    # Improper input validation (catch-all near the end)
    (r"\binput\s+validation\b", "CWE-20"),
]

_COMPILED_INFERENCE: list[tuple[re.Pattern[str], str]] = [
    (re.compile(p, re.IGNORECASE), c) for p, c in CWE_INFERENCE_TABLE
]


def load_sarif(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8", errors="strict") as fh:
        return json.load(fh)


def index_rules(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    driver = (run.get("tool") or {}).get("driver") or {}
    rules = driver.get("rules") or []
    by_id: dict[str, dict[str, Any]] = {}
    for rule in rules:
        rid = rule.get("id")
        if rid:
            by_id[rid] = rule
    return by_id


def _rule_for_result(result: dict[str, Any], rules_by_id: dict[str, dict[str, Any]],
                     rules_list: list[dict[str, Any]]) -> dict[str, Any]:
    rid = result.get("ruleId")
    if rid and rid in rules_by_id:
        return rules_by_id[rid]
    idx = result.get("ruleIndex")
    if isinstance(idx, int) and 0 <= idx < len(rules_list):
        return rules_list[idx]
    return {}


def severity_for(result: dict[str, Any], rule: dict[str, Any]) -> str:
    level = result.get("level")
    if level in SEVERITY_MAP:
        return SEVERITY_MAP[level]
    default_cfg = rule.get("defaultConfiguration") or {}
    rule_level = default_cfg.get("level")
    if rule_level in SEVERITY_MAP:
        return SEVERITY_MAP[rule_level]
    props = rule.get("properties") or {}
    prop_sev = props.get("severity")
    if isinstance(prop_sev, str):
        low = prop_sev.strip().lower()
        if low in SEVERITY_MAP:
            return SEVERITY_MAP[low]
        if low in {"critical", "high", "medium", "low"}:
            return low
    return SEVERITY_FALLBACK


_CWE_NORMALIZE = re.compile(r"^\s*(?:CWE[-_:\s]*)?(\d+)\s*$", re.IGNORECASE)


def _normalize_cwe(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        if not raw:
            return None
        raw = raw[0]
    if not isinstance(raw, (str, int)):
        return None
    s = str(raw).strip()
    if not s:
        return None
    m = _CWE_NORMALIZE.match(s)
    if m:
        return f"CWE-{int(m.group(1))}"
    return None


def infer_cwe(text: str) -> str | None:
    if not text:
        return None
    for pattern, cwe in _COMPILED_INFERENCE:
        if pattern.search(text):
            return cwe
    return None


def cwe_for(result: dict[str, Any], rule: dict[str, Any]) -> str:
    props = rule.get("properties") or {}
    candidate = _normalize_cwe(props.get("cwe"))
    if candidate:
        return candidate
    # Some Semgrep rules expose CWE under properties["cwe2022-top25"], "cwes",
    # or as part of a taxonomy. Be defensive but never silently drop.
    for key in ("cwes", "cwe2022-top25", "cwe2021-top25", "cwe-22", "cwe_id"):
        candidate = _normalize_cwe(props.get(key))
        if candidate:
            return candidate
    # Try result.taxa[].toolComponent.name == "CWE"
    for tax in result.get("taxa") or []:
        if isinstance(tax, dict):
            comp = tax.get("toolComponent") or {}
            if str(comp.get("name", "")).upper() == "CWE":
                candidate = _normalize_cwe(tax.get("id"))
                if candidate:
                    return candidate
    # Last resort: infer from the rule's message/full-description/short-description.
    parts: list[str] = []
    msg = result.get("message") or {}
    if isinstance(msg, dict):
        parts.append(str(msg.get("text", "")))
    for key in ("fullDescription", "shortDescription", "name", "id"):
        v = rule.get(key)
        if isinstance(v, dict):
            parts.append(str(v.get("text", "")))
        elif isinstance(v, str):
            parts.append(v)
    inferred = infer_cwe("\n".join(parts))
    if inferred:
        return inferred
    return CWE_UNKNOWN


def description_for(result: dict[str, Any]) -> str:
    msg = result.get("message") or {}
    text = ""
    if isinstance(msg, dict):
        text = msg.get("text") or msg.get("markdown") or ""
    elif isinstance(msg, str):
        text = msg
    if not isinstance(text, str):
        text = str(text)
    if len(text) > DESCRIPTION_MAX_CHARS:
        text = text[:DESCRIPTION_MAX_CHARS]
    return text


def _location(result: dict[str, Any], target_root: str | None) -> tuple[str, int]:
    locations = result.get("locations") or []
    file_uri = ""
    line = 0
    if locations:
        loc = locations[0] or {}
        phys = (loc.get("physicalLocation") or {})
        art = phys.get("artifactLocation") or {}
        uri = art.get("uri")
        if isinstance(uri, str):
            file_uri = _make_relative(uri, target_root)
        region = phys.get("region") or {}
        start = region.get("startLine")
        if isinstance(start, int):
            line = start
        elif isinstance(start, str):
            try:
                line = int(start)
            except ValueError:
                line = 0
    return file_uri, line


def _make_relative(uri: str, target_root: str | None) -> str:
    if not target_root:
        return uri
    # Strip a file:// prefix if present.
    candidate = uri
    if candidate.startswith("file://"):
        candidate = candidate[len("file://"):]
    # Normalize both sides for prefix comparison.
    root = target_root.rstrip("/")
    if root and candidate.startswith(root + "/"):
        return candidate[len(root) + 1:]
    if candidate == root:
        return ""
    return uri


def record_for(result: dict[str, Any], rule: dict[str, Any], target_root: str | None) -> dict[str, Any]:
    file_uri, line = _location(result, target_root)
    return {
        "file": file_uri,
        "line": line,
        "severity": severity_for(result, rule),
        "cwe": cwe_for(result, rule),
        "description": description_for(result),
    }


def normalize(sarif: dict[str, Any], target_root: str | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for run in sarif.get("runs") or []:
        rules_list = ((run.get("tool") or {}).get("driver") or {}).get("rules") or []
        rules_by_id = index_rules(run)
        for result in run.get("results") or []:
            rule = _rule_for_result(result, rules_by_id, rules_list)
            out.append(record_for(result, rule, target_root))
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="normalize-findings.py", add_help=True)
    parser.add_argument("input_sarif", type=Path, help="Path to results-semgrep.sarif")
    parser.add_argument("output_json", type=Path, help="Path to findings-config-b.json")
    parser.add_argument(
        "--target-root",
        type=str,
        default=None,
        help="Absolute path of the scanned repository root. When set, any "
        "absolute SARIF URI beginning with this prefix is rewritten to a path "
        "relative to that root (Directive 3 'relative path' requirement).",
    )
    args = parser.parse_args(argv)

    target_root: str | None = args.target_root
    if target_root:
        target_root = str(Path(target_root).resolve())

    sarif = load_sarif(args.input_sarif)
    records = normalize(sarif, target_root=target_root)
    payload = json.dumps(records, ensure_ascii=False, separators=(",", ":")) + "\n"
    args.output_json.write_bytes(payload.encode("utf-8"))
    sys.stderr.write(
        f"wrote {args.output_json} ({len(records)} records, {len(payload)} bytes)\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
