# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""
Follow-up Aged Receivables Report Parser (PF-003).

This module implements the data-preparation layer for the
'Follow-up Aged Receivables' PDF report. It is registered as an
``AbstractModel`` that Odoo's ``ir.actions.report`` engine looks up
automatically by the naming convention::

    report.<module_name>.<qweb_template_id>

matching the ``ir.actions.report`` record in ``report/followup_report.xml``.

The single entry point is :meth:`_get_report_values`, which receives the
wizard recordset IDs and a data dict containing wizard form values, and
returns a dict consumed by the QWeb template of the same name.

Core Responsibilities
---------------------
1. **Aged Receivables Aggregation** — Query ``account.move.line`` efficiently
   (single ``_read_group`` call, no row-level iteration) to compute
   per-partner aging buckets (Current, 1-30, 31-60, 61-90, 90+) across all
   posted receivable lines for customer invoices/refunds, filtered by the
   wizard's form values.
2. **Totals Computation** — Roll up per-partner amounts into grand totals,
   invoice counts, and bucket sums.
3. **Effectiveness Metrics** — Query ``account.followup.history`` and
   related invoice/payment data to compute Recovery Rate (%),
   Avg Days to Payment, Response Rate by Level, and Active Follow-ups
   count.

Integration Contract
--------------------
* **Parser ``_name``**:
  ``report.account_payment_followup.followup_aged_receivables``
* **QWeb template id**: ``followup_aged_receivables`` (declared
  in ``report/followup_report.xml``)
* **Report action ``report_name``**:
  ``account_payment_followup.followup_aged_receivables``
* **Document model**: ``account.followup.report.wizard`` (TransientModel
  declared in ``wizard/followup_report_wizard.py`` — its ``_get_form_values``
  method is the source of truth for form keys).

.. note::
   The template portion of the parser ``_name`` drops the redundant
   ``report_`` prefix that is already implied by Odoo's mandatory
   ``report.<module>.<template>`` naming convention. This is necessary
   to keep the auto-derived ``_table`` identifier under PostgreSQL's
   63-character maximum (see ``odoo/orm/utils.py::check_pg_name``). The
   full alternative name
   ``report.account_payment_followup.report_followup_aged_receivables``
   maps to a 64-character ``_table`` that Odoo rejects at registry
   load time, even for AbstractModels. The XML template ``id`` and the
   report action ``report_name`` in ``report/followup_report.xml`` MUST
   mirror the abbreviated template segment used here.

Rules Compliance (AAP §0.7)
---------------------------
* **R-01**: Zero imports from sibling new modules
  (``account_asset_management``, ``account_budget_management``,
  ``account_deferred_revenue``).
* **R-02**: Zero imports from Odoo Enterprise modules.
* **R-03**: Uses ``_name`` because this AbstractModel is net-new; does NOT
  redeclare an existing ORM model.
* **R-05**: No field definitions on core models (read-only access via
  ``_read_group`` / ``search`` / ``browse``).
* **R-07**: No ``sudo()`` calls; company-scope isolation is enforced by
  filtering every query by ``company_id`` from the wizard form.

