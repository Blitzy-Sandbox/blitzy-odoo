# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""FNV-1a 32-bit cross-language parity test.

This test verifies the Python FNV-1a 32-bit hash implementation is byte-identical
to the canonical TypeScript implementation (committed at
``packages/admin-ui/src/flags/fnv-hash.ts``). It loads the deterministic
100-vector JSON fixture committed at
``packages/admin-ui/src/flags/__tests__/fixtures/fnv-vectors.json`` and asserts
every Python output equals the TypeScript-generated expectation.

This file lives at the literal path requested in the project specification
("Section 3 -- FNV-1a parity test in ``blitzy-odoo/odoo/addons/base/models/
test_feature_flags.py``") and intentionally does NOT depend on the
``auth_v2`` addon. The FNV-1a function is INLINED below so this test loads
even when the ``auth_v2`` addon is not installed.

References:
    - Agent Action Plan (AAP) Section 0.5.1.5 -- Group 5 (Odoo addon)
    - Agent Action Plan (AAP) Section 0.2.1.2 -- Existing Files Requiring Modification (Odoo)
    - Agent Action Plan (AAP) FR-7 -- Cross-language FNV-1a parity
    - Agent Action Plan (AAP) Rule RF4 -- FNV-1a determinism (cross-language parity)
"""
import json
import os

import odoo.tests


def _fnv1a32(flag_name, subject=''):
    """Compute the FNV-1a 32-bit hash of ``flag_name + ':' + subject``.

    Algorithm parameters (must match canonical TypeScript implementation
    at ``packages/admin-ui/src/flags/fnv-hash.ts`` byte-for-byte):

    - FNV offset basis: ``2166136261`` (32-bit unsigned)
    - FNV prime: ``16777619``
    - Input encoding: UTF-8 of ``flag_name + ':' + subject``
    - Iteration: for each byte ``b`` of the UTF-8 input,
      ``hash = ((hash XOR b) * prime) AND 0xFFFFFFFF``

    The ``& 0xFFFFFFFF`` mask after each multiplication enforces 32-bit
    unsigned semantics, matching the JavaScript ``(hash >>> 0)`` idiom
    used in the canonical TypeScript implementation.

    This function is intentionally INLINED here (not imported from
    ``odoo.addons.auth_v2.models.fnv_hash``) so this test continues to
    load and run even in deployments where the ``auth_v2`` addon is not
    installed. The duplication is the smallest possible (a single function
    of <=10 lines) and is governed by the cross-language parity fixture
    that this test consumes.

    :param flag_name: Feature flag name (UTF-8 string).
    :param subject: Subject identifier (typically email) or empty string.
    :returns: 32-bit unsigned integer hash.
    """
    hash_val = 2166136261
    for byte in (flag_name + ':' + subject).encode('utf-8'):
        hash_val = ((hash_val ^ byte) * 16777619) & 0xFFFFFFFF
    return hash_val


@odoo.tests.tagged('post_install', '-at_install')
class TestFeatureFlagsFNVParity(odoo.tests.TransactionCase):
    """Verify Python FNV-1a 32-bit output matches the TypeScript fixture.

    This test class is intentionally decoupled from the ``auth_v2`` addon.
    It loads the canonical 100-vector JSON fixture committed at
    ``packages/admin-ui/src/flags/__tests__/fixtures/fnv-vectors.json``
    via a relative-path traversal (5 ``..`` levels from this file's
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
    # ``blitzy-odoo/odoo/addons/base/models/test_feature_flags.py``
    # we traverse 5 directories UP to the repository root:
    #   models/      -> 1: base/
    #   base/        -> 2: addons/
    #   addons/      -> 3: odoo/
    #   odoo/        -> 4: blitzy-odoo/
    #   blitzy-odoo/ -> 5: <repo root>
    # Then descend into:
    #   packages/admin-ui/src/flags/__tests__/fixtures/fnv-vectors.json
    _FIXTURE_PATH = os.path.normpath(os.path.join(
        os.path.dirname(__file__),
        '..', '..', '..', '..', '..',
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
        """Assert Python FNV-1a 32-bit output matches the TypeScript fixture.

        For every fixture vector, the Python ``_fnv1a32(flag_name, subject)``
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
                actual_hash = _fnv1a32(flag_name, subject)
                self.assertEqual(
                    actual_hash, expected_hash,
                    "FNV-1a 32-bit hash mismatch for "
                    "flag_name=%r subject=%r: Python=%d, TypeScript=%d"
                    % (flag_name, subject, actual_hash, expected_hash),
                )

    def test_rollout_decision_parity(self):
        """Assert Python rollout decisions match the TypeScript fixture.

        For every fixture vector, the Python rollout decision computed as
        ``(_fnv1a32(flag_name, subject) % 100) < rollout_percentage`` MUST
        equal the fixture's ``expected_enabled`` boolean. This validates
        the 4-step evaluation parity per AAP FR-5 and Rule RF4.

        Note: This test only validates step 4 (FNV bucket) of the 4-step
        evaluation order. Steps 1-3 (subject override, ``*`` global override,
        ``enabled=false`` short-circuit) are validated separately by the
        TypeScript and addon-local Python test suites and are NOT in scope
        for this literal-path parity test.
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
                    (_fnv1a32(flag_name, subject) % 100) < rollout_percentage
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
