# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""``account.move`` extension for budget actuals freshness (FB-04 fix).

The variance fields on ``budget.budget.line`` (``variance_actual``,
``variance_absolute``, ``variance_percent``,
``variance_consumption_percent``, ``variance_classification``,
``variance_threshold_status``) are *stored computed* fields. Their
``@api.depends`` declaration on ``budget_budget_line._compute_variance``
captures direct triggers on the budget line itself
(``planned_amount``, ``account_id``, ``analytic_distribution``,
``budget_id.date_from``, ``budget_id.date_to``, ``budget_id.state``)
but it cannot capture inverse triggers from ``account.move.line`` --
the relationship between a budget line and its actuals is established
at *search* time by ``_compute_variance`` via a ``_read_group`` over
``account.move.line.balance`` filtered by ``(account_id, company_id,
date in [date_from, date_to], analytic_distribution)``. There is no
``Many2one`` from ``account.move.line`` to ``budget.budget.line`` for
Odoo's ORM dependency engine to traverse.

QA Checkpoint 6 finding **FB-04** flagged this gap: when an accountant
posts a vendor bill or expense entry that hits a budgeted account with
the matching analytic distribution, the controller's "Actual Amount"
column on the budget remains stale until the BM-005 alert cron runs
or until a user manually invalidates the cache.

This file fixes that by overriding ``account.move._post()`` (the
canonical transition from ``draft``/``posted`` to ``posted``) to
identify all budget lines whose ``(account_id, company_id, date_from
..date_to)`` window includes the move's date and whose account
intersects the move's line accounts, then call
``_compute_variance()`` on the resulting recordset. The same hook is
applied to ``button_draft()`` (posted -> draft transition, e.g. when an
accountant reverses a posted move) so a previously-counted balance is
correctly removed from the actuals total.

AAP Rule Compliance
-------------------
* **R-01** (Module Independence) -- This file imports ONLY from
  ``odoo`` and ``odoo.exceptions`` plus the Python standard library.
  NO imports of ``account_asset_management``,
  ``account_deferred_revenue``, or ``account_payment_followup``.
* **R-02** (No Enterprise Dependencies) -- No Enterprise module names
  appear in the manifest's ``depends`` list, and this file imports no
  Enterprise model.
* **R-03** (``_inherit`` correctness) -- Declares
  ``_inherit = 'account.move'`` on an existing core model; no
  ``_name`` override.
* **R-05** (No Core Field Redefinition) -- This file declares NO new
  fields on ``account.move``. Only method overrides
  (``_post``, ``button_draft``) are added; both call ``super()`` to
  preserve the core behaviour, then dispatch a no-op-when-empty
  recompute on the affected ``budget.budget.line`` recordset.
* **R-07** (No unjustified ``sudo``) -- This file contains NO
  ``sudo()`` calls; the recompute uses the calling user's recordset
  scope, identical to the BM-005 cron's invocation pattern.