Performance SLAs (PF-003 §6)
----------------------------
* <10s end-to-end for 500 partners
* <20s end-to-end for 1000 partners
* <5s for the effectiveness-metrics sub-computation
"""
import logging
from collections import defaultdict
from datetime import date, timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


# Aging-bucket accumulator key constants — prevent typo-induced
# dictionary mismatches between the bucket classifier and the row builder.
_BUCKET_CURRENT = "aging_current"
_BUCKET_1_30 = "aging_1_30"
_BUCKET_31_60 = "aging_31_60"
_BUCKET_61_90 = "aging_61_90"
_BUCKET_90_PLUS = "aging_90_plus"

# Communication-oriented action types on ``account.followup.history``.
# Used to filter effectiveness metrics to outward-facing actions only
# (excludes internal 'status' / 'note' entries).
_COMMUNICATION_ACTION_TYPES = (
    "email",
    "phone",
    "letter",
    "meeting",
    "sms",
    "promise",
)

# Recovery window per PF-003 BR-004: a payment is counted as "recovered"
# only if it lands within this many days after a follow-up action.
_RECOVERY_WINDOW_DAYS = 30

# Default effectiveness evaluation window when the wizard does not
# provide ``date_from`` — 90 days back from ``report_date``.
_DEFAULT_EFFECTIVENESS_LOOKBACK_DAYS = 90

# Tolerance for monetary float comparisons — amounts with absolute value
# below this are treated as effectively zero. Currency precision is
# typically 2 decimals, so a half-cent threshold avoids floating-point
# equality hazards (ruff RUF069) without altering business semantics.
_AMOUNT_EPSILON = 0.005


class FollowupAgedReceivablesReport(models.AbstractModel):
    """
    Report parser for the PF-003 Follow-up Aged Receivables PDF.

    This is a stateless ``AbstractModel`` — it holds no database records;
    it exists solely to provide :meth:`_get_report_values`, which Odoo
    invokes once per PDF render request.

    The parser consumes a wizard recordset
    (``account.followup.report.wizard``) and produces a dict that the QWeb
    template iterates over.

    Naming-Convention Cross-Reference
    ---------------------------------
    The three following identifiers MUST align:

    * QWeb template ``id`` in ``followup_report.xml``
      = ``followup_aged_receivables``
    * Report action ``report_name`` in ``followup_report.xml``
      = ``account_payment_followup.followup_aged_receivables``
    * Parser ``_name`` (this class)
      = ``report.account_payment_followup.followup_aged_receivables``

    The parser ``_name`` is derived by prepending ``report.`` to the
    report action's ``report_name`` value.

    The template segment ``followup_aged_receivables`` (25 chars) is
    deliberately abbreviated from the full semantic
    ``report_followup_aged_receivables`` because Odoo auto-derives the
    ``_table`` identifier by replacing dots with underscores — and the
    fully prefixed variant produces a 64-character table name that
    exceeds PostgreSQL's 63-character identifier limit enforced by
    ``odoo/orm/utils.py::check_pg_name``. The abbreviated form yields a
    57-character table name, safely within the constraint. This check
    fires unconditionally at registry load time even for AbstractModels
    (no physical table is created, but the name validation still runs).

    Sibling models referenced at runtime (via ``self.env[...]``):

    * ``account.followup.report.wizard`` — document model (source of
      filter values).
    * ``account.followup.level`` — used by :meth:`_compute_response_rate_by_level`.
    * ``account.followup.history`` — used by :meth:`_compute_effectiveness_metrics`.
    * ``res.partner`` — used for display-name lookup and follow-up-level
      resolution in :meth:`_build_partner_level_map`.
    * ``res.company`` — used by :meth:`_get_report_company` for multi-
      company scoping.
    * ``account.move`` / ``account.move.line`` — read-only receivable
      aggregation target.
    """

    # NOTE: The template segment ``followup_aged_receivables`` intentionally
    # omits a ``report_`` prefix to keep the auto-derived ``_table`` identifier
    # (57 chars: ``report_account_payment_followup_followup_aged_receivables``)
    # under PostgreSQL's 63-character limit enforced by
    # ``odoo/orm/utils.py::check_pg_name``. The XML template ``id`` and the
    # ``ir.actions.report.report_name`` in ``report/followup_report.xml`` MUST
    # mirror this abbreviation.
    _name = "report.account_payment_followup.followup_aged_receivables"
    _description = "Follow-up Aged Receivables Report Parser"

    # ========================================================================
    # Public API — required by ir.actions.report rendering pipeline
    # ========================================================================

    @api.model
    def _get_report_values(self, docids, data=None):
        """Return the render context dict for the QWeb template.

        This method is invoked by Odoo's ``ir.actions.report`` engine each
        time the action is triggered. It delegates to private helpers for
        query building, aggregation, and effectiveness computation.

        :param list[int] docids: IDs of ``account.followup.report.wizard``
            records (the primary document). Typically a single-element list.
        :param dict data: Optional dict provided by
            ``action.report_action(wizard, data={'form': {...}})``.
            Contains wizard form values under the ``'form'`` key (nested)
            and/or at the root (flat).
        :returns: Dict with the following keys, all consumed by the
            QWeb template:

            * ``doc_ids`` (list[int]): Echo of ``docids``
            * ``doc_model`` (str): Wizard model technical name
            * ``docs`` (recordset): Wizard recordset (primary document)
            * ``data`` (dict): Flattened wizard form values
            * ``company`` (res.company): Report scope company
            * ``currency`` (res.currency): Company currency for monetary
              widget rendering
            * ``report_date`` (date): As-of date for aging snapshot
            * ``partners`` (list[dict]): Per-partner aging rows, sorted
              by ``total_overdue`` desc
            * ``totals`` (dict): Grand totals and per-bucket sums
            * ``effectiveness`` (dict | None): Collection-effectiveness
              metrics; ``None`` if not requested

        :rtype: dict

        Performance SLA (PF-003 §6):

        * <10s render for 500 partners
        * <20s render for 1000 partners
        """
        data = data or {}
        form, docs = self._normalize_form(docids, data)

        # Determine report scope
        company = self._get_report_company(form)
        report_date = self._resolve_report_date(form)

        # Core aggregation — single _read_group on account.move.line
        partners_data = self._query_aged_receivables(form, company, report_date)

        # Derived summaries
        totals = self._compute_totals(partners_data)

        # Effectiveness is OPTIONAL — controlled by wizard checkbox.
        # Default True per PF-003 Scenario 6.
        if form.get("include_effectiveness", True):
            effectiveness = self._compute_effectiveness_metrics(
                form, company, report_date,
            )
        else:
            effectiveness = None

        _logger.info(
            "PF-003 Follow-up Report generated: "
            "company=%s, as_of=%s, partner_count=%d",
            company.display_name,
            report_date,
            len(partners_data),
        )

        return {
            "doc_ids": list(docids or []),
            "doc_model": "account.followup.report.wizard",
            "docs": docs,
            "data": form,
            "company": company,
            "currency": company.currency_id,
            "report_date": report_date,
            "partners": partners_data,
            "totals": totals,
            "effectiveness": effectiveness,
        }

    # ========================================================================
    # Form / document normalization
    # ========================================================================

    def _normalize_form(self, docids, data):
        """Extract the form dict and locate the wizard recordset.

        Odoo's report engine sometimes passes form values under a nested
        ``'form'`` key (when invoked programmatically with ``data=``) and
        sometimes passes them flat (when invoked via the Print-menu
        binding). We handle both by falling through ``'form'`` to the
        root dict.

        When the wizard recordset exposes a ``_get_form_values()`` hook
        (as the sibling ``FollowupReportWizard`` does), we call it and
        let its return value override any flat values in ``data`` — the
        wizard record is the authoritative source of filter state.

        :param list[int] docids: Wizard record IDs
        :param dict data: Raw data dict from the report action
        :returns: ``(form_dict, wizard_recordset)`` tuple
        :rtype: tuple[dict, odoo.models.Model]
        """
        # Prefer nested 'form' key (programmatic invocation); fall back
        # to the root dict (Print-menu binding pushes values flat).
        if isinstance(data, dict) and isinstance(data.get("form"), dict):
            form = dict(data["form"])
        elif isinstance(data, dict):
            form = dict(data)
        else:
            form = {}

        # Resolve wizard recordset defensively — the wizard model may not
        # yet be installed (PF-003 is delivered in a later checkpoint
        # than the parser). When the model is absent, ``docs`` is an
        # empty placeholder recordset.
        docs = self.env["account.followup.report.wizard"].browse(list(docids or []))

        # If the wizard record exposes _get_form_values, merge its output
        # on top of the data-dict values (wizard is the source of truth).
        # The catch list covers the failure modes observed when the sibling
        # wizard's method signature or return shape drifts from the
        # parser's expectations; it is intentionally narrower than a
        # blanket ``Exception`` so that genuine bugs surface.
        if docs and hasattr(docs, "_get_form_values"):
            wizard_form = None
            try:
                wizard_form = docs[0]._get_form_values()
            except (AttributeError, KeyError, TypeError, ValueError) as error:
                _logger.debug(
                    "PF-003 wizard _get_form_values() raised %s; "
                    "falling back to data dict",
                    error,
                )
            if isinstance(wizard_form, dict):
                merged = dict(form)
                merged.update(wizard_form)
                form = merged

        return form, docs

    def _get_report_company(self, form):
        """Determine the company that scopes the report.

        Priority order:

        1. Explicit ``company_id`` in form
        2. Current user's company (``self.env.company``)

        :param dict form: Wizard form values
        :returns: ``res.company`` record (singleton)
        :rtype: odoo.models.Model
        """
        company_id = form.get("company_id")
        if company_id:
            # form may store it as int, recordset, or (id, name) tuple
            if isinstance(company_id, (list, tuple)) and company_id:
                company_id = company_id[0]
            if hasattr(company_id, "id"):
                company_id = company_id.id
            try:
                company_id = int(company_id)
            except (TypeError, ValueError):
                company_id = None
            if company_id:
                company = self.env["res.company"].browse(company_id).exists()
                if company:
                    return company
        return self.env.company

    def _resolve_report_date(self, form):
        """Determine the 'as-of' date for the aging snapshot.

        Priority order:

        1. Explicit ``report_date`` in form (string or ``date``)
        2. Today's date in the user's timezone

        :param dict form: Wizard form values
        :returns: ``date`` object
        :rtype: datetime.date
        """
        report_date = form.get("report_date")
        if report_date:
            if isinstance(report_date, str):
                try:
                    return fields.Date.from_string(report_date)
                except (ValueError, TypeError):
                    pass
            elif isinstance(report_date, date):
                return report_date
        return fields.Date.context_today(self)

    # ========================================================================
    # Aged-receivables aggregation — performance-critical path
    # ========================================================================

    def _query_aged_receivables(self, form, company, report_date):
        """Aggregate open receivable amounts per partner into aging buckets.

        Uses a single ``_read_group`` call on ``account.move.line`` to
        compute per-partner per-maturity-date residual sums, then rolls
        them into aging buckets in Python. This satisfies the PF-003
        performance SLA (<10s for 500 partners).

        Buckets (days past due relative to ``report_date``):

        * Current: ``days_overdue <= 0``
        * 1-30: ``1 <= days_overdue <= 30``
        * 31-60: ``31 <= days_overdue <= 60``
        * 61-90: ``61 <= days_overdue <= 90``
        * 90+: ``days_overdue > 90``

        Business Rules (PF-003 BR-001, BR-002, BR-003):

        * Only includes open (unreconciled) receivable lines
          (``account.internal_type == 'receivable'``, modern name:
          ``account_type == 'asset_receivable'``).
        * Only posted invoice/refund moves (``parent_state == 'posted'``).
        * Uses ``amount_residual``, NOT original amount.
        * Uses ``date_maturity`` for aging, not ``invoice_date``.
        * Filters customer-only (``move_type in ('out_invoice', 'out_refund')``).

        :param dict form: Wizard form values (see module docstring).
        :param odoo.model.Model company: Scope company (res.company).
        :param datetime.date report_date: As-of date for aging.
        :returns: List of per-partner dicts with keys:

            ``partner_id``, ``partner_name``, ``level_id``, ``level_name``,
            ``aging_current``, ``aging_1_30``, ``aging_31_60``,
            ``aging_61_90``, ``aging_90_plus``, ``total_overdue``,
            ``invoice_count``, ``oldest_date``, ``max_days_overdue``,
            ``currency_id``.
        :rtype: list[dict]
        """
        AccountMoveLine = self.env["account.move.line"]

        domain = self._build_receivable_domain(form, company)

        # Single _read_group call — performs the entire aggregation in
        # one SQL round trip. Odoo 19 returns list[tuple]; the tuple
        # shape is (groupby_1, groupby_2, aggregate_1, aggregate_2).
        groups = AccountMoveLine._read_group(
            domain=domain,
            groupby=["partner_id", "date_maturity:day"],
            aggregates=["amount_residual:sum", "__count"],
        )

        # Accumulate per-partner bucket sums
        partner_accumulator = defaultdict(self._new_partner_accumulator)

        for partner_rec, due_date, residual_sum, line_count in groups:
            # Empty partner_id (should be filtered out by domain but guard
            # defensively to prevent KeyError on the output).
            if not partner_rec:
                continue
            partner_id = partner_rec.id

            # Normalize due_date — _read_group with ':day' granularity
            # returns date objects but may occasionally return strings
            # if a fallback path is used.
            if isinstance(due_date, str):
                try:
                    due_date = fields.Date.from_string(due_date)
                except (ValueError, TypeError):
                    due_date = None

            bucket_key = self._bucket_for_due_date(due_date, report_date)
            accumulator = partner_accumulator[partner_id]
            accumulator[bucket_key] += residual_sum or 0.0
            accumulator["invoice_count"] += int(line_count or 0)

            # Track oldest maturity date and max days overdue
            days = self._days_overdue(due_date, report_date)
            if due_date and (
                accumulator["oldest_date"] is None
                or due_date < accumulator["oldest_date"]
            ):
                accumulator["oldest_date"] = due_date
            if days > accumulator["max_days_overdue"]:
                accumulator["max_days_overdue"] = days

        if not partner_accumulator:
            return []

        # Bulk-browse partners for display names and follow-up levels.
        # ``.exists()`` filters out any partner_ids deleted between the
        # _read_group and this browse call.
        partner_ids_sorted = sorted(partner_accumulator.keys())
        partners = self.env["res.partner"].browse(partner_ids_sorted).exists()

        # Build partner->level map (minimizes per-row ORM lookups)
        partner_level_map = self._build_partner_level_map(partners, company)

        # Apply optional post-aggregation filters and assemble rows
        rows = self._build_partner_rows(
            form, company, partners, partner_accumulator, partner_level_map,
        )

        # Sort by total_overdue descending (PF-003 Scenario 1)
        rows.sort(key=lambda row: row["total_overdue"], reverse=True)

        return rows

    def _build_receivable_domain(self, form, company):
        """Assemble the ``account.move.line`` domain for aged-receivables.

        The domain is intentionally minimal at the SQL layer; richer
        post-aggregation filtering (amount threshold, level selection)
        happens in :meth:`_build_partner_rows` to keep the SQL pass-through
        fast and predictable.

        :param dict form: Wizard form values.
        :param odoo.model.Model company: Scope company.
        :returns: Odoo domain list.
        :rtype: list
        """
        domain = [
            ("company_id", "=", company.id),
            ("parent_state", "=", "posted"),
            ("account_id.account_type", "=", "asset_receivable"),
            ("amount_residual", "!=", 0),
            ("move_id.move_type", "in", ("out_invoice", "out_refund")),
        ]

        # Optional date-maturity bounds — the wizard exposes these as
        # effectiveness-window bounds by default, but they also narrow
        # the aging universe when provided.
        date_from = form.get("date_from")
        date_to = form.get("date_to")
        if date_from:
            domain.append(("date_maturity", ">=", date_from))
        if date_to:
            domain.append(("date_maturity", "<=", date_to))

        # Partner restriction from the wizard (only if non-empty).
        partner_ids = form.get("partner_ids") or ()
        if partner_ids:
            # Coerce to list of ints — wizard may pass tuple, list, or recordset
            partner_id_list = self._coerce_to_id_list(partner_ids)
            if partner_id_list:
                domain.append(("partner_id", "in", partner_id_list))

        # Disputed-invoice exclusion — the sibling ``account_move``
        # extension declares ``is_disputed`` as a stored indexed Boolean,
        # so the filter is SQL-indexable.
        if not form.get("include_disputed", False):
            domain.append(("move_id.is_disputed", "=", False))

        # Draft-entry inclusion is controlled via 'target_moves'.
        # 'posted' (default) keeps the parent_state='posted' tuple above;
        # 'all' removes it by overriding.
        target_moves = form.get("target_moves") or "posted"
        if target_moves == "all":
            # Remove the parent_state constraint to include drafts
            domain = [clause for clause in domain if clause[0] != "parent_state"]

        return domain

    @staticmethod
    def _coerce_to_id_list(value):
        """Coerce a heterogeneous value to a clean list of int IDs.

        Handles recordsets, lists of records, lists of ids, tuples, and
        single ids. Filters out ``False`` / ``None`` entries.

        :param value: Partner IDs in any of the above shapes.
        :returns: List of int IDs.
        :rtype: list[int]
        """
        if value is None or value is False:
            return []
        if hasattr(value, "ids"):
            # Recordset
            return list(value.ids)
        if isinstance(value, (list, tuple, set)):
            result = []
            for item in value:
                if hasattr(item, "id"):
                    item = item.id
                try:
                    result.append(int(item))
                except (TypeError, ValueError):
                    continue
            return result
        try:
            return [int(value)]
        except (TypeError, ValueError):
            return []

    @staticmethod
    def _new_partner_accumulator():
        """Factory for the per-partner accumulator dict used in aggregation.

        Keeping this as a module-level helper allows ``defaultdict`` to
        create a fresh accumulator lazily for any partner encountered
        in the ``_read_group`` output, with all five bucket keys and the
        running counters pre-initialized.

        :returns: Fresh accumulator dict.
        :rtype: dict
        """
        return {
            _BUCKET_CURRENT: 0.0,
            _BUCKET_1_30: 0.0,
            _BUCKET_31_60: 0.0,
            _BUCKET_61_90: 0.0,
            _BUCKET_90_PLUS: 0.0,
            "invoice_count": 0,
            "oldest_date": None,
            "max_days_overdue": 0,
        }

    def _build_partner_rows(
        self, form, company, partners, partner_accumulator, partner_level_map,
    ):
        """Assemble the output dicts for each partner and apply final filters.

        Post-aggregation filters applied here (rather than in the SQL
        domain) because they operate on the summed ``total_overdue`` and
        on the follow-up-level association which is itself a stored
        computed field on ``res.partner``:

        * ``amount_threshold`` / ``minimum_amount`` — excludes partners
          whose total overdue is strictly less than the threshold.
        * ``followup_level_ids`` — restricts to partners currently at a
          specified level.
        * ``aging_bucket_filter`` — restricts to partners whose most-
          overdue bucket matches the selection.

        :param dict form: Wizard form values.
        :param odoo.model.Model company: Scope company.
        :param odoo.model.Model partners: ``res.partner`` recordset.
        :param dict partner_accumulator: Per-partner bucket sums.
        :param dict partner_level_map: Partner ID -> level info mapping.
        :returns: List of row dicts (unsorted).
        :rtype: list[dict]
        """
        threshold = self._coerce_to_float(
            form.get("amount_threshold") or form.get("minimum_amount") or 0.0,
        )
        requested_levels_raw = form.get("followup_level_ids") or ()
        requested_levels = set(self._coerce_to_id_list(requested_levels_raw))
        aging_bucket_filter = form.get("aging_bucket_filter") or "all"

        rows = []
        for partner in partners:
            acc = partner_accumulator.get(partner.id)
            if acc is None:
                continue

            total_overdue = (
                acc[_BUCKET_CURRENT]
                + acc[_BUCKET_1_30]
                + acc[_BUCKET_31_60]
                + acc[_BUCKET_61_90]
                + acc[_BUCKET_90_PLUS]
            )

            # Amount-threshold filter
            if threshold and total_overdue < threshold:
                continue

            # Level filter
            level_info = partner_level_map.get(partner.id) or {}
            level_id = level_info.get("level_id")
            level_name = level_info.get("level_name") or ""
            if requested_levels and level_id not in requested_levels:
                continue

            # Aging-bucket filter
            if not self._row_matches_aging_filter(acc, aging_bucket_filter):
                continue

            rows.append({
                "partner_id": partner.id,
                "partner_name": (
                    partner.display_name or partner.name or _("Unknown Customer")
                ),
                "level_id": level_id,
                "level_name": level_name,
                "aging_current": acc[_BUCKET_CURRENT],
                "aging_1_30": acc[_BUCKET_1_30],
                "aging_31_60": acc[_BUCKET_31_60],
                "aging_61_90": acc[_BUCKET_61_90],
                "aging_90_plus": acc[_BUCKET_90_PLUS],
                "total_overdue": total_overdue,
                "invoice_count": acc["invoice_count"],
                "oldest_date": acc["oldest_date"],
                "max_days_overdue": acc["max_days_overdue"],
                "currency_id": company.currency_id.id,
            })

        return rows

    @staticmethod
    def _row_matches_aging_filter(accumulator, aging_bucket_filter):
        """Check whether a partner's accumulated buckets match the filter.

        The wizard's ``aging_bucket_filter`` selection values:

        * ``all``: every partner passes.
        * ``current_only``: only partners whose overdue buckets are all zero.
        * ``overdue_only``: only partners with at least one overdue bucket > 0.
        * ``1_30`` / ``31_60`` / ``61_90`` / ``90_plus``: only partners
          with a non-zero amount in the specified bucket.

        :param dict accumulator: Partner accumulator from :meth:`_new_partner_accumulator`.
        :param str aging_bucket_filter: Wizard filter value.
        :returns: True when the partner should be retained in the report.
        :rtype: bool
        """
        if aging_bucket_filter in (None, "", "all"):
            return True
        overdue_sum = (
            accumulator[_BUCKET_1_30]
            + accumulator[_BUCKET_31_60]
            + accumulator[_BUCKET_61_90]
            + accumulator[_BUCKET_90_PLUS]
        )
        # Float-tolerance comparisons — RUF069 requires avoiding raw
        # ``==``/``!=`` on floats. ``_AMOUNT_EPSILON`` is a half-cent
        # tolerance which is safe for currency-denominated values.
        has_overdue = abs(overdue_sum) >= _AMOUNT_EPSILON
        if aging_bucket_filter == "current_only":
            has_current = abs(accumulator[_BUCKET_CURRENT]) >= _AMOUNT_EPSILON
            return not has_overdue and has_current
        if aging_bucket_filter == "overdue_only":
            return overdue_sum >= _AMOUNT_EPSILON
        if aging_bucket_filter == "1_30":
            return abs(accumulator[_BUCKET_1_30]) >= _AMOUNT_EPSILON
        if aging_bucket_filter == "31_60":
            return abs(accumulator[_BUCKET_31_60]) >= _AMOUNT_EPSILON
        if aging_bucket_filter == "61_90":
            return abs(accumulator[_BUCKET_61_90]) >= _AMOUNT_EPSILON
        if aging_bucket_filter == "90_plus":
            return abs(accumulator[_BUCKET_90_PLUS]) >= _AMOUNT_EPSILON
        # Unknown filter value — safer to include the partner
        return True

    # ========================================================================
    # Aging classification helpers
    # ========================================================================

    @staticmethod
    def _days_overdue(due_date, as_of_date):
        """Compute days past due for a single maturity date.

        Negative if not yet due; zero if due today.

        :param datetime.date | None due_date: ``account.move.line.date_maturity``.
        :param datetime.date as_of_date: Report 'as-of' date.
        :returns: Integer day-delta (as_of_date - due_date).
        :rtype: int
        """
        if not due_date:
            return 0
        return (as_of_date - due_date).days

    @classmethod
    def _bucket_for_due_date(cls, due_date, as_of_date):
        """Return the bucket accumulator key for a given maturity date.

        Buckets match the ``account.move.line.aging_bucket`` convention
        declared in the sibling ``models/account_move_line.py``:

        * ``aging_current``: ``days_overdue <= 0`` (not yet due).
        * ``aging_1_30``: ``1 <= days_overdue <= 30``.
        * ``aging_31_60``: ``31 <= days_overdue <= 60``.
        * ``aging_61_90``: ``61 <= days_overdue <= 90``.
        * ``aging_90_plus``: ``days_overdue > 90``.

        :param datetime.date | None due_date: ``account.move.line.date_maturity``.
        :param datetime.date as_of_date: Report as-of date.
        :returns: Accumulator key (see module-level ``_BUCKET_*`` constants).
        :rtype: str
        """
        days = cls._days_overdue(due_date, as_of_date)
        if days <= 0:
            return _BUCKET_CURRENT
        if days <= 30:
            return _BUCKET_1_30
        if days <= 60:
            return _BUCKET_31_60
        if days <= 90:
            return _BUCKET_61_90
        return _BUCKET_90_PLUS

    def _build_partner_level_map(self, partners, company):
        """Build a partner_id -> {level_id, level_name} map.

        Uses the ``followup_level_id`` field on ``res.partner`` declared
        by the sibling ``models/res_partner.py``. Since that field is
        stored, a single ``.mapped()`` prefetch is sufficient to avoid
        N+1 queries.

        :param odoo.models.Model partners: ``res.partner`` recordset.
        :param odoo.models.Model company: Scope company (levels are
            company-scoped; cross-company levels are excluded).
        :returns: Dict of partner_id -> {'level_id': int | None, 'level_name': str}.
        :rtype: dict[int, dict]
        """
        # Prefetch the ``followup_level_id`` one-to-many association
        partners.mapped("followup_level_id")

        result = {}
        for partner in partners:
            level = partner.followup_level_id
            if level and (
                not level.company_id or level.company_id.id == company.id
            ):
                result[partner.id] = {
                    "level_id": level.id,
                    "level_name": level.name or "",
                }
            else:
                result[partner.id] = {
                    "level_id": None,
                    "level_name": "",
                }
        return result

    @staticmethod
    def _coerce_to_float(value):
        """Coerce a form value to a float, returning 0.0 on failure.

        :param value: Any form value (typically str, int, float, Decimal).
        :returns: Float representation, or ``0.0`` if coercion fails.
        :rtype: float
        """
        if value in (None, False, ""):
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    # ========================================================================
    # Grand-totals rollup
    # ========================================================================

    @staticmethod
    def _compute_totals(partners_data):
        """Sum per-partner bucket values into grand totals.

        :param list[dict] partners_data: Output of
            :meth:`_query_aged_receivables`.
        :returns: Dict with keys:

            * ``current`` — sum of ``aging_current`` across all partners.
            * ``aging_1_30`` — sum of ``aging_1_30``.
            * ``aging_31_60`` — sum of ``aging_31_60``.
            * ``aging_61_90`` — sum of ``aging_61_90``.
            * ``aging_90_plus`` — sum of ``aging_90_plus``.
            * ``grand_total`` — sum of all buckets (= sum of ``total_overdue``).
            * ``total_invoice_count`` — sum of per-partner ``invoice_count``.
            * ``partner_count`` — number of partner rows in the report.
        :rtype: dict
        """
        totals = {
            "current": 0.0,
            "aging_1_30": 0.0,
            "aging_31_60": 0.0,
            "aging_61_90": 0.0,
            "aging_90_plus": 0.0,
            "grand_total": 0.0,
            "total_invoice_count": 0,
            "partner_count": len(partners_data),
        }
        for row in partners_data:
            totals["current"] += float(row.get("aging_current") or 0.0)
            totals["aging_1_30"] += float(row.get("aging_1_30") or 0.0)
            totals["aging_31_60"] += float(row.get("aging_31_60") or 0.0)
            totals["aging_61_90"] += float(row.get("aging_61_90") or 0.0)
            totals["aging_90_plus"] += float(row.get("aging_90_plus") or 0.0)
            totals["grand_total"] += float(row.get("total_overdue") or 0.0)
            totals["total_invoice_count"] += int(row.get("invoice_count") or 0)
        return totals

    # ========================================================================
    # Effectiveness metrics (PF-003 Scenario 6, BR-004)
    # ========================================================================

    def _compute_effectiveness_metrics(self, form, company, report_date):
        """Compute collection-effectiveness summary.

        Metrics produced (PF-003 BR-004):

        * ``recovery_rate_pct``: % of follow-up-subject invoices paid
          within ``_RECOVERY_WINDOW_DAYS`` (30) days of the most recent
          follow-up action.
        * ``avg_days_to_payment``: Average days between ``action_date``
          and invoice reconciliation date, for paid invoices.
        * ``active_followups``: Count of partners currently at any
          follow-up level (> 0 recorded follow-up levels).
        * ``response_rate_by_level``: Per-level breakdown (see
          :meth:`_compute_response_rate_by_level`).

        Data source: ``account.followup.history`` records with
        ``action_type`` in ``_COMMUNICATION_ACTION_TYPES`` for the period
        bounded by ``form['date_from']`` (default: 90 days back) and
        ``form['date_to']`` (default: ``report_date``).

        Response detection:

        A history record is "responded" if there exists a promise
        (``promised_amount > 0`` or ``promised_date`` set) OR any linked
        invoice became reconciled within ``_RECOVERY_WINDOW_DAYS`` after
        ``action_date``.

        :param dict form: Wizard form values.
        :param odoo.model.Model company: Report scope.
        :param datetime.date report_date: As-of date.
        :returns: Dict with keys ``recovery_rate_pct``,
            ``avg_days_to_payment``, ``active_followups``,
            ``response_rate_by_level``, ``total_sent``, ``total_recovered``.
        :rtype: dict
        """
        History = self.env["account.followup.history"]
        Level = self.env["account.followup.level"]
        Partner = self.env["res.partner"]

        window_start, window_end = self._resolve_effectiveness_window(
            form, report_date,
        )

        # 1. Active Follow-ups — distinct partners with a current level,
        #    scoped to the report company.
        active_followups = Partner.search_count([
            ("company_id", "in", (False, company.id)),
            ("followup_level_id", "!=", False),
        ])

        # 2. Build the history domain ONCE and reuse
        history_domain = [
            ("company_id", "=", company.id),
            (
                "action_date",
                ">=",
                fields.Datetime.to_datetime(window_start),
            ),
            (
                "action_date",
                "<=",
                fields.Datetime.to_datetime(window_end) + timedelta(days=1),
            ),
            ("action_type", "in", list(_COMMUNICATION_ACTION_TYPES)),
        ]
        history_records = History.search(history_domain)

        total_sent = len(history_records)
        recovery_count, days_to_payment_samples = self._evaluate_recovery(
            history_records,
        )

        recovery_rate_pct = (
            round(recovery_count * 100.0 / total_sent, 1) if total_sent else 0.0
        )
        avg_days_to_payment = (
            round(sum(days_to_payment_samples) / len(days_to_payment_samples), 1)
            if days_to_payment_samples
            else 0.0
        )

        # 3. Per-level response-rate breakdown
        response_rate_by_level = self._compute_response_rate_by_level(
            Level, history_records, company,
        )

        return {
            "recovery_rate_pct": recovery_rate_pct,
            "avg_days_to_payment": avg_days_to_payment,
            "active_followups": active_followups,
            "response_rate_by_level": response_rate_by_level,
            "total_sent": total_sent,
            "total_recovered": recovery_count,
            "window_start": window_start,
            "window_end": window_end,
        }

    def _resolve_effectiveness_window(self, form, report_date):
        """Determine the (window_start, window_end) date bounds.

        Default window: ``[report_date - 90 days, report_date]``.

        If the wizard supplies ``date_from`` and/or ``date_to``, those
        override the defaults. Invalid/unparseable strings fall back to
        the defaults.

        :param dict form: Wizard form values.
        :param datetime.date report_date: As-of date.
        :returns: ``(window_start, window_end)`` tuple of date objects.
        :rtype: tuple[datetime.date, datetime.date]
        """
        default_start = report_date - timedelta(
            days=_DEFAULT_EFFECTIVENESS_LOOKBACK_DAYS,
        )
        window_start = form.get("date_from") or default_start
        window_end = form.get("date_to") or report_date

        if isinstance(window_start, str):
            try:
                window_start = fields.Date.from_string(window_start)
            except (ValueError, TypeError):
                window_start = default_start
        if isinstance(window_end, str):
            try:
                window_end = fields.Date.from_string(window_end)
            except (ValueError, TypeError):
                window_end = report_date

        # Defensive ordering
        if window_start > window_end:
            window_start, window_end = window_end, window_start

        return window_start, window_end

    def _evaluate_recovery(self, history_records):
        """Compute recovery count and days-to-payment samples.

        For each history record, iterate its ``invoice_ids`` (Many2many
        to ``account.move``) and check whether any invoice became
        reconciled within ``_RECOVERY_WINDOW_DAYS`` of the history's
        ``action_date``. At most ONE invoice per history record contributes
        to ``recovery_count`` (conservative — prevents double-counting
        multi-invoice follow-ups).

        :param odoo.model.Model history_records: ``account.followup.history`` recordset.
        :returns: Tuple of (``recovery_count``, ``days_samples``).
        :rtype: tuple[int, list[int]]
        """
        recovery_count = 0
        days_samples = []

        for history in history_records:
            action_date = history.action_date
            if not action_date:
                continue
            action_date_as_date = (
                action_date.date() if hasattr(action_date, "date") else action_date
            )

            # ``invoice_ids`` is Many2many on the history model — iterate
            # all linked invoices, but count only the first one that
            # meets the recovery criterion.
            recovered_for_this_history = False
            for invoice in history.invoice_ids:
                pay_date = self._extract_invoice_payment_date(invoice)
                if not pay_date:
                    continue
                delta = (pay_date - action_date_as_date).days
                if 0 <= delta <= _RECOVERY_WINDOW_DAYS:
                    recovery_count += 1
                    days_samples.append(delta)
                    recovered_for_this_history = True
                    break
            # No fallthrough needed — the flag is only used for future extensions.
            del recovered_for_this_history

        return recovery_count, days_samples

    @staticmethod
    def _extract_invoice_payment_date(invoice):
        """Return the reconciliation date for a paid invoice, or None.

        Prefers the ``full_reconcile_id.create_date`` of the receivable
        line (the canonical payment-recording event). Falls back to the
        invoice's ``invoice_date_due`` when reconciliation data is not
        available (which may happen for partially-paid invoices or
        invoices reconciled via other mechanisms).

        :param odoo.models.Model invoice: ``account.move`` record.
        :returns: Payment date, or ``None`` if the invoice is not paid.
        :rtype: datetime.date | None
        """
        if not invoice:
            return None
        if invoice.payment_state not in ("paid", "in_payment", "reversed"):
            return None

        # Find the receivable line(s) on this invoice
        receivable_lines = invoice.line_ids.filtered(
            lambda line: (
                line.account_id
                and line.account_id.account_type == "asset_receivable"
            ),
        )
        if not receivable_lines:
            return invoice.invoice_date_due or invoice.date or None

        # Prefer the earliest full reconciliation date
        reconcile_dates = []
        for line in receivable_lines:
            full_reconcile = line.full_reconcile_id
            if full_reconcile and full_reconcile.create_date:
                reconcile_dates.append(full_reconcile.create_date.date())
        if reconcile_dates:
            return min(reconcile_dates)

        return invoice.invoice_date_due or invoice.date or None

    def _compute_response_rate_by_level(self, Level, history_records, company):
        """Per-level breakdown of sent vs responded follow-ups.

        A follow-up is considered "responded" if any of the following
        are true:

        * The history record has a captured promise
          (``promised_amount > 0`` or ``promised_date`` set).
        * One of the linked invoices reached ``payment_state`` paid/in_payment
          on or after ``action_date``.

        Levels with zero sent records are omitted from the result.

        :param odoo.models.Model Level: ``account.followup.level`` model proxy.
        :param odoo.models.Model history_records: Pre-filtered history recordset
            from :meth:`_compute_effectiveness_metrics`.
        :param odoo.models.Model company: Scope company.
        :returns: List of dicts: ``[{level_id, level_name, sent_count,
            response_count, response_rate_pct}, ...]``.
        :rtype: list[dict]
        """
        # Group history records by level for efficient iteration
        history_by_level = defaultdict(lambda: self.env["account.followup.history"])
        for history in history_records:
            level_id = history.followup_level_id.id if history.followup_level_id else None
            history_by_level[level_id] |= history

        levels = Level.search(
            [
                ("company_id", "in", (False, company.id)),
                ("active", "=", True),
            ],
            order="sequence, delay",
        )

        result = []
        for level in levels:
            level_history = history_by_level.get(level.id)
            if not level_history:
                continue
            sent_count = len(level_history)
            response_count = sum(
                1 for history in level_history
                if self._is_history_responded(history)
            )
            response_rate_pct = (
                round(response_count * 100.0 / sent_count, 1) if sent_count else 0.0
            )
            result.append({
                "level_id": level.id,
                "level_name": level.name or "",
                "sent_count": sent_count,
                "response_count": response_count,
                "response_rate_pct": response_rate_pct,
            })

        return result

    @staticmethod
    def _is_history_responded(history):
        """Determine whether a single history record shows a customer response.

        Conservative response criterion (avoids counting payments that
        happened independently of the follow-up):

        1. Promise captured (``promised_amount > 0`` or ``promised_date``).
        2. Any linked invoice in ``payment_state`` paid/in_payment.

        :param odoo.models.Model history: ``account.followup.history`` record.
        :returns: ``True`` when the history shows a response.
        :rtype: bool
        """
        if history.promised_amount and history.promised_amount > 0:
            return True
        if history.promised_date:
            return True
        # invoice_ids is Many2many; check each linked invoice
        for invoice in history.invoice_ids:
            if invoice.payment_state in ("paid", "in_payment"):
                return True
        return False
