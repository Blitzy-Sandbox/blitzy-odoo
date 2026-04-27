# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""FNV-1a 32-bit cross-language parity test (auth_v2 addon-local).

This test verifies the addon's Python FNV-1a 32-bit hash implementation
(``odoo.addons.auth_v2.models.fnv_hash.fnv1a32``) is byte-identical to the
canonical TypeScript implementation committed at
``packages/admin-ui/src/flags/fnv-hash.ts``. It loads the deterministic
100-vector JSON fixture committed at
``packages/admin-ui/src/flags/__tests__/fixtures/fnv-vectors.json`` and
asserts every Python output equals the TypeScript-generated expectation.

This file is the addon-local mirror of the literal-path parity suite at
``blitzy-odoo/odoo/addons/base/models/test_feature_flags.py``. Both files
exist because the AAP (Section 0.5.1.5) lists the addon-local path while
Section 3 of the project specification lists the literal-path. The two
suites differ only in:

1. **Import strategy**: This addon-local file imports ``fnv1a32`` from
   ``..models.fnv_hash`` (exercising the actual production implementation
   the addon ships). The literal-path file inlines its own ``_fnv1a32``
   so it can run in deployments where the ``auth_v2`` addon is not
   installed.

2. **Fixture path traversal**: This file uses ``4`` ``..`` levels (tests/
   -> auth_v2/ -> addons/ -> blitzy-odoo/ -> <repo root>) versus ``5``
   ``..`` levels for the literal-path file.

The test class is registered for Odoo's test discovery via
``addons/auth_v2/tests/__init__.py`` (which imports this module) plus
``addons/auth_v2/__init__.py`` -> ``models/__init__.py`` (which loads the
``fnv_hash`` module the test imports).

Rules enforced:
    - RF4 (FNV-1a determinism): cross-language byte parity
    - R3  (Flag isolation):     no module-load side effects
    - R10 (Odoo schema scope):  TransactionCase only, no field changes
    - R23 (Log hygiene):        test data only, no token/secret values

References:
    - Agent Action Plan (AAP) Section 0.5.1.5 -- Group 5 (Odoo addon)
    - Agent Action Plan (AAP) FR-7 -- Cross-language FNV-1a parity
    - Agent Action Plan (AAP) Rule RF4 -- FNV-1a determinism
    - Companion file: ``blitzy-odoo/odoo/addons/base/models/test_feature_flags.py``
