# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test suite for Directive 5: candidate_date_window parameter threading and
validation in the bank reconciliation wizard.

Covers two acceptance criteria:

(a) The ``date_window`` parameter threads from the
    :class:`~odoo.addons.account_bank_reconciliation_ce.wizard.reconciliation_wizard.ReconciliationWizard`
    field value through
    :meth:`~odoo.addons.account_bank_reconciliation_ce.models.reconciliation_matching_engine.ReconciliationMatchingEngine.find_matches`
    into
    :meth:`~odoo.addons.account_bank_reconciliation_ce.models.reconciliation_matching_engine.ReconciliationMatchingEngine._get_candidate_move_lines`.
    The test captures the ``date_window`` kwarg received by the inner-most
    helper and asserts it equals the wizard field value.

(b) The ``@api.constrains('candidate_date_window')`` validator raises
    :class:`~odoo.exceptions.ValidationError` when the field is set to
    zero or a negative integer.

These tests back up the Phase-5 refactor requested by the Refine PR
instructions and prevent regression.
"""

from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.account_bank_reconciliation_ce.tests.common import (
    BankReconciliationTestCommon,
)


# ---------------------------------------------------------------------------
# (a) date_window parameter threading
# ---------------------------------------------------------------------------
@tagged('post_install', '-at_install')
class TestCandidateDateWindowThreading(BankReconciliationTestCommon):
    """Verify the ``candidate_date_window`` wizard field propagates end-to-end.

    The matching engine exposes a ``date_window`` parameter on both
    :meth:`find_matches` and :meth:`_get_candidate_move_lines`.  The
    reconciliation wizard's ``candidate_date_window`` :class:`Integer` field
    is passed verbatim into :meth:`find_matches`, which in turn forwards it
    into :meth:`_get_candidate_move_lines`.  These tests validate that the
    value the user enters in the UI is the value used when computing the
    date-boundary domain on ``account.move.line`` queries.
    """

    def test_directive5_date_window_threads_to_candidate_retrieval(self):
        """The wizard field value reaches ``_get_candidate_move_lines``.

        Given a reconciliation wizard with ``candidate_date_window = 45``,
        When ``action_find_matches`` is triggered,
        Then ``_get_candidate_move_lines`` receives ``date_window=45``.
        """
        # Arrange — create a wizard bound to the bank journal with a custom
        # date window distinct from both the engine default (90) and 0.
        wizard = self.env['account.reconciliation.wizard'].create({
            'journal_id': self.bank_journal.id,
            'candidate_date_window': 45,
        })
        # Ensure the statement lines computed field is populated.
        wizard._compute_statement_lines()

        # Patch ``_get_candidate_move_lines`` on the engine class to capture
        # the ``date_window`` kwarg it receives.  Returning an empty recordset
        # keeps the rest of the pipeline a no-op.
        captured = {}
        original = type(self.env['account.reconciliation.matching'])\
            ._get_candidate_move_lines

        def _spy(engine_self, st_line, journal, date_window=None):
            # Record only the first call's kwarg — additional calls for the
            # same wizard will carry the same value per the contract.
            captured.setdefault('date_window', date_window)
            # Delegate to the real implementation for behaviour parity.
            return original(engine_self, st_line, journal, date_window=date_window)

        with patch.object(
            type(self.env['account.reconciliation.matching']),
            '_get_candidate_move_lines',
            _spy,
        ):
            wizard.action_find_matches()

        # Assert — the spy captured the wizard's field value.
        self.assertIn(
            'date_window', captured,
            "_get_candidate_move_lines must be invoked at least once "
            "during action_find_matches when unreconciled lines exist.",
        )
        self.assertEqual(
            captured['date_window'], 45,
            "The wizard's candidate_date_window field value must thread "
            "verbatim through find_matches into _get_candidate_move_lines; "
            "got %s instead of 45." % captured['date_window'],
        )

    def test_directive5_date_window_default_threads_through(self):
        """The default value (90) also threads end-to-end.

        Given a wizard created without overriding ``candidate_date_window``,
        When ``action_find_matches`` is triggered,
        Then ``_get_candidate_move_lines`` receives ``date_window=90``.
        """
        wizard = self.env['account.reconciliation.wizard'].create({
            'journal_id': self.bank_journal.id,
        })
        wizard._compute_statement_lines()
        self.assertEqual(
            wizard.candidate_date_window, 90,
            "Default candidate_date_window should be 90 days.",
        )

        captured = {}
        original = type(self.env['account.reconciliation.matching'])\
            ._get_candidate_move_lines

        def _spy(engine_self, st_line, journal, date_window=None):
            captured.setdefault('date_window', date_window)
            return original(
                engine_self, st_line, journal, date_window=date_window,
            )

        with patch.object(
            type(self.env['account.reconciliation.matching']),
            '_get_candidate_move_lines',
            _spy,
        ):
            wizard.action_find_matches()

        self.assertIn(
            'date_window', captured,
            "_get_candidate_move_lines must be invoked when unreconciled "
            "lines exist.",
        )
        self.assertEqual(
            captured['date_window'], 90,
            "The default candidate_date_window (90) must thread through.",
        )

    def test_directive5_find_matches_accepts_date_window_kwarg(self):
        """``find_matches`` accepts and honours an explicit ``date_window``.

        Directly calling the engine with a custom ``date_window`` must
        forward it verbatim to ``_get_candidate_move_lines``.  This is the
        unit-level contract test independent of the wizard layer.
        """
        MatchModel = self.env['account.reconciliation.matching']
        # Any non-reconciled statement line suffices as the subject.
        st_lines = self.bank_statement.line_ids.filtered(
            lambda sl: not sl.is_reconciled,
        )
        self.assertTrue(
            st_lines,
            "Test fixture must expose at least one unreconciled statement "
            "line; check BankReconciliationTestCommon.",
        )

        captured = {}
        original = type(MatchModel)._get_candidate_move_lines

        def _spy(engine_self, st_line, journal, date_window=None):
            captured.setdefault('date_window', date_window)
            return original(
                engine_self, st_line, journal, date_window=date_window,
            )

        with patch.object(
            type(MatchModel), '_get_candidate_move_lines', _spy,
        ):
            MatchModel.find_matches(
                st_lines,
                journal_id=self.bank_journal.id,
                date_window=7,
            )

        self.assertEqual(
            captured.get('date_window'), 7,
            "find_matches must forward its date_window kwarg to "
            "_get_candidate_move_lines verbatim.",
        )


# ---------------------------------------------------------------------------
# (b) @api.constrains rejects non-positive values
# ---------------------------------------------------------------------------
@tagged('post_install', '-at_install')
class TestCandidateDateWindowConstraint(BankReconciliationTestCommon):
    """Verify ``@api.constrains`` rejects invalid ``candidate_date_window``.

    The wizard's validator must raise :class:`ValidationError` for any value
    that is not a strictly positive integer.  Zero and negative integers are
    explicitly invalid because they either collapse the candidate window to
    zero days (no candidates ever match) or invert the date boundaries
    (non-sensical).
    """

    def test_directive5_constrains_rejects_zero(self):
        """``candidate_date_window = 0`` must raise ``ValidationError``.

        Given a reconciliation wizard,
        When the ``candidate_date_window`` is set to 0,
        Then a ``ValidationError`` is raised.
        """
        with self.assertRaises(
            ValidationError,
            msg="candidate_date_window = 0 must raise ValidationError",
        ):
            self.env['account.reconciliation.wizard'].create({
                'journal_id': self.bank_journal.id,
                'candidate_date_window': 0,
            })

    def test_directive5_constrains_rejects_negative(self):
        """Negative ``candidate_date_window`` must raise ``ValidationError``.

        Given a reconciliation wizard,
        When the ``candidate_date_window`` is set to a negative value (-1),
        Then a ``ValidationError`` is raised.
        """
        with self.assertRaises(
            ValidationError,
            msg="candidate_date_window = -1 must raise ValidationError",
        ):
            self.env['account.reconciliation.wizard'].create({
                'journal_id': self.bank_journal.id,
                'candidate_date_window': -1,
            })

    def test_directive5_constrains_rejects_large_negative(self):
        """A large negative ``candidate_date_window`` must raise.

        Given an existing reconciliation wizard,
        When ``candidate_date_window`` is updated to a large negative value,
        Then a ``ValidationError`` is raised.
        """
        wizard = self.env['account.reconciliation.wizard'].create({
            'journal_id': self.bank_journal.id,
            'candidate_date_window': 90,
        })
        with self.assertRaises(
            ValidationError,
            msg="candidate_date_window = -100 must raise ValidationError",
        ):
            wizard.candidate_date_window = -100

    def test_directive5_constrains_accepts_positive_values(self):
        """Positive integers must pass the ``@api.constrains`` check.

        Given a reconciliation wizard,
        When ``candidate_date_window`` is set to any positive integer,
        Then no error is raised.
        """
        # Small boundary value.
        w1 = self.env['account.reconciliation.wizard'].create({
            'journal_id': self.bank_journal.id,
            'candidate_date_window': 1,
        })
        self.assertEqual(w1.candidate_date_window, 1)

        # Typical value.
        w2 = self.env['account.reconciliation.wizard'].create({
            'journal_id': self.bank_journal.id,
            'candidate_date_window': 180,
        })
        self.assertEqual(w2.candidate_date_window, 180)

        # Larger value.
        w3 = self.env['account.reconciliation.wizard'].create({
            'journal_id': self.bank_journal.id,
            'candidate_date_window': 365,
        })
        self.assertEqual(w3.candidate_date_window, 365)

    def test_directive5_constrains_on_write(self):
        """The constraint fires on ``write`` as well as ``create``.

        Given an existing wizard with a valid candidate_date_window,
        When the field is updated to an invalid value,
        Then a ``ValidationError`` is raised.
        """
        wizard = self.env['account.reconciliation.wizard'].create({
            'journal_id': self.bank_journal.id,
            'candidate_date_window': 30,
        })
        # Sanity: valid write first.
        wizard.candidate_date_window = 60
        self.assertEqual(wizard.candidate_date_window, 60)

        # Invalid write must raise.
        with self.assertRaises(
            ValidationError,
            msg="Write of candidate_date_window=0 must raise ValidationError",
        ):
            wizard.candidate_date_window = 0
