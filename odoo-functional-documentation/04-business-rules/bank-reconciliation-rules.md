# Bank Reconciliation Business Rules

## Overview

This document describes the business rules that govern how Odoo processes bank reconciliation operations. These rules ensure data integrity, enforce proper validation, and control how the system matches bank transactions with accounting entries.

**Related Workflow:** [Bank Reconciliation User Flow](../02-user-flows/14-bank-reconciliation/flow-document.md)

**Primary Models:**
- `account.reconcile.model` - Reconciliation model (matching rule definitions)
- `account.reconcile.model.line` - Reconciliation model lines (specific account/amount entries)

---

## 1. Validation Logic

Odoo enforces the following validation rules to ensure data integrity in reconciliation models. These rules prevent users from saving invalid configurations.

### 1.1 Amount Validation

**Constraint Name:** `_validate_amount`

**When Applied:** Whenever a reconciliation model line's amount string is saved or modified.

**Business Rule:** The amount entered must be valid based on the selected amount type. This ensures the system can properly calculate write-off amounts during reconciliation.

| Amount Type | Validation Rule | Error Message |
|-------------|-----------------|---------------|
| **Fixed** | Amount cannot be zero | "The amount is not a number" |
| **Percentage of balance** | Percentage cannot be zero | "Balance percentage can't be 0" |
| **Percentage of statement line** | Percentage cannot be zero | "Statement line percentage can't be 0" |
| **From label** (regex) | Must be a valid regular expression pattern | "The regex is not valid" |

**What This Means for Users:**

- When using a **fixed amount**, you must enter an actual monetary value (positive for credit, negative for debit). Zero is not allowed because it would create meaningless write-off entries.
  
- When using **percentage**, you must enter a value between 1 and 100. Zero percent would result in no amount being calculated.

- When using **From label** (regex extraction), the pattern you enter must be syntactically correct. The system will use this pattern to extract amounts from transaction descriptions.

**Example Scenario:**

A company wants to automatically categorize bank fees. They create a reconciliation model with:
- Amount Type: "Fixed"
- Amount: "25.00" (the typical bank fee)

If the user accidentally enters "0" or leaves it blank, the system will reject the entry with an error message.

*Source: `addons/account/models/account_reconcile_model.py:64-77`*

---

### 1.2 Label Matching Regex Validation

**Constraint Name:** `_check_match_label_param`

**When Applied:** Whenever the match label type is set to "Match Regex" and the pattern parameter is saved.

**Business Rule:** When using regular expression matching for transaction labels, the regex pattern must be syntactically valid. Invalid patterns would cause errors during reconciliation processing.

| Condition | Validation | Error Message |
|-----------|------------|---------------|
| Match Label = "Match Regex" | Pattern must compile without errors | "The regex is not valid" |

**What This Means for Users:**

Regular expressions (regex) are special text patterns used to match transaction descriptions. For example:
- `Bank fee.*` matches any label starting with "Bank fee"
- `INV-[0-9]+` matches invoice numbers like "INV-12345"

If you enter an invalid pattern (like an unclosed bracket or invalid syntax), the system will prevent you from saving until the pattern is corrected.

**Common Regex Mistakes:**
- Unclosed parentheses: `(payment` instead of `(payment)`
- Invalid escape sequences: `\k` (undefined in Python regex)
- Unclosed character classes: `[0-9` instead of `[0-9]`

*Source: `addons/account/models/account_reconcile_model.py:138-145`*

---

## 2. Computation Rules

The following fields are automatically calculated by the system based on other field values. Users cannot directly edit these fields.

### 2.1 Float Amount Computation

**Computed Field:** `amount` (Float)

**Dependencies:** `amount_string`

**Computation Logic:** Converts the user-entered amount string into a numeric float value that the system uses for calculations.

```
For each reconciliation model line:
    TRY:
        amount = convert amount_string to float
    IF conversion fails:
        amount = 0
```

**What This Means for Users:**

The amount you enter in text form (like "100" or "25.50") is automatically converted to a number the system can use in calculations. If the text cannot be converted (for example, "abc"), the system sets the amount to zero.

This computed field works alongside the validation rules. While the conversion may succeed for "0", the validation rules will catch invalid zero amounts for fixed and percentage types.

*Source: `addons/account/models/account_reconcile_model.py:56-62`*

---

