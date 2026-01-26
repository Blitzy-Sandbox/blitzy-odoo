# Inventory Adjustment Business Rules

## Overview

This document describes the business rules governing inventory adjustments in Odoo 19.0. These rules ensure data integrity, enforce proper workflows, and maintain accurate inventory records throughout the adjustment process.

**Related Documentation:**
- [Inventory Adjustment User Flow](../02-user-flows/15-inventory-adjustment/flow-document.md)

**Source Reference:** `addons/stock/models/stock_quant.py`

---

## 1. Validation Rules

Odoo enforces several validation rules when creating or modifying inventory records (**quants**). These rules prevent invalid data from being saved and ensure business logic consistency.

### 1.1 Product Type Restriction

**Rule:** Only **storable products** can have inventory quantities recorded.

| Aspect | Details |
|--------|---------|
| **What is validated** | The product type assigned to a quant record |
| **Allowed values** | Products with `is_storable = True` (Storable Product type) |
| **Rejected values** | Consumable products and Service products |
| **When checked** | Every time a quant record is created or the product is changed |

**Business Rationale:**
Consumable products are assumed to always be available and don't require inventory tracking. Service products represent non-physical items that cannot be counted in a warehouse. Only storable products need physical inventory management.

**What the user sees when this rule is violated:**
> "Quants cannot be created for consumables or services."

**Example Scenario:**
- ✅ **Valid:** Counting "Laptop" (storable product) → Quant record created
- ❌ **Invalid:** Attempting to count "Consulting Hours" (service) → Error displayed

`Source: addons/stock/models/stock_quant.py:581-584`

---

### 1.2 Serial Number Uniqueness

**Rule:** A **serial number** (lot with serial tracking) can only exist once with positive quantity across all internal and transit locations.

| Aspect | Details |
|--------|---------|
| **What is validated** | Serial numbers for products tracked by serial number |
| **Condition** | Each serial number must have quantity ≤ 1 within the company |
| **Scope** | All child locations of the affected location, excluding inventory adjustment locations |
| **When checked** | After quantity changes for serial-tracked products |

**Business Rationale:**
Serial numbers uniquely identify individual product units. Having two units with the same serial number would break traceability, warranty tracking, and create confusion in returns and repairs.

**What the user sees when this rule is violated:**
> "The serial number has already been assigned:
> Product: [Product Name], Serial Number: [Serial Number]"

**Example Scenario:**
- ✅ **Valid:** Serial "SN-001" exists in Location A with quantity 1
- ❌ **Invalid:** Adjusting Serial "SN-001" to quantity 1 in Location B when it already exists in Location A

**Technical Note:** This validation uses a tolerance-aware comparison via the product's unit of measure to handle floating-point precision issues. The absolute quantity is checked to be greater than 1.

`Source: addons/stock/models/stock_quant.py:586-602`

---

### 1.3 Location Type Restriction

**Rule:** Products cannot be stored in or moved to **View** type locations.

| Aspect | Details |
|--------|---------|
| **What is validated** | The location type where inventory is recorded |
| **Allowed values** | Internal, Transit, Supplier, Customer, Production, Inventory Loss, and Scrap locations |
| **Rejected values** | View locations (used only for hierarchical organization) |
| **When checked** | When creating a quant or changing its location |

**Business Rationale:**
View locations are containers for organizing other locations in a hierarchy—they cannot physically hold stock. Attempting to store products in a View location would create phantom inventory that exists in the system but not in reality.

**What the user sees when this rule is violated:**
> "You cannot take products from or deliver products to a location of type "view" ([Location Name])."

**Example Scenario:**
- ✅ **Valid:** Stock in "WH/Stock" (internal location)
- ❌ **Invalid:** Stock in "Physical Locations" (view location used for grouping)

`Source: addons/stock/models/stock_quant.py:604-608`

---

### 1.4 Lot-Product Consistency

**Rule:** A **lot/serial number** must belong to the same product as the quant record.

