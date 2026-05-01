# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Unit tests for pure-helper functions in ``controllers/main.py``.

This test module verifies the pure-Python helpers in
``blitzy-odoo/addons/auth_v2/controllers/main.py`` that have NO
dependency on Odoo's request lifecycle, env, or registry. Specifically:

    - ``_generate_pkce_verifier`` -- entropy + character set
    - ``_derive_pkce_challenge``  -- S256 derivation correctness
    - ``_generate_state``          -- entropy + character set
    - ``_safe_compare``            -- constant-time equality
    - ``_is_safe_redirect``        -- open-redirect defense

These helpers are testable in isolation because they take pure-data
arguments (strings, bytes) and return pure-data outputs. The
controller methods themselves (``login``, ``callback``, ``logout``)
are NOT covered here -- they require Odoo's request/env/registry
and are exercised end-to-end via ``LOCAL_TESTING_GUIDE.md`` and via
the integration test suite.

Test classes:
    - ``TestPkceHelpers`` -- helpers used by the PKCE flow (verifier,
      challenge, state).
    - ``TestSafeCompare`` -- constant-time string comparison helper.
    - ``TestIsSafeRedirect`` -- open-redirect defense.

Per Rule R23, no test logs the verifier/challenge/state outputs, only
their lengths and character-set membership.

Coverage scope:
    These tests cover the helpers' contract surfaces:
        - return type
        - byte-range / character-set
        - length
        - cryptographic determinism (challenge depends only on verifier)
        - defensive rejections in _is_safe_redirect

See:
    - blitzy-odoo/addons/auth_v2/controllers/main.py (module under test)
    - Refine PR Directive D6 (cookie storage of PKCE state)
