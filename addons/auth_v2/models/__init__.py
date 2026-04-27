# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""auth_v2 addon — models package initializer.

This file imports every Python module under ``models/`` so Odoo's ORM and
test framework can discover them. New modules added in subsequent
checkpoints (CP5+: ``feature_flags``, ``ir_http``) MUST be appended below.

Current CP4 contents:
    - auth_v2:  Sidecar HTTP client (validate_token)
    - fnv_hash: Cross-language FNV-1a 32-bit (Rule RF4 parity contract)

Future CP5+ additions (per AAP Section 0.5.1.5):
    - feature_flags: Cache -> API -> os.environ flag client (Rule RF3)
    - ir_http:       _authenticate() override (Rules R3, R4, R13)

Import order is alphabetical to match Python community convention. Sibling
modules MUST NOT import from each other; each is a leaf in the dependency
graph (see Rule R17 -- interface-driven dependencies).

See:
    - AAP Section 0.5.1.5 (Group 5 — Odoo Addon)
    - AAP Section 0.7.1 R13 (Sidecar fail-closed)
    - AAP Section 0.7.2 RF4 (FNV-1a parity contract)
"""

from . import auth_v2, feature_flags, fnv_hash