| Aspect | Details |
|--------|---------|
| **What is validated** | The relationship between lot/serial number and product |
| **Requirement** | If a lot is specified, its product must match the quant's product |
| **Exception** | Lots without a product assigned pass validation |
| **When checked** | When creating a quant or changing its lot assignment |

**Business Rationale:**
Lots and serial numbers are created for specific products. Assigning a lot created for "Product A" to a quant of "Product B" would corrupt traceability and potentially cause quality or compliance issues.

**What the user sees when this rule is violated:**
> "The Lot/Serial number ([Lot Name]) is linked to another product."

**Example Scenario:**
- ✅ **Valid:** Lot "LOT-2024-001" (created for "Widget A") assigned to "Widget A" quant
- ❌ **Invalid:** Lot "LOT-2024-001" (created for "Widget A") assigned to "Widget B" quant

`Source: addons/stock/models/stock_quant.py:610-614`

---

## 2. Computation Rules

Odoo automatically calculates several fields based on other field values. These computed fields provide real-time information without requiring manual updates.

### 2.1 Available Quantity Calculation

**Field:** `available_quantity`

**Formula:** `Available Quantity = On-Hand Quantity - Reserved Quantity`

| Component | Description |
|-----------|-------------|
| **On-Hand Quantity** | Total physical quantity recorded in the quant |
| **Reserved Quantity** | Quantity already assigned to pending operations (deliveries, manufacturing, etc.) |
| **Available Quantity** | Quantity that can be used for new operations |

**Business Rationale:**
When a sales order is confirmed, Odoo reserves the required quantity to ensure availability at delivery time. The available quantity shows what remains unreserved and can be promised for new orders.

**Triggers:** Recalculated when either `quantity` or `reserved_quantity` changes.

**Example:**
| Scenario | On-Hand | Reserved | Available |
|----------|---------|----------|-----------|
| Initial stock | 100 | 0 | 100 |
| Sales order confirmed for 30 units | 100 | 30 | 70 |
| Delivery completed | 70 | 0 | 70 |

`Source: addons/stock/models/stock_quant.py:119-122`

---

### 2.2 Scheduled Inventory Date

**Field:** `inventory_date`

**Calculation Logic:**
1. Check if the quant has no scheduled date and is in an internal or transit location
2. Look up the location's **Cyclic Inventory Frequency** setting
3. Calculate the next inventory date based on the location's last inventory date plus the cycle frequency

| Aspect | Details |
|--------|---------|
| **Input** | Location's cyclic inventory frequency and last inventory date |
| **Output** | Next date when this product should be counted |
| **Default** | No date if frequency is not configured |
| **Manual Override** | Users can manually set a different date |

**Business Rationale:**
Cyclic counting spreads inventory verification throughout the year instead of annual physical counts. High-value or fast-moving items may be counted monthly, while slower items are counted quarterly or annually.

**Triggers:** Recalculated when the `location_id` changes (for quants without a date already set).

**Example:**
- Location "WH/Stock" has cyclic frequency of 30 days
- Last inventory date was January 1, 2025
- Scheduled inventory date calculates to January 31, 2025

`Source: addons/stock/models/stock_quant.py:124-129`

---

### 2.3 Inventory Difference Calculation

**Field:** `inventory_diff_quantity`

**Formula:** `Difference = Counted Quantity - On-Hand Quantity`

| Value | Meaning |
|-------|---------|
| **Positive** | Physical count found MORE than system shows (inventory gain) |
| **Negative** | Physical count found LESS than system shows (inventory loss) |
| **Zero** | Physical count matches system records |

**Conditions:**
- Only calculated when `inventory_quantity_set` is True (user has initiated a count)
- Returns 0 if no count is in progress

**Business Rationale:**
The difference indicates the adjustment that will be made when the count is applied. Positive differences create incoming moves from the "Inventory Loss" virtual location. Negative differences create outgoing moves to the "Inventory Loss" location.

**Triggers:** Recalculated when `inventory_quantity` or `inventory_quantity_set` changes.

