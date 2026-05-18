# Business Rules: Inventory Delivery Order Workflow

## Overview

This document describes the business rules governing the **Inventory Delivery Order** workflow in Odoo 19.0. A **Delivery Order** (technically called a `stock.picking`) represents an authorization and instruction for warehouse staff to ship products from the warehouse to a customer location.

Understanding these rules helps customer support teams and business analysts:
- Troubleshoot why a delivery might be stuck in a particular state
- Explain validation errors to end users
- Understand how the system handles partial shipments
- Identify why stock might not be available for a delivery

**Related Documentation:** [Inventory Delivery Order Flow Document](../02-user-flows/05-inventory-delivery-order/flow-document.md)

---

## 1. Validation Logic

### 1.1 Required Fields

Before a delivery order can be saved or processed, the system validates that certain fields contain values:

| Field | Technical Name | Error When Missing |
|-------|----------------|-------------------|
| **Operation Type** | `picking_type_id` | "Operation Type is required" |
| **Source Location** | `location_id` | "Source Location is required" |
| **Destination Location** | `location_dest_id` | "Destination Location is required" |

**Business Meaning:**
- **Operation Type** defines which warehouse operation is being performed (e.g., "Delivery Orders" for outbound shipments)
- **Source Location** is where products will be taken from (e.g., WH/Stock)
- **Destination Location** is where products will be sent (e.g., Partner Locations/Customers)

*Source: `addons/stock/models/stock_picking.py:609-616`*

### 1.2 Reference Uniqueness

The system enforces that each delivery order reference (the document number like "WH/OUT/00001") is unique within a company.

| Constraint | Rule |
|------------|------|
| **Unique Reference** | The combination of `name` and `company_id` must be unique |

**What This Means:**
- Two delivery orders cannot have the same reference number in the same company
- Different companies may have the same reference number
- If a duplicate is attempted, the system displays: "Reference must be unique per company!"

*Source: `addons/stock/models/stock_picking.py:710-713`*

### 1.3 Validation at Button Click

When a user clicks **Validate** to complete a delivery, the system performs sanity checks:

| Check | Condition | Error Message |
|-------|-----------|---------------|
| **Empty Transfer** | No products/moves added | "You can't validate an empty transfer. Please add some products to move before proceeding." |
| **No Quantities Done** | No quantities filled | "Please add 'Done' quantities to the picking." |
| **Missing Lot/Serial** | Tracked products without lot/serial | "You need to supply a Lot/Serial number for products [product names]." |

**Business Meaning:**
- The system prevents accidental validation of empty or incomplete deliveries
- For products tracked by lots or serial numbers, tracking information must be provided before shipment

*Source: `addons/stock/models/stock_picking.py:1344-1386`*

### 1.4 Move State Consistency

A delivery order's state is computed from the states of its individual product moves (called `stock.move` records). The system ensures consistency between the picking and its moves:

| Scenario | Result |
|----------|--------|
| All moves are cancelled | Picking state becomes "Cancelled" |
| All moves are done or cancelled | Picking state becomes "Done" |
| Any move is in draft | Picking state becomes "Draft" |
| Moves have mixed states | Picking state is computed based on shipping policy |

*Source: `addons/stock/models/stock_picking.py:809-857`*

---

## 2. State Transitions

### 2.1 Delivery Order States

A **Delivery Order** (`stock.picking`) can exist in one of six states:

| State | Display Label | What It Means to Users |
|-------|---------------|------------------------|
| `draft` | Draft | The delivery is created but not yet confirmed. Products are not reserved. |
| `waiting` | Waiting Another Operation | The delivery is waiting for an upstream operation (like manufacturing or receipt) to complete first. |
| `confirmed` | Waiting | The delivery is confirmed, but stock is not yet reserved. Click "Check Availability" to reserve stock. |
| `assigned` | Ready | Stock has been reserved. The delivery is ready to be processed and validated. |
| `done` | Done | The delivery has been completed. Stock has been deducted from the source location. |
| `cancel` | Cancelled | The delivery has been cancelled. Any reservations have been released. |

*Source: `addons/stock/models/stock_picking.py:575-589`*

### 2.2 State Transition Diagram

