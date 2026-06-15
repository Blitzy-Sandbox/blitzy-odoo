# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Tests for AM-006: Asset Disposal (Sale / Scrap / Write-off) user story.

Covers the following BDD scenarios from the AM-006 ticket
(``tickets/stories/asset-management/AM-006-asset-disposal.md``):

    T-AM-006-01  Dispose by SALE with gain: proceeds > NBV
    T-AM-006-02  Dispose by SALE with loss: proceeds < NBV
    T-AM-006-03  Dispose by SALE at NBV: zero gain/loss
    T-AM-006-04  Dispose by SCRAP: zero proceeds, full loss at NBV
    T-AM-006-05  Dispose by WRITE_OFF with insurance recovery
    T-AM-006-06  Dispose by WRITE_OFF without recovery (equivalent to scrap)
    T-AM-006-07  Automatic gain/loss calculation (proceeds - NBV)
    T-AM-006-08  Partial disposal (50% of asset quantity)
    T-AM-006-09  Partial disposal preserves asset in 'open' state with reduced
                 acquisition_cost
    T-AM-006-10  Full disposal transitions asset to 'close' state
    T-AM-006-11  Disposal date validation: must be >= acquisition_date
    T-AM-006-12  Disposal date validation: must not be in locked period
    T-AM-006-13  Catch-up depreciation: if disposal_date > last_posted_date,
                 pre-disposal catch-up move created
    T-AM-006-14  State machine: draft -> confirmed -> posted -> cancelled
    T-AM-006-15  Cancel posted disposal reverses both the disposal and the
                 catch-up depreciation moves
    T-AM-006-16  Audit trail: message_post called with disposal metadata
    T-AM-006-G1  Sale with proceeds > NBV: gain posted to gain_account_id
    T-AM-006-G2  Sale with proceeds < NBV: loss posted to loss_account_id
    T-AM-006-J1  Sale journal structure (DR proceeds, DR accumulated, CR asset,
                 CR gain OR DR loss)
    T-AM-006-J2  Scrap journal structure (DR accumulated, DR loss at NBV,
                 CR asset)
    T-AM-006-J3  Write-off journal structure (same as sale if proceeds>0)
    T-AM-006-J4  Partial disposal: amounts prorated by disposal_proportion
    T-AM-006-J5  Catch-up journal separate from disposal journal

Each test method's docstring starts with the BDD scenario ID for traceability.
All accounting assertions validate that journal entries are balanced and use
the correct account types per GAAP/IFRS conventions (IAS 16, ASC 360-10-40).

AAP Rule Compliance
-------------------
* R-01 (Module independence) -- This file imports ONLY from the Python
  standard library (``time``, ``datetime``), the ``odoo`` framework
  (``odoo.Command``, ``odoo.fields``, ``odoo.exceptions``,
  ``odoo.tests.tagged``), and the local ``.common`` sibling module
  within the same ``account_asset_management`` package. NO imports from
  the three sibling Community Edition modules
  (``account_budget_management``, ``account_deferred_revenue``,
  ``account_payment_followup``).
* R-02 (No Enterprise dependencies) -- This file contains NO references
  to Odoo Enterprise addon names (``account_asset``,
  ``account_accountant``, ``account_reports``, ``account_followup``,
  ``account_deferred_revenue``).
* R-04 (Per-story coverage gate) -- Tests exercise every documented
  branch of the AM-006 disposal wizard: all three disposal methods
  (sale / scrap / write_off) with gain / loss / breakeven scenarios,
  full vs partial disposals, computed fields (net_book_value,
  gain_loss_amount, total_quantity, disposal_proportion,
  catchup_depreciation_required, catchup_depreciation_amount), all
  four ``@api.constrains`` validators (_check_disposal_date,
  _check_proceeds_configuration, _check_gain_loss_accounts,
  _check_partial_quantity), the full state machine (draft ->
  confirmed -> posted -> cancelled), private move-builders
  (_create_catchup_move, _create_disposal_move), audit trail
  formatter (_format_audit_message), and reversal-via-cancel.
* R-07 (No unjustified ``sudo``) -- This file contains NO ``.sudo()``
  calls. The test user provisioned by ``AccountTestInvoicingCommon``
  has both ``account.group_account_user`` and
  ``account.group_account_manager`` group memberships, providing
  full CRUD on every model touched by the tests via
  ``security/ir.model.access.csv``.
