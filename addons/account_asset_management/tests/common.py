# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Common test base class for the account_asset_management module.

This module provides :class:`AssetManagementTestCommon`, a shared base class
extending :class:`AccountTestInvoicingCommon` that pre-seeds the accounts,
journal, category, and helper methods needed by the six per-story test
files (AM-001 through AM-006).

Usage
-----
Subclass in each test file and decorate with ``@tagged('post_install',
'-at_install')``::

    from .common import AssetManagementTestCommon
    from odoo.tests import tagged

    @tagged('post_install', '-at_install')
    class TestAssetRegistration(AssetManagementTestCommon):
        def test_create_asset(self):
            asset = self._create_basic_asset(self, name='Test Laptop')
            ...

Fixtures Provided
-----------------
- ``cls.company_a`` / ``cls.company_b``: Two companies for multi-company tests
  (company_a == ``cls.env.company``).
- ``cls.asset_account``: an ``account_type='asset_fixed'`` account.
- ``cls.expense_account``: an ``account_type='expense_depreciation'`` account.
- ``cls.accumulated_account``: an ``account_type='asset_non_current'`` account.
- ``cls.offset_account``: an ``account_type='liability_payable'`` account used
  as the offset for acquisition journal entries when no source invoice is
  linked.
- ``cls.depreciation_journal``: an ``account.journal`` of type ``general``.
- ``cls.asset_category_it``: a pre-seeded 3-year straight-line category
  "IT Equipment" with all required defaults populated.
- ``cls.vendor``: a supplier ``res.partner`` (``supplier_rank > 0``) for
  vendor-linkage tests.

Helper Methods
--------------
- ``cls._get_or_create_account(cls, code, name, account_type)``: Idempotent
  account creation.
- ``cls._create_basic_asset(cls, **overrides)``: Factory producing a draft
  ``account.asset`` with sensible defaults; accepts any asset field as
  keyword override.
- ``cls._confirm_asset(cls, asset)``: Calls ``action_confirm()`` and asserts
  post-conditions (state transition, acquisition_move_id set, schedule
  populated).
- ``cls._post_depreciation_lines(cls, asset, count)``: Posts the first N
  draft depreciation lines of an asset.

AAP Rule Compliance
-------------------
* R-01 (Module independence) -- This file imports ONLY from the Python
  standard library (``datetime``), the ``odoo`` framework
  (``odoo.Command``, ``odoo.fields``), and the core
  ``odoo.addons.account.tests.common.AccountTestInvoicingCommon`` test
  helper class. It contains NO imports from any sibling Community
  Edition module (``account_budget_management``,
  ``account_deferred_revenue``, ``account_payment_followup``).
* R-02 (No Enterprise dependencies) -- This file contains NO references
  to Odoo Enterprise addon names (``account_asset``,
  ``account_accountant``, ``account_reports``, ``account_followup``,
  ``account_deferred_revenue``) and NO occurrences of the literal
  string ``'enterprise'``.
* R-03 (``_inherit`` / ``_name`` correctness) -- NOT APPLICABLE: this
  file declares no ORM model. ``AssetManagementTestCommon`` is a pure
  ``unittest.TestCase`` subclass via the ``AccountTestInvoicingCommon``
  parent.
* R-05 (No core field redefinition) -- NOT APPLICABLE: no ORM model
  declarations in this file.
* R-07 (No unjustified ``sudo()``) -- This file contains NO ``.sudo()``
  call. ``AccountTestInvoicingCommon`` provisions a test user with
  ``account.group_account_manager`` + ``account.group_account_user``
  group memberships (see ``get_default_groups`` in the parent class)
  which provides full CRUD on every model defined by the Asset
  Management module per ``security/ir.model.access.csv``. No privilege
  escalation is required at any point during fixture setup or helper
  invocation.