"""

import ast
import base64
import hashlib
import os
import sys
import unittest

# Import directly without the Odoo addon path. The helpers in
# main.py are pure functions with no Odoo dependency, so we can
# import them by adding the controllers folder to sys.path.

_HERE = os.path.dirname(os.path.abspath(__file__))
_CONTROLLERS_DIR = os.path.join(_HERE, '..', 'controllers')
if _CONTROLLERS_DIR not in sys.path:
    sys.path.insert(0, _CONTROLLERS_DIR)

# Import the module file directly. We can't use the standard
# ``from odoo.addons.auth_v2.controllers.main import ...`` import
# because it would trigger the module's Odoo-flavored imports (
# ``from odoo import http``) which don't work without an Odoo
# runtime. Instead, we parse the AST and execute only the helper
# function definitions in a fresh namespace.

_MAIN_PY = os.path.join(_CONTROLLERS_DIR, 'main.py')


def _load_helpers():
    """Load only the helpers from main.py without triggering Odoo imports.

    The strategy: parse the file with ast, then execute only the
    pure-Python helper definitions in a fresh namespace. This
    avoids the ``from odoo import http`` import that would fail
    in a non-Odoo test environment.

    Returns:
        A dict containing the helper functions:
            - ``_generate_pkce_verifier``
            - ``_derive_pkce_challenge``
            - ``_generate_state``
            - ``_safe_compare``
            - ``_is_safe_redirect``
    """
    with open(_MAIN_PY, encoding='utf-8') as f:
        source = f.read()

    tree = ast.parse(source)

    # We only want the function definitions for our pure helpers,
    # plus their import dependencies. Skip class definitions
    # (which require Odoo) and any imports that require Odoo.
    HELPER_NAMES = {
        '_generate_pkce_verifier',
        '_derive_pkce_challenge',
        '_generate_state',
        '_safe_compare',
        '_is_safe_redirect',
    }
    HELPER_DEPS = {
        # Import lines this set of helpers needs.
        'base64', 'hashlib', 'hmac', 'secrets',
    }

    new_body = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            # Keep only the imports our helpers need.
            keep_aliases = [a for a in node.names if a.name in HELPER_DEPS]
            if keep_aliases:
                node.names = keep_aliases
                new_body.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in HELPER_NAMES:
            new_body.append(node)
        # Else: skip (classes, top-level constants we don't need, etc.)

    new_module = ast.Module(body=new_body, type_ignores=[])
    namespace = {
        # Provide constants the helpers reference. These mirror the
        # values defined as module-level constants in main.py.
        '_PKCE_VERIFIER_LENGTH_BYTES': 32,
        '_PKCE_STATE_LENGTH_BYTES': 32,
    }
    exec(compile(new_module, '<helpers>', 'exec'), namespace)
    return namespace


_HELPERS = _load_helpers()


class TestPkceHelpers(unittest.TestCase):
    """Tests for the PKCE verifier/challenge/state helpers."""

    def test_verifier_length_is_43_chars(self):
        """The verifier MUST be exactly 43 chars (32 bytes base64url, no pad).

        RFC 7636 §4.1 requires verifiers between 43 and 128 characters.
        We pin 43 (the minimum) for cross-app consistency with kalle's
        web flow.
        """
        verifier = _HELPERS['_generate_pkce_verifier']()
        self.assertEqual(len(verifier), 43)

    def test_verifier_uses_url_safe_base64_charset(self):
        """The verifier MUST use only URL-safe base64 characters [A-Za-z0-9_-]."""
        verifier = _HELPERS['_generate_pkce_verifier']()
        for ch in verifier:
            self.assertTrue(
                ch.isalnum() or ch in '-_',
                msg=f"verifier contains non-URL-safe-base64 char: {ch!r}",
            )

    def test_verifier_is_unique_per_call(self):
        """Each call MUST produce a distinct verifier (entropy contract)."""
        a = _HELPERS['_generate_pkce_verifier']()
        b = _HELPERS['_generate_pkce_verifier']()
        self.assertNotEqual(a, b)

    def test_challenge_is_s256_of_verifier(self):
        """The challenge MUST be base64url(SHA256(verifier)) without padding.

        Per RFC 7636 §4.2, the S256 challenge derivation is a
        deterministic function of the verifier; we assert byte-equality
        between the helper's output and the canonical SHA-256+base64url
        computation.
        """
        verifier = 'test-verifier-for-deterministic-derivation'
        expected_digest = hashlib.sha256(verifier.encode('ascii')).digest()
        expected = base64.urlsafe_b64encode(expected_digest).rstrip(b'=').decode('ascii')
        actual = _HELPERS['_derive_pkce_challenge'](verifier)
        self.assertEqual(actual, expected)

    def test_challenge_length_is_43_chars(self):
        """The S256 challenge MUST be exactly 43 chars (SHA-256 base64url no pad)."""
        challenge = _HELPERS['_derive_pkce_challenge']('any-verifier')
        self.assertEqual(len(challenge), 43)

    def test_state_length_is_43_chars(self):
        """The state MUST be exactly 43 chars (32 bytes base64url, no pad)."""
        state = _HELPERS['_generate_state']()
        self.assertEqual(len(state), 43)

    def test_state_is_unique_per_call(self):
        """Each call MUST produce a distinct state (CSRF defense entropy)."""
        a = _HELPERS['_generate_state']()
        b = _HELPERS['_generate_state']()
        self.assertNotEqual(a, b)


class TestSafeCompare(unittest.TestCase):
    """Tests for the constant-time string comparison helper."""

    def test_safe_compare_equal_strings(self):
        """Equal strings MUST compare True."""
        self.assertTrue(_HELPERS['_safe_compare']('abc123', 'abc123'))

    def test_safe_compare_different_strings(self):
        """Different strings MUST compare False."""
        self.assertFalse(_HELPERS['_safe_compare']('abc', 'xyz'))

    def test_safe_compare_different_lengths(self):
        """Different-length strings MUST compare False."""
        self.assertFalse(_HELPERS['_safe_compare']('a', 'ab'))

    def test_safe_compare_empty_strings(self):
        """Empty strings MUST compare True (both equal)."""
        self.assertTrue(_HELPERS['_safe_compare']('', ''))

    def test_safe_compare_rejects_none(self):
        """None inputs MUST compare False (defensive contract)."""
        self.assertFalse(_HELPERS['_safe_compare'](None, 'abc'))
        self.assertFalse(_HELPERS['_safe_compare']('abc', None))
        self.assertFalse(_HELPERS['_safe_compare'](None, None))

    def test_safe_compare_rejects_non_string(self):
        """Non-string inputs MUST compare False (defensive contract)."""
        self.assertFalse(_HELPERS['_safe_compare'](123, '123'))
        self.assertFalse(_HELPERS['_safe_compare']('123', 123))
        self.assertFalse(_HELPERS['_safe_compare']([], ''))


class TestIsSafeRedirect(unittest.TestCase):
    """Tests for the open-redirect defense helper.

    Per Refine PR Directive D5, ``request.redirect`` strips external
    hostnames and is therefore not safe to use for Keycloak URLs. This
    helper enforces the inverse: redirects RETURNING from external
    auth (back into the local Odoo app) must be local-only paths.
    """

    def test_local_path_is_safe(self):
        """A simple ``/odoo`` path MUST be accepted."""
        self.assertTrue(_HELPERS['_is_safe_redirect']('/odoo'))

    def test_nested_local_path_is_safe(self):
        """A nested local path MUST be accepted."""
        self.assertTrue(_HELPERS['_is_safe_redirect']('/odoo/action-1'))

    def test_root_path_is_safe(self):
        """The root path ``/`` MUST be accepted."""
        self.assertTrue(_HELPERS['_is_safe_redirect']('/'))

    def test_empty_string_is_unsafe(self):
        """Empty string MUST be rejected."""
        self.assertFalse(_HELPERS['_is_safe_redirect'](''))

    def test_none_is_unsafe(self):
        """None MUST be rejected."""
        self.assertFalse(_HELPERS['_is_safe_redirect'](None))

    def test_protocol_relative_url_is_unsafe(self):
        """Protocol-relative URLs MUST be rejected (open-redirect attack)."""
        self.assertFalse(_HELPERS['_is_safe_redirect']('//evil.example.com/path'))

    def test_absolute_http_url_is_unsafe(self):
        """Absolute http:// URLs MUST be rejected."""
        self.assertFalse(_HELPERS['_is_safe_redirect']('http://evil.example.com/path'))

    def test_absolute_https_url_is_unsafe(self):
        """Absolute https:// URLs MUST be rejected."""
        self.assertFalse(_HELPERS['_is_safe_redirect']('https://evil.example.com/path'))

    def test_javascript_scheme_is_unsafe(self):
        """``/javascript:...`` paths MUST be rejected (XSS via redirect)."""
        self.assertFalse(_HELPERS['_is_safe_redirect']('/javascript:alert(1)'))

    def test_no_leading_slash_is_unsafe(self):
        """Paths without a leading slash MUST be rejected."""
        self.assertFalse(_HELPERS['_is_safe_redirect']('odoo'))


if __name__ == '__main__':
    unittest.main()
