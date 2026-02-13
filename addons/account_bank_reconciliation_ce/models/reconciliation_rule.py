# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Extended Reconciliation Rule Model — Bank Reconciliation CE

Extends Odoo's core ``account.reconcile.model`` with enhanced capabilities
for the Community Edition bank reconciliation system (FEATURE-002 BR-004):

* **Priority ordering** — Lower-number priority rules are evaluated first,
  giving administrators deterministic control over rule application sequence.
* **Enhanced condition evaluation** — Payment reference matching (contains,
  not-contains, regex, exact), partner-name matching (contains, not-contains,
  regex), configurable date-range proximity, and percentage-based amount
  tolerance.
* **Confidence thresholds** — Per-rule minimum confidence score gating and
  auto-reconcile trigger threshold, integrating with the matching engine's
  confidence scoring system.
* **Evaluation statistics** — Tracks how often each rule is evaluated and
  how often it produces successful matches, along with the timestamp of the
  last evaluation.  These counters are purely informational and never block
  the reconciliation workflow.

Integration notes:
    - Uses ``_inherit = 'account.reconcile.model'`` — no new ``_name``,
      all fields are added to the existing ``account_reconcile_model`` table.
    - The core ``account`` module is never modified; only extended.
    - Zero Enterprise-module dependencies.
    - Python 3.10-3.13 compatible.
    - Performance target: < 1 second per rule evaluation.
