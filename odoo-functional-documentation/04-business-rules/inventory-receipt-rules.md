# Inventory Receipt Processing - Business Rules

## Overview

This document describes the business rules governing **Inventory Receipt Processing** in Odoo 19.0. These rules ensure that incoming goods are properly validated, tracked, and recorded in the warehouse management system. The documentation covers validation requirements, state transitions, automatic calculations, and access controls.

**Related Workflow:** [Inventory Receipt Processing Flow](../02-user-flows/04-inventory-receipt-processing/flow-document.md)

**Primary Data Model:** `stock.picking` with `picking_type_code='incoming'`

**Supporting Model:** `stock.move` for individual product movements within a receipt

---

## Validation Logic

### Quantity Validation Rules

When processing a receipt, the system validates received quantities according to the following rules:

#### Rule 1: Received Quantity Must Be Greater Than Zero

**What happens:** When the user clicks "Validate" on a receipt, the system checks that at least one product line has a quantity entered.

**Business reasoning:** An empty receipt serves no purpose—goods must be received for the operation to be meaningful.

**Error displayed to user:** If all quantities are zero, the user sees:
> "Transfer trouble alert! Validating a zero quantity transfer? You're not moving invisible goods around are you? Set some quantities and let's get moving!"

`Source: addons/stock/models/stock_picking.py:1503-1506`

#### Rule 2: Quantity Precision Follows Product Unit Settings

**What happens:** All received quantities respect the decimal precision configured for "Product Unit" in the system settings.

**Business reasoning:** Different businesses track inventory with different precision levels (whole units, tenths, hundredths). The system adapts to each organization's needs.

**Where configured:** Settings → Technical → Database Structure → Decimal Accuracy → Product Unit

`Source: addons/stock/models/stock_picking.py:1351`

#### Rule 3: Demand vs. Received Quantity Tracking

**What happens:** The system tracks two distinct quantities for each product line:
- **Demand**: The expected quantity to receive (from a purchase order or manual entry)
- **Quantity**: The actual quantity received

**Business reasoning:** This separation allows for:
- Partial receipts (receiving less than expected)
- Over-receipts when permitted by configuration
- Accurate tracking of delivery performance

`Source: addons/stock/models/stock_move.py:58-65`

---

### Serial and Lot Number Validation

When products require traceability (lot or serial number tracking), additional validation rules apply:

#### Rule 4: Tracked Products Require Lot/Serial Numbers

**What happens:** If a product is configured with "Lots" or "Serial Numbers" tracking, the system requires this information before validating the receipt.

**Error displayed to user:** If lot/serial information is missing:
> "You need to supply a Lot/Serial number for products [Product Names]."

**Business reasoning:** Traceability is legally required in many industries (food, pharmaceuticals, electronics). Missing lot information would break the chain of custody.

`Source: addons/stock/models/stock_picking.py:1373-1374`

#### Rule 5: Serial Number Uniqueness per Product

**What happens:** When using serial number tracking (one unit per serial), each serial number must be unique for that product within the company.

**Business reasoning:** Serial numbers exist specifically to uniquely identify individual units. Duplicate serials would defeat this purpose.

`Source: addons/stock/models/stock_move.py:1798-1801`

#### Rule 6: Lot Number Creation vs. Selection

**What happens:** The operation type configuration determines whether users can:
- **Create new lots**: Enter any lot name, system creates the lot record
- **Use existing lots**: Select from pre-registered lot numbers only

| Setting | Receipt Behavior |
|---------|------------------|
| Create New Lots = Yes | User can type new lot names |
| Use Existing Lots = Yes | User can select from dropdown |
| Both = Yes | User can do either |

**Business reasoning:** Some organizations pre-register lot numbers from vendor documentation, while others assign internal lot numbers upon receipt.

`Source: addons/stock/models/stock_picking.py:53-60, 782-792`

---

### Location Validation

#### Rule 7: Cannot Receive to "View" Type Locations