**Visual Indicator:** The difference column uses color coding:
- **Red background:** Negative difference (loss)
- **Green background:** Positive difference (gain)
- **White/neutral:** Zero difference

`Source: addons/stock/models/stock_quant.py:185-191`

---

### 2.4 Outdated Detection

**Field:** `is_outdated`

**Purpose:** Flags quants where the stock has moved since the user started counting.

**Detection Logic:**
1. Compare: `(Counted Quantity) - (Difference)` versus `(Current On-Hand Quantity)`
2. If they don't match (using UoM-aware comparison), the count is outdated
3. Only applies when a count is in progress (`inventory_quantity_set = True`)

| Condition | Result |
|-----------|--------|
| No stock movement since count started | `is_outdated = False` |
| Stock received or shipped after count started | `is_outdated = True` |

**Business Rationale:**
If a warehouse receives or ships goods while a count is in progress, the original difference becomes incorrect. This flag alerts users that they need to re-verify their count or choose how to resolve the conflict.

**What the user sees:**
- Outdated rows are highlighted in **yellow**
- Applying the adjustment opens a conflict resolution wizard

**Resolution Options:**
1. **Keep Counted Quantity:** System recalculates the difference based on new on-hand quantity
2. **Keep Difference:** System applies the original difference, adjusting the counted quantity

**Triggers:** Recalculated when `inventory_quantity`, `quantity`, or `product_id` changes.

`Source: addons/stock/models/stock_quant.py:197-202`

---

### 2.5 Duplicate Serial Number Detection

**Field:** `sn_duplicated`

**Purpose:** Identifies serial numbers that exist in multiple locations with positive quantities.

**Detection Logic:**
1. Find all quants with serial tracking (`tracking = 'serial'`)
2. Filter to those with positive quantities in internal/transit locations
3. Group by serial number and count occurrences
4. Flag all quants whose serial number appears more than once

| Condition | Result |
|-----------|--------|
| Serial number exists in one location only | `sn_duplicated = False` |
| Serial number exists in multiple locations | `sn_duplicated = True` |

**Business Rationale:**
Serial number duplication indicates a data quality issue—either incorrect data entry or a system bug. This flag helps inventory managers identify and correct these issues before they cause problems with traceability, returns, or audits.

**What the user sees:**
- Duplicate serial numbers are highlighted for attention
- Users should investigate and correct the root cause

**Triggers:** Recalculated when `lot_id` changes.

`Source: addons/stock/models/stock_quant.py:216-223`

---

## 3. Inventory Mode

**Inventory Mode** is a special operational context that enables direct manipulation of inventory quantities through the Physical Inventory interface.

### 3.1 What is Inventory Mode?

Inventory Mode is activated automatically when users access the **Physical Inventory** view through *Inventory → Operations → Physical Inventory*. It provides a controlled environment for making inventory adjustments.

**Activation Conditions:**
1. Context contains `inventory_mode = True`
2. User belongs to the **Inventory / User** security group (`stock.group_stock_user`)

`Source: addons/stock/models/stock_quant.py:1221-1226`

### 3.2 Behaviors in Inventory Mode

| Action | Normal Mode | Inventory Mode |
|--------|-------------|----------------|
| View quants | All locations visible | Only internal and transit locations |
| Create quant | Not allowed for users | Allowed with restrictions |
| Edit quant | Not allowed for users | Only specific fields editable |
| Delete quant | Not allowed | Sets quantity to zero via adjustment |
| Change on-hand quantity | Via stock moves only | Via inventory_quantity field |

### 3.3 Field Restrictions

**Fields editable during inventory adjustments:**
- `inventory_quantity` - The counted quantity
- `inventory_quantity_auto_apply` - For automatic adjustment
- `inventory_diff_quantity` - Difference calculation
- `inventory_date` - Scheduled count date
- `user_id` - Assigned counter
- `inventory_quantity_set` - Count in progress flag
- `is_outdated` - Outdated flag
- `lot_id` - Lot/Serial (for new lines)
- `location_id` - Location (for new lines)
- `package_id` - Package (for new lines)