```
                    ┌─────────────────────────────────────────────────┐
                    │                                                 │
                    ▼                                                 │
    ┌─────────┐   action_confirm()   ┌───────────┐                   │
    │  draft  │ ─────────────────────►│ confirmed │                   │
    └─────────┘         │            └───────────┘                   │
         │              │                   │                         │
         │              │     action_assign()│(if stock available)    │
         │              │                   │                         │
         │              ▼                   ▼                         │
         │        ┌───────────┐     ┌───────────┐                    │
         │        │  waiting  │     │  assigned │                    │
         │        └───────────┘     └───────────┘                    │
         │              │                   │                         │
         │              │                   │ button_validate()       │
         │              │                   ▼                         │
         │              │           ┌───────────┐                    │
         │              └───────────►│   done    │                    │
         │                          └───────────┘                    │
         │                                                           │
         │              action_cancel() (from any non-done state)     │
         └───────────────────────────────────────────────────────────►┐
                                                                      │
                                                                      ▼
                                                              ┌───────────┐
                                                              │  cancel   │
                                                              └───────────┘
```

### 2.3 Transition Methods

#### 2.3.1 action_confirm() — Confirm the Delivery

**What It Does:**
Confirms the delivery order and its stock moves. After confirmation, the system triggers reservation attempts based on the operation type's configuration.

**When It's Called:**
- Automatically when a sales order is confirmed (if auto-confirm is enabled)
- Manually when clicking "Mark as To Do" button on a draft picking

**Business Logic:**
1. Validates company ownership of all records
2. Confirms all draft moves (changes move state from `draft` to `confirmed` or `waiting`)
3. Triggers the scheduler for moves that may need procurement
4. If the operation type has `reservation_method = 'at_confirm'`, automatically attempts to reserve stock

**Possible Resulting States:**
| Scenario | Resulting Picking State |
|----------|------------------------|
| Moves have no dependencies | `confirmed` |
| Moves wait for upstream operations | `waiting` |
| Stock immediately available and reserved | `assigned` |

*Source: `addons/stock/models/stock_picking.py:1181-1188`*

#### 2.3.2 action_assign() — Check Availability / Reserve Stock

**What It Does:**
Attempts to reserve available stock for all moves in the delivery order.

**When It's Called:**
- When user clicks the "Check Availability" button
- Automatically at confirmation if configured
- When upstream operations complete

**Business Logic:**
1. If the picking is still in draft, first calls `action_confirm()`
2. Filters moves to only those in states `confirmed`, `waiting`, or `partially_available`
3. Sorts moves by priority (urgent first), then by deadline, then by scheduled date
4. For each move, attempts to reserve stock from quants (inventory records)
5. Creates move lines (`stock.move.line`) for reserved quantities

**Possible Resulting States:**
| Scenario | Resulting Move State | Resulting Picking State |
|----------|---------------------|------------------------|
| All quantity reserved | `assigned` | `assigned` (if shipping policy allows) |
| Partial quantity reserved | `partially_available` | Depends on shipping policy |
| No quantity reserved | `confirmed` (unchanged) | `confirmed` or `waiting` |

**Error Condition:**
If there are no moves to check availability for, the system displays: "Nothing to check the availability for."

*Source: `addons/stock/models/stock_picking.py:1190-1203`*

#### 2.3.3 button_validate() — Complete the Delivery

**What It Does:**
Validates and completes the delivery order, deducting stock from the source location and recording the shipment.

**When It's Called:**
- When user clicks the "Validate" button

**Business Logic:**
1. Filters out pickings already in `done` state
2. If any pickings are in `draft`, confirms them first and sets quantities
3. Performs sanity checks (see Section 1.3)
4. Runs pre-validation hooks (may open wizards for backorders, serial numbers, etc.)
5. Calls `_action_done()` to complete the moves
6. Records the completion date (`date_done`)
7. Triggers downstream operations (e.g., next transfer in chain)
8. Optionally creates backorders for unprocessed quantities

**Backorder Behavior:**
| Configuration | Behavior When Partial Quantity |
|--------------|-------------------------------|
| Create Backorder = "Always" | Automatically creates backorder for remaining |
| Create Backorder = "Never" | Cancels remaining quantities |
| Create Backorder = "Ask" | Opens wizard to let user decide |