**What happens:** The destination location for a receipt must be a physical storage location, not a "view" type location used for organizing the location hierarchy.

**Business reasoning:** "View" locations are organizational containers (like folders) that cannot hold physical stock. Goods must go to actual storage locations.

`Source: addons/stock/models/stock_move.py:81-84`

#### Rule 8: Destination Must Be Company-Owned Location

**What happens:** Incoming receipts must have a destination location that belongs to the receiving company's warehouse structure.

**Business reasoning:** Multi-company environments must maintain clear separation of inventory ownership.

`Source: addons/stock/models/stock_picking.py:613-616`

---

## State Transitions

### Receipt States Explained

A **Receipt (stock.picking with incoming type)** progresses through defined states. Each state represents where the receipt is in its lifecycle.

| State | Display Name | What It Means |
|-------|--------------|---------------|
| `draft` | Draft | Receipt created but not yet confirmed for processing |
| `waiting` | Waiting Another Operation | Receipt depends on another transfer completing first |
| `confirmed` | Waiting | Receipt confirmed but products not yet available to process |
| `assigned` | Ready | Products are available; receipt can be validated |
| `done` | Done | Receipt completed; inventory updated |
| `cancel` | Cancelled | Receipt cancelled; no inventory changes made |

`Source: addons/stock/models/stock_picking.py:575-589`

---

### State Transition Rules

#### Rule 9: State is Computed from Move States

**What happens:** The receipt's state is automatically calculated based on the states of its individual product lines (stock moves). This is not manually set but computed in real-time.

**State computation logic:**

```
IF no moves exist OR any move is in draft → receipt state = draft
IF all moves are cancelled → receipt state = cancel  
IF all moves are done or cancelled:
    IF all done moves went to scrap AND some were cancelled → state = cancel
    ELSE → receipt state = done
ELSE:
    IF location bypasses reservation OR all moves are make-to-stock → state = assigned
    ELSE → state = relevant state from moves (assigned, partially_available, waiting, confirmed)
```

**Business reasoning:** The receipt state should accurately reflect the readiness of all product lines, not be manually overridden.

`Source: addons/stock/models/stock_picking.py:809-857`

#### Rule 10: Confirmation Triggers Automatic Assignment for Receipts

**What happens:** When confirming a receipt (or adding products to an already confirmed receipt), the system automatically attempts to prepare it for processing.

For **incoming receipts specifically**: Since products are coming from outside the warehouse (vendor location), no stock reservation is needed. The receipt typically moves directly to "Ready" state.

**Business reasoning:** Incoming goods don't require reservation—they're being added to inventory, not removed. The "Ready" state simply means the receipt can be processed.

`Source: addons/stock/models/stock_picking.py:1181-1188, 849-850`

#### Rule 11: Validation Requires Non-Cancelled Moves

**What happens:** A receipt cannot be validated if all of its product lines have been cancelled. At least one active move must exist.

**Business reasoning:** There must be something to receive for validation to make sense.

`Source: addons/stock/models/stock_picking.py:1391-1392`

---

### Allowed State Transitions

The following transitions are permitted:

| From State | To State | Trigger | Business Scenario |
|------------|----------|---------|-------------------|
| Draft | Waiting | Confirm (with dependencies) | Receipt depends on another transfer |
| Draft | Confirmed | Confirm | Normal confirmation |
| Draft | Assigned | Check Availability | Direct readiness check |
| Draft | Cancel | Cancel button | User cancels before processing |
| Waiting | Confirmed | Dependency completes | Previous operation finished |
| Waiting | Cancel | Cancel button | User cancels while waiting |
| Confirmed | Assigned | Check Availability | Stock becomes available |
| Confirmed | Cancel | Cancel button | User cancels before processing |
| Assigned | Done | Validate | Successful receipt completion |
| Assigned | Confirmed | Unreserve | Rare: stock unreservation |
| Assigned | Cancel | Cancel button | User cancels ready receipt |
| Cancel | Draft | Reset to Draft | Re-enable cancelled receipt |

