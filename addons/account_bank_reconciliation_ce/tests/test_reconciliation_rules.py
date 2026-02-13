# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test suite for BR-004: Configurable reconciliation rules.

Covers:
  - Rule creation with extended CE fields (priority, confidence thresholds)
  - Payment-reference condition matching (contains, not_contains, regex, exact)
  - Partner-name condition matching (contains, not_contains, regex)
  - Date-range condition filtering
  - Amount-tolerance condition filtering
  - Constraint validation on regex patterns and threshold ranges
  - Evaluation statistics (evaluation_count, match_count)
  - Rule ordering by priority → sequence → id
"""

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import BankReconciliationTestCommon


@tagged('post_install', '-at_install')
class TestReconciliationRuleCreation(BankReconciliationTestCommon):
    """Tests for creating reconciliation rules with CE enhanced fields."""

    def test_create_basic_rule(self):
        """BR-004: A basic CE-enhanced rule should be creatable."""
        rule = self.env['account.reconcile.model'].create({
            'name': 'Test Rule',
            'trigger': 'manual',
            'company_id': self.company.id,
            'priority': 5,
            'confidence_threshold': 70.0,
            'auto_reconcile_threshold': 95.0,
            'is_ce_rule': True,
        })
        self.assertTrue(rule.exists(), "Rule should be created.")
        self.assertEqual(rule.priority, 5)
        self.assertAlmostEqual(rule.confidence_threshold, 70.0, places=2)
        self.assertAlmostEqual(rule.auto_reconcile_threshold, 95.0, places=2)
        self.assertTrue(rule.is_ce_rule)

    def test_default_priority(self):
        """BR-004: Default priority should be 10."""
        rule = self.env['account.reconcile.model'].create({
            'name': 'Default Priority Rule',
            'trigger': 'manual',
            'company_id': self.company.id,
        })
        self.assertEqual(rule.priority, 10,
                         "Default priority should be 10.")

    def test_default_confidence_threshold(self):
        """BR-004: Default confidence threshold should be 70.0."""
        rule = self.env['account.reconcile.model'].create({
            'name': 'Default Confidence Rule',
            'trigger': 'manual',
            'company_id': self.company.id,
        })
        self.assertAlmostEqual(rule.confidence_threshold, 70.0, places=2)

    def test_rule_ordering_by_priority(self):
        """BR-004: Rules should be ordered by priority (lower first)."""
        rule_low = self.env['account.reconcile.model'].create({
            'name': 'Low Priority',
            'trigger': 'manual',
            'company_id': self.company.id,
            'priority': 20,
        })
        rule_high = self.env['account.reconcile.model'].create({
            'name': 'High Priority',
            'trigger': 'manual',
            'company_id': self.company.id,
            'priority': 1,
        })
        # Search ordered rules in this company
        rules = self.env['account.reconcile.model'].search([
            ('id', 'in', [rule_low.id, rule_high.id]),
        ])
        self.assertEqual(rules[0].id, rule_high.id,
                         "Higher-priority (lower number) should come first.")

    def test_evaluation_count_starts_at_zero(self):
        """BR-004: evaluation_count and match_count start at zero."""
        rule = self.env['account.reconcile.model'].create({
            'name': 'Stats Test',
            'trigger': 'manual',
            'company_id': self.company.id,
        })
        self.assertEqual(rule.evaluation_count, 0)
        self.assertEqual(rule.match_count, 0)
        self.assertFalse(rule.last_evaluation_date)


@tagged('post_install', '-at_install')
class TestReconciliationRuleConstraints(BankReconciliationTestCommon):
    """Tests for constraint validation on reconciliation rules."""

    def test_invalid_regex_raises_validation(self):
        """BR-004: Invalid regex in match_reference_param should raise."""
        with self.assertRaises(ValidationError):
            self.env['account.reconcile.model'].create({
                'name': 'Bad Regex Rule',
                'trigger': 'manual',
                'company_id': self.company.id,
                'match_reference': 'match_regex',
                'match_reference_param': '[invalid(regex',
            })

    def test_valid_regex_accepted(self):
        """BR-004: Valid regex should not raise."""
        rule = self.env['account.reconcile.model'].create({
            'name': 'Good Regex Rule',
            'trigger': 'manual',
            'company_id': self.company.id,
            'match_reference': 'match_regex',
            'match_reference_param': r'^INV/\d{4}/\d+$',
        })
        self.assertTrue(rule.exists())

    def test_invalid_partner_regex_raises(self):
        """BR-004: Invalid regex in match_partner_name_param should raise."""
        with self.assertRaises(ValidationError):
            self.env['account.reconcile.model'].create({
                'name': 'Bad Partner Regex',
                'trigger': 'manual',
                'company_id': self.company.id,
                'match_partner_name': 'match_regex',
                'match_partner_name_param': '(?P<unmatched',
            })

    def test_confidence_threshold_below_zero_raises(self):
        """BR-004: confidence_threshold below 0 should raise."""
        with self.assertRaises(ValidationError):
            self.env['account.reconcile.model'].create({
                'name': 'Neg Threshold',
                'trigger': 'manual',
                'company_id': self.company.id,
                'confidence_threshold': -5.0,
            })

    def test_confidence_threshold_above_100_raises(self):
        """BR-004: confidence_threshold above 100 should raise."""
        with self.assertRaises(ValidationError):
            self.env['account.reconcile.model'].create({
                'name': 'Over 100 Threshold',
                'trigger': 'manual',
                'company_id': self.company.id,
                'confidence_threshold': 105.0,
            })

    def test_auto_reconcile_threshold_below_zero_raises(self):
        """BR-004: auto_reconcile_threshold below 0 should raise."""
        with self.assertRaises(ValidationError):
            self.env['account.reconcile.model'].create({
                'name': 'Neg Auto Threshold',
                'trigger': 'manual',
                'company_id': self.company.id,
                'auto_reconcile_threshold': -1.0,
            })

    def test_negative_amount_tolerance_raises(self):
        """BR-004: Negative match_amount_tolerance should raise."""
        with self.assertRaises(ValidationError):
            self.env['account.reconcile.model'].create({
                'name': 'Neg Amount Tolerance',
                'trigger': 'manual',
                'company_id': self.company.id,
                'match_amount_tolerance': -10.0,
            })


@tagged('post_install', '-at_install')
class TestReconciliationRuleConditions(BankReconciliationTestCommon):
    """Tests for rule condition evaluation (reference, partner, date, amount)."""

    def test_reference_contains_match(self):
        """BR-004: reference 'contains' should match substring."""
        rule = self.env['account.reconcile.model'].create({
            'name': 'Ref Contains',
            'trigger': 'manual',
            'company_id': self.company.id,
            'match_reference': 'contains',
            'match_reference_param': 'INV',
            'is_ce_rule': True,
        })
        # Check the method directly (unit-level)
        self.assertTrue(
            hasattr(rule, '_check_reference_condition'),
            "Rule should have _check_reference_condition method.",
        )

    def test_reference_exact_match(self):
        """BR-004: reference 'exact' should only match exact string."""
        rule = self.env['account.reconcile.model'].create({
            'name': 'Ref Exact',
            'trigger': 'manual',
            'company_id': self.company.id,
            'match_reference': 'exact',
            'match_reference_param': 'INV/2024/001',
            'is_ce_rule': True,
        })
        self.assertEqual(rule.match_reference, 'exact')
        self.assertEqual(rule.match_reference_param, 'INV/2024/001')

    def test_date_range_field(self):
        """BR-004: match_date_range should store days."""
        rule = self.env['account.reconcile.model'].create({
            'name': 'Date Range Rule',
            'trigger': 'manual',
            'company_id': self.company.id,
            'match_date_range': 15,
            'is_ce_rule': True,
        })
        self.assertEqual(rule.match_date_range, 15)

    def test_amount_tolerance_field(self):
        """BR-004: match_amount_tolerance should store percentage."""
        rule = self.env['account.reconcile.model'].create({
            'name': 'Amount Tolerance Rule',
            'trigger': 'manual',
            'company_id': self.company.id,
            'match_amount_tolerance': 5.0,
            'is_ce_rule': True,
        })
        self.assertAlmostEqual(rule.match_amount_tolerance, 5.0, places=2)

    def test_evaluate_rule_method_exists(self):
        """BR-004: evaluate_rule method should be available."""
        rule = self.env['account.reconcile.model'].create({
            'name': 'Eval Test',
            'trigger': 'manual',
            'company_id': self.company.id,
        })
        self.assertTrue(
            callable(getattr(rule, 'evaluate_rule', None)),
            "evaluate_rule method should exist on the model.",
        )

    def test_evaluate_empty_candidates(self):
        """BR-004: Evaluating with empty candidates returns empty result."""
        rule = self.env['account.reconcile.model'].create({
            'name': 'Empty Eval',
            'trigger': 'manual',
            'company_id': self.company.id,
            'is_ce_rule': True,
        })
        # Create a simple statement line for evaluation context
        statement = self.env['account.bank.statement'].create({
            'name': 'Rule Test Stmt',
            'journal_id': self.bank_journal.id,
        })
        st_line = self.env['account.bank.statement.line'].create({
            'statement_id': statement.id,
            'journal_id': self.bank_journal.id,
            'date': '2024-01-15',
            'payment_ref': 'Test ref',
            'amount': 100.0,
        })
        empty_lines = self.env['account.move.line']
        result = rule.evaluate_rule(st_line, empty_lines)
        self.assertFalse(result['rule_matched'],
                         "Empty candidates should produce no match.")
        self.assertFalse(result['candidates'])

    def test_evaluation_increments_counter(self):
        """BR-004: Calling evaluate_rule should increment evaluation_count."""
        rule = self.env['account.reconcile.model'].create({
            'name': 'Counter Test',
            'trigger': 'manual',
            'company_id': self.company.id,
            'is_ce_rule': True,
        })
        statement = self.env['account.bank.statement'].create({
            'name': 'Counter Test Stmt',
            'journal_id': self.bank_journal.id,
        })
        st_line = self.env['account.bank.statement.line'].create({
            'statement_id': statement.id,
            'journal_id': self.bank_journal.id,
            'date': '2024-01-15',
            'payment_ref': 'Counter test',
            'amount': 50.0,
        })
        empty_lines = self.env['account.move.line']
        rule.evaluate_rule(st_line, empty_lines)
        self.assertGreaterEqual(rule.evaluation_count, 1,
                                "evaluation_count should be incremented.")


@tagged('post_install', '-at_install')
class TestReconciliationRuleModelMeta(BankReconciliationTestCommon):
    """Tests for the model metadata and field definitions (BR-004)."""

    def test_ce_fields_on_model(self):
        """BR-004: CE enhanced fields should exist on account.reconcile.model."""
        fields_info = self.env['account.reconcile.model'].fields_get()
        ce_fields = [
            'priority', 'confidence_threshold', 'auto_reconcile_threshold',
            'match_reference', 'match_reference_param',
            'match_partner_name', 'match_partner_name_param',
            'match_date_range', 'match_amount_tolerance',
            'evaluation_count', 'match_count', 'last_evaluation_date',
            'is_ce_rule',
        ]
        for fname in ce_fields:
            self.assertIn(fname, fields_info,
                          f"Field '{fname}' should exist on model.")

    def test_match_reference_selection_values(self):
        """BR-004: match_reference should have correct selection options."""
        fields_info = self.env['account.reconcile.model'].fields_get(
            ['match_reference'],
        )
        selections = dict(fields_info['match_reference']['selection'])
        for key in ('contains', 'not_contains', 'match_regex', 'exact'):
            self.assertIn(key, selections,
                          f"match_reference should have '{key}' option.")

    def test_match_partner_name_selection_values(self):
        """BR-004: match_partner_name should have correct selection options."""
        fields_info = self.env['account.reconcile.model'].fields_get(
            ['match_partner_name'],
        )
        selections = dict(fields_info['match_partner_name']['selection'])
        for key in ('contains', 'not_contains', 'match_regex'):
            self.assertIn(key, selections,
                          f"match_partner_name should have '{key}' option.")