**Resulting State:** `done`

*Source: `addons/stock/models/stock_picking.py:1391-1451`*

#### 2.3.4 action_cancel() — Cancel the Delivery

**What It Does:**
Cancels the delivery order and releases any reserved stock.

**When It's Called:**
- When user clicks the "Cancel" button

**Business Logic:**
1. Cancels all associated stock moves via `_action_cancel()`
2. Releases any reserved quantities back to available stock
3. Locks the picking (prevents editing)
4. If picking has no moves, directly sets state to `cancel`

**Important:** A delivery in `done` state cannot be cancelled. To reverse a completed delivery, the user must create a return.

**Error Condition:**
If attempting to cancel a done move that is not an inventory adjustment: "You cannot cancel a stock move that has been set to 'Done'. Create a return in order to reverse the moves which took place."

*Source: `addons/stock/models/stock_picking.py:1205-1209` and `addons/stock/models/stock_move.py:2028-2065`*

---

## 3. Computation Rules

### 3.1 State Computation

The delivery order state is **automatically computed** from the states of its individual moves, based on the shipping policy.

**Dependency Fields:** `move_type`, `move_ids.state`, `move_ids.picking_id`

**Computation Logic:**

```
IF no moves OR any move is 'draft':
    picking.state = 'draft'
ELSE IF all moves are 'cancel':
    picking.state = 'cancel'
ELSE IF all moves are 'done' or 'cancel':
    picking.state = 'done'
ELSE:
    IF location should bypass reservation AND all moves are make-to-stock:
        picking.state = 'assigned'
    ELSE:
        Compute relevant state from moves based on shipping policy
```

**Shipping Policy Effect on State:**

| Shipping Policy | State When Partially Reserved |
|-----------------|------------------------------|
| "As soon as possible" (`direct`) | `assigned` (ready to ship partial) |
| "When all products are ready" (`one`) | `confirmed` (waiting for full reservation) |

*Source: `addons/stock/models/stock_picking.py:809-857`*

### 3.2 Products Availability Computation

The system computes a human-readable availability status for the delivery.

**Dependency Fields:** `state`, `picking_type_code`, `scheduled_date`, `move_ids`, `move_ids.forecast_availability`, `move_ids.forecast_expected_date`

**Applies To:** Outgoing and internal transfers in states `waiting`, `confirmed`, or `assigned`

**Computation Logic:**

| Condition | Availability Text | Availability State |
|-----------|------------------|-------------------|
| All products available | "Available" | `available` |
| Any product has insufficient forecast | "Not Available" | `late` |
| Products available in future | "Exp [date]" | `expected` or `late` |

**Example Display Values:**
- "Available" — All products can be shipped now
- "Not Available" — Some products don't have enough stock
- "Exp 01/30/2026" — Products expected to be available on that date

*Source: `addons/stock/models/stock_picking.py:756-780`*

### 3.3 Deadline Issue Detection

The system automatically detects if a delivery is late or will be late.

**Dependency Fields:** `date_deadline`, `scheduled_date`

**Computation Logic:**

```
has_deadline_issue = date_deadline AND date_deadline < scheduled_date
```

**Business Meaning:**
- If the deadline for delivery is earlier than the scheduled processing date, the delivery is flagged as having a deadline issue
- This appears as a visual indicator (often red/orange) in the delivery list views

*Source: `addons/stock/models/stock_picking.py:724-727`*

### 3.4 Scheduled Date Computation

The scheduled date is computed based on the dates of individual moves and the shipping policy.

**Dependency Fields:** `move_ids.state`, `move_ids.date`, `move_type`

**Computation Logic:**

| Shipping Policy | Scheduled Date Calculation |
|-----------------|---------------------------|
| "As soon as possible" (`direct`) | **Minimum** date among non-completed moves |
| "When all products are ready" (`one`) | **Maximum** date among non-completed moves |

**Business Meaning:**
- For partial shipments ("direct"), the date reflects when the first items can ship
- For full shipments ("one"), the date reflects when all items will be ready