`Source: addons/stock/models/stock_picking.py:1181-1209`

---

## Computation Rules

### Automatically Calculated Fields

The following fields are automatically computed by the system based on other data:

#### Computed Field: State

**Field:** `state`
**Depends on:** `move_type`, `move_ids.state`, `move_ids.picking_id`

**What it calculates:** The overall receipt status based on the status of all product lines.

**When it recalculates:** Whenever any move changes state, or the shipping policy changes.

**Business impact:** Users always see an accurate representation of receipt readiness without manual updates.

`Source: addons/stock/models/stock_picking.py:809-857`

---

#### Computed Field: Show Lots Text Entry

**Field:** `show_lots_text`
**Depends on:** `move_line_ids`, `picking_type_id.use_create_lots`, `picking_type_id.use_existing_lots`, `state`

**What it calculates:** Whether the user interface should show a text field for entering lot names.

**Calculation logic:**
```
IF no move lines AND create lots not enabled → hide
IF user has lot management permission AND create lots enabled AND use existing lots disabled AND state is not done → show text entry
ELSE → hide text entry
```

**Business impact:** Users see the appropriate input method for lot numbers based on their operation type configuration.

`Source: addons/stock/models/stock_picking.py:782-792`

---

#### Computed Field: Has Deadline Issue

**Field:** `has_deadline_issue`  
**Depends on:** `date_deadline`, `scheduled_date`

**What it calculates:** Whether the receipt is late or will be late based on the deadline compared to the scheduled date.

**Calculation logic:**
```
IF date_deadline exists AND date_deadline < scheduled_date → mark as having issue
ELSE → no issue
```

**Business impact:** Late receipts can be visually flagged in lists and reports, helping warehouse staff prioritize.

`Source: addons/stock/models/stock_picking.py:724-727`

---

#### Computed Field: Delay Alert Date

**Field:** `delay_alert_date`
**Depends on:** `move_ids.delay_alert_date`

**What it calculates:** The maximum delay alert date from all product lines in the receipt.

**Business impact:** Provides visibility into supply chain delays that affect receipt processing. If any product line has a delay alert, the receipt shows the most significant one.

`Source: addons/stock/models/stock_picking.py:737-742`

---

#### Computed Field: Scheduled Date

**Field:** `scheduled_date`
**Depends on:** `move_ids.state`, `move_ids.date`, `move_type`

**What it calculates:** The expected processing date for the receipt.

**Calculation logic:**
- If shipping policy is "As soon as possible": earliest date among all non-done/cancelled moves
- If shipping policy is "When all products are ready": latest date among all moves

**Business impact:** Warehouse staff can plan receiving dock usage based on expected arrivals.

`Source: addons/stock/models/stock_picking.py:858-867`

---

#### Computed Field: Products Availability

**Field:** `products_availability`, `products_availability_state`
**Depends on:** `state`, `picking_type_code`, `scheduled_date`, `move_ids`, `move_ids.forecast_availability`, `move_ids.forecast_expected_date`

**What it calculates:** The availability status of products for outgoing/internal transfers.

**Note for receipts:** This field primarily applies to outgoing transfers. For incoming receipts, products are being added to inventory, so availability is typically shown as "Available" once confirmed.

**Business impact:** Helps prioritize transfers based on stock availability.

`Source: addons/stock/models/stock_picking.py:756-780`

---

## Backorder Handling

### What is a Backorder?

A **backorder** is a new receipt automatically created when the user processes only a partial quantity of the expected goods. The remaining quantity moves to the backorder for later processing.

**Example scenario:**
- Expected: 100 units of Product A
- Received: 60 units
- Result: Original receipt marked done for 60 units; Backorder created for remaining 40 units

---

### Backorder Creation Rules

#### Rule 12: Backorder Policy Configuration

**What happens:** The operation type (Receipt) can be configured with one of three backorder policies:

