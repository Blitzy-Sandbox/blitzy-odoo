# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Post-install hooks for ``account_bank_reconciliation_ce``.

This module isolates install/upgrade hooks so the package ``__init__.py``
remains a thin re-export surface (matching OCA/Odoo community conventions
and satisfying ``ruff`` rule RUF067).

The manifest references :func:`post_init_hook` by name; Odoo's module loader
(`odoo.modules.loading` -> ``getattr(py_module, post_init)``) resolves it
against the package's top-level ``__init__`` namespace, so the hook must be
re-exported there.
"""


def post_init_hook(env):
    """Ensure every user granted the Accounting / Manager or Accounting / User
    role (or this module's Bank Reconciliation groups) also belongs to the
    base Internal User group (``base.group_user``).

    Rationale
    ---------
    ``ir.attachment`` write access — needed to upload bank-statement files
    and any other binary field on the reconciliation wizards — is gated on
    membership of ``base.group_user``.  If an administrator installs this
    module on a pre-existing database that has non-internal users in the
    accounting-manager role (e.g. a portal user who was given accounting
    permissions), file uploads would raise :class:`AccessError`.

    This hook runs once on module install **and** every subsequent upgrade
    because the module's manifest wires it to the
    ``post_init_hook`` entry point.  Re-running is safe — ``Command.link``
    on ``groups_id`` is idempotent (the ORM deduplicates existing links).
    """
    # Collect the full set of groups whose members must also be in
    # ``base.group_user``.
    group_xmlids = (
        "base.group_user",
        "account.group_account_user",
        "account.group_account_manager",
        "account_bank_reconciliation_ce.group_bank_reconciliation_user",
        "account_bank_reconciliation_ce.group_bank_reconciliation_manager",
    )
    try:
        internal_group = env.ref("base.group_user")
    except ValueError:
        # ``base`` is always present, but be defensive in case of upgrade
        # scenarios where the XML ID has been reseeded.
        return

    # Union of all users in any of the accounting / reconciliation groups.
    users = env["res.users"].browse()
    for xmlid in group_xmlids[1:]:
        group = env.ref(xmlid, raise_if_not_found=False)
        if group:
            users |= group.user_ids

    # Add the internal user group to every such user (idempotent).
    missing_users = users.filtered(
        lambda u: internal_group not in u.group_ids,
    )
    if missing_users:
        missing_users.write({
            "group_ids": [(4, internal_group.id, False)],
        })