### 2.2 Proposal Eligibility Computation

**Computed Field:** `can_be_proposed` (Boolean)

**Dependencies:** `mapped_partner_id`, `match_label`, `match_amount`, `match_partner_ids`, `trigger`

**Computation Logic:** Determines whether the reconciliation model can be suggested to users during manual reconciliation. A model can be proposed when:

1. It is NOT already mapped to a specific partner (partner mapping takes precedence), AND
2. At least ONE of the following conditions is true:
   - The model has label matching criteria configured
   - The model has amount matching criteria configured
   - The model is restricted to specific partners
   - The model is set to auto-reconcile (trigger = 'auto_reconcile')

```
can_be_proposed = (
    mapped_partner_id is NOT set
    AND (
        match_label is set
        OR match_amount is set
        OR match_partner_ids has entries
        OR trigger = 'auto_reconcile'
    )
)
```

**What This Means for Users:**

When you're reconciling a bank transaction, Odoo will suggest reconciliation models that might apply. This computation determines which models appear in the suggestions:

- **Partner-mapped models** are automatically applied when the partner is detected, so they don't need to be "proposed"
- **Matching models** with label or amount criteria are proposed when transactions match those criteria
- **Auto-reconcile models** are proposed because they're intended to automatically match transactions

**Example:**

| Model Name | Match Label | Match Amount | Trigger | Can Be Proposed? |
|------------|-------------|--------------|---------|------------------|
| "Bank Fees" | "fee" | - | Manual | Yes (has label match) |
| "Wire Transfer" | - | Between $100-$500 | Manual | Yes (has amount match) |
| "Generic Rule" | - | - | Manual | No (no matching criteria) |
| "Auto Fee" | - | - | Auto | Yes (auto-reconcile) |

*Source: `addons/account/models/account_reconcile_model.py:147-150`*

---

### 2.3 Partner Mapping Computation

**Computed Field:** `mapped_partner_id` (Many2one to res.partner)

**Dependencies:** `match_label`, `line_ids.partner_id`, `line_ids.account_id`

**Computation Logic:** Identifies when a reconciliation model is specifically designed to map transactions to a partner. This is true when ALL of the following conditions are met:

1. The model has label matching criteria configured
2. The model has exactly ONE line
3. That line has a partner specified
4. That line does NOT have an account specified

```
is_partner_mapping = (
    match_label is set
    AND line_ids has exactly 1 entry
    AND that line has partner_id set
    AND that line does NOT have account_id set
)

IF is_partner_mapping:
    mapped_partner_id = line_ids[0].partner_id
ELSE:
    mapped_partner_id = None
```

**What This Means for Users:**

Partner mapping is a special type of reconciliation model used to automatically identify the business partner (customer or vendor) for unknown transactions based on the transaction label.

**When Partner Mapping is Used:**

Imagine you receive regular payments from "ACME Corp" but the bank shows them as "ACME CORP PAYMENT REF:12345". You can create a partner mapping rule:

- Match Label: "ACME CORP"
- Single line with: Partner = "ACME Corporation" (no account)

When a transaction matches "ACME CORP" in the label, Odoo will automatically suggest ACME Corporation as the partner, helping you reconcile the payment to the correct customer.

**Why Account Must Be Empty:**

If you specify an account, the model becomes a write-off rule (creating accounting entries) rather than a partner identification rule. Partner mapping only identifies the partner; actual reconciliation is done with existing invoices or payments.

*Source: `addons/account/models/account_reconcile_model.py:152-156`*

---

## 3. State and Selection Fields

Reconciliation models use several selection fields to control their behavior. These define how and when the model is applied.

### 3.1 Amount Type

**Field:** `amount_type` on `account.reconcile.model.line`

**Purpose:** Determines how the write-off amount is calculated for this line.

| Value | Display Name | Description |
|-------|--------------|-------------|
| `fixed` | **Fixed** | Use the exact amount specified |
| `percentage` | **Percentage of balance** | Calculate as percentage of the remaining balance to reconcile |
| `percentage_st_line` | **Percentage of statement line** | Calculate as percentage of the original bank statement line amount |
| `regex` | **From label** | Extract amount from the transaction label using a regex pattern |

**Default Value:** `percentage`

**Practical Examples:**