| Policy | System Behavior |
|--------|----------------|
| **Ask** | Prompt user to choose whether to create a backorder |
| **Always** | Automatically create backorder for remaining quantities |
| **Never** | Cancel remaining quantities; no backorder created |

**Where configured:** Inventory → Configuration → Operation Types → [Receipt Type] → Backorder field

`Source: addons/stock/models/stock_picking.py:133-139`

#### Rule 13: Backorder Detection

**What happens:** Before completing a receipt, the system checks whether any product line has:
- Unfulfilled demand (received quantity < expected quantity), OR
- A line that wasn't marked as picked

**Calculation:**
```
FOR each move in receipt:
    IF move not cancelled AND:
        (quantity demanded > 0 AND not picked) OR
        (picked quantity < demanded quantity)
    THEN → backorder is needed
```

`Source: addons/stock/models/stock_picking.py:1526-1539`

#### Rule 14: Backorder Inherits Receipt Details

**What happens:** When a backorder is created, it inherits:
- Same partner/vendor
- Same source and destination locations
- Same operation type
- Reference link to original receipt (`backorder_id` field)

**What changes:**
- New reference number assigned
- Quantities reflect remaining (unprocessed) amounts
- State starts fresh (typically "assigned" if reservation method is at_confirm)

`Source: addons/stock/models/stock_picking.py:1569-1594`

#### Rule 15: Return Receipts Skip Backorder Logic

**What happens:** If a receipt is a return of another receipt (has `return_id` set), the backorder policy is ignored.

**Business reasoning:** Returns are typically one-time corrections and shouldn't generate ongoing backorder chains.

`Source: addons/stock/models/stock_picking.py:1491-1494`

---

### Backorder User Interaction

When the backorder policy is "Ask" and partial quantities exist:

1. User clicks "Validate"
2. System detects partial quantities
3. Popup dialog appears asking:
   - **Create Backorder**: Remaining quantities moved to new receipt
   - **No Backorder**: Remaining quantities cancelled
4. User makes selection
5. Validation proceeds accordingly

`Source: addons/stock/models/stock_picking.py:1508-1519`

---

## Putaway Rules

### What are Putaway Rules?

**Putaway rules** automatically suggest destination locations when receiving products. Instead of always putting goods in a generic "Stock" location, the system can direct specific products or categories to appropriate storage areas.

---

### Putaway Rule Application

#### Rule 16: Automatic Location Suggestion

**What happens:** When processing a receipt, the system evaluates putaway rules to suggest the best destination location for each product.

**Rule evaluation order:**
1. Rules matching the specific product
2. Rules matching the product category
3. Rules matching parent categories (hierarchical search)
4. Default destination location from operation type

**Business reasoning:** Putaway rules optimize warehouse organization by ensuring products go to their designated storage areas automatically.

`Source: addons/stock/models/stock_move.py:1488`

#### Rule 17: Putaway Considers Quantity

**What happens:** The putaway strategy can consider the quantity being received to select an appropriate location with sufficient capacity.

**Business reasoning:** Some storage locations have capacity limits. The system can direct large quantities to bulk storage and small quantities to picking locations.

`Source: addons/stock/models/stock_move.py:1488`

---

## Quality Integration

### Quality Checks at Receipt (Enterprise Feature)

**Note:** Full quality check integration requires the Enterprise Quality module. This section describes the integration point.

#### Rule 18: Quality Checks Block Validation

**What happens:** When quality checks are configured for a receipt operation type, the system may require passing checks before validation is permitted.

**Quality check types that may apply:**
- Visual inspection
- Measurement verification
- Photo documentation
- Pass/fail confirmation

**Business reasoning:** Quality control at receiving prevents defective goods from entering inventory and ensures vendor compliance with quality standards.

---

## Access Control

### Security Groups

The following security groups control access to receipt processing:

| Security Group | Technical ID | Access Level |
|----------------|--------------|--------------|
| **Inventory User** | `stock.group_stock_user` | Process receipts, view inventory |
| **Inventory Administrator** | `stock.group_stock_manager` | Full access including configuration |

