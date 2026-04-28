# -*- coding: utf-8 -*-  # noqa: UP009
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""auth_v2 addon — models package initializer.

This file imports every Python module under ``models/`` so Odoo's ORM and
test framework can discover them. The import order is alphabetical to
match Python community convention.

Module contents:
    - auth_v2:       Sidecar HTTP client (``validate_token``)
                     (Rule R13 -- fail-closed on sidecar failure)
    - feature_flags: Cache -> API -> ``os.environ`` flag client
                     (``is_enabled``) (Rule RF3 -- fail-open)
    - fnv_hash:      Cross-language FNV-1a 32-bit hash
                     (Rule RF4 -- TypeScript/Python parity contract)
    - ir_http:       ``_authenticate()`` override
                     (Rules R3, R4, R13 -- flag-gated dispatch to V2)

The import of ``ir_http`` MUST be after ``auth_v2`` and ``feature_flags``
because ``ir_http`` imports both as sibling modules (relative imports
inside ``ir_http.py``). The ``feature_flags`` module imports ``fnv_hash``
for the local rollout-bucket evaluation.

Sibling-import dependency graph (within this package):
    - fnv_hash       <- (no dependencies; leaf)
    - feature_flags  <- fnv_hash
    - auth_v2        <- (no dependencies; leaf)
    - ir_http        <- auth_v2, feature_flags

The order ``auth_v2, feature_flags, fnv_hash, ir_http`` below respects
the dependency graph -- ``ir_http`` is imported last because it depends
on the previously-imported sibling modules.

See:
    - AAP Section 0.5.1.5 (Group 5 — Odoo Addon)
    - AAP Section 0.7.1 R3 (flag isolation), R4 (flag exclusivity),
      R13 (sidecar fail-closed)
    - AAP Section 0.7.2 RF3 (flag fail-open), RF4 (FNV-1a parity contract)
"""

from . import auth_v2, feature_flags, fnv_hash, ir_http