| Scenario | Amount Type | Amount String | Result |
|----------|-------------|---------------|--------|
| Bank charges $5 fee | Fixed | "5.00" | Always $5.00 |
| Bank charges 0.5% fee | Percentage of statement | "0.5" | 0.5% of transaction amount |
| Rounding adjustment | Percentage of balance | "100" | Full remaining balance |
| Variable fee in description | From label | `(\d+\.\d{2})` | Extracts "15.00" from "FEE: 15.00" |

**Behavior When Changing Amount Type:**

When you change the amount type, the system automatically updates the amount string to a sensible default:
- Percentage types → "100" (100%)
- From label (regex) → `([\d,]+)` (pattern to capture numbers)
- Fixed → Cleared (you must enter the amount)

*Source: `addons/account/models/account_reconcile_model.py:25-34`*

---

### 3.2 Trigger Mode

**Field:** `trigger` on `account.reconcile.model`

**Purpose:** Determines when the reconciliation model is applied.

| Value | Display Name | Description |
|-------|--------------|-------------|
| `manual` | **Manual** | Model is suggested to user but requires manual confirmation |
| `auto_reconcile` | **Automated** | Model is automatically applied when conditions match |

**Default Value:** `manual`

**What This Means for Users:**

- **Manual models** appear as suggestions during reconciliation. You review them and click to apply.
- **Automated models** process matching transactions automatically without user intervention.

**Caution with Automated Models:**

Automated reconciliation should be used carefully. The system will create accounting entries without user review. Best practices:
- Start with manual mode to verify the model works correctly
- Only switch to automated after confirming the matching criteria are precise
- Regularly review automated reconciliations

**Track Changes:** This field has change tracking enabled. When modified, Odoo records who changed it and when.

*Source: `addons/account/models/account_reconcile_model.py:96-97`*

---

### 3.3 Amount Matching Criteria

**Field:** `match_amount` on `account.reconcile.model`

**Purpose:** Restricts when the model applies based on the transaction amount.

| Value | Display Name | Parameters Required | Description |
|-------|--------------|---------------------|-------------|
| `lower` | **Is lower than or equal to** | `match_amount_max` | Transaction ≤ specified amount |
| `greater` | **Is greater than or equal to** | `match_amount_min` | Transaction ≥ specified amount |
| `between` | **Is between** | Both min and max | Transaction is within range |

**Related Fields:**
- `match_amount_min` (Float): Minimum amount threshold
- `match_amount_max` (Float): Maximum amount threshold

**What This Means for Users:**

Amount matching lets you create rules that only apply to transactions within certain value ranges:

| Scenario | Match Amount | Min | Max | Transactions That Match |
|----------|--------------|-----|-----|-------------------------|
| Small purchases | Lower | - | 50 | $10, $25, $50 ✓ / $75 ✗ |
| Large transfers | Greater | 1000 | - | $1500 ✓ / $500 ✗ |
| Typical payroll | Between | 2000 | 5000 | $3500 ✓ / $1000 ✗ |

**Track Changes:** This field has change tracking enabled.

*Source: `addons/account/models/account_reconcile_model.py:116-123`*

---

### 3.4 Label Matching Criteria

**Field:** `match_label` on `account.reconcile.model`

**Purpose:** Restricts when the model applies based on the transaction label/description.

| Value | Display Name | Description |
|-------|--------------|-------------|
| `contains` | **Contains** | Transaction label must contain the specified text (case insensitive) |
| `not_contains` | **Not Contains** | Transaction label must NOT contain the specified text |
| `match_regex` | **Match Regex** | Transaction label must match the specified regular expression pattern |

**Related Field:** `match_label_param` (Char): The text or pattern to match against

**What This Means for Users:**

Label matching is one of the most powerful ways to identify recurring transactions:

**Contains Example:**
- Parameter: "PAYPAL"
- Matches: "PAYPAL TRANSFER", "PAYPAL-MERCHANT", "FROM PAYPAL INC"

**Not Contains Example:**
- Parameter: "FEE"
- Matches: Transactions WITHOUT "FEE" in the label
- Useful for: Applying a rule to all transactions EXCEPT fees

**Match Regex Example:**
- Parameter: `INV-\d{4,}` 
- Matches: "INV-1234", "INV-99999"
- Does NOT match: "INV-12" (less than 4 digits)

**Where Matching is Applied:**