`Source: addons/stock/security/stock_security.xml:10-22`

---

### Access Control Rules

#### Rule 19: Multi-Company Isolation

**What happens:** Users can only see and process receipts belonging to companies they have access to.

**Technical implementation:** Record rule filters receipts by `company_id in company_ids`

**Business reasoning:** Multi-company environments must maintain strict separation of operations and data.

`Source: addons/stock/security/stock_security.xml:72-76`

#### Rule 20: User Permission Requirements

**To process receipts, users must have:**

| Action | Minimum Group Required |
|--------|----------------------|
| View receipts | Inventory User |
| Process receipts (enter quantities, validate) | Inventory User |
| Create manual receipts | Inventory User |
| Configure receipt operation types | Inventory Administrator |
| Delete receipts | Inventory Administrator |
| Modify validated receipts (unlock) | Inventory Administrator |

---

### Field-Level Access

#### Rule 21: Locked Receipts Prevent Modification

**What happens:** After a receipt is validated (state = done), the receipt becomes "locked" by default. Locked receipts cannot be modified.

**To modify a completed receipt:**
1. User must have Inventory Administrator permissions
2. Click "Unlock" to enable editing
3. Make corrections
4. Changes are tracked in the message history

`Source: addons/stock/models/stock_picking.py:658-660`

#### Rule 22: Responsible User Assignment

**What happens:** Each receipt can have a "Responsible" user assigned. This field is limited to users who belong to the Inventory User group.

**Business reasoning:** Only users with inventory permissions should be assigned responsibility for warehouse operations.

`Source: addons/stock/models/stock_picking.py:637-641`

---

## Integration Triggers

### Automatic Receipt Creation

Receipts can be automatically created by other business processes:

| Source | Trigger | Result |
|--------|---------|--------|
| Purchase Order confirmation | `purchase.order.button_confirm()` | Receipt created for ordered products |
| Inter-warehouse transfer | Stock rule execution | Receipt created at destination warehouse |
| Manufacturing return | MRP scrap processing | Return receipt for unused components |

---

### Post-Validation Triggers

When a receipt is validated, the following automatic processes may occur:

| Process | Condition | Action |
|---------|-----------|--------|
| **Inventory Update** | Always | Stock quants updated with received quantities |
| **Move Assignment** | Other moves waiting for these products | Downstream moves become available |
| **Purchase Order Update** | Receipt linked to PO | PO received quantities updated |
| **Backorder Creation** | Partial receipt with backorder policy | New receipt for remaining quantities |

`Source: addons/stock/models/stock_picking.py:1270-1273`

---

## Error Scenarios

### Common Validation Errors

| Error Message | Cause | Resolution |
|---------------|-------|------------|
| "You can't validate an empty transfer" | No products added | Add product lines before validating |
| "Set some quantities and let's get moving!" | All quantities are zero | Enter received quantities |
| "You need to supply a Lot/Serial number for products..." | Tracked products missing lot info | Enter lot/serial numbers |
| "Reference must be unique per company!" | Duplicate receipt reference | System auto-generates; report if seen |

---

## Summary

This document covered the key business rules for Inventory Receipt Processing in Odoo 19.0:

1. **Validation Logic**: Quantity requirements, lot/serial tracking, location restrictions
2. **State Transitions**: Automatic state computation based on move states
3. **Computation Rules**: How fields like state, scheduled date, and availability are calculated
4. **Backorder Handling**: Policies and automatic creation for partial receipts
5. **Putaway Rules**: Automatic destination location suggestion
6. **Access Control**: Security groups and multi-company isolation

For step-by-step instructions on processing receipts, refer to the [Inventory Receipt Processing Workflow](../02-user-flows/04-inventory-receipt-processing/flow-document.md).

---

*Document generated for Odoo 19.0 Community Edition*
*Last updated: Based on source code analysis*