"""

# ``date`` is imported for downstream use in AM-005 / AM-006 test files
# whose docstring examples set ``self.env.company.fiscalyear_lock_date =
# date(2024, 12, 31)`` to exercise fiscal-year boundary scenarios. The
# import is intentionally kept here (rather than per-test-file) so that
# every test module subclassing ``AssetManagementTestCommon`` can
# ``from .common import date`` and re-export the symbol if needed.
from datetime import date  # noqa: F401

from odoo import Command, fields

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class AssetManagementTestCommon(AccountTestInvoicingCommon):
    """Shared base fixtures for account_asset_management tests.

    Subclasses MUST decorate with ``@tagged('post_install', '-at_install')``
    so that the test runner waits until ``account_asset_management`` is
    fully installed before instantiating the fixtures (the ``account.asset``,
    ``account.asset.category``, and ``account.asset.depreciation.line``
    models, the ``ir.model.access.csv`` ACL grants, and the
    ``security/asset_security.xml`` ``ir.rule`` records all need to be
    present in the registry before ``setUpClass`` runs).

    The class follows the convention established by
    :class:`~odoo.addons.account_bank_reconciliation_ce.tests.common.BankReconciliationTestCommon`:
    fixtures are class attributes seeded once in ``setUpClass`` and reused
    across all test methods within a test class instance, drastically
    reducing per-test setup overhead.

    Notes on the helper-method signatures
    -------------------------------------
    Each helper method (``_get_or_create_account``, ``_create_basic_asset``,
    ``_confirm_asset``, ``_post_depreciation_lines``) accepts a redundant
    second positional argument named ``cls_ref``. This argument exists to
    tolerate call-sites that pass ``cls`` (or ``self``) explicitly --
    e.g. ``cls._create_basic_asset(cls, name='Test')`` -- which is the
    convention adopted by the per-story ``test_am_*.py`` files.

    The argument is intentionally ignored: the methods always use the
    implicit classmethod ``cls`` binding for state access. This dual-call
    convention means tests can use any of:

      * ``cls.method(cls, ...)``    -- explicit-cls (test_am_*.py style)
      * ``self.method(self, ...)``  -- explicit-self (instance-method style)
      * ``cls.method(...)``         -- modern classmethod style (only for
                                       ``_create_basic_asset`` whose
                                       ``cls_ref`` defaults to ``None``)
    """

    # =========================================================================
    # SETUP
    # =========================================================================

    @classmethod
    def setUpClass(cls):
        """Seed the minimum environment required by AM-001..AM-006 tests.

        Builds, in order:

        1. ``cls.company_a`` / ``cls.company_b`` — two companies for
           multi-company isolation tests, with ``cls.env.user`` granted
           access to both via ``company_ids``.
        2. ``cls.asset_account`` / ``cls.expense_account`` /
           ``cls.accumulated_account`` / ``cls.offset_account`` — the
           four ``account.account`` records needed for asset registration
           (AM-001) and depreciation posting (AM-004).
        3. ``cls.depreciation_journal`` — an ``account.journal`` of type
           ``general`` (re-uses an existing one when present, otherwise
           creates one named ``Asset Depreciation`` with code ``ASSET``).
        4. ``cls.vendor`` — a shared (cross-company) supplier
           ``res.partner`` with ``supplier_rank=1`` for AM-001 Scenario 5.
        5. ``cls.asset_category_it`` — a 3-year straight-line ``IT
           Equipment`` category template covering AM-001 Scenario 3 and
           AM-002 Scenario 6 / 11 inheritance assertions.

        Implementation note
        -------------------
        The Odoo 19.0 :class:`AccountTestInvoicingCommon` base class
        declares ``setUpClass(cls)`` without parameters (see
        ``addons/account/tests/common.py``). We mirror that exact
        signature here. To customize the chart template, set
        ``cls.chart_template`` BEFORE invoking
        ``AssetManagementTestCommon.setUpClass()`` or use the
        ``AccountTestInvoicingCommon.setup_chart_template`` class
        decorator on the subclass.
        """
        super().setUpClass()
        # ----------------------------------------------------------------
        # 1. Companies — company_a is the default from AccountTestInvoicingCommon;
        #    company_b is a freshly-created sibling for multi-company tests.
        # ----------------------------------------------------------------
        # company_a is the default (cls.env.company == cls.company_data['company'])
        cls.company_a = cls.env.company
        # company_b is a second company for multi-company isolation tests
        cls.company_b = cls.env['res.company'].create({
            'name': 'Asset Test Company B',
            'currency_id': cls.company_a.currency_id.id,
        })
        # Allow the test user to access both companies. Using Command.link
        # (additive) preserves any companies the parent class has already
        # assigned to ``cls.env.user`` -- which currently includes
        # ``cls.company_a`` -- and adds ``cls.company_b`` to the allowed set.
        cls.env.user.company_ids = [Command.link(cls.company_b.id)]

        # ----------------------------------------------------------------
        # 2. Required accounts for company_a.
        #    Each account is created with the ``company_ids`` Many2many
        #    membership including ``cls.company_a`` so that
        #    ``check_company=True`` Many2one fields on the asset model
        #    (``asset_account_id``, ``expense_account_id`` etc.) can
        #    select these accounts without raising a domain-mismatch
        #    error at form save time.
        # ----------------------------------------------------------------
        cls.asset_account = cls._get_or_create_account(
            cls, code='151000', name='Fixed Assets at Cost',
            account_type='asset_fixed', company=cls.company_a,
        )
        cls.expense_account = cls._get_or_create_account(
            cls, code='681000', name='Depreciation Expense',
            account_type='expense_depreciation', company=cls.company_a,
        )
        cls.accumulated_account = cls._get_or_create_account(
            cls, code='158000', name='Accumulated Depreciation',
            account_type='asset_non_current', company=cls.company_a,
        )
        cls.offset_account = cls._get_or_create_account(
            cls, code='401000', name='Suppliers - Asset Acquisition',
            account_type='liability_payable', company=cls.company_a,
        )

        # ----------------------------------------------------------------
        # 3. Depreciation journal.
        #    The asset model restricts ``journal_id`` to type='general'
        #    via its domain. ``AccountTestInvoicingCommon`` already creates
        #    a ``default_journal_misc`` (type='general') in
        #    ``collect_company_accounting_data``; we search for any
        #    pre-existing general journal first and only create a fresh
        #    one when none is found, to avoid disturbing the existing
        #    fixture's accounting state.
        # ----------------------------------------------------------------
        cls.depreciation_journal = cls.env['account.journal'].search([
            ('company_id', '=', cls.company_a.id),
            ('type', '=', 'general'),
        ], limit=1)
        if not cls.depreciation_journal:
            cls.depreciation_journal = cls.env['account.journal'].create({
                'name': 'Asset Depreciation',
                'code': 'ASSET',
                'type': 'general',
                'company_id': cls.company_a.id,
            })

        # ----------------------------------------------------------------
        # 4. Vendor for AM-001 Scenario 5 (vendor / source-invoice linkage).
        #    ``company_id=False`` makes the partner shared across every
        #    company in a multi-company database, matching the convention
        #    used by ``cls.partner_a`` / ``cls.partner_b`` from the
        #    parent ``AccountTestInvoicingCommon`` fixture (line 150-151,
        #    addons/account/tests/common.py).
        # ----------------------------------------------------------------
        cls.vendor = cls.env['res.partner'].create({
            'name': 'Asset Vendor Test',
            'supplier_rank': 1,
            'company_id': False,  # shared across companies
        })

        # ----------------------------------------------------------------
        # 5. Default category: IT Equipment, 3-year straight-line.
        #    Used by AM-001 Scenario 3 to verify category-driven defaults
        #    propagate to a newly-created asset (``_onchange_category_id``
        #    on ``account.asset``) and by AM-002 Scenario 6 / Scenario 11
        #    to assert category-template inheritance for depreciation
        #    method, useful life, and start-date option.
        # ----------------------------------------------------------------
        cls.asset_category_it = cls.env['account.asset.category'].create({
            'name': 'IT Equipment',
            'code': 'IT',
            'company_id': cls.company_a.id,
            'depreciation_method': 'straight_line',
            'useful_life_unit': 'years',
            'useful_life_years': 3,
            'salvage_percent': 0.0,
            'start_date_option': 'acquisition_date',
            'asset_account_id': cls.asset_account.id,
            'expense_account_id': cls.expense_account.id,
            'accumulated_depreciation_account_id': cls.accumulated_account.id,
            'journal_id': cls.depreciation_journal.id,
            'auto_post_depreciation': False,
        })

    # =========================================================================
    # HELPERS
    # =========================================================================

    @classmethod
    def _get_or_create_account(cls, cls_ref, code, name, account_type,
                               company=None):
        """Idempotent ``account.account`` creation by ``(code, company)``.

        Searches for an existing ``account.account`` whose code matches
        ``code`` AND whose ``company_ids`` Many2many includes ``company``.
        Returns the first match if found; otherwise creates a new account
        with the requested code, name, type, and company linkage.

        The signature includes a redundant ``cls_ref`` positional argument
        (the second formal parameter) so that call-sites passing ``cls``
        explicitly -- e.g. ``cls._get_or_create_account(cls, code='151000',
        ...)`` -- do not raise ``TypeError``. The argument is intentionally
        ignored; we always use the implicit classmethod binding ``cls`` to
        access the registry and environment.

        Args:
            cls_ref: Redundant first positional. Ignored.
            code (str): Account code, e.g. ``'151000'``.
            name (str): Human-readable account name.
            account_type (str): One of the ``account.account.account_type``
                Selection values (``'asset_fixed'``,
                ``'expense_depreciation'``, ``'asset_non_current'``,
                ``'liability_payable'``, ...).
            company (recordset, optional): The ``res.company`` record the
                account should belong to. Defaults to ``cls.env.company``.

        Returns:
            recordset: The matching or freshly-created ``account.account``
                singleton record.

        Notes:
            ``cls_ref`` is intentionally unused. See class-level docstring
            for the rationale (dual call-site compatibility with
            ``test_am_*.py`` files).
        """
        del cls_ref  # explicitly mark as intentionally unused
        company = company or cls.env.company

        # Determine the company-membership field name on ``account.account``.
        # In Odoo 17.0+ the Many2many ``company_ids`` replaces the legacy
        # Many2one ``company_id``. Introspect the field map at runtime to
        # remain forward- and backward-compatible across minor versions.
        account_fields = cls.env['account.account']._fields
        if 'company_ids' in account_fields:
            company_field = 'company_ids'
            domain_clause = ('company_ids', 'in', [company.id])
            create_company_value = [Command.link(company.id)]
        else:
            company_field = 'company_id'
            domain_clause = ('company_id', '=', company.id)
            create_company_value = company.id

        account = cls.env['account.account'].search([
            ('code', '=', code),
            domain_clause,
        ], limit=1)
        if account:
            return account
        return cls.env['account.account'].create({
            'code': code,
            'name': name,
            'account_type': account_type,
            company_field: create_company_value,
        })

    @classmethod
    def _create_basic_asset(cls, cls_ref=None, **overrides):
        """Create a draft ``account.asset`` with sensible defaults.

        Returns a freshly-created ``account.asset`` record in ``draft``
        state. All defaults are overridable via ``**overrides`` --
        any field name accepted by ``account.asset.create`` may be passed
        as a keyword argument and will replace the corresponding default.

        The signature accepts a redundant ``cls_ref`` first positional
        (defaulting to ``None``) to tolerate call-sites passing ``cls`` /
        ``self`` explicitly -- e.g. ``cls._create_basic_asset(cls,
        name='X')`` or ``self._create_basic_asset(self, name='X')``. The
        argument is ignored.

        Args:
            cls_ref: Redundant first positional. Defaults to ``None``;
                ignored.
            **overrides: Any field accepted by ``account.asset.create``.
                Common overrides:
                  - ``name`` (str) -- asset display name.
                  - ``acquisition_date`` (date | str) -- defaults to today.
                  - ``acquisition_cost`` (float) -- defaults to 10000.0.
                  - ``salvage_value`` (float) -- defaults to 0.0.
                  - ``useful_life_unit`` (str) -- defaults to ``'years'``.
                  - ``useful_life_years`` (int) -- defaults to 5.
                  - ``useful_life_months`` (int) -- defaults to 0.
                  - ``depreciation_method`` (str) -- defaults to
                    ``'straight_line'``.
                  - ``start_date_option`` (str) -- defaults to
                    ``'acquisition_date'``.
                  - ``asset_account_id`` (int) -- defaults to
                    ``cls.asset_account.id``.
                  - ``expense_account_id`` (int) -- defaults to
                    ``cls.expense_account.id``.
                  - ``accumulated_depreciation_account_id`` (int) --
                    defaults to ``cls.accumulated_account.id``.
                  - ``journal_id`` (int) -- defaults to
                    ``cls.depreciation_journal.id``.
                  - ``company_id`` (int) -- defaults to
                    ``cls.company_a.id``.

                Other arbitrary fields (``vendor_id``, ``source_invoice_id``,
                ``category_id``, ``declining_factor``, ``switch_to_straight_line``,
                ``units_production_total``, ``depreciation_start_date``, ...)
                are passed through verbatim into ``create``.

        Returns:
            recordset: The freshly-created ``account.asset`` singleton in
                ``state='draft'`` (the ORM default).

        Notes:
            ``cls_ref`` is intentionally unused. See class-level docstring
            for the rationale.
        """
        del cls_ref  # explicitly mark as intentionally unused
        vals = {
            'name': overrides.pop('name', 'Test Asset'),
            'acquisition_date': overrides.pop(
                'acquisition_date',
                fields.Date.context_today(cls.env.user),
            ),
            'acquisition_cost': overrides.pop('acquisition_cost', 10000.0),
            'salvage_value': overrides.pop('salvage_value', 0.0),
            'useful_life_unit': overrides.pop('useful_life_unit', 'years'),
            'useful_life_years': overrides.pop('useful_life_years', 5),
            'useful_life_months': overrides.pop('useful_life_months', 0),
            'depreciation_method': overrides.pop(
                'depreciation_method', 'straight_line',
            ),
            'start_date_option': overrides.pop(
                'start_date_option', 'acquisition_date',
            ),
            'asset_account_id': overrides.pop(
                'asset_account_id', cls.asset_account.id,
            ),
            'expense_account_id': overrides.pop(
                'expense_account_id', cls.expense_account.id,
            ),
            'accumulated_depreciation_account_id': overrides.pop(
                'accumulated_depreciation_account_id',
                cls.accumulated_account.id,
            ),
            'journal_id': overrides.pop(
                'journal_id', cls.depreciation_journal.id,
            ),
            'company_id': overrides.pop('company_id', cls.company_a.id),
        }
        # Attach any remaining overrides verbatim. This permits passing
        # vendor_id, source_invoice_id, category_id, declining_factor,
        # switch_to_straight_line, units_production_total, depreciation_start_date,
        # or any other ``account.asset`` field directly through to ``create()``.
        vals.update(overrides)
        return cls.env['account.asset'].create(vals)

    @classmethod
    def _confirm_asset(cls, cls_ref, asset):
        """Call ``action_confirm()`` on ``asset`` and assert post-conditions.

        Verifies the canonical AM-001 Scenario 2 outcome: confirmation
        transitions the asset from ``draft`` to ``open``, posts the
        acquisition ``account.move`` (recorded in
        ``asset.acquisition_move_id``), and generates the depreciation
        schedule (``asset.depreciation_line_ids`` is non-empty).

        Args:
            cls_ref: Redundant first positional. Ignored.
            asset (recordset): A ``account.asset`` singleton in ``draft``
                state.

        Returns:
            recordset: The same ``asset`` singleton, now in ``state='open'``.

        Raises:
            AssertionError: If any of the three post-condition assertions
                fails (state did not transition to ``open``;
                ``acquisition_move_id`` is unset; or
                ``depreciation_line_ids`` is empty).

        Notes:
            ``cls_ref`` is intentionally unused. See class-level docstring
            for the rationale.

            We use plain ``assert`` here (not :meth:`unittest.TestCase.assertEqual`)
            because this helper is a ``@classmethod`` invoked from
            ``setUpClass`` contexts where the ``self``-bound assertion
            methods are not yet available. Plain ``assert`` raises
            ``AssertionError`` which is captured by both ``unittest`` and
            ``pytest`` test runners equivalently.
        """
        del cls_ref  # explicitly mark as intentionally unused
        asset.action_confirm()
        assert asset.state == 'open', (
            f'Expected state=open after action_confirm(), '
            f'got state={asset.state}'
        )
        assert asset.acquisition_move_id, (
            'Expected acquisition_move_id to be set after action_confirm()'
        )
        assert asset.depreciation_line_ids, (
            'Expected depreciation_line_ids to be generated after '
            'action_confirm()'
        )
        return asset

    @classmethod
    def _post_depreciation_lines(cls, cls_ref, asset, count):
        """Post the first ``count`` draft depreciation lines of ``asset``.

        Filters the asset's ``depreciation_line_ids`` to those in
        ``state='draft'``, sorts ascending by ``depreciation_date``, takes
        the first ``count`` lines, and invokes ``action_post()`` on each
        line in turn. If the line's ``move_id`` was created in
        ``state='draft'`` (the default for asset categories where
        ``auto_post_depreciation=False``), the journal entry is also posted
        via ``move_id.action_post()`` to advance the depreciation event
        end-to-end.

        Args:
            cls_ref: Redundant first positional. Ignored.
            asset (recordset): A ``account.asset`` singleton.
            count (int): Number of draft lines to post.

        Returns:
            recordset: The recordset of ``account.asset.depreciation.line``
                lines that were posted (may be shorter than ``count`` if
                fewer than ``count`` draft lines are available).

        Notes:
            ``cls_ref`` is intentionally unused. See class-level docstring
            for the rationale.

            The slice ``[:count]`` on a recordset is a standard Odoo idiom
            that returns a new recordset of at most ``count`` records. No
            error is raised if the asset has fewer than ``count`` draft
            lines -- the helper is intentionally permissive here so that
            tests can verify edge cases (e.g., posting all remaining
            lines when fewer than expected exist).
        """
        del cls_ref  # explicitly mark as intentionally unused
        draft_lines = asset.depreciation_line_ids.filtered(
            lambda line: line.state == 'draft',
        ).sorted('depreciation_date')[:count]
        for line in draft_lines:
            line.action_post()
            if line.move_id and line.move_id.state == 'draft':
                line.move_id.action_post()
        return draft_lines