The system checks the match against multiple sources:
1. Statement line label (main description)
2. Transaction details (additional information from bank)
3. Notes (user-added comments)

**Track Changes:** This field has change tracking enabled.

*Source: `addons/account/models/account_reconcile_model.py:124-132`*

---

## 4. Access Control

Security groups control who can view, create, modify, and delete reconciliation models.

### 4.1 Permission Matrix

**Model: `account.reconcile.model`**

| Security Group | Read | Create | Update | Delete |
|----------------|------|--------|--------|--------|
| **Show Accounting Features (Readonly)** | ✓ | ✗ | ✗ | ✗ |
| **Invoicing / Billing** | ✓ | ✓ | ✗ | ✗ |
| **Accountant (Basic)** | ✓ | ✓ | ✓ | ✓ |

**Model: `account.reconcile.model.line`**

| Security Group | Read | Create | Update | Delete |
|----------------|------|--------|--------|--------|
| **Show Accounting Features (Readonly)** | ✓ | ✗ | ✗ | ✗ |
| **Invoicing / Billing** | ✓ | ✓ | ✗ | ✗ |
| **Accountant (Basic)** | ✓ | ✓ | ✓ | ✓ |

### 4.2 Permission Explanations

**Show Accounting Features (Readonly)** - `account.group_account_readonly`
- Can view existing reconciliation models
- Cannot make any changes
- Suitable for: Auditors, viewers who need to understand rules but not modify them

**Invoicing / Billing** - `account.group_account_invoice`
- Can view and create new reconciliation models
- Cannot modify or delete existing models
- Suitable for: Staff who need to set up rules but shouldn't change established ones

**Accountant (Basic)** - `account.group_account_basic`
- Full access to reconciliation models
- Can create, modify, and delete rules
- Suitable for: Finance staff responsible for maintaining reconciliation rules

### 4.3 Multi-Company Isolation

Reconciliation models are subject to multi-company security rules. Users can only access models belonging to companies they are assigned to.

**Rule Applied:** Each model's `company_id` is checked against the user's allowed companies.

**What This Means:**
- A model created for "Company A" is only visible to users with access to "Company A"
- Users with access to multiple companies see models from all their companies
- Models cannot be shared across companies

*Source: `addons/account/security/ir.model.access.csv:91-96`*

---

## 5. Integration Points

Reconciliation models integrate with several other Odoo components.

### 5.1 Journal Restrictions

**Field:** `match_journal_ids` on `account.reconcile.model`

**Purpose:** Limits which bank journals can use this reconciliation model.

**Domain Restriction:** Only bank, cash, and credit card journals can be selected:
```
domain="[('type', 'in', ('bank', 'cash', 'credit'))]"
```

**What This Means for Users:**

You can configure a reconciliation model to only appear when reconciling specific bank accounts. This is useful when:
- Different banks have different fee structures
- Certain transaction types only occur in specific accounts
- You want to separate rules by payment method (bank vs. cash vs. credit card)

**Example:**
- Model "Wells Fargo Fees" → Only linked to "Wells Fargo Bank" journal
- Model "Credit Card Fees" → Only linked to "Corporate Amex" journal

If no journals are selected, the model applies to all applicable journals.

### 5.2 Partner Restrictions

**Field:** `match_partner_ids` on `account.reconcile.model`

**Purpose:** Limits the model to transactions involving specific customers or vendors.

**What This Means for Users:**

When configured, the model will only be suggested for transactions where:
- The partner is already identified as one of the selected partners, OR
- The model is used specifically to identify these partners

This is useful for vendor-specific rules like:
- "Utility Company Payment" → Only for "City Water Department" partner
- "Major Customer Receipt" → Only for your top 3 customers

### 5.3 Account Integration

**Field:** `account_id` on `account.reconcile.model.line`

**Purpose:** Specifies which account receives the write-off amount.

**Domain Restriction:** Cannot use off-balance sheet accounts:
```
domain="[('account_type', '!=', 'off_balance')]"
```

**What This Means for Users:**

When the reconciliation model creates a write-off entry, it posts to the specified account. Common examples:
- Bank fees → "Bank Charges" expense account
- Interest earned → "Interest Income" revenue account
- Rounding differences → "Cash Rounding" expense account

### 5.4 Tax Integration

**Field:** `tax_ids` on `account.reconcile.model.line`

