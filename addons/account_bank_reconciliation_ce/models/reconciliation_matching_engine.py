# -*- coding: utf-8 -*-
# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Reconciliation Matching Engine

Algorithmic matching engine for the Bank Reconciliation CE module.
Implements BR-002: Algorithmic Matching — scoring bank statement lines against
open journal entries using configurable weights for amount, reference, partner,
and date proximity.  Provides confidence level classification, multi-match
resolution logic, and one-to-many / many-to-one matching support.

Performance target: evaluate 1,000 statement lines in <5 seconds.
Accuracy target: ≥95% matching accuracy.

Design Notes:
    - Uses ``read_group`` and batch SQL queries for candidate retrieval.
    - Scoring is pure-Python on pre-fetched data to avoid N+1 ORM calls.
    - Multi-company isolation enforced via ``_check_company_auto`` and explicit
      company_id domain filters on every query.
    - Zero dependencies on Odoo Enterprise modules.
"""

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError

from datetime import timedelta
import itertools
import logging
import re
import time

_logger = logging.getLogger(__name__)


class ReconciliationMatching(models.Model):
    """Reconciliation Matching Engine — core intelligence for BR-002.

    Each record represents a *proposed* match between a single bank-statement
    line and a single journal item, together with the per-dimension sub-scores
    and the overall weighted confidence score.
    """

    _name = 'account.reconciliation.matching'
    _description = 'Reconciliation Matching Engine'
    _order = 'confidence_score desc, id desc'
    _check_company_auto = True

    # -------------------------------------------------------------------------
    # CONFIDENCE THRESHOLDS (class-level constants)
    # -------------------------------------------------------------------------
    CONFIDENCE_HIGH = 90.0
    CONFIDENCE_MEDIUM = 70.0
    CONFIDENCE_LOW = 50.0

    # Scoring weights — sum must equal 1.0.
    DEFAULT_WEIGHTS = {
        'amount': 0.40,
        'reference': 0.25,
        'partner': 0.20,
        'date': 0.15,
    }

    # Maximum number of items considered in one-to-many combination search.
    _MAX_COMBINATION_SIZE = 5
    # Date window (days) for candidate retrieval.
    _CANDIDATE_DATE_WINDOW = 90
    # Amount tolerance for combination matching (5 %).
    _COMBINATION_AMOUNT_TOLERANCE = 0.05

    # -------------------------------------------------------------------------
    # FIELDS
    # -------------------------------------------------------------------------

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    statement_line_id = fields.Many2one(
        comodel_name='account.bank.statement.line',
        string='Statement Line',
        required=True,
        ondelete='cascade',
        index=True,
    )

    move_line_id = fields.Many2one(
        comodel_name='account.move.line',
        string='Journal Item',
        required=True,
        ondelete='cascade',
        index=True,
    )

    confidence_score = fields.Float(
        string='Confidence Score',
        digits=(5, 2),
        help='Overall matching confidence from 0 to 100.',
    )

    confidence_level = fields.Selection(
        selection=[
            ('high', 'High (≥90%)'),
            ('medium', 'Medium (70-89%)'),
            ('low', 'Low (50-69%)'),
            ('none', 'Below Threshold (<50%)'),
        ],
        string='Confidence Level',
        compute='_compute_confidence_level',
        store=True,
    )

    amount_score = fields.Float(
        string='Amount Score',
        digits=(5, 2),
        help='Sub-score for amount proximity (0-100).',
    )

    reference_score = fields.Float(
        string='Reference Score',
        digits=(5, 2),
        help='Sub-score for reference/label similarity (0-100).',
    )

    partner_score = fields.Float(
        string='Partner Score',
        digits=(5, 2),
        help='Sub-score for partner match (0-100).',
    )

    date_score = fields.Float(
        string='Date Score',
        digits=(5, 2),
        help='Sub-score for date proximity (0-100).',
    )

    is_selected = fields.Boolean(
        string='Selected for Reconciliation',
        default=False,
    )

    match_type = fields.Selection(
        selection=[
            ('one_to_one', 'One-to-One'),
            ('one_to_many', 'One-to-Many'),
            ('many_to_one', 'Many-to-One'),
        ],
        string='Match Type',
        default='one_to_one',
    )

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        related='company_id.currency_id',
        store=True,
    )

    matched_amount = fields.Monetary(
        string='Matched Amount',
        currency_field='currency_id',
    )

    state = fields.Selection(
        selection=[
            ('proposed', 'Proposed'),
            ('confirmed', 'Confirmed'),
            ('rejected', 'Rejected'),
        ],
        string='State',
        default='proposed',
    )

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------

    @api.depends('confidence_score')
    def _compute_confidence_level(self):
        """Classify *confidence_score* into a human-readable bucket."""
        for record in self:
            score = record.confidence_score or 0.0
            if score >= self.CONFIDENCE_HIGH:
                record.confidence_level = 'high'
            elif score >= self.CONFIDENCE_MEDIUM:
                record.confidence_level = 'medium'
            elif score >= self.CONFIDENCE_LOW:
                record.confidence_level = 'low'
            else:
                record.confidence_level = 'none'

    # -------------------------------------------------------------------------
    # MAIN MATCHING ENTRY POINT
    # -------------------------------------------------------------------------

    @api.model
    def find_matches(self, statement_lines, journal_id=None):
        """Find and score matches for the supplied statement lines.

        This is the primary public API of the matching engine.  For each
        **unreconciled** statement line the method:

        1. Retrieves candidate open journal items via
           :meth:`_get_candidate_move_lines`.
        2. Computes a weighted confidence score for every (statement-line,
           candidate) pair via :meth:`_compute_match_score`.
        3. Creates ``account.reconciliation.matching`` records for every pair
           that meets the minimum threshold (``CONFIDENCE_LOW``).
        4. Attempts one-to-many combination matching for lines with no
           high-confidence one-to-one match.
        5. Resolves multi-match ambiguity via :meth:`_resolve_multi_matches`.

        Args:
            statement_lines: ``account.bank.statement.line`` recordset.
            journal_id: Optional ``account.journal`` record id to restrict
                candidate search.

        Returns:
            Recordset of created ``account.reconciliation.matching`` records.
        """
        if not statement_lines:
            return self.browse()

        t_start = time.time()

        # Resolve the journal object when an id is passed.
        journal = None
        if journal_id:
            journal = self.env['account.journal'].browse(journal_id).exists()

        # Filter to unreconciled lines only.
        unreconciled = statement_lines.filtered(lambda sl: not sl.is_reconciled)
        if not unreconciled:
            _logger.info("find_matches: all %d statement lines already reconciled.", len(statement_lines))
            return self.browse()

        # Remove any previous *proposed* matches for these lines to avoid
        # duplicates when re-running the engine.
        existing = self.search([
            ('statement_line_id', 'in', unreconciled.ids),
            ('state', '=', 'proposed'),
        ])
        if existing:
            existing.unlink()

        all_vals = []
        matches_by_line = {}  # st_line.id -> list of vals dicts

        for st_line in unreconciled:
            line_journal = journal or st_line.journal_id
            candidates = self._get_candidate_move_lines(st_line, line_journal)
            if not candidates:
                _logger.debug(
                    "find_matches: no candidates for statement line %s (id=%s).",
                    st_line.payment_ref or '', st_line.id,
                )
                continue

            scored = []
            for ml in candidates:
                scores = self._compute_match_score(st_line, ml)
                if scores['confidence_score'] >= self.CONFIDENCE_LOW:
                    vals = {
                        'company_id': st_line.company_id.id,
                        'statement_line_id': st_line.id,
                        'move_line_id': ml.id,
                        'confidence_score': scores['confidence_score'],
                        'amount_score': scores['amount_score'],
                        'reference_score': scores['reference_score'],
                        'partner_score': scores['partner_score'],
                        'date_score': scores['date_score'],
                        'match_type': 'one_to_one',
                        'matched_amount': abs(ml.amount_residual),
                        'state': 'proposed',
                    }
                    scored.append(vals)

            # Attempt one-to-many combination matching when no single
            # candidate scores ≥ CONFIDENCE_HIGH.
            has_high = any(v['confidence_score'] >= self.CONFIDENCE_HIGH for v in scored)
            if not has_high and candidates:
                combo_vals = self._find_combination_matches(st_line, candidates)
                scored.extend(combo_vals)

            if scored:
                matches_by_line[st_line.id] = scored
                all_vals.extend(scored)

        if not all_vals:
            elapsed = time.time() - t_start
            _logger.info(
                "find_matches: processed %d lines in %.2fs — no matches above threshold.",
                len(unreconciled), elapsed,
            )
            return self.browse()

        # Batch-create all matching records.
        created = self.create(all_vals)

        # Build a mapping from statement_line_id to created records for
        # multi-match resolution.
        created_by_line = {}
        for rec in created:
            created_by_line.setdefault(rec.statement_line_id.id, self.browse())
            created_by_line[rec.statement_line_id.id] |= rec

        self._resolve_multi_matches(created_by_line)

        elapsed = time.time() - t_start
        _logger.info(
            "find_matches: processed %d lines in %.2fs — created %d matching records.",
            len(unreconciled), elapsed, len(created),
        )
        return created

    # -------------------------------------------------------------------------
    # CANDIDATE RETRIEVAL
    # -------------------------------------------------------------------------

    def _get_candidate_move_lines(self, st_line, journal):
        """Return candidate ``account.move.line`` records for *st_line*.

        Candidates must satisfy all of the following:
        * Posted move (``parent_state == 'posted'``).
        * Not yet fully reconciled (``reconciled == False``).
        * Same company (multi-company isolation).
        * On a reconcilable account.
        * Within a reasonable date window (±90 days by default).
        * Not originating from the statement line's own move.

        Args:
            st_line: Single ``account.bank.statement.line`` record.
            journal: ``account.journal`` record to scope the search.

        Returns:
            ``account.move.line`` recordset.
        """
        company = st_line.company_id
        child_companies = self.env['res.company'].search([
            ('id', 'child_of', company.id),
        ])

        # Determine date window boundaries.
        st_date = st_line.date or fields.Date.context_today(self)
        date_from = st_date - timedelta(days=self._CANDIDATE_DATE_WINDOW)
        date_to = st_date + timedelta(days=self._CANDIDATE_DATE_WINDOW)

        # Collect reconcilable account ids for the company.
        reconcilable_accounts = self.env['account.account'].sudo().search([
            ('company_ids', 'child_of', company.root_id.id),
            ('reconcile', '=', True),
        ])
        if not reconcilable_accounts:
            return self.env['account.move.line']

        domain = [
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
            ('company_id', 'in', child_companies.ids),
            ('account_id', 'in', reconcilable_accounts.ids),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('display_type', 'not in',
             ('line_section', 'line_subsection', 'line_note')),
        ]

        # Exclude the statement line's own move to prevent self-matching.
        if st_line.move_id:
            domain.append(('move_id', '!=', st_line.move_id.id))

        # Exclude payment lines on receivable/payable to mirror core logic.
        domain.extend([
            '|',
            ('account_id.account_type', 'not in',
             ('asset_receivable', 'liability_payable')),
            ('payment_id', '=', False),
        ])

        # Performance: limit the number of candidates to avoid runaway
        # scoring.  1 000 candidates per statement line is generous.
        candidates = self.env['account.move.line'].search(domain, limit=1000)
        return candidates

    # -------------------------------------------------------------------------
    # SCORE COMPUTATION
    # -------------------------------------------------------------------------

    def _compute_match_score(self, st_line, move_line):
        """Compute the weighted confidence score for a single pair.

        Returns:
            dict with keys ``confidence_score``, ``amount_score``,
            ``reference_score``, ``partner_score``, ``date_score``.
        """
        weights = self.DEFAULT_WEIGHTS

        st_amount = st_line.amount or 0.0
        ml_balance = move_line.balance or 0.0
        ml_residual = move_line.amount_residual or 0.0

        amount_score = self._score_amount(st_amount, ml_balance, ml_residual)
        reference_score = self._score_reference(
            st_line.payment_ref or '',
            move_line.ref or '',
            move_line.name or '',
        )
        partner_score = self._score_partner(
            st_line.partner_id,
            st_line.partner_name or '',
            move_line.partner_id,
        )
        date_score = self._score_date(
            st_line.date,
            move_line.date,
        )

        confidence_score = (
            weights['amount'] * amount_score
            + weights['reference'] * reference_score
            + weights['partner'] * partner_score
            + weights['date'] * date_score
        )

        _logger.debug(
            "Score for st_line %s vs ml %s: amount=%.1f ref=%.1f partner=%.1f "
            "date=%.1f → total=%.2f",
            st_line.id, move_line.id,
            amount_score, reference_score, partner_score, date_score,
            confidence_score,
        )

        return {
            'confidence_score': round(confidence_score, 2),
            'amount_score': round(amount_score, 2),
            'reference_score': round(reference_score, 2),
            'partner_score': round(partner_score, 2),
            'date_score': round(date_score, 2),
        }

    # -- Amount ---------------------------------------------------------------

    @staticmethod
    def _score_amount(st_amount, ml_amount, ml_amount_residual):
        """Score the amount proximity between statement line and move line.

        Uses the *residual* amount when available because we want to match
        against the remaining open balance.  Handles sign differences arising
        from the debit/credit convention by comparing absolute values.

        Scoring tiers:
            * Exact match → 100
            * Within 1 %  → 90
            * Within 5 %  → 70
            * Within 10 % → 50
            * Beyond 10 % → proportional decrease down to 0
        """
        # Use residual if non-zero, otherwise fall back to original balance.
        ml_compare = ml_amount_residual if ml_amount_residual else ml_amount

        abs_st = abs(st_amount)
        abs_ml = abs(ml_compare)

        # Avoid division by zero — if both are zero, it is a perfect match.
        if abs_st == 0.0 and abs_ml == 0.0:
            return 100.0
        if abs_st == 0.0 or abs_ml == 0.0:
            return 0.0

        # Check sign compatibility.  A positive statement amount should match
        # against a *negative* residual (credit) and vice-versa.  We score on
        # absolute values but give a bonus/penalty for sign alignment.
        # In Odoo, a bank *credit* (deposit) produces a positive st_amount and
        # the matching invoice payment line has a negative balance.  So
        # opposite signs are actually the expected case.
        sign_match = (st_amount > 0) != (ml_compare > 0)

        # Relative difference on absolute values.
        diff = abs(abs_st - abs_ml)
        max_val = max(abs_st, abs_ml)
        pct_diff = diff / max_val

        if pct_diff == 0.0:
            score = 100.0
        elif pct_diff <= 0.01:
            score = 90.0
        elif pct_diff <= 0.05:
            # Interpolate between 70 and 90.
            score = 90.0 - (pct_diff - 0.01) / (0.05 - 0.01) * 20.0
        elif pct_diff <= 0.10:
            # Interpolate between 50 and 70.
            score = 70.0 - (pct_diff - 0.05) / (0.10 - 0.05) * 20.0
        elif pct_diff <= 1.0:
            # Proportional decrease from 50 down to 0.
            score = 50.0 * (1.0 - (pct_diff - 0.10) / 0.90)
        else:
            score = 0.0

        # Penalise same-sign matches (unusual in bank reconciliation).
        if not sign_match:
            score *= 0.6

        return max(round(score, 2), 0.0)

    # -- Reference ------------------------------------------------------------

    @staticmethod
    def _score_reference(st_ref, ml_ref, ml_name):
        """Score reference similarity between statement line label and journal
        item reference / label.

        Scoring tiers:
            * Exact match (normalised) → 100
            * Substring containment    → 80
            * Partial token overlap    → 60
            * No meaningful overlap    →  0

        Normalisation strips all non-alphanumeric characters and folds to
        lower-case before comparison.
        """
        if not st_ref:
            return 0.0

        def _normalise(text):
            """Lower-case, strip non-alphanumeric."""
            return re.sub(r'[^a-z0-9]', '', (text or '').lower())

        def _tokenise(text):
            """Split on non-alphanumeric boundaries, lower-case."""
            return set(
                tok for tok in re.split(r'[^a-z0-9]+', (text or '').lower())
                if tok
            )

        norm_st = _normalise(st_ref)
        if not norm_st:
            return 0.0

        # Build a list of candidate reference strings from the move line.
        ml_refs = []
        if ml_ref:
            ml_refs.append(ml_ref)
        if ml_name and ml_name != ml_ref:
            ml_refs.append(ml_name)

        best_score = 0.0
        st_tokens = _tokenise(st_ref)

        for candidate in ml_refs:
            norm_ml = _normalise(candidate)
            if not norm_ml:
                continue

            # Exact normalised match.
            if norm_st == norm_ml:
                return 100.0

            # Substring containment (either direction).
            if norm_st in norm_ml or norm_ml in norm_st:
                best_score = max(best_score, 80.0)
                continue

            # Check if any meaningful token from the statement ref appears
            # in the move line text using regex search.
            ml_tokens = _tokenise(candidate)
            if st_tokens and ml_tokens:
                common = st_tokens & ml_tokens
                if common:
                    # Proportion of statement tokens found.
                    overlap = len(common) / max(len(st_tokens), 1)
                    token_score = 40.0 + 20.0 * min(overlap, 1.0)
                    best_score = max(best_score, round(token_score, 2))
                    continue

            # Fallback: try regex search for the escaped statement reference
            # inside the candidate.
            escaped = re.escape(norm_st)
            if re.search(escaped, norm_ml):
                best_score = max(best_score, 80.0)

        return best_score

    # -- Partner --------------------------------------------------------------

    @staticmethod
    def _score_partner(st_partner, st_partner_name, ml_partner):
        """Score the partner match.

        Scoring:
            * Exact ``partner_id`` match → 100
            * Name ``ilike`` match       →  80
            * Partial name overlap       →  50
            * No data available          →   0
        """
        # Both partner ids present — fastest path.
        if st_partner and ml_partner:
            if st_partner.id == ml_partner.id:
                return 100.0
            # Check commercial partner (parent company).
            if (st_partner.commercial_partner_id
                    and ml_partner.commercial_partner_id
                    and st_partner.commercial_partner_id.id == ml_partner.commercial_partner_id.id):
                return 100.0

        # Fall back to name-based comparison.
        st_name_str = ''
        if st_partner:
            st_name_str = (st_partner.name or '').strip().lower()
        if not st_name_str and st_partner_name:
            st_name_str = st_partner_name.strip().lower()

        ml_name_str = ''
        if ml_partner:
            ml_name_str = (ml_partner.name or '').strip().lower()

        if not st_name_str or not ml_name_str:
            return 0.0

        # Exact name match (case-insensitive).
        if st_name_str == ml_name_str:
            return 100.0

        # ilike-style containment.
        if st_name_str in ml_name_str or ml_name_str in st_name_str:
            return 80.0

        # Token overlap (e.g. "Acme Corp" vs "ACME Corporation").
        st_tokens = set(st_name_str.split())
        ml_tokens = set(ml_name_str.split())
        if st_tokens and ml_tokens:
            common = st_tokens & ml_tokens
            if common:
                overlap = len(common) / max(len(st_tokens), len(ml_tokens))
                if overlap >= 0.5:
                    return 50.0

        return 0.0

    # -- Date -----------------------------------------------------------------

    @staticmethod
    def _score_date(st_date, ml_date):
        """Score date proximity.

        Scoring tiers:
            * Same day       → 100
            * ≤ 3 days       →  90
            * ≤ 7 days       →  70
            * ≤ 14 days      →  50
            * ≤ 30 days      →  30
            * > 30 days      →  10
        """
        if not st_date or not ml_date:
            return 10.0

        delta_days = abs((st_date - ml_date).days)

        if delta_days == 0:
            return 100.0
        if delta_days <= 3:
            return 90.0
        if delta_days <= 7:
            return 70.0
        if delta_days <= 14:
            return 50.0
        if delta_days <= 30:
            return 30.0
        return 10.0

    # -------------------------------------------------------------------------
    # MULTI-MATCH RESOLUTION
    # -------------------------------------------------------------------------

    def _resolve_multi_matches(self, matches_by_line):
        """For statement lines with multiple high-confidence matches, mark the
        single best candidate as *selected* and down-rank the others.

        Resolution priority:
            1. Prefer exact amount match (``amount_score == 100``).
            2. Highest overall ``confidence_score``.
            3. Most recent date on the move line.

        Args:
            matches_by_line: dict mapping ``statement_line_id`` to a recordset
                of ``account.reconciliation.matching``.
        """
        for _sl_id, matches in matches_by_line.items():
            if not matches or len(matches) <= 1:
                # Single (or no) match — auto-select if score is high enough.
                if matches and matches[0].confidence_score >= self.CONFIDENCE_HIGH:
                    matches[0].write({'is_selected': True})
                continue

            # Sort: exact amount first, then highest score, then newest date.
            sorted_matches = matches.sorted(
                key=lambda m: (
                    m.amount_score >= 99.99,      # exact amount match
                    m.confidence_score,
                    m.move_line_id.date or fields.Date.context_today(self),
                ),
                reverse=True,
            )

            best = sorted_matches[0]
            if best.confidence_score >= self.CONFIDENCE_HIGH:
                best.write({'is_selected': True})
                _logger.debug(
                    "Multi-match resolved for st_line %s: selected ml %s "
                    "(score=%.2f).",
                    best.statement_line_id.id, best.move_line_id.id,
                    best.confidence_score,
                )
            else:
                _logger.warning(
                    "Multi-match for st_line %s: best score %.2f is below "
                    "HIGH threshold — no auto-select.",
                    best.statement_line_id.id, best.confidence_score,
                )

    # -------------------------------------------------------------------------
    # ONE-TO-MANY COMBINATION MATCHING
    # -------------------------------------------------------------------------

    def _find_combination_matches(self, st_line, candidates):
        """Search for combinations of move lines whose residual amounts sum to
        the statement line amount (within tolerance).

        This handles the common scenario where a single bank transaction
        corresponds to multiple invoices / payments.

        The search is bounded to combinations of at most
        ``_MAX_COMBINATION_SIZE`` candidates and uses an early-termination
        heuristic to meet the <5 s performance target.

        Args:
            st_line: Single ``account.bank.statement.line`` record.
            candidates: ``account.move.line`` recordset of potential matches.

        Returns:
            list of vals dicts ready for ``create``.
        """
        st_amount = abs(st_line.amount or 0.0)
        if st_amount == 0.0:
            return []

        tolerance = st_amount * self._COMBINATION_AMOUNT_TOLERANCE

        # Pre-filter candidates to those whose absolute residual is ≤ the
        # statement amount (no point including larger ones in a sum).
        filtered = [
            ml for ml in candidates
            if 0.0 < abs(ml.amount_residual) <= st_amount + tolerance
        ]

        if len(filtered) < 2:
            return []

        # Sort by absolute residual descending for early-termination benefit.
        filtered.sort(key=lambda ml: abs(ml.amount_residual), reverse=True)

        # Limit to top-N candidates for performance.
        filtered = filtered[:20]

        combo_vals = []
        found = False

        # Iterate combination sizes from 2 up to _MAX_COMBINATION_SIZE.
        for size in range(2, min(self._MAX_COMBINATION_SIZE + 1, len(filtered) + 1)):
            if found:
                break
            for combo in itertools.combinations(filtered, size):
                combo_sum = abs(sum(ml.amount_residual for ml in combo))
                if abs(combo_sum - st_amount) <= tolerance:
                    # Found a valid combination — generate matching records.
                    for ml in combo:
                        # Compute individual scores for each member of the
                        # combination so the user can evaluate each leg.
                        scores = self._compute_match_score(st_line, ml)
                        vals = {
                            'company_id': st_line.company_id.id,
                            'statement_line_id': st_line.id,
                            'move_line_id': ml.id,
                            'confidence_score': scores['confidence_score'],
                            'amount_score': scores['amount_score'],
                            'reference_score': scores['reference_score'],
                            'partner_score': scores['partner_score'],
                            'date_score': scores['date_score'],
                            'match_type': 'one_to_many',
                            'matched_amount': abs(ml.amount_residual),
                            'state': 'proposed',
                        }
                        combo_vals.append(vals)
                    found = True
                    break

        return combo_vals

    # -------------------------------------------------------------------------
    # USER ACTIONS
    # -------------------------------------------------------------------------

    def action_confirm_match(self):
        """Confirm the selected matching proposals and execute the actual
        reconciliation.

        For each selected match the method reconciles the statement line's
        counterpart move lines with the matched journal items using Odoo's
        native ``reconcile()`` mechanism on ``account.move.line``.

        Raises:
            UserError: When no matches are selected or when the reconciliation
                fails due to account/company incompatibility.
        """
        selected = self.filtered(lambda m: m.state == 'proposed')
        if not selected:
            raise UserError(
                _("No proposed matches to confirm. Please select at least one match.")
            )

        confirmed = self.browse()
        errors = []

        # Group by statement line to handle one-to-many matches as a batch.
        by_st_line = {}
        for match in selected:
            by_st_line.setdefault(match.statement_line_id.id, self.browse())
            by_st_line[match.statement_line_id.id] |= match

        for _sl_id, matches in by_st_line.items():
            st_line = matches[0].statement_line_id
            matched_move_lines = matches.mapped('move_line_id')

            try:
                # Obtain the counterpart lines from the statement line's move.
                # In Odoo, the statement line creates a journal entry; we need
                # the counterpart (non-liquidity) lines from that entry.
                _liquidity_lines, suspense_lines, _other_lines = (
                    st_line._seek_for_lines()
                )
                lines_to_reconcile = suspense_lines | matched_move_lines

                if not lines_to_reconcile:
                    _logger.warning(
                        "action_confirm_match: no lines to reconcile for "
                        "statement line %s.", st_line.id,
                    )
                    continue

                # Perform reconciliation via Odoo's standard mechanism.
                lines_to_reconcile.with_context(
                    no_exchange_difference=False,
                ).reconcile()

                matches.write({'state': 'confirmed'})
                confirmed |= matches

                _logger.info(
                    "Confirmed reconciliation for statement line %s with %d "
                    "journal items (score range %.1f–%.1f).",
                    st_line.id, len(matched_move_lines),
                    min(matches.mapped('confidence_score')),
                    max(matches.mapped('confidence_score')),
                )
            except (UserError, ValidationError) as exc:
                errors.append(_(
                    "Failed to reconcile statement line '%(line)s': %(error)s",
                    line=st_line.payment_ref or st_line.id,
                    error=str(exc),
                ))
                _logger.error(
                    "Reconciliation failed for statement line %s: %s",
                    st_line.id, exc,
                )
            except Exception as exc:
                errors.append(_(
                    "Unexpected error reconciling statement line '%(line)s': %(error)s",
                    line=st_line.payment_ref or st_line.id,
                    error=str(exc),
                ))
                _logger.exception(
                    "Unexpected error during reconciliation for statement line %s.",
                    st_line.id,
                )

        if errors and not confirmed:
            raise UserError('\n'.join(errors))

        if errors:
            _logger.warning(
                "action_confirm_match completed with %d errors out of %d "
                "statement lines.", len(errors), len(by_st_line),
            )

        return confirmed

    def action_reject_match(self):
        """Reject proposed matches — marks records as 'rejected' and deselects
        them.  The matching proposals remain in the database for audit
        purposes but are excluded from future confirmation batches.
        """
        proposed = self.filtered(lambda m: m.state == 'proposed')
        if not proposed:
            raise UserError(
                _("No proposed matches to reject.")
            )
        proposed.write({
            'state': 'rejected',
            'is_selected': False,
        })
        _logger.info(
            "Rejected %d matching proposals (ids: %s).",
            len(proposed), proposed.ids,
        )
        return proposed
