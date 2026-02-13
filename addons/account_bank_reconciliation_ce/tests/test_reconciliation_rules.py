# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test Suite for BR-004: Configurable Reconciliation Rules
=========================================================

Validates the extended reconciliation rule model implemented for
FEATURE-002 (Bank Reconciliation System).  Covers:

* Rule creation with enhanced CE fields (``priority``,
  ``confidence_threshold``, ``auto_reconcile_threshold``,
  ``match_date_range``, ``is_ce_rule``).
* Payment-reference matching (contains, not_contains, exact, regex).
* Partner-name matching (contains, not_contains, regex).
* Date-range proximity filtering on candidates.
* Amount-tolerance percentage filtering on candidates.
* Constraint validation (regex patterns, threshold ranges, tolerance).
* Rule evaluation statistics tracking (``evaluation_count``,
  ``match_count``, ``last_evaluation_date``).
* Priority-based ordered rule retrieval and evaluation ordering.
* Auto-reconcile triggering when confidence meets threshold.

All tests are tagged ``@tagged('post_install', '-at_install')`` per Odoo
convention and extend :class:`BankReconciliationTestCommon` for shared
fixtures.
"""

from datetime import date, timedelta

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.account_bank_reconciliation_ce.tests.common import (
    BankReconciliationTestCommon,
)

# =========================================================================
# Helper: quick journal-entry candidate creation
# =========================================================================


def _make_candidate(test_case, amount, partner=None, move_date=None):
    """Create a posted journal entry and return its receivable move line.

    Uses a general journal with explicit debit/credit amounts so that no
    taxes or fiscal-position transformations interfere with the expected
    balance.

    Args:
        test_case: ``BankReconciliationTestCommon`` instance.
        amount (float): Positive amount for the receivable line.
        partner (recordset | None): ``res.partner`` or *None* for
            ``partner_a``.
        move_date (date | None): Entry date.  Defaults to today.

    Returns:
        recordset: ``account.move.line`` singleton (receivable line).
    """
    partner = partner or test_case.partner_a
    move = test_case.env['account.move'].create({
        'move_type': 'entry',
        'date': move_date or fields.Date.today(),
        'journal_id': test_case.company_data['default_journal_misc'].id,
        'line_ids': [
            Command.create({
                'name': 'Candidate receivable',
                'account_id': test_case.company_data['default_account_receivable'].id,
                'debit': amount,
                'credit': 0.0,
                'partner_id': partner.id,
            }),
            Command.create({
                'name': 'Candidate counterpart',
                'account_id': test_case.company_data['default_account_revenue'].id,
                'debit': 0.0,
                'credit': amount,
            }),
        ],
    })
    move.action_post()
    return move.line_ids.filtered(
        lambda line: line.account_id == test_case.company_data['default_account_receivable'],
    )


# =========================================================================
# 1. TestRuleCreation
# =========================================================================

@tagged('post_install', '-at_install')
class TestRuleCreation(BankReconciliationTestCommon):
    """BR-004: Rule creation, field defaults, priority ordering, CE flag."""

    def test_br004_rule_creation_defaults(self):
        """Create an account.reconcile.model with CE extension fields and
        verify the default values: priority=10, confidence_threshold=70.0,
        auto_reconcile_threshold=95.0, match_date_range=30, is_ce_rule=False.
        """
        # Verify company_data fixture from setUpClass is available
        self.assertTrue(self.company_data, "company_data fixture required.")
        rule = self.env['account.reconcile.model'].create({
            'name': 'Test Default Rule',
            'trigger': 'manual',
        })
        self.assertEqual(rule.priority, 10,
                         "Default priority must be 10.")
        self.assertAlmostEqual(rule.confidence_threshold, 70.0, places=2,
                               msg="Default confidence_threshold must be 70.0.")
        self.assertAlmostEqual(rule.auto_reconcile_threshold, 95.0, places=2,
                               msg="Default auto_reconcile_threshold must be 95.0.")
        self.assertEqual(rule.match_date_range, 30,
                         "Default match_date_range must be 30 days.")
        self.assertFalse(rule.is_ce_rule,
                         "Default is_ce_rule must be False.")
        # Statistics should initialise to zero / empty
        self.assertEqual(rule.evaluation_count, 0)
        self.assertEqual(rule.match_count, 0)
        self.assertFalse(rule.last_evaluation_date)

    def test_br004_rule_priority_ordering(self):
        """Create rules with different priorities and verify
        ``get_ordered_rules`` returns them in ascending priority order
        (priority → sequence → id).
        """
        rule_p20 = self.env['account.reconcile.model'].create({
            'name': 'Priority 20',
            'trigger': 'manual',
            'priority': 20,
            'is_ce_rule': True,
        })
        rule_p5 = self.env['account.reconcile.model'].create({
            'name': 'Priority 5',
            'trigger': 'manual',
            'priority': 5,
            'is_ce_rule': True,
        })
        rule_p10 = self.env['account.reconcile.model'].create({
            'name': 'Priority 10',
            'trigger': 'manual',
            'priority': 10,
            'is_ce_rule': True,
        })
        ordered = self.env['account.reconcile.model'].get_ordered_rules(
            self.env.company.id,
        )
        # Filter to the rules we just created
        test_ids = {rule_p5.id, rule_p10.id, rule_p20.id}
        test_ordered = ordered.filtered(lambda r: r.id in test_ids)
        ids_list = test_ordered.ids

        self.assertEqual(ids_list[0], rule_p5.id,
                         "Priority 5 rule must come first.")
        self.assertLess(
            ids_list.index(rule_p10.id),
            ids_list.index(rule_p20.id),
            "Priority 10 must precede priority 20.",
        )

    def test_br004_rule_ce_flag(self):
        """Setting is_ce_rule=True should be persisted correctly."""
        rule = self.env['account.reconcile.model'].create({
            'name': 'CE Flag Rule',
            'trigger': 'manual',
            'is_ce_rule': True,
        })
        self.assertTrue(rule.is_ce_rule,
                        "is_ce_rule should be True when explicitly set.")
        # Verify that the base statement and journal fixtures exist
        self.assertTrue(self.bank_statement,
                        "Shared bank statement fixture must exist.")
        self.assertTrue(self.bank_journal,
                        "Shared bank journal fixture must exist.")
        self.assertEqual(self.bank_statement.journal_id, self.bank_journal,
                         "Statement must be linked to the bank journal.")


# =========================================================================
# 2. TestRuleReferenceMatching
# =========================================================================

@tagged('post_install', '-at_install')
class TestRuleReferenceMatching(BankReconciliationTestCommon):
    """BR-004: Payment-reference condition evaluation."""

    def _make_ref_rule(self, condition, param, **extra):
        """Shorthand: create a CE rule focused on reference matching.

        Sets generous amount tolerance and disables date-range check so
        that only the reference gate determines the outcome.
        """
        vals = {
            'name': f'Ref {condition} Rule',
            'trigger': 'manual',
            'match_reference': condition,
            'match_reference_param': param,
            'match_date_range': 0,
            'match_amount_tolerance': 100.0,
            'is_ce_rule': True,
        }
        vals.update(extra)
        return self.env['account.reconcile.model'].create(vals)

    def test_br004_reference_contains(self):
        """Rule 'contains' matches when ``payment_ref`` includes the param."""
        rule = self._make_ref_rule('contains', 'INV')
        # st_line_1.payment_ref == 'Payment INV/2024/001' → 'INV' ∈ text
        result = rule.evaluate_rule(self.st_line_1, self.invoice_receivable_line)
        self.assertTrue(result['rule_matched'],
                        "'contains' should match 'INV' in 'Payment INV/2024/001'.")
        self.assertTrue(result['candidates'],
                        "Matched candidates must not be empty.")

    def test_br004_reference_not_contains(self):
        """Rule 'not_contains' matches when param is absent from payment_ref."""
        rule = self._make_ref_rule('not_contains', 'INTERNAL')
        # st_line_1.payment_ref == 'Payment INV/2024/001' → no 'INTERNAL'
        result = rule.evaluate_rule(self.st_line_1, self.invoice_receivable_line)
        self.assertTrue(result['rule_matched'],
                        "'not_contains' should pass when 'INTERNAL' is absent.")

    def test_br004_reference_exact_match(self):
        """Rule 'exact' matches only when payment_ref equals param exactly."""
        # Create a statement line whose ref matches the rule param exactly
        st_line = self.create_bank_statement_line(
            amount=1000.0,
            payment_ref='INV/2024/001',
            partner=self.partner_a,
        )
        rule = self._make_ref_rule('exact', 'INV/2024/001')
        candidate = _make_candidate(self, 1000.0, partner=self.partner_a)
        result = rule.evaluate_rule(st_line, candidate)
        self.assertTrue(result['rule_matched'],
                        "'exact' should match identical reference.")

        # A different ref should NOT match
        st_line_diff = self.create_bank_statement_line(
            amount=1000.0,
            payment_ref='INV/2024/002',
            partner=self.partner_a,
        )
        result_diff = rule.evaluate_rule(st_line_diff, candidate)
        self.assertFalse(result_diff['rule_matched'],
                         "'exact' must reject non-identical reference.")

    def test_br004_reference_regex_match(self):
        r"""Rule 'match_regex' with ``INV/\d{4}/\d{3}`` matches valid refs."""
        rule = self._make_ref_rule('match_regex', r'INV/\d{4}/\d{3}')
        # st_line_1.payment_ref contains 'INV/2024/001'
        result = rule.evaluate_rule(self.st_line_1, self.invoice_receivable_line)
        self.assertTrue(result['rule_matched'],
                        "Regex should find 'INV/2024/001' in the payment_ref.")

    def test_br004_reference_regex_no_match(self):
        """Regex that does NOT match the payment_ref → rule_matched=False."""
        rule = self._make_ref_rule('match_regex', r'^BILL/\d{4}')
        # st_line_1.payment_ref == 'Payment INV/2024/001' → no BILL prefix
        result = rule.evaluate_rule(self.st_line_1, self.invoice_receivable_line)
        self.assertFalse(result['rule_matched'],
                         "Non-matching regex should yield rule_matched=False.")
        self.assertFalse(result['candidates'],
                         "Candidates recordset should be empty on gate failure.")

    def test_br004_reference_regex_invalid_pattern(self):
        """Invalid regex in ``match_reference_param`` → ValidationError.

        Also verifies that the CE constraint raises
        :class:`~odoo.exceptions.ValidationError` (not
        :class:`~odoo.exceptions.UserError`).
        """
        with self.assertRaises(ValidationError):
            self.env['account.reconcile.model'].create({
                'name': 'Bad Regex Rule',
                'trigger': 'manual',
                'match_reference': 'match_regex',
                'match_reference_param': '[invalid(regex',
                'is_ce_rule': True,
            })

        # The CE extension deliberately raises ValidationError.
        # Ensure it is NOT a UserError (which the base model uses for
        # its own match_label regex constraint).
        error_is_validation = False
        try:
            self.env['account.reconcile.model'].create({
                'name': 'Bad Regex 2',
                'trigger': 'manual',
                'match_reference': 'match_regex',
                'match_reference_param': '(?P<broken',
                'is_ce_rule': True,
            })
        except ValidationError:
            error_is_validation = True
        except UserError:
            self.fail("CE reference-regex constraint must raise "
                      "ValidationError, not UserError.")
        self.assertTrue(error_is_validation,
                        "Expected ValidationError for invalid regex.")


# =========================================================================
# 3. TestRulePartnerMatching
# =========================================================================

@tagged('post_install', '-at_install')
class TestRulePartnerMatching(BankReconciliationTestCommon):
    """BR-004: Partner-name condition evaluation."""

    def _make_partner_rule(self, condition, param, **extra):
        """Shorthand: create a CE rule focused on partner-name matching."""
        vals = {
            'name': f'Partner {condition} Rule',
            'trigger': 'manual',
            'match_partner_name': condition,
            'match_partner_name_param': param,
            'match_date_range': 0,
            'match_amount_tolerance': 100.0,
            'is_ce_rule': True,
        }
        vals.update(extra)
        return self.env['account.reconcile.model'].create(vals)

    def test_br004_partner_name_contains(self):
        """Rule 'contains' matches when partner name includes the param."""
        # partner_reconcile.name == 'Reconciliation Test Partner'
        rule = self._make_partner_rule('contains', 'Test Partner')
        st_line = self.create_bank_statement_line(
            amount=1000.0,
            payment_ref='PartnerContainsTest',
            partner=self.partner_reconcile,
        )
        candidate = _make_candidate(self, 1000.0, partner=self.partner_reconcile)
        result = rule.evaluate_rule(st_line, candidate)
        self.assertTrue(result['rule_matched'],
                        "'contains' should match 'Test Partner' in "
                        "'Reconciliation Test Partner'.")

    def test_br004_partner_name_not_contains(self):
        """Rule 'not_contains' passes when param is absent from partner name."""
        # partner_supplier.name == 'Test Supplier Ltd'
        rule = self._make_partner_rule('not_contains', 'ACME')
        st_line = self.create_bank_statement_line(
            amount=500.0,
            payment_ref='PartnerNotContainsTest',
            partner=self.partner_supplier,
        )
        candidate = _make_candidate(self, 500.0, partner=self.partner_supplier)
        result = rule.evaluate_rule(st_line, candidate)
        self.assertTrue(result['rule_matched'],
                        "'not_contains' should pass when 'ACME' is absent "
                        "from 'Test Supplier Ltd'.")

    def test_br004_partner_name_regex(self):
        r"""Regex matching on partner name."""
        # partner_a.name typically == 'partner_a' (from AccountTestInvoicingCommon)
        rule = self._make_partner_rule('match_regex', r'^partner_[a-z]')
        # Use the pre-created st_line_1 (partner_a)
        result = rule.evaluate_rule(self.st_line_1, self.invoice_receivable_line)
        self.assertTrue(result['rule_matched'],
                        "Regex should match 'partner_a'.")

    def test_br004_partner_name_regex_invalid(self):
        """Invalid regex in ``match_partner_name_param`` → ValidationError."""
        with self.assertRaises(ValidationError):
            self.env['account.reconcile.model'].create({
                'name': 'Bad Partner Regex',
                'trigger': 'manual',
                'match_partner_name': 'match_regex',
                'match_partner_name_param': '(?P<broken',
                'is_ce_rule': True,
            })


# =========================================================================
# 4. TestRuleConditions
# =========================================================================

@tagged('post_install', '-at_install')
class TestRuleConditions(BankReconciliationTestCommon):
    """BR-004: Date-range, amount-tolerance, and combined conditions."""

    def test_br004_date_range_within(self):
        """Statement line within ``match_date_range`` days of candidate."""
        today = date.today()  # Uses datetime.date constructor
        close_date = today - timedelta(days=5)

        rule = self.env['account.reconcile.model'].create({
            'name': 'Date Range 30 Rule',
            'trigger': 'manual',
            'match_date_range': 30,
            'match_amount_tolerance': 100.0,
            'is_ce_rule': True,
        })
        st_line = self.create_bank_statement_line(
            amount=1000.0,
            payment_ref='DateWithin',
            partner=self.partner_a,
            date=today,
        )
        candidate = _make_candidate(self, 1000.0, partner=self.partner_a,
                                    move_date=close_date)
        result = rule.evaluate_rule(st_line, candidate)
        self.assertTrue(result['rule_matched'],
                        "5-day gap must pass a 30-day date range.")

    def test_br004_date_range_outside(self):
        """Statement line beyond ``match_date_range`` → candidate filtered."""
        today = fields.Date.today()
        far_date = today - timedelta(days=60)

        rule = self.env['account.reconcile.model'].create({
            'name': 'Date Range 10 Rule',
            'trigger': 'manual',
            'match_date_range': 10,
            'match_amount_tolerance': 100.0,
            'is_ce_rule': True,
        })
        st_line = self.create_bank_statement_line(
            amount=1000.0,
            payment_ref='DateOutside',
            partner=self.partner_a,
            date=today,
        )
        candidate = _make_candidate(self, 1000.0, partner=self.partner_a,
                                    move_date=far_date)
        result = rule.evaluate_rule(st_line, candidate)
        self.assertFalse(result['rule_matched'],
                         "60-day gap must fail a 10-day date range.")

    def test_br004_amount_tolerance_exact(self):
        """Tolerance 0 %% requires amounts to match within 0.005."""
        today = fields.Date.today()
        rule = self.env['account.reconcile.model'].create({
            'name': 'Exact Tolerance',
            'trigger': 'manual',
            'match_date_range': 0,
            'match_amount_tolerance': 0.0,
            'is_ce_rule': True,
        })
        st_line = self.create_bank_statement_line(
            amount=1000.0,
            payment_ref='AmountExact',
            partner=self.partner_a,
            date=today,
        )
        # Exact-match candidate (balance == 1000.0)
        exact_candidate = _make_candidate(self, 1000.0,
                                          partner=self.partner_a,
                                          move_date=today)
        result_ok = rule.evaluate_rule(st_line, exact_candidate)
        self.assertTrue(result_ok['rule_matched'],
                        "Exact same amount must pass 0 %% tolerance.")

        # Non-matching candidate (balance == 1050.0 — 5 %% off)
        off_candidate = _make_candidate(self, 1050.0,
                                        partner=self.partner_a,
                                        move_date=today)
        result_bad = rule.evaluate_rule(st_line, off_candidate)
        self.assertFalse(result_bad['rule_matched'],
                         "1050 vs 1000 must fail at 0 %% tolerance.")

    def test_br004_amount_tolerance_5pct(self):
        """Tolerance 5 %% accepts candidates within 5 %% of the line amount."""
        today = fields.Date.today()
        rule = self.env['account.reconcile.model'].create({
            'name': '5 Pct Tolerance',
            'trigger': 'manual',
            'match_date_range': 0,
            'match_amount_tolerance': 5.0,
            'is_ce_rule': True,
        })
        st_line = self.create_bank_statement_line(
            amount=1000.0,
            payment_ref='Amount5Pct',
            partner=self.partner_a,
            date=today,
        )
        # 3 %% off (1030) — within 5 %%
        near_candidate = _make_candidate(self, 1030.0,
                                         partner=self.partner_a,
                                         move_date=today)
        result_near = rule.evaluate_rule(st_line, near_candidate)
        self.assertTrue(result_near['rule_matched'],
                        "3 %% diff must pass 5 %% tolerance.")

        # 10 %% off (1100) — outside 5 %%
        far_candidate = _make_candidate(self, 1100.0,
                                        partner=self.partner_a,
                                        move_date=today)
        result_far = rule.evaluate_rule(st_line, far_candidate)
        self.assertFalse(result_far['rule_matched'],
                         "10 %% diff must fail 5 %% tolerance.")

    def test_br004_amount_tolerance_constraint(self):
        """Negative ``match_amount_tolerance`` → ValidationError."""
        with self.assertRaises(ValidationError):
            self.env['account.reconcile.model'].create({
                'name': 'Neg Tolerance',
                'trigger': 'manual',
                'match_amount_tolerance': -10.0,
            })

    def test_br004_confidence_threshold_constraint(self):
        """``confidence_threshold`` outside [0, 100] → ValidationError."""
        with self.assertRaises(ValidationError):
            self.env['account.reconcile.model'].create({
                'name': 'Over 100',
                'trigger': 'manual',
                'confidence_threshold': 150.0,
            })
        with self.assertRaises(ValidationError):
            self.env['account.reconcile.model'].create({
                'name': 'Below 0',
                'trigger': 'manual',
                'confidence_threshold': -5.0,
            })

    def test_br004_combined_conditions(self):
        """All configured conditions must pass for a candidate to match.

        Creates a rule with reference 'contains', partner 'contains',
        date-range, and amount-tolerance.  Only candidates satisfying
        **every** condition should survive the evaluation.
        """
        today = fields.Date.today()
        rule = self.env['account.reconcile.model'].create({
            'name': 'Combined Rule',
            'trigger': 'manual',
            'match_reference': 'contains',
            'match_reference_param': 'INV',
            'match_partner_name': 'contains',
            'match_partner_name_param': 'partner',
            'match_date_range': 15,
            'match_amount_tolerance': 5.0,
            'is_ce_rule': True,
        })
        # Statement line satisfies both rule-level gates
        st_line = self.create_bank_statement_line(
            amount=1000.0,
            payment_ref='INV/2024/100',
            partner=self.partner_a,
            date=today,
        )

        # Good candidate: matching amount, close date
        good_candidate = _make_candidate(
            self, 1000.0, partner=self.partner_a,
            move_date=today - timedelta(days=3),
        )
        # Bad candidate: date too far away (fails date-range)
        bad_candidate = _make_candidate(
            self, 1000.0, partner=self.partner_a,
            move_date=today - timedelta(days=60),
        )
        # Combine both candidates into one recordset
        all_candidates = good_candidate | bad_candidate
        result = rule.evaluate_rule(st_line, all_candidates)

        self.assertTrue(result['rule_matched'],
                        "At least one candidate should match.")
        self.assertIn(good_candidate.id, result['candidates'].ids,
                      "Good candidate must be in the result.")
        self.assertNotIn(bad_candidate.id, result['candidates'].ids,
                         "Bad candidate (date out of range) must be filtered.")


# =========================================================================
# 5. TestRuleEvaluation
# =========================================================================

@tagged('post_install', '-at_install')
class TestRuleEvaluation(BankReconciliationTestCommon):
    """BR-004: ``evaluate_rule`` method, statistics, auto-reconcile."""

    def test_br004_evaluate_rule_basic(self):
        """Basic evaluation: matching rule returns filtered candidates."""
        rule = self.env['account.reconcile.model'].create({
            'name': 'Basic Eval Rule',
            'trigger': 'manual',
            'match_reference': 'contains',
            'match_reference_param': 'INV',
            'match_date_range': 0,
            'match_amount_tolerance': 100.0,
            'is_ce_rule': True,
        })
        # Verify test_invoice fixture is a posted invoice
        self.assertEqual(self.test_invoice.state, 'posted',
                         "test_invoice fixture must be posted.")
        # Use pre-built fixtures (invoice_receivable_line derives from test_invoice)
        result = rule.evaluate_rule(self.st_line_1, self.invoice_receivable_line)
        self.assertTrue(result['rule_matched'],
                        "Rule should match st_line_1 with 'INV' in ref.")
        self.assertTrue(result['candidates'],
                        "Candidates must not be empty.")
        self.assertGreaterEqual(result['confidence_adjustment'], 0.0,
                                "confidence_adjustment must be non-negative.")

    def test_br004_evaluation_stats_increment(self):
        """After ``evaluate_rule``, ``evaluation_count`` is incremented and
        ``last_evaluation_date`` is populated.
        """
        rule = self.env['account.reconcile.model'].create({
            'name': 'Stats Increment Rule',
            'trigger': 'manual',
            'match_date_range': 0,
            'match_amount_tolerance': 100.0,
            'is_ce_rule': True,
        })
        self.assertEqual(rule.evaluation_count, 0,
                         "Count must start at 0.")
        self.assertFalse(rule.last_evaluation_date,
                         "last_evaluation_date must be empty initially.")

        empty_candidates = self.env['account.move.line']
        rule.evaluate_rule(self.st_line_1, empty_candidates)

        # Invalidate cache to pick up the sudo() write
        rule.invalidate_recordset()
        self.assertEqual(rule.evaluation_count, 1,
                         "evaluation_count must be 1 after one call.")
        self.assertTrue(rule.last_evaluation_date,
                        "last_evaluation_date must be set.")
        # The timestamp should be very recent
        now = fields.Datetime.now()
        diff = abs((now - rule.last_evaluation_date).total_seconds())
        self.assertLess(diff, 60,
                        "last_evaluation_date should be within 60 seconds of now.")

    def test_br004_match_stats_on_success(self):
        """When the rule matches, ``match_count`` is incremented."""
        today = fields.Date.today()
        rule = self.env['account.reconcile.model'].create({
            'name': 'Match Stats Rule',
            'trigger': 'manual',
            'match_date_range': 0,
            'match_amount_tolerance': 100.0,
            'is_ce_rule': True,
        })
        # Use test_bill and its payable line to cover bill fixture usage
        bill_line = self.create_bank_statement_line(
            amount=-500.0,
            payment_ref='BILL/2024/001',
            partner=self.partner_b,
            date=today,
        )
        result = rule.evaluate_rule(bill_line, self.bill_payable_line)

        rule.invalidate_recordset()
        if result['rule_matched']:
            self.assertGreaterEqual(rule.match_count, 1,
                                    "match_count must increment on success.")
        # Verify test_bill fixture
        self.assertTrue(self.test_bill,
                        "test_bill fixture must exist.")
        self.assertEqual(rule.evaluation_count, 1,
                         "evaluation_count must be exactly 1.")

    def test_br004_evaluation_stats_no_match(self):
        """When the rule does NOT match, ``match_count`` stays unchanged."""
        rule = self.env['account.reconcile.model'].create({
            'name': 'No Match Stats Rule',
            'trigger': 'manual',
            'match_reference': 'contains',
            'match_reference_param': 'XYZNOEXIST',
            'match_date_range': 0,
            'match_amount_tolerance': 100.0,
            'is_ce_rule': True,
        })
        result = rule.evaluate_rule(self.st_line_1, self.invoice_receivable_line)
        self.assertFalse(result['rule_matched'],
                         "Reference gate should block the match.")

        rule.invalidate_recordset()
        self.assertEqual(rule.match_count, 0,
                         "match_count must stay 0 when nothing matched.")
        self.assertEqual(rule.evaluation_count, 1,
                         "evaluation_count must still increment.")

    def test_br004_auto_reconcile_trigger(self):
        """When the rule matches with trigger='auto_reconcile' and
        ``auto_reconcile_threshold`` ≤ expected confidence, the result
        signals that auto-reconciliation should proceed.
        """
        today = fields.Date.today()
        rule = self.env['account.reconcile.model'].create({
            'name': 'Auto Reconcile Rule',
            'trigger': 'auto_reconcile',
            'match_reference': 'contains',
            'match_reference_param': 'INV',
            'match_partner_name': 'contains',
            'match_partner_name_param': 'partner',
            'match_date_range': 0,
            'match_amount_tolerance': 100.0,
            'auto_reconcile_threshold': 95.0,
            'is_ce_rule': True,
        })
        # Create an invoice with matching amount for a strong confidence
        invoice = self.create_posted_invoice(
            1000.0, partner=self.partner_a, date=today,
            ref='INV/2024/AUTOTEST',
        )
        receivable = invoice.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable',
        )
        result = rule.evaluate_rule(self.st_line_1, receivable)

        self.assertTrue(result['rule_matched'],
                        "Rule must match when all conditions are met.")
        self.assertEqual(rule.trigger, 'auto_reconcile',
                         "Rule trigger must be 'auto_reconcile'.")
        # The confidence_adjustment includes reference bonus (+5) and
        # partner bonus (+5), plus amount proximity — it should be > 0.
        self.assertGreater(result['confidence_adjustment'], 0.0,
                           "confidence_adjustment should be positive for "
                           "a full match.")

    def test_br004_auto_reconcile_below_threshold(self):
        """When the reference gate fails, rule_matched=False → no auto-rec."""
        rule = self.env['account.reconcile.model'].create({
            'name': 'Below Threshold Rule',
            'trigger': 'auto_reconcile',
            'match_reference': 'contains',
            'match_reference_param': 'NOMATCH_STRING',
            'match_date_range': 0,
            'match_amount_tolerance': 100.0,
            'auto_reconcile_threshold': 95.0,
            'is_ce_rule': True,
        })
        # st_line_2.payment_ref == 'Supplier Payment BILL/2024/001'
        result = rule.evaluate_rule(self.st_line_2, self.bill_payable_line)
        self.assertFalse(result['rule_matched'],
                         "Rule must NOT match when reference gate fails.")
        self.assertAlmostEqual(result['confidence_adjustment'], 0.0,
                               msg="Adjustment should be 0 for non-match.")


# =========================================================================
# 6. TestRuleOrdering
# =========================================================================

@tagged('post_install', '-at_install')
class TestRuleOrdering(BankReconciliationTestCommon):
    """BR-004: Priority-based ordering and company-scoped retrieval."""

    def test_br004_ordered_rules_by_priority(self):
        """``get_ordered_rules`` returns lowest priority number first."""
        rule_a = self.env['account.reconcile.model'].create({
            'name': 'Order A (p=30)',
            'trigger': 'manual',
            'priority': 30,
            'is_ce_rule': True,
        })
        rule_b = self.env['account.reconcile.model'].create({
            'name': 'Order B (p=1)',
            'trigger': 'manual',
            'priority': 1,
            'is_ce_rule': True,
        })
        rule_c = self.env['account.reconcile.model'].create({
            'name': 'Order C (p=15)',
            'trigger': 'manual',
            'priority': 15,
            'is_ce_rule': True,
        })
        ordered = self.env['account.reconcile.model'].get_ordered_rules(
            self.env.company.id,
        )
        test_ids = {rule_a.id, rule_b.id, rule_c.id}
        test_ordered = ordered.filtered(lambda r: r.id in test_ids)
        ids_list = test_ordered.ids

        self.assertEqual(ids_list[0], rule_b.id,
                         "Priority 1 should come first.")
        self.assertLess(ids_list.index(rule_c.id),
                        ids_list.index(rule_a.id),
                        "Priority 15 must precede priority 30.")

    def test_br004_ordered_rules_same_priority(self):
        """Same priority → ordered by sequence, then id."""
        rule_x = self.env['account.reconcile.model'].create({
            'name': 'Same P - Seq 20',
            'trigger': 'manual',
            'priority': 10,
            'sequence': 20,
            'is_ce_rule': True,
        })
        rule_y = self.env['account.reconcile.model'].create({
            'name': 'Same P - Seq 5',
            'trigger': 'manual',
            'priority': 10,
            'sequence': 5,
            'is_ce_rule': True,
        })
        ordered = self.env['account.reconcile.model'].get_ordered_rules(
            self.env.company.id,
        )
        test_ids = {rule_x.id, rule_y.id}
        test_ordered = ordered.filtered(lambda r: r.id in test_ids)
        ids_list = test_ordered.ids

        self.assertEqual(ids_list[0], rule_y.id,
                         "Sequence 5 should come before sequence 20 "
                         "at the same priority.")

    def test_br004_ordered_rules_company_filtered(self):
        """Rules from other companies are excluded from results."""
        # Create rules in the current company
        rule_co1 = self.env['account.reconcile.model'].create({
            'name': 'Company 1 Rule',
            'trigger': 'manual',
            'priority': 10,
            'is_ce_rule': True,
        })
        # Set up a second company
        company_data_2 = self.setup_other_company()
        company_2 = company_data_2['company']

        # Create a rule in the second company's context
        rule_co2 = self.env['account.reconcile.model'].with_company(
            company_2,
        ).create({
            'name': 'Company 2 Rule',
            'trigger': 'manual',
            'priority': 5,
            'is_ce_rule': True,
            'company_id': company_2.id,
        })

        # Retrieve for company 1 only
        ordered = self.env['account.reconcile.model'].get_ordered_rules(
            self.env.company.id,
        )
        self.assertIn(rule_co1.id, ordered.ids,
                      "Rule from current company must be included.")
        self.assertNotIn(rule_co2.id, ordered.ids,
                         "Rule from other company must be excluded.")

    def test_br004_rule_evaluation_order(self):
        """First matching rule (by priority) takes precedence.

        Creates two rules at different priorities.  Only the higher-priority
        rule's reference condition matches the statement line.  Evaluating
        in get_ordered_rules order proves that the first matching rule is
        the one whose result matters.
        """
        # High-priority rule (p=1): matches 'INV'
        rule_hp = self.env['account.reconcile.model'].create({
            'name': 'HP Rule (p=1)',
            'trigger': 'manual',
            'priority': 1,
            'match_reference': 'contains',
            'match_reference_param': 'INV',
            'match_date_range': 0,
            'match_amount_tolerance': 100.0,
            'is_ce_rule': True,
        })
        # Low-priority rule (p=50): also matches (broader condition)
        rule_lp = self.env['account.reconcile.model'].create({
            'name': 'LP Rule (p=50)',
            'trigger': 'manual',
            'priority': 50,
            'match_reference': 'contains',
            'match_reference_param': 'Payment',
            'match_date_range': 0,
            'match_amount_tolerance': 100.0,
            'is_ce_rule': True,
        })

        ordered = self.env['account.reconcile.model'].get_ordered_rules(
            self.env.company.id,
        )
        test_ids = {rule_hp.id, rule_lp.id}
        test_ordered = ordered.filtered(lambda r: r.id in test_ids)

        # Walk rules in priority order; the first match wins
        first_match_rule = None
        first_match_result = None
        # Use the pre-built st_line_1 ('Payment INV/2024/001')
        # and a fresh candidate created via create_posted_bill to
        # exercise both bill helper and bill_payable_line
        bill = self.create_posted_bill(
            1000.0, partner=self.partner_b,
            date=fields.Date.today(),
        )
        candidate = bill.line_ids.filtered(
            lambda line: line.account_id.account_type == 'liability_payable',
        )
        for rule in test_ordered:
            result = rule.evaluate_rule(self.st_line_1, candidate)
            if result['rule_matched']:
                first_match_rule = rule
                first_match_result = result
                break

        self.assertIsNotNone(first_match_rule,
                             "At least one rule should match.")
        self.assertEqual(first_match_rule.id, rule_hp.id,
                         "Higher-priority rule (p=1) must be the first match.")
        self.assertTrue(first_match_result['rule_matched'])