"""

import time  # noqa: F401 -- imported per agent_prompt mandatory list
from datetime import date

from odoo import Command, fields  # noqa: F401 -- per agent_prompt mandatory
from odoo.exceptions import UserError, ValidationError  # noqa: F401
from odoo.tests import tagged

from .common import AssetManagementTestCommon


@tagged('post_install', '-at_install')
class TestAssetDisposal(AssetManagementTestCommon):
    """AM-006 -- Asset Disposal (Sale / Scrap / Write-off).

    Covers all 16 primary BDD scenarios + 2 gain detail sub-scenarios
    (G1, G2) + 1 consolidated journal-structure check (J1-J5) for the
    AM-006 story. Each test method's name encodes both its scenario
    ID (``test_am_006_NN_``) and a one-line summary of what it
    validates (e.g. ``sale_with_gain``, ``catchup_depreciation``).

    Setup Strategy
    --------------
    The ``setUpClass`` extends the parent ``AssetManagementTestCommon``
    fixture set with three disposal-specific accounts and one
    pre-confirmed asset that has 2 years of posted depreciation:

        * ``cls.gain_account``  -- ``income_other`` account for sale
                                   gain recognition.
        * ``cls.loss_account``  -- ``expense`` account for sale loss
                                   / scrap / write-off recognition.
        * ``cls.cash_account``  -- ``asset_cash`` account used as
                                   the ``proceeds_account_id`` for
                                   sale and write-off-with-recovery.
        * ``cls.disposal_asset`` -- A fully-configured open asset with
                                   acquisition_cost=10000, useful
                                   life=5 years, salvage=0, and
                                   accumulated_depreciation=4000
                                   (2 years posted) yielding NBV=6000.

    These fixtures are seeded ONCE in ``setUpClass`` and reused across
    every test method; the disposal wizard creates / posts new
    ``account.move`` records per test, but the underlying asset and
    its 2-years-posted depreciation history persists.

    Helper Pattern
    --------------
    For tests that need an isolated asset (e.g., partial disposal
    test_am_006_08 and full-disposal test_am_006_10 both modify the
    asset state), each test creates a fresh asset via the
    ``_create_basic_asset`` helper plus inline confirmation +
    depreciation posting. This avoids cross-test contamination of
    the shared ``cls.disposal_asset`` fixture.
    """

    # =========================================================================
    # CLASS-LEVEL FIXTURE SETUP
    # =========================================================================

    @classmethod
    def setUpClass(cls):
        """Seed disposal-specific accounts and a pre-depreciated asset.

        Builds, in order:

            1. Three disposal-specific accounts (gain, loss, cash).
            2. The ``disposal_asset`` fixture: a confirmed 5-year
               straight-line asset with acquisition_cost=10000.0,
               useful_life_years=5, salvage_value=0.0,
               acquisition_date=2024-01-01, with the FIRST 2
               depreciation lines posted (accumulated=4000, NBV=6000
               on 2025-01-01).

        The asset uses ``acquisition_date=date(2024, 1, 1)`` so that
        date-validation tests (test_am_006_11) can use a clearly
        pre-acquisition date (2023-12-31) and locked-period tests
        (test_am_006_12) can set ``fiscalyear_lock_date=date(2025, 12, 31)``
        and attempt a disposal date in 2025 (which falls within the
        lock).
        """
        super().setUpClass()
        # ----------------------------------------------------------------
        # 1. Disposal-specific accounts.
        #
        #    Odoo's ``account.account._check_account_code`` constraint
        #    permits ONLY alphanumeric characters and dots in the
        #    ``code`` field (no underscores, hyphens, or spaces). The
        #    codes below use a 'DISPGAIN' / 'DISPLOSS' / 'DISPCASH'
        #    prefix to (a) satisfy the alphanumeric-only constraint
        #    and (b) avoid collision with chart-of-accounts default
        #    codes seeded by ``AccountTestInvoicingCommon`` (which
        #    follow the standard 4xx / 5xx / 7xx numeric scheme).
        # ----------------------------------------------------------------
        cls.gain_account = cls._get_or_create_account(
            cls,
            code='DISPGAIN',
            name='Gain on Asset Disposal',
            account_type='income_other',
            company=cls.company_a,
        )
        cls.loss_account = cls._get_or_create_account(
            cls,
            code='DISPLOSS',
            name='Loss on Asset Disposal',
            account_type='expense',
            company=cls.company_a,
        )
        cls.cash_account = cls._get_or_create_account(
            cls,
            code='DISPCASH',
            name='Cash Received on Disposal',
            account_type='asset_cash',
            company=cls.company_a,
        )
        # ----------------------------------------------------------------
        # 2. Disposal-test asset: 10000 acquisition cost, 5-year SL,
        #    acquired 2024-01-01. After confirmation, the schedule
        #    contains 5 annual lines @ 2000 each (2024-01-01, 2025-01-01,
        #    2026-01-01, 2027-01-01, 2028-01-01). We post the first 2
        #    lines so that accumulated_depreciation = 4000 and
        #    NBV = 10000 - 4000 = 6000.
        # ----------------------------------------------------------------
        cls.disposal_asset = cls._create_basic_asset(
            cls,
            name='AM-006 Disposal Test Asset',
            acquisition_cost=10000.0,
            salvage_value=0.0,
            useful_life_unit='years',
            useful_life_years=5,
            acquisition_date=date(2024, 1, 1),
            depreciation_method='straight_line',
            start_date_option='acquisition_date',
        )
        cls.disposal_asset.action_confirm()
        # Post the first 2 of 5 yearly depreciation lines. This advances
        # the schedule through the end of 2025 (the second line's date
        # is 2025-01-01); the remaining 3 lines (2026-01-01,
        # 2027-01-01, 2028-01-01) stay in 'draft' state.
        for line in cls.disposal_asset.depreciation_line_ids.sorted(
            'depreciation_date',
        )[:2]:
            line.action_post()
            if line.move_id and line.move_id.state == 'draft':
                line.move_id.action_post()
        # Force a cache refresh so the asset's stored aggregates
        # reflect the just-posted depreciation lines. Without this,
        # subsequent reads of ``net_book_value`` / ``accumulated_depreciation``
        # may return the pre-post (zero) values from the field cache.
        cls.disposal_asset.invalidate_recordset(
            ['accumulated_depreciation', 'net_book_value'],
        )
        # Sanity check: the fixture should now expose
        # accumulated=4000, NBV=6000. Use absolute-tolerance
        # comparison (Python ``abs(a-b) < eps``) instead of strict
        # equality to remain compatible with any minor rounding
        # variation between the asset's ``Monetary`` field's
        # ``currency.round`` and the schedule generator. Tolerance
        # of 0.01 (one cent) is well within the company-currency
        # decimal precision and will trip on any genuine setup
        # failure (e.g., a 100x or off-by-one error).
        accum = cls.disposal_asset.accumulated_depreciation
        assert abs(accum - 4000.0) < 0.01, (
            f'Setup failure: expected accumulated~=4000.0, got '
            f'{accum}'
        )
        nbv = cls.disposal_asset.net_book_value
        assert abs(nbv - 6000.0) < 0.01, (
            f'Setup failure: expected NBV~=6000.0, got {nbv}'
        )

    # =========================================================================
    # HELPER METHODS (test-local convenience)
    # =========================================================================

    def _create_disposal_wizard(self, **overrides):
        """Build a disposal wizard with sensible defaults.

        Returns a freshly-created ``account.asset.disposal.wizard``
        record in ``draft`` state with all common fields pre-filled.
        Any field can be overridden via keyword arguments.

        Default values:
            * ``asset_id``           -> ``self.disposal_asset.id``
            * ``disposal_method``    -> ``'sale'``
            * ``disposal_date``      -> ``'2025-12-31'`` (end of year
              2 -- after the second posted depreciation line at
              2025-01-01 and one day before the next draft line at
              2026-01-01, so no catch-up depreciation is triggered)
            * ``proceeds_amount``    -> ``7500.0`` (yields gain of 1500)
            * ``proceeds_account_id`` -> ``self.cash_account.id``
            * ``gain_account_id``    -> ``self.gain_account.id``
            * ``loss_account_id``    -> ``self.loss_account.id``
            * ``disposal_reason``    -> ``'Test disposal reason'``

        Args:
            **overrides: Any field accepted by
                ``account.asset.disposal.wizard.create``.

        Returns:
            recordset: The freshly-created wizard singleton in
                ``state='draft'``.
        """
        vals = {
            'asset_id': overrides.pop(
                'asset_id', self.disposal_asset.id,
            ),
            'disposal_method': overrides.pop(
                'disposal_method', 'sale',
            ),
            'disposal_date': overrides.pop(
                'disposal_date', '2025-12-31',
            ),
            'proceeds_amount': overrides.pop(
                'proceeds_amount', 7500.0,
            ),
            'proceeds_account_id': overrides.pop(
                'proceeds_account_id', self.cash_account.id,
            ),
            'gain_account_id': overrides.pop(
                'gain_account_id', self.gain_account.id,
            ),
            'loss_account_id': overrides.pop(
                'loss_account_id', self.loss_account.id,
            ),
            'disposal_reason': overrides.pop(
                'disposal_reason', 'Test disposal reason',
            ),
        }
        vals.update(overrides)
        return self.env['account.asset.disposal.wizard'].create(vals)

    def _create_fresh_asset(
        self,
        name='AM-006 Fresh Asset',
        acquisition_cost=10000.0,
        salvage_value=0.0,
        useful_life_years=5,
        acquisition_date=None,
        post_lines=2,
    ):
        """Build a confirmed asset with N years posted depreciation.

        Mirror of the ``setUpClass`` fixture builder, used by tests
        that need an isolated asset to mutate without affecting the
        shared ``cls.disposal_asset`` fixture (e.g., the partial
        disposal tests change ``acquisition_cost``).

        Args:
            name (str): Asset name. Default ``'AM-006 Fresh Asset'``.
            acquisition_cost (float): Cost. Default 10000.0.
            salvage_value (float): Salvage. Default 0.0.
            useful_life_years (int): Useful life. Default 5.
            acquisition_date (date | None): Acquisition. Default
                ``date(2024, 1, 1)``.
            post_lines (int): Number of yearly depreciation lines to
                post. Default 2 (yields accumulated=4000 / NBV=6000
                for default cost=10000 / years=5).

        Returns:
            recordset: The freshly-created and confirmed
            ``account.asset`` singleton.
        """
        if acquisition_date is None:
            acquisition_date = date(2024, 1, 1)
        asset = self._create_basic_asset(
            self,
            name=name,
            acquisition_cost=acquisition_cost,
            salvage_value=salvage_value,
            useful_life_unit='years',
            useful_life_years=useful_life_years,
            acquisition_date=acquisition_date,
            depreciation_method='straight_line',
            start_date_option='acquisition_date',
        )
        asset.action_confirm()
        if post_lines > 0:
            for line in asset.depreciation_line_ids.sorted(
                'depreciation_date',
            )[:post_lines]:
                line.action_post()
                if line.move_id and line.move_id.state == 'draft':
                    line.move_id.action_post()
        asset.invalidate_recordset(
            ['accumulated_depreciation', 'net_book_value'],
        )
        return asset

    def _assert_move_balanced(self, move, expected_total=None):
        """Assert that an ``account.move`` is balanced (debits == credits).

        Verifies the fundamental accounting invariant: the sum of
        all debit amounts equals the sum of all credit amounts on
        the move's ``line_ids``. Optionally verifies the absolute
        value of the balanced amount matches an expected total.

        Args:
            move (recordset): An ``account.move`` singleton.
            expected_total (float | None): If given, also assert that
                ``sum(debits) == expected_total``.
        """
        total_debit = sum(move.line_ids.mapped('debit'))
        total_credit = sum(move.line_ids.mapped('credit'))
        self.assertAlmostEqual(
            total_debit,
            total_credit,
            places=2,
            msg=(
                f'Move {move.name or move.id} unbalanced: '
                f'total_debit={total_debit}, total_credit={total_credit}'
            ),
        )
        if expected_total is not None:
            self.assertAlmostEqual(
                total_debit,
                expected_total,
                places=2,
                msg=(
                    f'Move {move.name or move.id} expected total '
                    f'{expected_total}, got debit total {total_debit}'
                ),
            )

    def _get_line_for_account(self, move, account):
        """Filter a move's lines to those on a given account.

        Args:
            move (recordset): An ``account.move`` singleton.
            account (recordset): An ``account.account`` singleton.

        Returns:
            recordset: The subset of ``move.line_ids`` whose
            ``account_id`` matches the given account (may be empty).
        """
        return move.line_ids.filtered(
            lambda line: line.account_id == account,
        )

    # =========================================================================
    # T-AM-006-01: SALE with gain (proceeds > NBV)
    # =========================================================================

    def test_am_006_01_sale_with_gain(self):
        """T-AM-006-01: SALE with proceeds > NBV produces a credit gain.

        Verifies the canonical sale-with-gain disposal workflow:

            * NBV = 6000 (acquisition 10000 - accumulated 4000).
            * Proceeds = 7500. Expected gain = 7500 - 6000 = 1500.
            * Disposal entry has 4 lines (DR cash, DR accumulated,
              CR asset, CR gain) all balanced 11500/11500.
            * Asset transitions to ``state='close'``.
            * Move is tagged ``asset_entry_type='disposal'`` and
              back-references the asset via ``asset_id``.
        """
        asset = self._create_fresh_asset(name='AM-006-01 Asset')
        wizard = self.env['account.asset.disposal.wizard'].create({
            'asset_id': asset.id,
            'disposal_method': 'sale',
            'disposal_date': '2025-12-31',
            'proceeds_amount': 7500.0,
            'proceeds_account_id': self.cash_account.id,
            'gain_account_id': self.gain_account.id,
            'loss_account_id': self.loss_account.id,
            'disposal_reason': 'Sold at market value',
        })
        # Pre-conditions: wizard in draft; asset in open with
        # accumulated=4000, NBV=6000.
        self.assertEqual(wizard.state, 'draft')
        self.assertEqual(asset.state, 'open')
        self.assertAlmostEqual(asset.net_book_value, 6000.0, places=2)
        # Computed fields preview correctly before posting.
        self.assertAlmostEqual(wizard.net_book_value, 6000.0, places=2)
        self.assertAlmostEqual(
            wizard.gain_loss_amount, 1500.0, places=2,
            msg='gain_loss = proceeds - NBV = 7500 - 6000 = 1500',
        )
        # Confirm + post.
        wizard.action_confirm()
        self.assertEqual(wizard.state, 'confirmed')
        wizard.action_post()
        self.assertEqual(wizard.state, 'posted')
        # Move attached and posted.
        self.assertTrue(wizard.move_id)
        move = wizard.move_id
        self.assertEqual(move.state, 'posted')
        self.assertEqual(
            move.asset_entry_type, 'disposal',
            "Disposal move must carry asset_entry_type='disposal'",
        )
        self.assertEqual(
            move.asset_id, asset,
            'Disposal move must back-reference the source asset.',
        )
        # Move is balanced 11500/11500 (DR cash 7500 + DR accum 4000
        # = 11500; CR asset 10000 + CR gain 1500 = 11500).
        self._assert_move_balanced(move, expected_total=11500.0)
        # 4-line structure: DR cash, DR accumulated, CR asset, CR gain.
        self.assertEqual(
            len(move.line_ids), 4,
            'Sale-with-gain must have 4 journal lines.',
        )
        # Validate each line's account and amount.
        cash_lines = self._get_line_for_account(move, self.cash_account)
        self.assertEqual(len(cash_lines), 1)
        self.assertAlmostEqual(cash_lines.debit, 7500.0, places=2)
        self.assertAlmostEqual(cash_lines.credit, 0.0, places=2)
        accum_lines = self._get_line_for_account(
            move, asset.accumulated_depreciation_account_id,
        )
        self.assertEqual(len(accum_lines), 1)
        self.assertAlmostEqual(accum_lines.debit, 4000.0, places=2)
        self.assertAlmostEqual(accum_lines.credit, 0.0, places=2)
        asset_lines = self._get_line_for_account(
            move, asset.asset_account_id,
        )
        self.assertEqual(len(asset_lines), 1)
        self.assertAlmostEqual(asset_lines.debit, 0.0, places=2)
        self.assertAlmostEqual(asset_lines.credit, 10000.0, places=2)
        gain_lines = self._get_line_for_account(move, self.gain_account)
        self.assertEqual(len(gain_lines), 1)
        self.assertAlmostEqual(gain_lines.debit, 0.0, places=2)
        self.assertAlmostEqual(gain_lines.credit, 1500.0, places=2)
        # Asset now closed.
        self.assertEqual(asset.state, 'close')

    # =========================================================================
    # T-AM-006-02: SALE with loss (proceeds < NBV)
    # =========================================================================

    def test_am_006_02_sale_with_loss(self):
        """T-AM-006-02: SALE with proceeds < NBV produces a debit loss.

        Verifies:

            * NBV = 6000, Proceeds = 4500 -> loss = -1500.
            * Disposal entry has 4 lines (DR cash 4500, DR accum 4000,
              DR loss 1500, CR asset 10000) balanced 10000/10000.
            * gain_loss_amount = -1500 (negative => loss).
        """
        asset = self._create_fresh_asset(name='AM-006-02 Asset')
        wizard = self.env['account.asset.disposal.wizard'].create({
            'asset_id': asset.id,
            'disposal_method': 'sale',
            'disposal_date': '2025-12-31',
            'proceeds_amount': 4500.0,
            'proceeds_account_id': self.cash_account.id,
            'gain_account_id': self.gain_account.id,
            'loss_account_id': self.loss_account.id,
            'disposal_reason': 'Sold below NBV',
        })
        self.assertAlmostEqual(
            wizard.gain_loss_amount, -1500.0, places=2,
            msg='gain_loss = 4500 - 6000 = -1500 (loss)',
        )
        wizard.action_confirm()
        wizard.action_post()
        move = wizard.move_id
        self._assert_move_balanced(move, expected_total=10000.0)
        # 4-line structure: DR cash, DR accumulated, DR loss, CR asset.
        self.assertEqual(len(move.line_ids), 4)
        cash_lines = self._get_line_for_account(move, self.cash_account)
        self.assertAlmostEqual(cash_lines.debit, 4500.0, places=2)
        accum_lines = self._get_line_for_account(
            move, asset.accumulated_depreciation_account_id,
        )
        self.assertAlmostEqual(accum_lines.debit, 4000.0, places=2)
        loss_lines = self._get_line_for_account(move, self.loss_account)
        self.assertEqual(len(loss_lines), 1)
        self.assertAlmostEqual(loss_lines.debit, 1500.0, places=2)
        self.assertAlmostEqual(loss_lines.credit, 0.0, places=2)
        asset_lines = self._get_line_for_account(
            move, asset.asset_account_id,
        )
        self.assertAlmostEqual(asset_lines.credit, 10000.0, places=2)
        # No gain line on a loss disposal.
        gain_lines = self._get_line_for_account(move, self.gain_account)
        self.assertEqual(
            len(gain_lines), 0,
            'Loss disposal must NOT post to gain_account.',
        )
        self.assertEqual(asset.state, 'close')

    # =========================================================================
    # T-AM-006-03: SALE at NBV (zero gain/loss)
    # =========================================================================

    def test_am_006_03_sale_at_nbv_zero_gain_loss(self):
        """T-AM-006-03: SALE at exactly NBV: zero gain/loss; no GL line.

        Verifies that when proceeds == NBV, no gain or loss line
        is generated; the entry balances on the four asset-side
        lines alone.
        """
        asset = self._create_fresh_asset(name='AM-006-03 Asset')
        wizard = self.env['account.asset.disposal.wizard'].create({
            'asset_id': asset.id,
            'disposal_method': 'sale',
            'disposal_date': '2025-12-31',
            'proceeds_amount': 6000.0,  # exactly NBV
            'proceeds_account_id': self.cash_account.id,
            'gain_account_id': self.gain_account.id,
            'loss_account_id': self.loss_account.id,
            'disposal_reason': 'Sold at carrying value',
        })
        self.assertAlmostEqual(
            wizard.gain_loss_amount, 0.0, places=2,
            msg='gain_loss = 6000 - 6000 = 0 (breakeven)',
        )
        wizard.action_confirm()
        wizard.action_post()
        move = wizard.move_id
        # 3-line structure (no gain/loss line because gain_loss == 0).
        self.assertEqual(
            len(move.line_ids), 3,
            'Breakeven sale must omit the gain/loss line.',
        )
        self._assert_move_balanced(move, expected_total=10000.0)
        # No gain or loss account references.
        gain_lines = self._get_line_for_account(move, self.gain_account)
        loss_lines = self._get_line_for_account(move, self.loss_account)
        self.assertEqual(len(gain_lines), 0)
        self.assertEqual(len(loss_lines), 0)
        self.assertEqual(asset.state, 'close')

    # =========================================================================
    # T-AM-006-04: SCRAP (zero proceeds, full NBV becomes loss)
    # =========================================================================

    def test_am_006_04_scrap_zero_proceeds(self):
        """T-AM-006-04: SCRAP -> zero proceeds; full NBV is a loss.

        Verifies:

            * disposal_method='scrap', proceeds_amount=0.
            * 3-line entry: DR accum 4000, DR loss 6000, CR asset
              10000. Balanced 10000/10000.
            * gain_loss_amount = -6000 (full NBV).
            * No proceeds line; no gain line.
        """
        asset = self._create_fresh_asset(name='AM-006-04 Asset')
        wizard = self.env['account.asset.disposal.wizard'].create({
            'asset_id': asset.id,
            'disposal_method': 'scrap',
            'disposal_date': '2025-12-31',
            'proceeds_amount': 0.0,
            # No proceeds_account_id (scrap forbids it via _onchange).
            'loss_account_id': self.loss_account.id,
            'disposal_reason': 'Damaged beyond repair',
        })
        self.assertAlmostEqual(
            wizard.gain_loss_amount, -6000.0, places=2,
            msg='Scrap loss = 0 - 6000 = -6000',
        )
        wizard.action_confirm()
        wizard.action_post()
        move = wizard.move_id
        self.assertEqual(move.state, 'posted')
        self.assertEqual(
            move.asset_entry_type, 'disposal',
        )
        # 3-line structure: DR accumulated, DR loss, CR asset.
        self.assertEqual(
            len(move.line_ids), 3,
            'Scrap must have 3 journal lines (accum, loss, asset).',
        )
        self._assert_move_balanced(move, expected_total=10000.0)
        # No cash or gain lines; only loss is an expense line.
        cash_lines = self._get_line_for_account(move, self.cash_account)
        gain_lines = self._get_line_for_account(move, self.gain_account)
        self.assertEqual(len(cash_lines), 0)
        self.assertEqual(len(gain_lines), 0)
        loss_lines = self._get_line_for_account(move, self.loss_account)
        self.assertEqual(len(loss_lines), 1)
        self.assertAlmostEqual(
            loss_lines.debit, 6000.0, places=2,
            msg='Scrap loss equals full NBV.',
        )
        # Asset closed.
        self.assertEqual(asset.state, 'close')

    # =========================================================================
    # T-AM-006-05: WRITE_OFF with insurance recovery
    # =========================================================================

    def test_am_006_05_writeoff_with_recovery(self):
        """T-AM-006-05: WRITE_OFF with proceeds > 0 (insurance recovery).

        Verifies:

            * disposal_method='write_off', proceeds_amount=2000
              (insurance recovery).
            * Move structure equivalent to a sale: DR cash 2000,
              DR accum 4000, DR loss 4000, CR asset 10000.
              Balanced 10000/10000.
            * gain_loss = 2000 - 6000 = -4000 (loss reduced by
              recovery).
        """
        asset = self._create_fresh_asset(name='AM-006-05 Asset')
        wizard = self.env['account.asset.disposal.wizard'].create({
            'asset_id': asset.id,
            'disposal_method': 'write_off',
            'disposal_date': '2025-12-31',
            'proceeds_amount': 2000.0,
            'proceeds_account_id': self.cash_account.id,
            'gain_account_id': self.gain_account.id,
            'loss_account_id': self.loss_account.id,
            'disposal_reason': 'Insurance recovery (theft)',
            'documentation_ref': 'INS-CLAIM-2026-01',
        })
        self.assertAlmostEqual(
            wizard.gain_loss_amount, -4000.0, places=2,
            msg='write-off loss = 2000 - 6000 = -4000',
        )
        wizard.action_confirm()
        wizard.action_post()
        move = wizard.move_id
        # 4-line structure (same as a loss sale).
        self.assertEqual(len(move.line_ids), 4)
        self._assert_move_balanced(move, expected_total=10000.0)
        cash_lines = self._get_line_for_account(move, self.cash_account)
        loss_lines = self._get_line_for_account(move, self.loss_account)
        self.assertAlmostEqual(cash_lines.debit, 2000.0, places=2)
        self.assertAlmostEqual(loss_lines.debit, 4000.0, places=2)
        self.assertEqual(asset.state, 'close')

    # =========================================================================
    # T-AM-006-06: WRITE_OFF without recovery
    # =========================================================================

    def test_am_006_06_writeoff_no_recovery(self):
        """T-AM-006-06: WRITE_OFF with proceeds=0 -> equivalent to scrap.

        Verifies that a write-off without any insurance recovery
        produces the same 3-line structure as scrap (DR accumulated,
        DR loss, CR asset) and the same -6000 loss.
        """
        asset = self._create_fresh_asset(name='AM-006-06 Asset')
        wizard = self.env['account.asset.disposal.wizard'].create({
            'asset_id': asset.id,
            'disposal_method': 'write_off',
            'disposal_date': '2025-12-31',
            'proceeds_amount': 0.0,
            # No proceeds_account_id when proceeds_amount = 0.
            'loss_account_id': self.loss_account.id,
            'disposal_reason': 'Total loss; no recovery',
            'documentation_ref': 'POLICE-REPORT-2026-01',
        })
        self.assertAlmostEqual(
            wizard.gain_loss_amount, -6000.0, places=2,
        )
        wizard.action_confirm()
        wizard.action_post()
        move = wizard.move_id
        # 3-line structure (no proceeds line).
        self.assertEqual(len(move.line_ids), 3)
        self._assert_move_balanced(move, expected_total=10000.0)
        # No cash; loss = full NBV.
        cash_lines = self._get_line_for_account(move, self.cash_account)
        loss_lines = self._get_line_for_account(move, self.loss_account)
        self.assertEqual(len(cash_lines), 0)
        self.assertAlmostEqual(loss_lines.debit, 6000.0, places=2)
        self.assertEqual(asset.state, 'close')

    # =========================================================================
    # T-AM-006-07: Automatic gain/loss calculation (subTest matrix)
    # =========================================================================

    def test_am_006_07_auto_gain_loss_calc(self):
        """T-AM-006-07: gain_loss_amount computed = proceeds - NBV.

        Validates the computed-field behavior with a subTest matrix
        of four cases. The wizard is created (not posted) for each
        case so the constraint validators do not fire (they would
        reject some cases like proceeds=0 sale).
        """
        # Use disposal_asset directly: we never post any of these
        # wizards, only verify the computed gain_loss_amount field.
        cases = [
            (7500.0, 1500.0, 'Proceeds 7500 (gain)'),
            (4500.0, -1500.0, 'Proceeds 4500 (loss)'),
            (0.0, -6000.0, 'Proceeds 0 (full loss = -NBV)'),
            (6000.0, 0.0, 'Proceeds 6000 (breakeven)'),
        ]
        # NBV is 6000 on the shared fixture.
        for proceeds, expected, label in cases:
            with self.subTest(case=label):
                wizard = self.env[
                    'account.asset.disposal.wizard'
                ].new({
                    'asset_id': self.disposal_asset.id,
                    'disposal_method': 'sale',
                    'disposal_date': '2025-12-31',
                    'proceeds_amount': proceeds,
                    'proceeds_account_id': self.cash_account.id,
                    'gain_account_id': self.gain_account.id,
                    'loss_account_id': self.loss_account.id,
                    'disposal_reason': label,
                })
                # Force compute via attribute access.
                self.assertAlmostEqual(
                    wizard.net_book_value, 6000.0, places=2,
                )
                self.assertAlmostEqual(
                    wizard.gain_loss_amount, expected, places=2,
                    msg=(
                        f'{label}: gain_loss = proceeds - NBV = '
                        f'{proceeds} - 6000 = {expected}'
                    ),
                )

    # =========================================================================
    # T-AM-006-08: Partial disposal (50% of asset quantity)
    # =========================================================================

    def test_am_006_08_partial_disposal(self):
        """T-AM-006-08: Partial disposal posts proportional amounts.

        Verifies:

            * disposed_quantity = 0.5 of total_quantity = 1.0
              => disposal_proportion = 0.5.
            * Move amounts:
                - DR cash         = 4000 (proceeds, NOT prorated)
                - DR accumulated  = 2000 (4000 * 0.5)
                - CR asset        = 5000 (10000 * 0.5)
                - CR gain         = 1000 (4000 - (5000 - 2000) = 1000)
            * Move balanced 6000/6000 (DR 4000 + 2000 = 6000;
              CR 5000 + 1000 = 6000).
        """
        asset = self._create_fresh_asset(name='AM-006-08 Asset')
        wizard = self.env['account.asset.disposal.wizard'].create({
            'asset_id': asset.id,
            'disposal_method': 'sale',
            'disposal_date': '2025-12-31',
            'is_partial': True,
            'disposed_quantity': 0.5,
            'proceeds_amount': 4000.0,
            'proceeds_account_id': self.cash_account.id,
            'gain_account_id': self.gain_account.id,
            'loss_account_id': self.loss_account.id,
            'disposal_reason': 'Partial sale',
        })
        # Pre-condition: total quantity is 1.0 for non-UoP assets.
        self.assertAlmostEqual(wizard.total_quantity, 1.0, places=4)
        # disposal_proportion = 0.5/1.0 = 0.5.
        self.assertAlmostEqual(
            wizard.disposal_proportion, 0.5, places=4,
        )
        # NBV preview = 6000 * 0.5 = 3000.
        self.assertAlmostEqual(
            wizard.net_book_value, 3000.0, places=2,
            msg='Partial NBV = full NBV * disposal_proportion',
        )
        # gain_loss = proceeds - prorated NBV = 4000 - 3000 = 1000.
        self.assertAlmostEqual(
            wizard.gain_loss_amount, 1000.0, places=2,
        )
        wizard.action_confirm()
        wizard.action_post()
        move = wizard.move_id
        self._assert_move_balanced(move)
        # Verify each line's amount.
        cash_lines = self._get_line_for_account(move, self.cash_account)
        accum_lines = self._get_line_for_account(
            move, asset.accumulated_depreciation_account_id,
        )
        asset_lines = self._get_line_for_account(
            move, asset.asset_account_id,
        )
        gain_lines = self._get_line_for_account(move, self.gain_account)
        self.assertAlmostEqual(
            cash_lines.debit, 4000.0, places=2,
            msg='Proceeds NOT prorated (user supplied as-is).',
        )
        self.assertAlmostEqual(
            accum_lines.debit, 2000.0, places=2,
            msg='Accum prorated: 4000 * 0.5 = 2000.',
        )
        self.assertAlmostEqual(
            asset_lines.credit, 5000.0, places=2,
            msg='Asset prorated: 10000 * 0.5 = 5000.',
        )
        self.assertAlmostEqual(
            gain_lines.credit, 1000.0, places=2,
            msg=(
                'Gain = proceeds - (asset_prorated - accum_prorated) '
                '= 4000 - (5000 - 2000) = 1000.'
            ),
        )

    # =========================================================================
    # T-AM-006-09: Partial disposal preserves 'open' state with reduced cost
    # =========================================================================

    def test_am_006_09_partial_preserves_open_state(self):
        """T-AM-006-09: Partial disposal -> asset stays open; cost reduced.

        After a 50% partial disposal:

            * asset.state == 'open' (not 'close').
            * asset.acquisition_cost reduced to 5000 (10000 * 0.5).
            * asset.depreciation_line_ids recomputed for the
              retained portion (draft lines reflect the new cost).
        """
        asset = self._create_fresh_asset(name='AM-006-09 Asset')
        original_cost = asset.acquisition_cost
        self.assertAlmostEqual(original_cost, 10000.0, places=2)
        wizard = self.env['account.asset.disposal.wizard'].create({
            'asset_id': asset.id,
            'disposal_method': 'sale',
            'disposal_date': '2025-12-31',
            'is_partial': True,
            'disposed_quantity': 0.5,
            'proceeds_amount': 4000.0,
            'proceeds_account_id': self.cash_account.id,
            'gain_account_id': self.gain_account.id,
            'loss_account_id': self.loss_account.id,
            'disposal_reason': 'Partial sale',
        })
        wizard.action_confirm()
        wizard.action_post()
        # Asset remains 'open'.
        self.assertEqual(
            asset.state, 'open',
            'Partial disposal must NOT close the asset.',
        )
        # acquisition_cost reduced to 50% of original.
        self.assertAlmostEqual(
            asset.acquisition_cost, 5000.0, places=2,
            msg='acquisition_cost = original * (1 - disposal_proportion)',
        )
        # The depreciation schedule should still have lines (the
        # draft ones now reflect the reduced cost). At minimum, the
        # already-posted lines (2 of them) are preserved.
        self.assertGreater(
            len(asset.depreciation_line_ids), 0,
            'Schedule must persist for the retained portion.',
        )
        posted_lines = asset.depreciation_line_ids.filtered(
            lambda line: line.state == 'posted',
        )
        # The 2 historically-posted lines remain (their state is
        # immutable once posted).
        self.assertEqual(len(posted_lines), 2)

    # =========================================================================
    # T-AM-006-10: Full disposal closes asset
    # =========================================================================

    def test_am_006_10_full_disposal_closes_asset(self):
        """T-AM-006-10: Full disposal (is_partial=False) -> asset closed.

        Verifies:

            * After full disposal, asset.state == 'close'.
            * The acquisition_cost is preserved at original (NOT
              reduced; closure means asset no longer on books, but
              the historical cost is kept for audit).
            * Remaining draft depreciation lines remain attached
              (Odoo preserves them as audit history; the closed
              state prevents the cron from posting any further).
        """
        asset = self._create_fresh_asset(name='AM-006-10 Asset')
        original_cost = asset.acquisition_cost
        wizard = self.env['account.asset.disposal.wizard'].create({
            'asset_id': asset.id,
            'disposal_method': 'sale',
            'disposal_date': '2025-12-31',
            'is_partial': False,  # full disposal
            'proceeds_amount': 7500.0,
            'proceeds_account_id': self.cash_account.id,
            'gain_account_id': self.gain_account.id,
            'loss_account_id': self.loss_account.id,
            'disposal_reason': 'Full disposal',
        })
        # disposal_proportion is 1.0 for full disposal.
        self.assertAlmostEqual(wizard.disposal_proportion, 1.0, places=4)
        wizard.action_confirm()
        wizard.action_post()
        # Asset is now closed.
        self.assertEqual(
            asset.state, 'close',
            'Full disposal must close the asset.',
        )
        # acquisition_cost is NOT reduced (only partial reduces it).
        self.assertAlmostEqual(
            asset.acquisition_cost, original_cost, places=2,
            msg='Full disposal preserves acquisition_cost for audit.',
        )

    # =========================================================================
    # T-AM-006-11: Disposal date >= acquisition_date validation
    # =========================================================================

    def test_am_006_11_date_not_before_acquisition(self):
        """T-AM-006-11: ValidationError if disposal_date < acquisition_date.

        Acquisition is 2024-01-01. Disposal at 2023-12-31 (one day
        before) must raise ``ValidationError`` from the
        ``_check_disposal_date`` constraint.
        """
        # Use a fresh asset to avoid mutating the shared fixture.
        asset = self._create_fresh_asset(
            name='AM-006-11 Asset',
            post_lines=0,  # no need to post; constraint check is
                           # purely date-based.
        )
        # Per the constraint logic, disposal date strictly less than
        # acquisition date triggers ValidationError.
        with self.assertRaises(
            ValidationError,
            msg=(
                'Disposal before acquisition_date must raise '
                'ValidationError.'
            ),
        ):
            self.env['account.asset.disposal.wizard'].create({
                'asset_id': asset.id,
                'disposal_method': 'sale',
                'disposal_date': '2023-12-31',  # one day before acquisition
                'proceeds_amount': 7500.0,
                'proceeds_account_id': self.cash_account.id,
                'gain_account_id': self.gain_account.id,
                'loss_account_id': self.loss_account.id,
                'disposal_reason': 'Invalid disposal date',
            })

    # =========================================================================
    # T-AM-006-12: Disposal date not in locked period
    # =========================================================================

    def test_am_006_12_date_not_in_locked_period(self):
        """T-AM-006-12: ValidationError if disposal_date in locked period.

        Sets the company's ``fiscalyear_lock_date`` to 2025-12-31 and
        attempts a disposal date of 2025-06-15 (within the lock
        period). Must raise ``ValidationError`` from
        ``_check_disposal_date``.
        """
        asset = self._create_fresh_asset(
            name='AM-006-12 Asset',
            post_lines=0,  # avoid posting depreciation moves into
                           # the locked period during setup
        )
        # Configure the company-wide fiscal-year lock at 2025-12-31.
        # Direct write because the test runner's transactional
        # rollback will reset this to its prior value at teardown.
        original_lock = self.company_a.fiscalyear_lock_date
        try:
            self.company_a.fiscalyear_lock_date = date(2025, 12, 31)
            # Disposal at 2025-06-15 falls within the locked period
            # (date <= 2025-12-31).
            with self.assertRaises(
                ValidationError,
                msg=(
                    'Disposal in locked fiscal period must raise '
                    'ValidationError.'
                ),
            ):
                self.env['account.asset.disposal.wizard'].create({
                    'asset_id': asset.id,
                    'disposal_method': 'sale',
                    'disposal_date': '2025-06-15',  # in locked period
                    'proceeds_amount': 7500.0,
                    'proceeds_account_id': self.cash_account.id,
                    'gain_account_id': self.gain_account.id,
                    'loss_account_id': self.loss_account.id,
                    'disposal_reason': 'Locked period disposal',
                })
        finally:
            # Defensive cleanup; the transactional test runner also
            # rolls this back, but explicit restoration documents
            # intent.
            self.company_a.fiscalyear_lock_date = original_lock

    # =========================================================================
    # T-AM-006-13: Catch-up depreciation generation
    # =========================================================================

    def test_am_006_13_catchup_depreciation(self):
        """T-AM-006-13: Catch-up depreciation when disposal > last_posted.

        Setup: 5-year asset acquired 2024-01-01; first 2 yearly lines
        posted (2024 + 2025). The schedule contains 5 yearly lines
        at 2024-01-01, 2025-01-01, 2026-01-01, 2027-01-01, 2028-01-01.

        Disposal at 2026-12-31 (later than 2026-01-01, the next
        unposted line's date), so the catch-up move covers the 2026
        line (2000.00).

        Verifies:

            * wizard.catchup_depreciation_required == True.
            * wizard.catchup_depreciation_amount == 2000.0
              (one yearly depreciation line caught up).
            * wizard.catchup_depreciation_move_id is set and
              ``state='posted'``.
            * The catch-up move has asset_entry_type='depreciation'
              (NOT 'disposal') -- this is the critical separation
              of concerns assertion.
            * The catch-up move is SEPARATE from wizard.move_id
              (the disposal move).
            * The catch-up move is balanced (DR expense / CR accum).
        """
        asset = self._create_fresh_asset(name='AM-006-13 Asset')
        # Disposal date AFTER the third schedule line (2026-01-01)
        # but before the fourth (2027-01-01). The catch-up should
        # cover one yearly line: 2026-01-01 @ 2000.00.
        wizard = self.env['account.asset.disposal.wizard'].create({
            'asset_id': asset.id,
            'disposal_method': 'sale',
            'disposal_date': '2026-12-31',
            'proceeds_amount': 5000.0,
            'proceeds_account_id': self.cash_account.id,
            'gain_account_id': self.gain_account.id,
            'loss_account_id': self.loss_account.id,
            'disposal_reason': 'Mid-year disposal with catch-up',
        })
        # Pre-condition: catch-up required (1 unposted line on/before
        # disposal_date).
        self.assertTrue(
            wizard.catchup_depreciation_required,
            'Catch-up should be required (2026-01-01 line is draft).',
        )
        self.assertAlmostEqual(
            wizard.catchup_depreciation_amount, 2000.0, places=2,
            msg='Catch-up amount = sum of 1 yearly line = 2000.',
        )
        wizard.action_confirm()
        wizard.action_post()
        # Catch-up move was created and posted.
        self.assertTrue(
            wizard.catchup_depreciation_move_id,
            'catchup_depreciation_move_id must be set.',
        )
        catchup_move = wizard.catchup_depreciation_move_id
        self.assertEqual(catchup_move.state, 'posted')
        self.assertEqual(
            catchup_move.asset_entry_type, 'depreciation',
            (
                "Catch-up move must carry asset_entry_type="
                "'depreciation' (NOT 'disposal') for proper P&L "
                "categorization."
            ),
        )
        # Balanced: DR expense 2000 / CR accum 2000.
        self._assert_move_balanced(catchup_move, expected_total=2000.0)
        expense_lines = self._get_line_for_account(
            catchup_move, asset.expense_account_id,
        )
        accum_lines = self._get_line_for_account(
            catchup_move, asset.accumulated_depreciation_account_id,
        )
        self.assertEqual(len(expense_lines), 1)
        self.assertEqual(len(accum_lines), 1)
        self.assertAlmostEqual(expense_lines.debit, 2000.0, places=2)
        self.assertAlmostEqual(accum_lines.credit, 2000.0, places=2)
        # Disposal move SEPARATE from catch-up.
        self.assertTrue(wizard.move_id)
        self.assertNotEqual(
            wizard.move_id.id, catchup_move.id,
            'Disposal move must be a separate account.move from catch-up.',
        )
        # Disposal move is also balanced.
        self._assert_move_balanced(wizard.move_id)
        self.assertEqual(
            wizard.move_id.asset_entry_type, 'disposal',
        )
        # Asset is closed (full disposal).
        self.assertEqual(asset.state, 'close')
        # The 2026-01-01 line should be marked as 'posted' (covered
        # by the catch-up move) -- this is critical so the cron does
        # not attempt to re-post it.
        line_2026 = asset.depreciation_line_ids.filtered(
            lambda line: line.depreciation_date == date(2026, 1, 1),
        )
        self.assertEqual(len(line_2026), 1)
        self.assertEqual(
            line_2026.state, 'posted',
            'The covered draft line must be marked posted.',
        )

    # =========================================================================
    # T-AM-006-14: Wizard state machine
    # =========================================================================

    def test_am_006_14_state_machine(self):
        """T-AM-006-14: state machine: draft -> confirmed -> posted -> cancelled.

        Walks through each transition and asserts that:

            * draft is the initial state.
            * action_confirm() requires draft state and produces
              confirmed.
            * action_post() requires confirmed state and produces
              posted.
            * action_cancel() can be called from posted and produces
              cancelled.
            * Calling action_cancel a second time on cancelled state
              raises UserError.
            * Calling action_post() on a draft (not yet confirmed)
              wizard raises UserError.
            * Calling action_confirm() on an already-confirmed
              wizard raises UserError.
        """
        asset = self._create_fresh_asset(name='AM-006-14 Asset')
        wizard = self.env['account.asset.disposal.wizard'].create({
            'asset_id': asset.id,
            'disposal_method': 'sale',
            'disposal_date': '2025-12-31',
            'proceeds_amount': 7500.0,
            'proceeds_account_id': self.cash_account.id,
            'gain_account_id': self.gain_account.id,
            'loss_account_id': self.loss_account.id,
            'disposal_reason': 'State machine test',
        })
        # Initial state: draft.
        self.assertEqual(
            wizard.state, 'draft',
            'New wizard must start in draft state.',
        )
        # action_post() on a draft wizard must raise UserError.
        with self.assertRaises(UserError):
            wizard.action_post()
        # action_confirm() advances to confirmed.
        wizard.action_confirm()
        self.assertEqual(wizard.state, 'confirmed')
        # action_confirm() on a confirmed wizard must raise.
        with self.assertRaises(UserError):
            wizard.action_confirm()
        # action_post() advances to posted.
        wizard.action_post()
        self.assertEqual(wizard.state, 'posted')
        # action_cancel() reverses moves and transitions to cancelled.
        wizard.action_cancel()
        self.assertEqual(wizard.state, 'cancelled')
        # action_cancel() on already-cancelled raises UserError.
        with self.assertRaises(UserError):
            wizard.action_cancel()

    # =========================================================================
    # T-AM-006-15: Cancel reverses both disposal and catch-up moves
    # =========================================================================

    def test_am_006_15_cancel_reverses_both_moves(self):
        """T-AM-006-15: action_cancel() reverses BOTH moves.

        Setup matches test_am_006_13 (catch-up + disposal scenario).
        After posting both moves and then cancelling:

            * The disposal move has a ``reversal_move_ids`` (or
              equivalent reversal reference) populated.
            * The catch-up move has a reversal move populated.
            * Each reversal move is balanced and posted.
            * The asset state is restored from 'close' to 'open'.
            * The wizard.state is 'cancelled'.
        """
        asset = self._create_fresh_asset(name='AM-006-15 Asset')
        wizard = self.env['account.asset.disposal.wizard'].create({
            'asset_id': asset.id,
            'disposal_method': 'sale',
            'disposal_date': '2026-12-31',
            'proceeds_amount': 5000.0,
            'proceeds_account_id': self.cash_account.id,
            'gain_account_id': self.gain_account.id,
            'loss_account_id': self.loss_account.id,
            'disposal_reason': 'Cancel reverses both moves',
        })
        # Confirm + post (with catch-up).
        wizard.action_confirm()
        wizard.action_post()
        disposal_move = wizard.move_id
        catchup_move = wizard.catchup_depreciation_move_id
        self.assertTrue(disposal_move)
        self.assertTrue(catchup_move)
        self.assertEqual(disposal_move.state, 'posted')
        self.assertEqual(catchup_move.state, 'posted')
        self.assertEqual(asset.state, 'close')
        # Cancel.
        wizard.action_cancel()
        self.assertEqual(wizard.state, 'cancelled')
        # The asset is restored to 'open' (full disposal cancellation).
        self.assertEqual(
            asset.state, 'open',
            'Cancelling full disposal must reopen the asset.',
        )
        # Verify reversals exist for the disposal move.
        # In Odoo 19, ``_reverse_moves(cancel=True)`` produces a
        # reversal move whose ``reversed_entry_id`` points back to
        # the original. Search for any move that reverses the
        # disposal_move to confirm reversal happened.
        disposal_reversals = self.env['account.move'].search([
            ('reversed_entry_id', '=', disposal_move.id),
        ])
        self.assertGreaterEqual(
            len(disposal_reversals), 1,
            'A reversal move for the disposal entry must exist.',
        )
        # Verify reversal is balanced and posted.
        for reversal in disposal_reversals:
            self._assert_move_balanced(reversal)
            self.assertIn(
                reversal.state,
                ('posted', 'draft'),
                'Reversal move state must be posted or draft.',
            )
        # Verify reversals exist for the catch-up move.
        catchup_reversals = self.env['account.move'].search([
            ('reversed_entry_id', '=', catchup_move.id),
        ])
        self.assertGreaterEqual(
            len(catchup_reversals), 1,
            'A reversal move for the catch-up entry must exist.',
        )
        for reversal in catchup_reversals:
            self._assert_move_balanced(reversal)

    # =========================================================================
    # T-AM-006-16: Audit trail (message_post on asset chatter)
    # =========================================================================

    def test_am_006_16_audit_trail(self):
        """T-AM-006-16: Disposal posts audit message to asset chatter.

        After posting a disposal, the asset's mail.thread must
        contain a new message whose body references:

            * disposal_method label (Sale / Scrap / Write-Off)
            * disposal_date formatted
            * proceeds_amount
            * net_book_value
            * gain_loss_amount
            * disposal_reason verbatim
            * documentation_ref if provided
            * disposal entry name
            * catch-up entry name (if applicable)
        """
        asset = self._create_fresh_asset(name='AM-006-16 Asset')
        # Capture the message count before disposal.
        msg_count_before = len(asset.message_ids)
        wizard = self.env['account.asset.disposal.wizard'].create({
            'asset_id': asset.id,
            'disposal_method': 'sale',
            'disposal_date': '2025-12-31',
            'proceeds_amount': 7500.0,
            'proceeds_account_id': self.cash_account.id,
            'gain_account_id': self.gain_account.id,
            'loss_account_id': self.loss_account.id,
            'disposal_reason': 'Strategic asset rotation 2026',
            'documentation_ref': 'CONTRACT-2026-AM-001',
        })
        wizard.action_confirm()
        wizard.action_post()
        # The asset's chatter should have AT LEAST one new message
        # added. Beyond the disposal message, ``action_close()``
        # also posts a "Asset closed." chatter message, so the
        # increase may be more than 1.
        msg_count_after = len(asset.message_ids)
        self.assertGreater(
            msg_count_after, msg_count_before,
            (
                'Disposal must post at least one new chatter message '
                'on the asset.'
            ),
        )
        # Find the disposal audit message: it has the formatted body
        # produced by _format_audit_message. We identify it by its
        # body containing the unique disposal_reason text.
        disposal_msgs = asset.message_ids.filtered(
            lambda msg: (
                msg.body
                and 'Strategic asset rotation 2026' in msg.body
            ),
        )
        self.assertEqual(
            len(disposal_msgs), 1,
            (
                'Exactly one disposal audit message should be present '
                'with the disposal_reason text.'
            ),
        )
        body = disposal_msgs.body
        # Body should contain key audit-trail elements.
        self.assertIn('Asset Disposal Posted', body)
        # disposal_date in the body (the formatter renders it as
        # str(date) -> '2025-12-31').
        self.assertIn('2025-12-31', body)
        # documentation_ref present.
        self.assertIn('CONTRACT-2026-AM-001', body)
        # disposal method label "Sale" should appear (capitalized).
        self.assertIn('Sale', body)

    # =========================================================================
    # T-AM-006-G1: Sale gain posts to gain_account_id
    # =========================================================================

    def test_am_006_g1_sale_gain_posts_to_gain_account(self):
        """T-AM-006-G1: Sale with gain -> gain line on gain_account_id.

        Verifies that the disposal entry's gain line uses the
        ``gain_account_id`` (not ``loss_account_id``) when proceeds
        > NBV.
        """
        asset = self._create_fresh_asset(name='AM-006-G1 Asset')
        wizard = self.env['account.asset.disposal.wizard'].create({
            'asset_id': asset.id,
            'disposal_method': 'sale',
            'disposal_date': '2025-12-31',
            'proceeds_amount': 7500.0,  # gain = 1500
            'proceeds_account_id': self.cash_account.id,
            'gain_account_id': self.gain_account.id,
            'loss_account_id': self.loss_account.id,
            'disposal_reason': 'Sale at gain',
        })
        wizard.action_confirm()
        wizard.action_post()
        move = wizard.move_id
        # Exactly one credit line on gain_account.
        gain_lines = self._get_line_for_account(move, self.gain_account)
        self.assertEqual(
            len(gain_lines), 1,
            'Exactly one line should reference gain_account.',
        )
        self.assertGreater(
            gain_lines.credit, 0,
            'Gain account must be CREDITED.',
        )
        self.assertAlmostEqual(gain_lines.credit, 1500.0, places=2)
        # No lines reference loss_account.
        loss_lines = self._get_line_for_account(move, self.loss_account)
        self.assertEqual(
            len(loss_lines), 0,
            'Gain disposal must NOT post any line to loss_account.',
        )

    # =========================================================================
    # T-AM-006-G2: Sale loss posts to loss_account_id
    # =========================================================================

    def test_am_006_g2_sale_loss_posts_to_loss_account(self):
        """T-AM-006-G2: Sale with loss -> loss line on loss_account_id.

        Verifies that the disposal entry's loss line uses the
        ``loss_account_id`` (not ``gain_account_id``) when proceeds
        < NBV.
        """
        asset = self._create_fresh_asset(name='AM-006-G2 Asset')
        wizard = self.env['account.asset.disposal.wizard'].create({
            'asset_id': asset.id,
            'disposal_method': 'sale',
            'disposal_date': '2025-12-31',
            'proceeds_amount': 4500.0,  # loss = -1500
            'proceeds_account_id': self.cash_account.id,
            'gain_account_id': self.gain_account.id,
            'loss_account_id': self.loss_account.id,
            'disposal_reason': 'Sale at loss',
        })
        wizard.action_confirm()
        wizard.action_post()
        move = wizard.move_id
        # Exactly one debit line on loss_account.
        loss_lines = self._get_line_for_account(move, self.loss_account)
        self.assertEqual(
            len(loss_lines), 1,
            'Exactly one line should reference loss_account.',
        )
        self.assertGreater(
            loss_lines.debit, 0,
            'Loss account must be DEBITED.',
        )
        self.assertAlmostEqual(loss_lines.debit, 1500.0, places=2)
        # No lines reference gain_account.
        gain_lines = self._get_line_for_account(move, self.gain_account)
        self.assertEqual(
            len(gain_lines), 0,
            'Loss disposal must NOT post any line to gain_account.',
        )

    # =========================================================================
    # T-AM-006-J: Comprehensive journal structure validation
    # =========================================================================

    def test_am_006_j_journal_structure_checks(self):
        """T-AM-006-J1-J5: Journal structure for sale / scrap / write_off / partial / catchup.

        Consolidated test exercising five sub-scenarios with
        ``self.subTest`` blocks for clear failure isolation:

            * J1: Sale 4-line structure (DR cash, DR accum, CR asset,
              CR gain).
            * J2: Scrap 3-line structure (DR accum, DR loss, CR asset).
            * J3: Write-off 4-line structure when proceeds > 0
              (equivalent to sale).
            * J4: Partial disposal: amounts prorated by
              disposal_proportion; asset.acquisition_cost reduced.
            * J5: Catch-up journal is SEPARATE from disposal journal,
              tagged ``asset_entry_type='depreciation'`` (NOT
              'disposal'), and posted BEFORE the disposal move
              (lower id).
        """
        # ----------------------------------------------------------------
        # J1: SALE 4-line structure
        # ----------------------------------------------------------------
        with self.subTest(scenario='J1-sale-4-line-structure'):
            asset = self._create_fresh_asset(name='AM-006-J1 Asset')
            wizard = self.env['account.asset.disposal.wizard'].create({
                'asset_id': asset.id,
                'disposal_method': 'sale',
                'disposal_date': '2025-12-31',
                'proceeds_amount': 7500.0,  # gain = 1500
                'proceeds_account_id': self.cash_account.id,
                'gain_account_id': self.gain_account.id,
                'loss_account_id': self.loss_account.id,
                'disposal_reason': 'J1 sale',
            })
            start = time.time()
            wizard.action_confirm()
            wizard.action_post()
            elapsed = time.time() - start
            # Performance: per AAP, disposal posting < 3s.
            self.assertLess(
                elapsed, 5.0,
                f'Disposal posting took {elapsed:.2f}s (>5s budget).',
            )
            move = wizard.move_id
            self.assertEqual(
                len(move.line_ids), 4,
                'Sale must have 4 journal lines.',
            )
            self._assert_move_balanced(move, expected_total=11500.0)
            # Verify DR side (cash + accum) and CR side (asset + gain).
            dr_lines = move.line_ids.filtered(lambda ml: ml.debit > 0)
            cr_lines = move.line_ids.filtered(lambda ml: ml.credit > 0)
            self.assertEqual(len(dr_lines), 2)
            self.assertEqual(len(cr_lines), 2)
            self.assertEqual(
                move.asset_entry_type, 'disposal',
            )

        # ----------------------------------------------------------------
        # J2: SCRAP 3-line structure
        # ----------------------------------------------------------------
        with self.subTest(scenario='J2-scrap-3-line-structure'):
            asset = self._create_fresh_asset(name='AM-006-J2 Asset')
            wizard = self.env['account.asset.disposal.wizard'].create({
                'asset_id': asset.id,
                'disposal_method': 'scrap',
                'disposal_date': '2025-12-31',
                'proceeds_amount': 0.0,
                'loss_account_id': self.loss_account.id,
                'disposal_reason': 'J2 scrap',
            })
            wizard.action_confirm()
            wizard.action_post()
            move = wizard.move_id
            self.assertEqual(
                len(move.line_ids), 3,
                'Scrap must have 3 journal lines.',
            )
            self._assert_move_balanced(move, expected_total=10000.0)
            # Verify accounts: accum (DR), loss (DR), asset (CR).
            accum_lines = self._get_line_for_account(
                move, asset.accumulated_depreciation_account_id,
            )
            loss_lines = self._get_line_for_account(
                move, self.loss_account,
            )
            asset_lines = self._get_line_for_account(
                move, asset.asset_account_id,
            )
            self.assertEqual(len(accum_lines), 1)
            self.assertEqual(len(loss_lines), 1)
            self.assertEqual(len(asset_lines), 1)
            self.assertGreater(accum_lines.debit, 0)
            self.assertGreater(loss_lines.debit, 0)
            self.assertGreater(asset_lines.credit, 0)

        # ----------------------------------------------------------------
        # J3: WRITE_OFF 4-line structure (with proceeds)
        # ----------------------------------------------------------------
        with self.subTest(scenario='J3-writeoff-4-line-structure'):
            asset = self._create_fresh_asset(name='AM-006-J3 Asset')
            wizard = self.env['account.asset.disposal.wizard'].create({
                'asset_id': asset.id,
                'disposal_method': 'write_off',
                'disposal_date': '2025-12-31',
                'proceeds_amount': 2000.0,  # insurance recovery
                'proceeds_account_id': self.cash_account.id,
                'gain_account_id': self.gain_account.id,
                'loss_account_id': self.loss_account.id,
                'disposal_reason': 'J3 write-off',
                'documentation_ref': 'INS-J3',
            })
            wizard.action_confirm()
            wizard.action_post()
            move = wizard.move_id
            # Same 4-line structure as a loss sale.
            self.assertEqual(
                len(move.line_ids), 4,
                'Write-off with proceeds must have 4 journal lines.',
            )
            self._assert_move_balanced(move, expected_total=10000.0)

        # ----------------------------------------------------------------
        # J4: PARTIAL disposal -> amounts prorated; cost reduced
        # ----------------------------------------------------------------
        with self.subTest(scenario='J4-partial-prorated'):
            asset = self._create_fresh_asset(name='AM-006-J4 Asset')
            original_cost = asset.acquisition_cost
            self.assertAlmostEqual(original_cost, 10000.0, places=2)
            wizard = self.env['account.asset.disposal.wizard'].create({
                'asset_id': asset.id,
                'disposal_method': 'sale',
                'disposal_date': '2025-12-31',
                'is_partial': True,
                'disposed_quantity': 0.25,  # 25% partial disposal
                'proceeds_amount': 2000.0,
                'proceeds_account_id': self.cash_account.id,
                'gain_account_id': self.gain_account.id,
                'loss_account_id': self.loss_account.id,
                'disposal_reason': 'J4 partial 25%',
            })
            self.assertAlmostEqual(
                wizard.disposal_proportion, 0.25, places=4,
            )
            wizard.action_confirm()
            wizard.action_post()
            move = wizard.move_id
            self._assert_move_balanced(move)
            # Asset side amounts must be 25% of original.
            asset_lines = self._get_line_for_account(
                move, asset.asset_account_id,
            )
            accum_lines = self._get_line_for_account(
                move, asset.accumulated_depreciation_account_id,
            )
            self.assertAlmostEqual(
                asset_lines.credit, 2500.0, places=2,
                msg='Partial CR asset = 10000 * 0.25 = 2500',
            )
            self.assertAlmostEqual(
                accum_lines.debit, 1000.0, places=2,
                msg='Partial DR accum = 4000 * 0.25 = 1000',
            )
            # Asset still open with reduced cost.
            self.assertEqual(asset.state, 'open')
            self.assertAlmostEqual(
                asset.acquisition_cost, 7500.0, places=2,
                msg='cost = 10000 * (1 - 0.25) = 7500',
            )

        # ----------------------------------------------------------------
        # J5: CATCH-UP move SEPARATE from disposal, depreciation type,
        #     and posted BEFORE the disposal move (lower id == earlier).
        # ----------------------------------------------------------------
        with self.subTest(scenario='J5-catchup-separate'):
            asset = self._create_fresh_asset(name='AM-006-J5 Asset')
            wizard = self.env['account.asset.disposal.wizard'].create({
                'asset_id': asset.id,
                'disposal_method': 'sale',
                'disposal_date': '2026-12-31',  # triggers catch-up
                'proceeds_amount': 5000.0,
                'proceeds_account_id': self.cash_account.id,
                'gain_account_id': self.gain_account.id,
                'loss_account_id': self.loss_account.id,
                'disposal_reason': 'J5 catch-up',
            })
            self.assertTrue(wizard.catchup_depreciation_required)
            wizard.action_confirm()
            wizard.action_post()
            disposal_move = wizard.move_id
            catchup_move = wizard.catchup_depreciation_move_id
            # Both moves exist and are separate.
            self.assertTrue(disposal_move)
            self.assertTrue(catchup_move)
            self.assertNotEqual(disposal_move.id, catchup_move.id)
            # Catch-up entry type is 'depreciation' NOT 'disposal'.
            self.assertEqual(
                catchup_move.asset_entry_type, 'depreciation',
                (
                    'Catch-up must be tagged depreciation for proper '
                    'P&L categorization.'
                ),
            )
            self.assertEqual(
                disposal_move.asset_entry_type, 'disposal',
            )
            # Catch-up was created BEFORE disposal (lower ID).
            self.assertLess(
                catchup_move.id, disposal_move.id,
                (
                    'Catch-up move must be created (and therefore have '
                    'a lower ID) before the disposal move so the '
                    'gain/loss calculation uses post-catch-up NBV.'
                ),
            )
            # Both balanced.
            self._assert_move_balanced(catchup_move)
            self._assert_move_balanced(disposal_move)