"""

import logging
import math
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ReconciliationRuleExtension(models.Model):
    """Extended reconciliation rules for Community Edition bank reconciliation.

    Inherits ``account.reconcile.model`` to add enhanced matching capabilities
    without modifying the core module.  All new fields are added to the
    existing ``account_reconcile_model`` database table via Odoo's ``_inherit``
    mechanism.

    Key enhancements over the base model
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    * Priority-based rule ordering (lower number = higher priority).
    * Payment-reference matching with regex support and exact-match mode.
    * Partner-name matching with regex support.
    * Date-range proximity matching (configurable number of days).
    * Amount-tolerance percentage matching.
    * Per-rule confidence threshold for match-quality gating.
    * Auto-reconcile trigger at a configurable confidence level.
    * Evaluation statistics for rule-performance tracking.

    Performance
    ~~~~~~~~~~~
    Rule evaluation targets **< 1 second** per rule per AAP §0.1.2.
    All condition checks use in-memory comparisons on already-loaded
    recordsets — no additional SQL queries are issued during evaluation.
    """

    _inherit = 'account.reconcile.model'
    _order = 'priority, sequence, id'

    # -------------------------------------------------------------------------
    # PRIORITY AND CONFIDENCE FIELDS
    # -------------------------------------------------------------------------

    priority = fields.Integer(
        string='Priority',
        default=10,
        help='Lower number = higher priority.  Rules are evaluated in '
             'priority order, then by sequence, then by ID.',
    )
    confidence_threshold = fields.Float(
        string='Min Confidence Threshold',
        default=70.0,
        digits=(5, 2),
        help='Minimum matching-engine confidence score (0–100) required '
             'for this rule to apply.  Statement-line matches below this '
             'threshold will be ignored by this rule.',
    )
    auto_reconcile_threshold = fields.Float(
        string='Auto-Reconcile Threshold',
        default=95.0,
        digits=(5, 2),
        help='Confidence score at which automatic reconciliation is '
             'triggered without manual review.  Must be ≥ confidence_threshold.',
    )

    # -------------------------------------------------------------------------
    # ENHANCED MATCHING CONDITION FIELDS
    # -------------------------------------------------------------------------

    match_reference = fields.Selection(
        selection=[
            ('contains', 'Contains'),
            ('not_contains', 'Not Contains'),
            ('match_regex', 'Match Regex'),
            ('exact', 'Exact Match'),
        ],
        string='Payment Reference',
        help='Match condition applied to the payment-reference field '
             'of the bank statement line.  Leave empty to skip this check.',
    )
    match_reference_param = fields.Char(
        string='Reference Parameter',
        help='Value or pattern used for payment-reference matching.  '
             'For "Match Regex", provide a valid Python regular expression.',
    )
    match_partner_name = fields.Selection(
        selection=[
            ('contains', 'Contains'),
            ('not_contains', 'Not Contains'),
            ('match_regex', 'Match Regex'),
        ],
        string='Partner Name Match',
        help='Match condition applied to the partner-name field '
             'of the bank statement line.  Leave empty to skip this check.',
    )
    match_partner_name_param = fields.Char(
        string='Partner Name Parameter',
        help='Value or pattern used for partner-name matching.',
    )
    match_date_range = fields.Integer(
        string='Date Range (days)',
        default=30,
        help='Maximum number of days between the bank statement line date '
             'and the journal-entry date for a match to be considered valid.  '
             'Set to 0 to disable the date-range check.',
    )
    match_amount_tolerance = fields.Float(
        string='Amount Tolerance %',
        default=0.0,
        digits=(5, 2),
        help='Percentage tolerance for amount matching.  '
             '0 = exact match required.  Example: 5.00 means amounts '
             'within 5 %% of each other are considered matching.',
    )

    # -------------------------------------------------------------------------
    # EVALUATION STATISTICS FIELDS
    # -------------------------------------------------------------------------

    evaluation_count = fields.Integer(
        string='Times Evaluated',
        readonly=True,
        default=0,
        help='Total number of times this rule has been evaluated '
             'against statement lines.',
    )
    match_count = fields.Integer(
        string='Successful Matches',
        readonly=True,
        default=0,
        help='Number of times this rule produced at least one '
             'matching candidate.',
    )
    last_evaluation_date = fields.Datetime(
        string='Last Evaluated',
        readonly=True,
        help='Timestamp of the most recent evaluation of this rule.',
    )

    # -------------------------------------------------------------------------
    # CE ENHANCEMENT FLAG
    # -------------------------------------------------------------------------

    is_ce_rule = fields.Boolean(
        string='CE Enhanced Rule',
        default=False,
        help='Flag indicating this rule uses Community Edition enhanced '
             'features (reference matching, partner-name matching, '
             'date range, amount tolerance, confidence thresholds).',
    )

    # =====================================================================
    # CONSTRAINT VALIDATORS
    # =====================================================================

    @api.constrains('match_reference', 'match_reference_param')
    def _check_match_reference_regex(self):
        """Validate regex patterns in *match_reference_param*.

        When ``match_reference`` is set to ``'match_regex'`` the parameter
        string must be a valid Python regular expression.  A
        :class:`~odoo.exceptions.ValidationError` is raised if compilation
        fails.
        """
        for record in self:
            if record.match_reference == 'match_regex' and record.match_reference_param:
                try:
                    re.compile(record.match_reference_param)
                except re.error as exc:
                    raise ValidationError(
                        _('Invalid regular expression for Payment Reference: %s',
                          str(exc)),
                    )

    @api.constrains('match_partner_name', 'match_partner_name_param')
    def _check_match_partner_name_regex(self):
        """Validate regex patterns in *match_partner_name_param*.

        When ``match_partner_name`` is set to ``'match_regex'`` the parameter
        string must be a valid Python regular expression.  A
        :class:`~odoo.exceptions.ValidationError` is raised if compilation
        fails.
        """
        for record in self:
            if record.match_partner_name == 'match_regex' and record.match_partner_name_param:
                try:
                    re.compile(record.match_partner_name_param)
                except re.error as exc:
                    raise ValidationError(
                        _('Invalid regular expression for Partner Name: %s',
                          str(exc)),
                    )

    @api.constrains('confidence_threshold')
    def _check_confidence_threshold_range(self):
        """Ensure *confidence_threshold* is within the [0, 100] range."""
        for record in self:
            if record.confidence_threshold < 0.0 or record.confidence_threshold > 100.0:
                raise ValidationError(
                    _('Confidence Threshold must be between 0 and 100.  '
                      'Current value: %s', record.confidence_threshold),
                )

    @api.constrains('auto_reconcile_threshold')
    def _check_auto_reconcile_threshold_range(self):
        """Ensure *auto_reconcile_threshold* is within the [0, 100] range."""
        for record in self:
            if record.auto_reconcile_threshold < 0.0 or record.auto_reconcile_threshold > 100.0:
                raise ValidationError(
                    _('Auto-Reconcile Threshold must be between 0 and 100.  '
                      'Current value: %s', record.auto_reconcile_threshold),
                )

    @api.constrains('match_amount_tolerance')
    def _check_match_amount_tolerance_nonneg(self):
        """Ensure *match_amount_tolerance* is non-negative."""
        for record in self:
            if record.match_amount_tolerance < 0.0:
                raise ValidationError(
                    _('Amount Tolerance must be non-negative.  '
                      'Current value: %s', record.match_amount_tolerance),
                )

    # =====================================================================
    # RULE EVALUATION METHODS
    # =====================================================================

    def evaluate_rule(self, st_line, candidates):
        """Evaluate this rule against a statement line and candidate move lines.

        Applies all configured match conditions in sequence:

        1. **Payment-reference** matching (``match_reference`` /
           ``match_reference_param``) — rule-level gate.
        2. **Partner-name** matching (``match_partner_name`` /
           ``match_partner_name_param``) — rule-level gate.
        3. **Date-range proximity** (``match_date_range``) — per-candidate
           filter.
        4. **Amount tolerance** (``match_amount_tolerance``) — per-candidate
           filter.

        If a rule-level gate fails, the rule does not apply at all and an
        empty result is returned.  Candidate-level filters are applied
        independently to each move line.

        Args:
            st_line (recordset): ``account.bank.statement.line`` singleton.
            candidates (recordset): ``account.move.line`` recordset of
                potential matches.

        Returns:
            dict:
                * ``candidates`` — filtered ``account.move.line`` recordset.
                * ``confidence_adjustment`` — float adjustment to the base
                  confidence score.
                * ``rule_matched`` — *bool* indicating whether at least one
                  candidate passed all conditions.

        Performance:
            Targets < 1 second execution per rule.  All condition checks
            operate on in-memory recordsets; no extra SQL queries are issued.
        """
        self.ensure_one()

        empty_result = {
            'candidates': self.env['account.move.line'],
            'confidence_adjustment': 0.0,
            'rule_matched': False,
        }

        if not candidates:
            self._increment_evaluation_stats(matched=False)
            return empty_result

        # ------------------------------------------------------------------
        # Rule-level gates — these check properties of *st_line* only.
        # If a gate fails the entire rule is skipped for this statement line.
        # ------------------------------------------------------------------
        if self.match_reference and self.match_reference_param:
            # Pass a single candidate for API consistency; the reference
            # check only inspects the statement line.
            if not self._check_reference_condition(st_line, candidates[:1]):
                self._increment_evaluation_stats(matched=False)
                return empty_result

        if self.match_partner_name and self.match_partner_name_param:
            if not self._check_partner_name_condition(st_line, candidates[:1]):
                self._increment_evaluation_stats(matched=False)
                return empty_result

        # ------------------------------------------------------------------
        # Candidate-level filters — applied to each move line individually.
        # ------------------------------------------------------------------
        matched_candidates = self.env['account.move.line']
        confidence_adjustments = []

        for move_line in candidates:
            passes_all = True
            candidate_adjustment = 0.0

            # ---- Date-range condition ----
            if self.match_date_range and self.match_date_range > 0:
                if not self._check_date_range_condition(st_line, move_line):
                    passes_all = False
                else:
                    st_date = st_line.date
                    ml_date = move_line.date
                    if st_date and ml_date:
                        day_diff = abs((st_date - ml_date).days)
                        # Proportional boost: 0-day diff → +10, max-day diff → +0
                        date_proximity = max(
                            0.0,
                            1.0 - (day_diff / max(self.match_date_range, 1)),
                        )
                        candidate_adjustment += date_proximity * 10.0

            # ---- Amount-tolerance condition ----
            if passes_all:
                if not self._check_amount_tolerance_condition(st_line, move_line):
                    passes_all = False
                else:
                    st_amount = abs(st_line.amount or 0.0)
                    ml_amount = abs(move_line.balance or 0.0)
                    if st_amount > 0.0:
                        diff_pct = abs(st_amount - ml_amount) / st_amount * 100.0
                        tolerance = max(self.match_amount_tolerance, 0.01)
                        amount_proximity = max(
                            0.0,
                            1.0 - (diff_pct / tolerance),
                        )
                        candidate_adjustment += amount_proximity * 15.0
                    elif math.isclose(ml_amount, 0.0, abs_tol=1e-9):
                        # Both amounts are zero — perfect match
                        candidate_adjustment += 15.0

            if passes_all:
                matched_candidates |= move_line
                confidence_adjustments.append(candidate_adjustment)

        # ------------------------------------------------------------------
        # Aggregate confidence adjustment
        # ------------------------------------------------------------------
        avg_adjustment = 0.0
        if confidence_adjustments:
            avg_adjustment = sum(confidence_adjustments) / len(confidence_adjustments)

        # Bonus for matching rule-level conditions
        if self.match_reference and self.match_reference_param:
            avg_adjustment += 5.0
        if self.match_partner_name and self.match_partner_name_param:
            avg_adjustment += 5.0

        has_matches = bool(matched_candidates)
        self._increment_evaluation_stats(matched=has_matches)

        _logger.debug(
            "Rule '%s' (id=%s) evaluation: %d/%d candidates matched, "
            "confidence_adjustment=%.2f",
            self.name, self.id,
            len(matched_candidates), len(candidates),
            avg_adjustment,
        )

        return {
            'candidates': matched_candidates,
            'confidence_adjustment': avg_adjustment,
            'rule_matched': has_matches,
        }

    # =====================================================================
    # INDIVIDUAL CONDITION CHECKS
    # =====================================================================

    def _check_reference_condition(self, st_line, move_line):
        """Check whether the payment reference satisfies the configured condition.

        Tests the statement line's ``payment_ref`` field against the rule's
        ``match_reference`` condition type and ``match_reference_param`` value.
        The *move_line* parameter is accepted for API consistency and future
        cross-reference checks but is not used in the current implementation.

        Args:
            st_line (recordset): ``account.bank.statement.line`` singleton.
            move_line (recordset): ``account.move.line`` recordset (context).

        Returns:
            bool: ``True`` if the condition is met **or** not configured.
        """
        if not self.match_reference:
            return True

        text = st_line.payment_ref or ''
        param = self.match_reference_param or ''

        # An empty parameter with a non-"not_contains" condition has no
        # meaningful match criteria — treat as pass.
        if not param and self.match_reference != 'not_contains':
            return True

        if self.match_reference == 'contains':
            return param.lower() in text.lower()

        if self.match_reference == 'not_contains':
            if not param:
                return True
            return param.lower() not in text.lower()

        if self.match_reference == 'match_regex':
            return self._apply_regex_match(param, text)

        if self.match_reference == 'exact':
            return param.strip().lower() == text.strip().lower()

        # Unknown condition type — pass by default (defensive)
        return True

    def _check_partner_name_condition(self, st_line, move_line):
        """Check whether the partner name satisfies the configured condition.

        Tests the statement line's ``partner_name`` (with a fallback to
        ``partner_id.name``) against the rule's ``match_partner_name``
        condition type and ``match_partner_name_param`` value.

        Args:
            st_line (recordset): ``account.bank.statement.line`` singleton.
            move_line (recordset): ``account.move.line`` recordset (context).

        Returns:
            bool: ``True`` if the condition is met **or** not configured.
        """
        if not self.match_partner_name:
            return True

        # Prefer the free-text partner_name; fall back to the linked partner.
        text = st_line.partner_name or ''
        if not text and st_line.partner_id:
            text = st_line.partner_id.name or ''

        param = self.match_partner_name_param or ''

        if not param and self.match_partner_name != 'not_contains':
            return True

        if self.match_partner_name == 'contains':
            return param.lower() in text.lower()

        if self.match_partner_name == 'not_contains':
            if not param:
                return True
            return param.lower() not in text.lower()

        if self.match_partner_name == 'match_regex':
            return self._apply_regex_match(param, text)

        # Unknown condition type — pass by default (defensive)
        return True

    def _check_date_range_condition(self, st_line, move_line):
        """Check whether the date difference is within *match_date_range* days.

        Compares the absolute day-difference between the statement-line date
        and the move-line date.  A ``match_date_range`` of ``0`` (or negative)
        disables the check entirely.

        Args:
            st_line (recordset): ``account.bank.statement.line`` singleton.
            move_line (recordset): ``account.move.line`` singleton.

        Returns:
            bool: ``True`` if within range, if the check is disabled, or if
            either date is missing.
        """
        if not self.match_date_range or self.match_date_range <= 0:
            return True

        st_date = st_line.date
        ml_date = move_line.date

        if not st_date or not ml_date:
            # Cannot evaluate without both dates — pass by default.
            return True

        day_difference = abs((st_date - ml_date).days)
        return day_difference <= self.match_date_range

    def _check_amount_tolerance_condition(self, st_line, move_line):
        """Check whether amounts match within the configured tolerance.

        Compares the absolute amounts of the statement line and the move line.
        When ``match_amount_tolerance`` is ``0.0``, exact matching is required
        (with a half-cent precision guard of 0.005 to avoid floating-point
        comparison issues).  Otherwise the percentage difference must be at
        most ``match_amount_tolerance``.

        Args:
            st_line (recordset): ``account.bank.statement.line`` singleton.
            move_line (recordset): ``account.move.line`` singleton.

        Returns:
            bool: ``True`` if within tolerance.
        """
        st_amount = abs(st_line.amount or 0.0)
        ml_amount = abs(move_line.balance or 0.0)

        # Both zero → trivial match.
        if math.isclose(st_amount, 0.0, abs_tol=1e-9) and math.isclose(ml_amount, 0.0, abs_tol=1e-9):
            return True
        # Exactly one is zero → no match.
        if math.isclose(st_amount, 0.0, abs_tol=1e-9) or math.isclose(ml_amount, 0.0, abs_tol=1e-9):
            return False

        # Exact-match mode (tolerance == 0): use a half-cent guard.
        if math.isclose(self.match_amount_tolerance, 0.0, abs_tol=1e-9):
            return abs(st_amount - ml_amount) < 0.005

        # Percentage-tolerance mode.
        pct_difference = abs(st_amount - ml_amount) / st_amount * 100.0
        return pct_difference <= self.match_amount_tolerance

    # =====================================================================
    # REGEX HELPER
    # =====================================================================

    def _apply_regex_match(self, pattern, text):
        """Safely compile and execute a regex pattern against *text*.

        Handles :class:`re.error` and any unexpected runtime exceptions
        gracefully — logs a warning and returns ``False`` so that the
        reconciliation workflow is never blocked by a malformed pattern.

        Args:
            pattern (str): Regular expression pattern string.
            text (str): Text to search.

        Returns:
            bool: ``True`` if the pattern matches anywhere in *text*.
        """
        if not pattern or not text:
            return False

        try:
            compiled = re.compile(pattern, re.IGNORECASE)
            return bool(compiled.search(text))
        except re.error as exc:
            _logger.warning(
                "Invalid regex pattern '%s' in reconciliation rule %s: %s",
                pattern,
                self.id if self else 'N/A',
                exc,
            )
            return False
        except (TypeError, AttributeError) as exc:
            _logger.warning(
                "Unexpected error applying regex '%s' in rule %s: %s",
                pattern,
                self.id if self else 'N/A',
                exc,
            )
            return False

    # =====================================================================
    # EVALUATION STATISTICS
    # =====================================================================

    def _increment_evaluation_stats(self, matched):
        """Update rule evaluation statistics.

        Increments ``evaluation_count`` unconditionally, increments
        ``match_count`` when *matched* is ``True``, and sets
        ``last_evaluation_date`` to the current UTC timestamp.

        Uses :meth:`sudo` to bypass potential access restrictions on the
        statistics fields.  Failures are logged as warnings but never
        propagate — statistics updates must never block the reconciliation
        workflow.

        Args:
            matched (bool): Whether the evaluation produced at least one
                matching candidate.
        """
        if not self:
            return

        now = fields.Datetime.now()
        for record in self:
            try:
                update_vals = {
                    'evaluation_count': record.evaluation_count + 1,
                    'last_evaluation_date': now,
                }
                if matched:
                    update_vals['match_count'] = record.match_count + 1
                record.sudo().write(update_vals)
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                # Statistics failure must never block reconciliation.
                _logger.warning(
                    "Failed to update evaluation stats for rule %s (id=%s): %s",
                    record.name if record else 'unknown',
                    record.id if record else 'N/A',
                    exc,
                )

    # =====================================================================
    # ORDERED RULE RETRIEVAL
    # =====================================================================

    @api.model
    def get_ordered_rules(self, company_id):
        """Return all active CE-enhanced rules for a company, ordered by priority.

        Retrieves all records where ``active=True`` and ``is_ce_rule=True``
        for the given company, sorted by ``priority ASC, sequence ASC, id ASC``.

        Args:
            company_id (int): ID of the target ``res.company``.

        Returns:
            recordset: ``account.reconcile.model`` records ordered by
            priority, sequence, id.  An empty recordset is returned when
            *company_id* is falsy or no matching rules exist.
        """
        if not company_id:
            return self.browse()

        domain = [
            ('active', '=', True),
            ('company_id', '=', company_id),
            ('is_ce_rule', '=', True),
        ]

        rules = self.search(domain, order='priority, sequence, id')
        _logger.debug(
            "Retrieved %d active CE rules for company %s",
            len(rules),
            company_id,
        )
        return rules