*Source: `addons/stock/models/stock_picking.py:858-867`*

### 3.5 Deadline Date Computation

The deadline is derived from the stock moves' deadlines.

**Dependency Fields:** `move_ids.date_deadline`

**Business Meaning:**
- For outgoing deliveries: The date by which the transfer must be validated to meet customer delivery promises
- For incoming transfers: The date by which goods must be received per supplier commitments

---

## 4. Shipping Policies (Move Type)

The **Shipping Policy** determines how the system handles deliveries when only partial quantities are available.

### 4.1 Policy Definitions

| Policy | Technical Value | Display Name | Behavior |
|--------|----------------|--------------|----------|
| **Partial Delivery** | `direct` | "As soon as possible" | Ship whatever is available now; create backorder for remaining |
| **Full Delivery** | `one` | "When all products are ready" | Wait until all products are available before allowing shipment |

*Source: `addons/stock/models/stock_picking.py:571-574`*

### 4.2 Policy Effects on Workflow

#### As Soon As Possible (`direct`)

**Scenario:** Order for 10 units, only 7 available

| Step | Quantity | Result |
|------|----------|--------|
| Reserve stock | 7 reserved | Picking state = `assigned` (Ready) |
| Validate | Process 7 | Original delivery = `done`, Backorder created for 3 |

**User Experience:**
- The "Check Availability" button reserves available stock
- The delivery shows "Ready" state even with partial reservation
- Upon validation, a backorder is automatically created for the remaining quantity

#### When All Products Are Ready (`one`)

**Scenario:** Order for 10 units, only 7 available

| Step | Quantity | Result |
|------|----------|--------|
| Reserve stock | 7 reserved | Picking state = `confirmed` (Waiting) |
| Wait for more stock | 3 more available | Now fully reserved |
| Reserve again | 10 reserved | Picking state = `assigned` (Ready) |

**User Experience:**
- The delivery remains in "Waiting" state even though partial stock is reserved
- The user must wait until all products are available before shipping
- The "Validate" button is only enabled when fully ready

### 4.3 Default Policy

The default shipping policy is inherited from the **Operation Type** configuration:

1. Operation Type defines a default `move_type`
2. When a delivery is created for that operation type, it inherits this default
3. Users can override the policy on individual deliveries if needed

*Source: `addons/stock/models/stock_picking.py:719-722`*

---

## 5. Priority and Reservation Order

### 5.1 Priority Levels

Delivery orders can be assigned a priority that affects reservation order:

| Priority | Technical Value | Display Name | Effect |
|----------|-----------------|--------------|--------|
| **Normal** | `0` | Normal | Standard processing order |
| **Urgent** | `1` | Urgent | Reserved before normal priority items |

*Source: `addons/stock/models/stock_move.py:15`*

### 5.2 Reservation Order

When multiple deliveries compete for limited stock, the system reserves in this order:

1. **Priority** — Urgent (1) before Normal (0)
2. **Has Deadline** — Deliveries with deadlines before those without
3. **Deadline Date** — Earlier deadlines first
4. **Scheduled Date** — Earlier scheduled dates first
5. **Record ID** — Oldest records first (first-in, first-out)

**Business Meaning:**
- Mark a delivery as "Urgent" (starred) to ensure it gets stock first
- Deliveries with customer-promised dates are prioritized over open-ended ones

*Source: `addons/stock/models/stock_picking.py:1197-1198`*

### 5.3 Reservation Method Configuration

Each Operation Type can be configured with a reservation method:

| Method | Technical Value | Behavior |
|--------|-----------------|----------|
| **At Confirmation** | `at_confirm` | Reserve stock immediately when delivery is confirmed |
| **Manually** | `manual` | User must click "Check Availability" to reserve |
| **Before Scheduled Date** | `by_date` | Reserve automatically X days before scheduled date |

*Source: `addons/stock/models/stock_picking.py:68-72`*

---

## 6. Access Control

### 6.1 Security Groups

Access to delivery orders is controlled by security groups:

| Group | Technical Name | Permissions |
|-------|----------------|-------------|
| **Inventory / User** | `stock.group_stock_user` | Create, read, update, delete own deliveries |
| **Inventory / Administrator** | `stock.group_stock_manager` | Full access including configuration |

