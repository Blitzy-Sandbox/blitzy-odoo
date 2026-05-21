# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Cross-language FNV-1a 32-bit hash for the auth_v2 addon.

This module is the Python counterpart of
``packages/admin-ui/src/flags/fnv-hash.ts``. It implements the 32-bit
FNV-1a (Fowler-Noll-Vo) hash function over the UTF-8 encoding of
``flag_name + ':' + subject`` and MUST produce byte-identical output
to the TypeScript implementation for every (flag_name, subject) pair.

Algorithm (verbatim from the user prompt, AAP Section 0.1.2)::

    hash = 2166136261
    for byte in UTF8(flag_name + ':' + subject):
        hash = ((hash ^ byte) * 16777619) & 0xFFFFFFFF

Constants:

    - Offset basis: 0x811c9dc5 (decimal 2166136261)  -- FNV-1a 32-bit
    - Prime:        0x01000193 (decimal 16777619)    -- FNV-1a 32-bit
    - Mask:         0xFFFFFFFF                       -- 32-bit unsigned
    - Separator:    ':'                              -- single ASCII colon

Determinism contract (Rule RF4):

    The 100-vector fixture at
    ``packages/admin-ui/src/flags/__tests__/fixtures/fnv-vectors.json``
    is the cross-language parity contract. The test
    ``blitzy-odoo/addons/auth_v2/tests/test_feature_flags.py`` loads
    that fixture and asserts that, for every (flag_name, subject) pair,
    this implementation returns ``expected_hash`` byte-equal.

This module is PURE -- it has no I/O, no logging, no environment access,
no imports of sibling modules, no module-level state mutations, and no
network calls. It is the most foundational module in the ``auth_v2``
addon and serves as a leaf node in the dependency graph: every other
module in the addon may depend on this one, but this one depends on
nothing.

The function is total: every (str, str) input has a defined ``int``
output in the range ``[0, 0xFFFFFFFF]``. No exceptions are raised; no
input is rejected.

Mathematical relationship to the TypeScript counterpart:

    JavaScript's ``>>> 0`` (unsigned right shift by zero) and Python's
    ``& 0xFFFFFFFF`` (bitwise AND with the 32-bit mask) are mathematically
    equivalent for 32-bit unsigned coercion. The TypeScript implementation
    uses ``Math.imul(a, b)`` for 32-bit signed integer multiplication
    followed by ``>>> 0`` to coerce the bit pattern to unsigned; the Python
    implementation uses unbounded integer multiplication followed by the
    mask. Both produce the lower 32 bits of the multiplication treated as
    unsigned -- byte-identical output for any input.

See:

    - AAP Section 0.7.2 RF4 (Flag Determinism / FNV parity)
    - AAP Section 0.5.1.5 (Group 5 -- Odoo Addon, this file mandate)
    - AAP Section 0.1.2 (verbatim algorithm specification)
    - AAP Section 0.7.4 R7 (zero warnings -- explicit types, no Any)

References:

    - https://en.wikipedia.org/wiki/Fowler%E2%80%93Noll%E2%80%93Vo_hash_function
    - http://www.isthe.com/chongo/tech/comp/fnv/
    - packages/admin-ui/src/flags/fnv-hash.ts (TypeScript counterpart)
    - packages/admin-ui/src/flags/__tests__/fixtures/fnv-vectors.json (fixture)
