# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""auth_v2 addon — tests package initializer.

This file imports every Python test module under ``tests/`` so Odoo's
test framework can discover them via ``odoo-bin -d <db> --test-enable
--init=auth_v2`` (or ``-u auth_v2`` on a previously-installed module).

Current CP4 contents:
    - test_feature_flags: Cross-language FNV-1a 32-bit parity test
                          (Rule RF4 / AAP FR-7)

Future CP6+ additions per AAP Section 0.5.1.5 will append modules here
as they are authored (e.g., ``test_ir_http`` for the ``_authenticate``
override regression suite, ``test_auth_v2`` for the sidecar HTTP client
contract suite). Each new test module name MUST be added below.

Test discovery requires:
    1. This file (registers ``tests`` as a Python package)
    2. ``addons/auth_v2/__init__.py`` (registers the addon root package)
    3. ``addons/auth_v2/models/__init__.py`` (registers the models the
       tests import via ``..models.fnv_hash``)

See:
    - AAP Section 0.5.1.5 (Group 5 — Odoo Addon)
    - AAP Section 0.7.1 R10, R13 (sidecar fail-closed; schema scope)
    - AAP Section 0.7.2 RF4 (FNV-1a parity contract)
"""

from . import test_feature_flags