**Fields NOT editable once quant exists:**
- `product_id` - Cannot change the product
- Core location, lot, package, owner (on existing records)

`Source: addons/stock/models/stock_quant.py:1228-1241`

### 3.4 Creating New Inventory Lines

When adding a product that doesn't have an existing quant at a specific location/lot/package/owner combination, Inventory Mode allows creation with:

**Allowed fields for creation:**
- `product_id` - Required
- `owner_id` - Optional
- All fields allowed for editing (see above)

**Automatic behaviors:**
- System searches for existing quants matching the product/location/lot/package/owner combination
- If found, updates the existing quant instead of creating a duplicate
- If not found, creates a new quant with quantity = 0, then applies the adjustment

`Source: addons/stock/models/stock_quant.py:252-313`

---

## 4. Removal Strategies

While primarily related to outbound operations, removal strategies affect inventory management by determining which quants are selected when fulfilling orders.

### 4.1 Available Removal Strategies

| Strategy | Method Code | Selection Priority | Best Used For |
|----------|-------------|-------------------|---------------|
| **First In First Out (FIFO)** | `fifo` | Oldest incoming date first | Perishables, dated items, standard warehousing |
| **Last In First Out (LIFO)** | `lifo` | Newest incoming date first | Non-perishables with frequent price changes |
| **Closest Location** | `closest` | Nearest to the packing zone | Large warehouses, minimizing travel time |
| **Least Packages** | `least_packages` | Fewest package movements | Reducing handling, pallet-level operations |

`Source: addons/stock/data/stock_data.xml:4-19`

### 4.2 Strategy Determination Hierarchy

When selecting products for outbound moves, the system determines the removal strategy by:

1. **Product Category Level:** Check if the product's category has a forced removal strategy
2. **Location Hierarchy:** Walk up the location tree checking for removal strategy settings
3. **Default:** Use FIFO if no strategy is explicitly configured

```
Decision Flow:
Product Category Removal Strategy? → Use that
    ↓ (No)
Current Location has Removal Strategy? → Use that
    ↓ (No)
Parent Location has Removal Strategy? → Use that
    ↓ (No, continue to root)
Default → FIFO
```

`Source: addons/stock/models/stock_quant.py:617-627`

### 4.3 Impact on Inventory Counts

Removal strategies affect inventory counts in these ways:

- **FIFO/LIFO:** Items with specific incoming dates may have higher count priority due to age
- **Closest:** Physical proximity may influence count scheduling routes
- **Lot-based products:** Strategy determines which lots are depleted first, affecting which lots need counting

---

## 5. Access Control

### 5.1 Security Groups

| Group | Technical Name | Permissions |
|-------|----------------|-------------|
| **Inventory / User** | `stock.group_stock_user` | View inventory, enter counts, start counts |
| **Inventory / Manager** | `stock.group_stock_manager` | Full access including apply adjustments, delete quants |

### 5.2 Permission Matrix

| Action | User Group | Manager Group |
|--------|------------|---------------|
| View Physical Inventory | ✅ | ✅ |
| View On Hand Quantities | ✅ | ✅ |
| Enter counted quantities | ✅ | ✅ |
| Set "Count to quantity on hand" | ✅ | ✅ |
| Apply inventory adjustments | ❌ | ✅ |
| Clear all counts | ❌ | ✅ |
| Delete quant records | ❌ | ✅ |
| Relocate inventory | ❌ | ✅ |
| Assign users to count | ❌ | ✅ |
| Request inventory counts | ❌ | ✅ |

`Source: addons/stock/security/ir.model.access.csv:21-22`

### 5.3 Record-Level Rules

**User Assignment Filtering:**
- When a User (not Manager) opens Physical Inventory, the view defaults to showing only items assigned to them (`search_default_my_count = True`)
- Managers see all items by default

**Company Isolation:**
- Quants are company-specific through the location's company assignment
- Users only see quants in locations belonging to their current company