"""

# This module is intentionally pure and dependency-free.
# Do NOT add imports -- no logging, no os, no httpx, no relative imports.
# Any future addition of an import to this file MUST be reviewed against
# Rules RF1 (no kalle/, blitzy-odoo/, packages/auth/ imports across libs)
# and RF7 (admin-ui MUST NOT import @blitzy/auth) before merge. The Python
# counterpart in this addon is held to the same isolation discipline.


# ---------------------------------------------------------------------------
# Constants -- FNV-1a 32-bit Algorithmic Parameters
# ---------------------------------------------------------------------------
#
# These constants are NOT magic numbers. They are the canonical algorithmic
# parameters for 32-bit FNV-1a as defined by Glenn Fowler, Landon Curt Noll,
# and Phong Vo, published at:
#
#   http://www.isthe.com/chongo/tech/comp/fnv/
#
# Substituting any other value would BREAK the cross-language parity
# contract (Rule RF4) with the TypeScript counterpart. The TypeScript
# implementation declares the same numeric values; the only spelling
# difference is naming convention (TypeScript uses ``FNV_OFFSET_BASIS_32``
# without leading underscore because it is module-private by export, while
# Python uses leading-underscore ``_FNV_OFFSET_BASIS_32`` for the same
# semantic of "module-internal").

#: FNV-1a 32-bit offset basis (the seed value before any byte is processed).
#:
#: Hexadecimal: ``0x811c9dc5``
#: Decimal:     ``2166136261``
#:
#: This is the canonical seed for 32-bit FNV-1a per the FNV reference page.
#: For an empty input the function would return this value unchanged; in this
#: module the input is always ``flag_name + ':' + subject`` which is at
#: minimum the single-byte string ``':'``, so the offset basis is always
#: mixed with at least one byte before being returned.
_FNV_OFFSET_BASIS_32: int = 0x811c9dc5  # 2166136261

#: FNV-1a 32-bit prime (the multiplier applied after each byte XOR).
#:
#: Hexadecimal: ``0x01000193``
#: Decimal:     ``16777619``
#:
#: This is the canonical FNV-32 prime. Any substitution silently breaks
#: the parity contract while still producing valid-looking 32-bit hashes.
#: The choice of this specific prime -- rather than a generic 32-bit prime --
#: is critical: FNV's avalanche characteristics depend on this exact value.
_FNV_PRIME_32: int = 0x01000193  # 16777619

#: 32-bit unsigned mask. After each multiplication we apply this mask to
#: truncate the result back to 32 bits, mirroring TypeScript's ``>>> 0``
#: unsigned-32-bit conversion. Python's ``int`` is unbounded internally,
#: so without the mask the hash would grow without limit and diverge from
#: the TypeScript counterpart after the first multiplication.
_UINT32_MASK: int = 0xFFFFFFFF  # 4294967295

#: Separator inserted between flag_name and subject before UTF-8 encoding.
#: This matches the TypeScript implementation's literal ``':'`` (ASCII
#: colon, code point 0x3A, single byte in UTF-8).
#:
#: CRITICAL: do not change to ``' '`` or ``'/'`` or ``'|'`` -- the
#: TypeScript-Python contract is locked to ``':'`` per AAP Section 0.1.2.
_SEPARATOR: str = ':'


# ---------------------------------------------------------------------------
# Public API -- fnv1a32
# ---------------------------------------------------------------------------


def fnv1a32(flag_name: str, subject: str = '') -> int:
    """Compute the FNV-1a 32-bit hash of ``flag_name + ':' + subject``.

    This function is the Python counterpart of
    ``packages/admin-ui/src/flags/fnv-hash.ts``. It MUST produce byte-
    identical output to the TypeScript implementation for every
    (flag_name, subject) pair (Rule RF4).

    The algorithm is:

        1. Initialize hash to the FNV-1a 32-bit offset basis
           (``0x811c9dc5`` = ``2166136261``).
        2. Concatenate ``flag_name + ':' + subject`` and encode as UTF-8.
        3. For each byte in the encoded sequence::

               hash = ((hash XOR byte) * FNV_PRIME_32) & 0xFFFFFFFF

        4. Return the final hash as a Python ``int`` in the range
           ``[0, 4294967295]``.

    The XOR-then-multiply order is what distinguishes FNV-1a from FNV-1
    (which multiplies first). The 32-bit mask ensures the result fits in
    an unsigned 32-bit integer regardless of Python's unbounded integer
    arithmetic, and is applied AFTER multiplication to mirror TypeScript's
    ``>>> 0`` (which converts a JavaScript number to unsigned 32-bit).

    No normalization is performed on the inputs. The TypeScript counterpart
    does not lowercase, trim, or otherwise mutate its inputs, and neither
    does this implementation -- the parity contract requires bit-exact
    equivalence of the encoded byte sequence.

    Args:
        flag_name: The flag identifier (e.g., ``'AUTH_V2_ENABLED'``).
            Case-sensitive; UPPERCASE convention but not enforced. May be
            an empty string, in which case the hash is computed over
            ``':' + subject``.
        subject: The user identifier (typically an email). Defaults to
            ``''`` (empty string) so callers MAY omit it for "no subject"
            cases. The TypeScript counterpart treats undefined/null as
            empty string identically; passing ``''`` here matches that
            behavior. NO normalization (no trim, no lowercase) is applied.

    Returns:
        A 32-bit unsigned integer in ``[0, 4294967295]`` inclusive.
        The same (flag_name, subject) pair always returns the same value
        (deterministic) and that value equals the TypeScript counterpart's
        output byte-for-byte.

    Examples:
        Canonical reference values from the FNV-32a specification (computed
        as ``fnv1a32(flag_name='', subject='') = fnv1a32 of bytes(':')``):

        >>> fnv1a32('', '')
        1057798253

        Explicit subject usage::

            >>> fnv1a32('AUTH_V2_ENABLED', 'alice@example.com')
            # deterministic value identical to TypeScript counterpart

        Default subject (equivalent to passing ``''``)::

            >>> fnv1a32('AUTH_V2_ENABLED') == fnv1a32('AUTH_V2_ENABLED', '')
            True

        Bucket calculation for a rollout percentage::

            >>> bucket = fnv1a32('NEW_CHECKOUT_FLOW', 'user@example.com') % 100
            >>> 0 <= bucket < 100
            True

    Note:
        The function is intentionally pure -- no side effects, no I/O, no
        logging, no module-level state. Callers can safely invoke it from
        any thread without coordination. Performance is dominated by the
        per-byte inner loop; for typical flag names (<=32 chars) and
        subjects (<=320 chars per RFC 5321) the call completes in a few
        microseconds and is suitable for hot-path use without caching.
    """
    # ------------------------------------------------------------------
    # Step 1: Initialize hash with the FNV-1a 32-bit offset basis.
    #
    # The offset basis is already <= 0xFFFFFFFF, so no masking is needed
    # at this point. Subsequent steps maintain the invariant
    # ``0 <= hash_val <= 0xFFFFFFFF`` after every iteration.
    # ------------------------------------------------------------------
    hash_val: int = _FNV_OFFSET_BASIS_32

    # ------------------------------------------------------------------
    # Step 2: Concatenate inputs with the separator and encode as UTF-8.
    #
    # ``str.encode('utf-8')`` is Python's standard UTF-8 encoder; ASCII
    # inputs encode to single-byte sequences (identical to ASCII), and
    # non-ASCII inputs (e.g., emails with international characters)
    # encode to multi-byte sequences using the standard UTF-8 rules.
    #
    # This MUST match TypeScript's ``new TextEncoder().encode(input)``
    # byte-for-byte; the WHATWG Encoding spec defines UTF-8 as the only
    # encoding TextEncoder supports, which is the same encoding Python's
    # ``encode('utf-8')`` produces.
    #
    # The concatenation uses the ``+`` operator rather than ``':'.join([...])``
    # because for two strings the operator form is both clearer and
    # marginally faster (no intermediate list allocation), matching the
    # TypeScript counterpart's ``flagName + ':' + subject``.
    # ------------------------------------------------------------------
    input_bytes: bytes = (flag_name + _SEPARATOR + subject).encode('utf-8')

    # ------------------------------------------------------------------
    # Step 3: For each byte, XOR THEN multiply (the FNV-1a order).
    #
    # FNV-1a: ``hash = (hash XOR byte) * prime``  (THIS variant)
    # FNV-1:  ``hash = (hash * prime) XOR byte``  (the other variant)
    #
    # Reversing the operations would silently produce a different hash
    # sequence (still 32-bit, still uniform-looking) and break parity.
    #
    # In Python 3, iterating a ``bytes`` object yields ``int`` values in
    # the range [0, 255] -- exactly what FNV's XOR step expects. No
    # conversion is needed; the byte int is XORed directly with the
    # current hash value, and the result is multiplied by the prime
    # before being masked back to 32 bits.
    #
    # Mask placement: the mask is applied AFTER multiplication, NOT
    # before. Applying it before would still leave a hash value in the
    # 32-bit range, but the multiplication ``(hash ^ byte) * prime``
    # produces an intermediate value that may exceed 2^32; applying the
    # mask afterward truncates to the lower 32 bits, mirroring
    # TypeScript's ``>>> 0`` semantics and matching the user's verbatim
    # algorithm specification.
    # ------------------------------------------------------------------
    for byte in input_bytes:
        hash_val = ((hash_val ^ byte) * _FNV_PRIME_32) & _UINT32_MASK

    # ------------------------------------------------------------------
    # Step 4: Return the final 32-bit unsigned hash.
    #
    # Postconditions:
    #   - 0 <= hash_val <= 0xFFFFFFFF (4294967295)
    #   - hash_val is the same value the TypeScript fnv1a32WithSubject
    #     would return for the same (flag_name, subject) pair
    #   - hash_val is reproducible: same inputs -> same output, every time
    #   - hash_val is suitable for ``% 100`` rollout-bucket computation
    # ------------------------------------------------------------------
    return hash_val