**Purpose:** Applies taxes to the write-off entry.

**What This Means for Users:**

If the write-off amount should include tax calculation (for example, bank services with VAT), you can specify the applicable taxes. The system will:
1. Calculate the tax amount based on the write-off
2. Create additional journal entry lines for tax

### 5.5 Activity Scheduling

**Field:** `next_activity_type_id` on `account.reconcile.model`

**Purpose:** Automatically schedules a follow-up activity when the model is applied.

**What This Means for Users:**

You can configure the model to create a reminder or task when applied. For example:
- When a large receipt is reconciled, schedule "Follow up with customer" activity
- When bank fees are recorded, schedule "Review fee statement" activity

This helps ensure important reconciled items receive appropriate follow-up attention.

---

## 6. Error Scenarios and Recovery

### 6.1 Common Validation Errors

| Error Message | Cause | Resolution |
|---------------|-------|------------|
| "The amount is not a number" | Fixed amount type with zero or non-numeric value | Enter a valid non-zero amount |
| "Balance percentage can't be 0" | Percentage type with zero value | Enter a percentage between 1 and 100 |
| "Statement line percentage can't be 0" | Statement line percentage with zero value | Enter a percentage between 1 and 100 |
| "The regex is not valid" | Invalid regular expression syntax | Correct the regex pattern syntax |

### 6.2 Reconciliation Failures

If a reconciliation model fails to apply correctly:

1. **Amount Mismatch:** The calculated amount doesn't balance
   - Check percentage calculations
   - Verify fixed amounts are correct
   - Review regex extraction patterns

2. **Partner Not Found:** Expected partner mapping failed
   - Verify match_label criteria matches transaction text
   - Check that single line has partner but no account

3. **Account Missing:** Write-off cannot be created
   - Ensure account_id is set on reconciliation lines
   - Verify account is active and accessible

### 6.3 Recovery Actions

**To undo an incorrectly applied reconciliation:**
1. Navigate to the reconciled bank transaction
2. Click "Unreconcile" or open the reconciliation details
3. Remove the incorrect matching
4. Correct the reconciliation model configuration
5. Re-apply reconciliation

**To test a reconciliation model before automation:**
1. Keep the model in "Manual" trigger mode
2. Process several transactions using the model
3. Verify results are correct
4. Only then switch to "Automated" if desired

---

## 7. Best Practices

### 7.1 Creating Effective Reconciliation Models

1. **Start Specific, Then Generalize**
   - Create rules for your most common, predictable transactions first
   - Use precise matching criteria initially
   - Expand criteria only after confirming accuracy

2. **Use Descriptive Names**
   - Name models clearly: "Monthly Rent Payment - ABC Properties"
   - Include key matching criteria in the name for easy identification

3. **Test Before Automating**
   - Always start with manual trigger
   - Review matched transactions for accuracy
   - Document the expected behavior
   - Switch to automated only after confidence is established

4. **Maintain Documentation**
   - Record why each model was created
   - Note any special circumstances or exceptions
   - Review and update models periodically

### 7.2 Regex Pattern Guidelines

For "From label" amount extraction:

| Pattern | Use Case | Example Match |
|---------|----------|---------------|
| `([\d,]+\.\d{2})` | US currency with cents | "1,234.56" |
| `([\d.]+,\d{2})` | European currency | "1.234,56" |
| `\$\s*([\d,]+\.\d{2})` | US dollar amounts | "$ 100.00" |
| `Amount:\s*([\d.]+)` | Labeled amounts | "Amount: 50.00" |

### 7.3 Security Recommendations

1. Limit "Accountant (Basic)" access to trusted finance staff
2. Use "Invoicing" level for staff who only need to create rules
3. Regular audit of automated reconciliation models
4. Review reconciliation model changes in the activity log

---

## Related Documentation

- [Bank Reconciliation User Flow](../02-user-flows/14-bank-reconciliation/flow-document.md) - Step-by-step workflow guide
- [Invoice Payment Rules](./invoice-payment-rules.md) - Related payment business rules
- [Capabilities Inventory](../01-capabilities-overview/capabilities-inventory.md) - Module overview and glossary

---

*Document Version: 1.0*
*Last Updated: Based on Odoo 19.0 Community Edition*
*Source References: `addons/account/models/account_reconcile_model.py`, `addons/account/security/ir.model.access.csv`*