*Source: `addons/stock/security/stock_security.xml`*

### 6.2 Permission Requirements by Action

| Action | Required Permission | Notes |
|--------|---------------------|-------|
| View delivery orders | `stock.group_stock_user` | See deliveries for accessible warehouses |
| Create delivery order | `stock.group_stock_user` | Typically auto-created from sales orders |
| Check availability | `stock.group_stock_user` | Reserves stock from locations user can access |
| Validate delivery | `stock.group_stock_user` | Completes the delivery |
| Cancel delivery | `stock.group_stock_user` | Only for non-done deliveries |
| Unlock done delivery | `stock.group_stock_manager` | Required to edit completed deliveries |
| Configure operation types | `stock.group_stock_manager` | Set up warehouses and operations |

### 6.3 Multi-Location Access

If the **Multi-Locations** feature is enabled, additional considerations apply:

- Users can only see deliveries for locations they have access to
- The `Responsible` field on a delivery can restrict visibility
- Inter-warehouse transfers may require elevated permissions

---

## 7. Integration Triggers

### 7.1 Upstream Triggers

| Source | Trigger | Creates |
|--------|---------|---------|
| Sales Order confirmation | `_action_launch_stock_rule()` | Delivery Order for ordered products |
| Purchase Order receipt | Internal transfer | Moves products to stock |
| Manufacturing completion | Finished goods transfer | Products to deliver |

### 7.2 Downstream Effects

| Event | Triggered Action |
|-------|------------------|
| Delivery validated | Stock quantities updated in source location |
| Delivery validated | Destination location quantities increased |
| Delivery validated | Downstream operations triggered (if chained) |
| Delivery validated | Confirmation email sent (if configured) |
| Partial delivery | Backorder created with remaining quantities |

*Source: `addons/stock/models/stock_picking.py:1270-1274`*

---

## 8. Error Handling

### 8.1 Common Validation Errors

| Error Message | Cause | Resolution |
|---------------|-------|------------|
| "You can't validate an empty transfer" | No products added to delivery | Add products before validating |
| "Nothing to check the availability for" | All moves already reserved or none to reserve | Proceed to validate or add more products |
| "You need to supply a Lot/Serial number" | Tracked product without lot/serial | Enter lot/serial numbers before validating |
| "You cannot cancel a stock move that has been set to 'Done'" | Trying to cancel completed delivery | Create a return instead |
| "Reference must be unique per company!" | Duplicate delivery reference | System auto-generates unique references |

### 8.2 State-Based Restrictions

| Action | Allowed In States | Blocked In States |
|--------|-------------------|-------------------|
| Edit quantities | `draft`, `confirmed`, `assigned` | `done`, `cancel` |
| Check availability | `draft`, `confirmed`, `waiting`, `partially_available` | `done`, `cancel`, `assigned` |
| Validate | `draft`, `confirmed`, `assigned` | `done`, `cancel` |
| Cancel | `draft`, `waiting`, `confirmed`, `assigned` | `done` |
| Create return | `done` | All others |

---

## 9. Glossary

| Term | Definition |
|------|------------|
| **Picking** | Technical name for a stock transfer document (delivery order, receipt, internal transfer) |
| **Stock Move** | An individual product line within a picking, representing demand for a specific product quantity |
| **Stock Move Line** | A detailed operation within a move, specifying exact quantities, lots, and locations |
| **Quant** | An inventory record tracking actual quantities at specific locations |
| **Reservation** | The act of earmarking specific stock for a delivery, preventing other uses |
| **Backorder** | A new delivery automatically created for quantities not processed in the original delivery |
| **Operation Type** | Configuration defining how a type of transfer behaves (receipts, deliveries, internal) |

---

## Document Information

| Attribute | Value |
|-----------|-------|
| **Module** | `stock` |
| **Primary Model** | `stock.picking` |
| **Related Models** | `stock.move`, `stock.move.line`, `stock.quant` |
| **Source Files** | `addons/stock/models/stock_picking.py`, `addons/stock/models/stock_move.py` |
| **Odoo Version** | 19.0 |
| **Last Updated** | Based on code analysis |