`Source: addons/stock/models/stock_quant.py:410-411`

---

## 6. Adjustment Move Creation

When an inventory adjustment is applied, the system creates stock moves to reconcile the system quantity with the physical count.

### 6.1 Move Direction Logic

| Difference | Move Direction | Move Type |
|------------|----------------|-----------|
| **Positive** (found more) | FROM Inventory Loss → TO Stock Location | Incoming adjustment |
| **Negative** (found less) | FROM Stock Location → TO Inventory Loss | Outgoing adjustment |
| **Zero** | No move created | No adjustment needed |

### 6.2 Inventory Loss Location

The **Inventory Loss** location (`property_stock_inventory` on the product) is a virtual location used as the counterpart for adjustments:

- **For gains:** Products "appear" from this location
- **For losses:** Products "disappear" to this location

This maintains double-entry integrity while capturing inventory discrepancies.

### 6.3 Move Properties

Adjustment moves are created with specific properties:

| Property | Value | Purpose |
|----------|-------|---------|
| `is_inventory` | True | Marks move as inventory adjustment |
| `state` | confirmed | Bypasses draft state |
| `picked` | True | Indicates immediate transfer |
| `inventory_name` | User-provided reason | Audit trail description |

`Source: addons/stock/models/stock_quant.py:995-1025, 1243-1281`

---

## 7. Conflict Resolution Rules

### 7.1 Conflict Detection

A conflict occurs when:
- A count is in progress (`inventory_quantity_set = True`)
- Stock movement occurs affecting the same product/location
- The `is_outdated` flag becomes True

### 7.2 Resolution Options

When applying an adjustment with conflicts, users must choose:

| Option | Behavior | When to Use |
|--------|----------|-------------|
| **Keep Counted Quantity** | Recalculates difference: `new_diff = counted - new_on_hand` | When you're confident in your physical count |
| **Keep Difference** | Recalculates counted: `new_counted = new_on_hand + original_diff` | When you want to apply the same adjustment regardless of movements |

### 7.3 Conflict Prevention

To minimize conflicts:
- Complete counts and apply adjustments promptly
- Avoid scheduling counts during peak receiving/shipping times
- Use cycle counting during slower periods
- Communicate count schedules to prevent simultaneous operations

---

## 8. Related Business Rules

### 8.1 Quant Duplication Prevention

**Rule:** Quant records cannot be duplicated.

Attempting to copy a quant record raises an error: "You cannot duplicate stock quants."

**Rationale:** Each quant represents a specific inventory position. Duplication would create phantom inventory.

`Source: addons/stock/models/stock_quant.py:245-246`

### 8.2 Quant Deletion Behavior

**Rule:** Only managers can delete quants, and deletion is converted to a zero-quantity adjustment.

When a manager deletes a quant:
1. System sets `inventory_quantity = 0`
2. System applies the adjustment (creating a move to Inventory Loss)
3. Original quant may remain with zero quantity or be cleaned up

**Rationale:** Direct deletion would create orphaned stock moves and break audit trails.

`Source: addons/stock/models/stock_quant.py:362-369`

### 8.3 Negative Inventory Handling

**Rule:** Quants can have negative quantities in certain circumstances.

Negative quants occur when:
- Products are shipped before being received (back orders)
- Adjustments create negative on-hand
- Timing issues between receiving and consuming

**Impact:** Negative quants still participate in available quantity calculations and must be resolved by incoming stock.

---

## Summary

The inventory adjustment business rules work together to maintain:

1. **Data Integrity:** Validation rules prevent invalid inventory records
2. **Real-time Accuracy:** Computed fields keep information current
3. **Controlled Access:** Security groups restrict sensitive operations
4. **Audit Trail:** All adjustments create traceable stock moves
5. **Conflict Management:** Outdated detection prevents stale adjustments

For step-by-step instructions on performing inventory adjustments, see the [Inventory Adjustment User Flow](../02-user-flows/15-inventory-adjustment/flow-document.md).