"""

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    """Budget-aware extension of ``account.move``.

    Two transitions on the move's lifecycle invalidate the freshness
    of the variance compute on related budget lines:

        * ``draft`` / ``cancel`` -> ``posted`` (forward post): a new
          ``account.move.line`` recordset enters the
          ``parent_state = 'posted'`` filter that
          ``_compute_variance`` reads, increasing
          ``variance_actual`` for any budget line whose window and
          account scope match.
        * ``posted`` -> ``draft`` / ``cancel`` (reversal): an
          existing ``account.move.line`` recordset leaves the
          ``parent_state = 'posted'`` filter, decreasing
          ``variance_actual`` for the same budget lines.

    Both transitions are intercepted to call
    ``_compute_variance()`` on the affected budget lines AFTER the
    state change is persisted (so the recompute observes the new
    state of ``account.move.line.parent_state``).
    """

    _inherit = 'account.move'

    # ==================================================================
    # Lifecycle hooks for budget actuals freshness
    # ==================================================================

    def _post(self, soft=True):
        """Override to recompute budget variances after move posting.

        Calls ``super()._post(soft=soft)`` first so the journal-entry
        validation, sequence assignment, and lock-date checks defined
        by ``addons/account/models/account_move.py::_post`` are applied
        verbatim. After ``super()`` returns, we identify budget lines
        whose ``(account_id, company_id, date_from..date_to)`` window
        and account intersect the just-posted moves' line accounts,
        and trigger ``_compute_variance()`` on them.

        :param bool soft: forwarded verbatim to ``super()``; when
            ``True`` (the default), future-dated documents are not
            immediately posted but auto-posted at their accounting
            date.
        :returns: the recordset of moves that were posted (the value
            returned by ``super()._post``).
        :rtype: account.move
        """
        result = super()._post(soft=soft)
        # ``super()._post`` returns the recordset of moves that
        # actually transitioned to ``posted`` (which may be a strict
        # subset of ``self`` when ``soft=True`` and some documents
        # are future-dated). We trigger recompute against THAT
        # subset, not against ``self``, to avoid recomputing for
        # moves that remain in the soft-post queue.
        posted_moves = result if result else self
        affected = posted_moves._budget_management_find_affected_lines()
        if affected:
            _logger.debug(
                'FB-04: triggering variance recompute on %d budget '
                'lines after posting %d move(s).',
                len(affected),
                len(posted_moves),
            )
            affected._compute_variance()
        return result

    def button_draft(self):
        """Override to recompute budget variances when reverting to draft.

        Captures the affected budget lines BEFORE delegating to
        ``super()`` because the budget lines are identified through
        ``account.move.line`` records whose ``parent_state`` will
        change from ``posted`` to ``draft`` when ``super()`` runs;
        capturing pre-transition guarantees we still see the original
        line accounts.

        :returns: whatever the core ``button_draft`` returns
            (typically ``True`` or no explicit return).
        """
        # Capture before transition: only moves currently in
        # ``posted`` state contribute to a budget's actuals; draft /
        # cancel moves are already excluded from
        # ``_compute_variance``'s ``parent_state = 'posted'`` filter.
        was_posted = self.filtered(lambda m: m.state == 'posted')
        affected = (
            was_posted._budget_management_find_affected_lines()
            if was_posted
            else self.env['budget.budget.line']
        )
        result = super().button_draft()
        if affected:
            _logger.debug(
                'FB-04: triggering variance recompute on %d budget '
                'lines after reverting %d move(s) to draft.',
                len(affected),
                len(was_posted),
            )
            affected._compute_variance()
        return result

    # ==================================================================
    # Helper: find budget lines whose actuals depend on these moves
    # ==================================================================

    def _budget_management_find_affected_lines(self):
        """Return the union of budget.budget.line records whose actuals
        compute domain intersects ``self.line_ids``.

        Implementation matches the search domain used by
        ``budget.budget.line._compute_variance``:

            * ``account_id`` IN (the union of all line accounts on
              every move in ``self``)
            * ``company_id`` matches each move's company
            * ``budget_id.date_from <= move.date <= budget_id.date_to``

        The analytic distribution intersection is intentionally NOT
        included in the search domain -- it is applied per-line by
        ``_compute_variance`` itself; including it here would require
        a JSON containment predicate that is more expensive than
        recomputing one or two extra lines.

        Returns:
            budget.budget.line: the (possibly empty) union of
            affected budget lines. ``_compute_variance`` is a no-op
            on an empty recordset.
        """
        if not self:
            return self.env['budget.budget.line']
        BudgetLine = self.env['budget.budget.line']
        affected = BudgetLine
        for move in self:
            if not move.line_ids:
                continue
            # ``move.line_ids`` includes payment-term and tax lines
            # whose ``account_id`` is unlikely to be budgeted, but
            # ``_compute_variance`` already filters them out via its
            # ``balance:sum`` aggregation -- we pass them all here
            # for simplicity and let the recompute do the precision
            # filtering.
            account_ids = move.line_ids.mapped('account_id').ids
            if not account_ids:
                continue
            domain = [
                ('account_id', 'in', account_ids),
                ('budget_id.date_from', '<=', move.date),
                ('budget_id.date_to', '>=', move.date),
            ]
            if move.company_id:
                domain.append(('company_id', '=', move.company_id.id))
            affected |= BudgetLine.search(domain)
        return affected