"""
import json
import os

import odoo.tests

from ..models.fnv_hash import fnv1a32


@odoo.tests.tagged('post_install', '-at_install')
class TestFeatureFlagsFNVParity(odoo.tests.TransactionCase):
    """Verify the addon's FNV-1a 32-bit output matches the TypeScript fixture.

    This test class exercises the production ``fnv1a32`` function exported
    from ``odoo.addons.auth_v2.models.fnv_hash``. It loads the canonical
    100-vector JSON fixture committed at
    ``packages/admin-ui/src/flags/__tests__/fixtures/fnv-vectors.json``
    via a relative-path traversal (4 ``..`` levels from this file's
    directory to the repository root, then into the ``packages/`` tree).

    Each fixture vector contains:

    - ``flag_name`` (str): The feature flag name.
    - ``subject`` (str): The subject identifier (email or ``""`` for global).
    - ``rollout_percentage`` (int): Rollout percentage in ``[0, 100]``.
    - ``expected_hash`` (int): TypeScript-computed FNV-1a 32-bit hash.
    - ``expected_enabled`` (bool): TypeScript-computed rollout decision.

    The test asserts both the raw hash equality (cross-language byte
    parity) and the rollout decision equality (4-step evaluation parity).
    """

    # Path math: from
    # ``blitzy-odoo/addons/auth_v2/tests/test_feature_flags.py``
    # we traverse 4 directories UP to the repository root:
    #   tests/       -> 1: auth_v2/
    #   auth_v2/     -> 2: addons/
    #   addons/      -> 3: blitzy-odoo/
    #   blitzy-odoo/ -> 4: <repo root>
    # Then descend into:
    #   packages/admin-ui/src/flags/__tests__/fixtures/fnv-vectors.json
    _FIXTURE_PATH = os.path.normpath(os.path.join(
        os.path.dirname(__file__),
        '..', '..', '..', '..',
        'packages', 'admin-ui', 'src', 'flags', '__tests__',
        'fixtures', 'fnv-vectors.json',
    ))

    @classmethod
    def _load_fixture(cls):
        """Load the 100-vector JSON fixture committed by the admin-ui agent.

        The fixture is generated as a side effect of the canonical
        TypeScript test in ``packages/admin-ui/src/flags/__tests__/
        fnv-hash.spec.ts`` and committed to the repository so that the
        Python parity suite can read it without re-running the TypeScript
        suite.

        :returns: List of dicts with keys ``flag_name``, ``subject``,
            ``rollout_percentage``, ``expected_hash``, ``expected_enabled``.
        :raises FileNotFoundError: If the fixture has not yet been generated
            by ``packages/admin-ui/src/flags/__tests__/fnv-hash.spec.ts``.
        """
        with open(cls._FIXTURE_PATH, encoding='utf-8') as f:
            return json.load(f)

    def test_fnv1a32_hash_parity(self):
        """Assert the addon's FNV-1a 32-bit output matches the TypeScript fixture.

        For every fixture vector, the addon's ``fnv1a32(flag_name, subject)``
        output MUST equal the ``expected_hash`` field stored in the fixture.
        Any mismatch indicates a cross-language drift in the FNV-1a
        implementation and MUST fail the build.

        Per AAP FR-7 and Rule RF4, the fixture must contain at least 100
        deterministic vectors; this test asserts that minimum size before
        iterating over the vectors.
        """
        vectors = self._load_fixture()
        self.assertGreaterEqual(
            len(vectors), 100,
            "fnv-vectors.json fixture must contain at least 100 vectors "
            "(per AAP FR-7 and Rule RF4); found %d" % len(vectors),
        )
        for vector in vectors:
            flag_name = vector['flag_name']
            subject = vector.get('subject', '')
            expected_hash = vector['expected_hash']
            with self.subTest(flag_name=flag_name, subject=subject):
                actual_hash = fnv1a32(flag_name, subject)
                self.assertEqual(
                    actual_hash, expected_hash,
                    "FNV-1a 32-bit hash mismatch for "
                    "flag_name=%r subject=%r: Python=%d, TypeScript=%d"
                    % (flag_name, subject, actual_hash, expected_hash),
                )

    def test_rollout_decision_parity(self):
        """Assert the addon's rollout decisions match the TypeScript fixture.

        For every fixture vector, the rollout decision computed as
        ``(fnv1a32(flag_name, subject) % 100) < rollout_percentage`` MUST
        equal the fixture's ``expected_enabled`` boolean. This validates
        the 4-step evaluation parity per AAP FR-5 and Rule RF4.

        Note: This test only validates step 4 (FNV bucket) of the 4-step
        evaluation order. Steps 1-3 (subject override, ``*`` global override,
        ``enabled=false`` short-circuit) are validated separately by the
        TypeScript and (forthcoming) addon-local feature_flags test suites
        and are NOT in scope for this parity test.
        """
        vectors = self._load_fixture()
        for vector in vectors:
            flag_name = vector['flag_name']
            subject = vector.get('subject', '')
            rollout_percentage = vector['rollout_percentage']
            expected_enabled = vector['expected_enabled']
            with self.subTest(
                flag_name=flag_name,
                subject=subject,
                rollout_percentage=rollout_percentage,
            ):
                actual_enabled = (
                    (fnv1a32(flag_name, subject) % 100) < rollout_percentage
                )
                self.assertEqual(
                    actual_enabled, expected_enabled,
                    "Rollout decision mismatch for "
                    "flag_name=%r subject=%r rollout=%d: "
                    "Python=%s, TypeScript=%s"
                    % (
                        flag_name, subject, rollout_percentage,
                        actual_enabled, expected_enabled,
                    ),
                )
