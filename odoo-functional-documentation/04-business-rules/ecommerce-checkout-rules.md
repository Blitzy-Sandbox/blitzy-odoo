# Business Rules: eCommerce Checkout

## Overview

This document describes the business rules that govern the eCommerce checkout workflow in Odoo 19.0. These rules define how the system validates data, calculates values, and manages the shopping cart throughout the online purchasing process.

The eCommerce checkout extends Odoo's standard Sales Order functionality with website-specific features for online stores. Understanding these rules helps customer support teams explain system behavior and troubleshoot checkout issues.

**Related Flow Documentation:** [Website eCommerce Checkout Flow](../02-user-flows/13-website-ecommerce-checkout/flow-document.md)

---

## 1. Validation Logic

The system enforces several validation rules to ensure data integrity and prevent configuration errors during checkout.

### 1.1 Pricelist and Company Consistency

**Rule:** When a pricelist is assigned to a specific website, the pricelist's company must match the website's company.

| Field | Validation Rule |
|-------|-----------------|
| `pricelist.website_id` | If set, must belong to the same company as `pricelist.company_id` |
| `pricelist.company_id` | If set along with `website_id`, companies must match |

**What This Means for Users:**
- A pricelist configured for "Company A" cannot be used on a website belonging to "Company B"
- This prevents pricing conflicts in multi-company environments
- To use a pricelist across multiple companies, leave the pricelist's Company field empty

**Error Message When Violated:**
> "Only the company's websites are allowed. Leave the Company field empty or select a website from that company."

*Source: `addons/website_sale/models/product_pricelist.py:42-53`*

---

### 1.2 Base Unit Count Validation

**Rule:** Products displayed in the eCommerce shop must have a non-negative base unit count.

| Field | Validation Rule |
|-------|-----------------|
| `product.base_unit_count` | Must be greater than or equal to 0 |

**What This Means for Users:**
- The **Base Unit Count** determines how the "price per unit" is displayed on the shop
- Setting it to **0** hides the price-per-unit display for that product
- Any positive value (e.g., 1, 0.5, 100) calculates price-per-unit as: `Product Price ÷ Base Unit Count`
- Negative values are not allowed

**Example:**
- A 500ml bottle of juice priced at $2.50 with base_unit_count = 0.5 displays "$5.00 per liter"
- Setting base_unit_count = 0 hides this calculation entirely

**Error Message When Violated:**
> "The value of Base Unit Count must be greater than 0. Use 0 to hide the price per unit on this product."

*Source: `addons/website_sale/models/product_product.py:82-88`*

---

### 1.3 Video URL Validation

**Rule:** Product images with video URLs must link to valid, embeddable video platforms (YouTube, Vimeo, etc.).

| Field | Validation Rule |
|-------|-----------------|
| `product.image.video_url` | Must generate a valid embed code when provided |

**What This Means for Users:**
- Product galleries can include video content alongside images
- Only videos from supported platforms (YouTube, Vimeo, Dailymotion) can be embedded
- Invalid or unsupported video URLs are rejected

**Supported Video Formats:**
- YouTube: `https://www.youtube.com/watch?v=XXXXX` or `https://youtu.be/XXXXX`
- Vimeo: `https://vimeo.com/XXXXX`

**Error Message When Violated:**
> "Provided video URL for '[Image Name]' is not valid. Please enter a valid video URL."

*Source: `addons/website_sale/models/product_image.py:63-67`*

---

### 1.4 Product Feed Category Limit

**Rule:** Product feeds (for Google Merchant Center) have a limit on the number of products they can contain.

| Setting | Value | Description |
|---------|-------|-------------|
| Soft Limit | 5,000 products | Warning threshold |
| Hard Limit | 6,000 products | Absolute maximum during rendering |

**What This Means for Users:**
- When creating a Google Merchant Center feed, the selected categories cannot include more than 5,000 products combined
- If you need to export more products, create multiple feeds with different category selections
- Feeds exceeding the limit display an error during save

**Error Message When Violated:**
> "A single feed cannot contain more than 5,000 products. Please separate products with Categories."

*Source: `addons/website_sale/models/product_feed.py:95-110`*

---

### 1.5 Cart Readiness Validation

**Rule:** Before proceeding to payment, the cart must pass several validation checks.

| Check | Requirement | Error When Failed |
|-------|-------------|-------------------|
| Cart has items | At least one product in the cart | "Your cart is not ready to be paid, please verify previous steps." |
| Delivery method selected | Required for physical products | "No shipping method is selected." |
| Delivery method valid | Must be compatible with shipping address | "The delivery method is not compatible with your delivery address." |

**Services-Only Orders:**
- If the cart contains only service products (no physical goods), delivery method selection is skipped
- The system automatically removes any delivery charges when only services are in the cart

*Source: `addons/website_sale/models/sale_order.py:880-903`*

---

## 2. Computation Rules

The following fields are automatically calculated by the system based on the cart contents and website configuration.

### 2.1 Website Order Lines (Displayable Cart Items)

**Field:** `sale.order.website_order_line`  
**Depends on:** `order_line`

**Calculation Logic:**
1. Retrieves all order lines for the current cart
2. Filters to show only lines that should appear in the cart display
3. Excludes lines marked as non-displayable (e.g., internal adjustments, certain discount lines)

**What Users See:**
- The cart page shows only relevant product lines
- Delivery charges, promotional items, and other system-generated lines may be displayed separately
- Hidden lines still contribute to the order total but aren't shown in the product list

*Source: `addons/website_sale/models/sale_order.py:52-59`*

---

### 2.2 Delivery Amount Calculation

**Field:** `sale.order.amount_delivery`  
**Depends on:** `order_line.price_total`, `order_line.price_subtotal`

**Calculation Logic:**

```
If website displays prices with "Tax Included":
    Delivery Amount = Sum of delivery lines' price_total (tax included)
Else (Tax Excluded):
    Delivery Amount = Sum of delivery lines' price_subtotal (tax excluded)
```

| Website Tax Display Setting | Uses Field | Example |
|----------------------------|------------|---------|
| Tax Included | `price_total` | $10.00 shipping shows as $10.00 |
| Tax Excluded | `price_subtotal` | $10.00 shipping (with 10% tax) shows as $9.09 |

**What Users See:**
- The delivery amount shown on the cart and checkout pages matches the website's tax display preference
- This setting is configured per website under "Line Subtotals Tax Display"

*Source: `addons/website_sale/models/sale_order.py:61-69`*

---

### 2.3 Cart Information (Quantity and Services Flag)

**Fields:** 
- `sale.order.cart_quantity` - Total number of items in the cart
- `sale.order.only_services` - Whether the cart contains only service products

**Depends on:** `order_line.product_uom_qty`, `order_line.product_id`

**Calculation Logic:**

| Field | Formula |
|-------|---------|
| `cart_quantity` | Sum of quantities from all displayable order lines (rounded to whole number) |
| `only_services` | True if ALL products in the cart have type = 'service' |

**What Users See:**
- The cart icon in the header shows the `cart_quantity` number
- If `only_services` is true:
  - Delivery method selection is skipped
  - Shipping address may be optional
  - The checkout flow is streamlined for digital/service purchases

**Example:**
| Cart Contents | cart_quantity | only_services |
|---------------|---------------|---------------|
| 2 T-shirts + 1 Consulting Hour | 3 | False |
| 3 Online Course Subscriptions | 3 | True |

*Source: `addons/website_sale/models/sale_order.py:71-75`*

---

### 2.4 Abandoned Cart Detection

**Field:** `sale.order.is_abandoned_cart`  
**Depends on:** `website_id`, `date_order`, `order_line`, `state`, `partner_id`

**Calculation Logic:**

A cart is considered **abandoned** when ALL of the following conditions are true:

| Condition | Description |
|-----------|-------------|
| Has website | Order was created through the eCommerce checkout |
| State is 'draft' | Order has not been confirmed |
| Has order date | The cart was created at a specific time |
| Not public user | Customer is logged in (not a guest) |
| Has items | Cart contains at least one product |
| Delay exceeded | Cart age exceeds the website's `cart_abandoned_delay` setting |

**Abandoned Delay Calculation:**
```
Abandoned Datetime = Current Time - Website's Abandoned Delay (in hours)
Is Abandoned = Order Date ≤ Abandoned Datetime
```

**Default Settings:**
- The default abandoned delay is **10 hours** (configurable per website)
- If no delay is configured, the system falls back to **1 hour**

**What This Enables:**
- Automated abandoned cart recovery emails
- Dashboard reports showing abandoned carts
- Sales team follow-up on high-value abandoned orders

**Important:** Guest carts (linked to the website's public user) are never marked as abandoned because there's no customer email to send recovery notifications to.

*Source: `addons/website_sale/models/sale_order.py:77-89`*

---

### 2.5 Signature Requirement Override

**Field:** `sale.order.require_signature`

**Website Behavior:**
- Orders placed through the website **never** require a signature
- This overrides any company-level signature requirements
- The confirmation occurs through the payment process instead

*Source: `addons/website_sale/models/sale_order.py:91-94`*

---

### 2.6 Payment Term Default

**Field:** `sale.order.payment_term_id`

**Website Behavior:**
When a website order doesn't have a payment term set:
1. The system looks for the "Immediate Payment" term in the company
2. If not found, it searches for any available payment term in the company
3. This ensures website orders always have a valid payment term

*Source: `addons/website_sale/models/sale_order.py:96-116`*

---

### 2.7 Pricelist Computation with GeoIP

**Field:** `sale.order.pricelist_id`

**Enhanced Logic for Website Orders:**
- If the visitor's location can be determined (via GeoIP):
  - The system checks if there's a pricelist specific to their country
  - Country-specific pricelists take precedence over default pricelists
- This enables automatic currency and pricing adjustments based on customer location

*Source: `addons/website_sale/models/sale_order.py:118-126`*

---

## 3. Cart State Management

The eCommerce cart uses Odoo's standard Sales Order states with website-specific behaviors at each stage.

### 3.1 Cart States

| State | Display Name | Description | User Experience |
|-------|--------------|-------------|-----------------|
| `draft` | Quotation (Cart) | Items added to cart, not yet checked out | Customer can modify quantities, add/remove items |
| `sent` | Quotation Sent | Cart has been processed but not confirmed | Rare in eCommerce; typically skipped |
| `sale` | Sales Order | Order confirmed after successful payment | Customer receives confirmation email |
| `cancel` | Cancelled | Order was cancelled or payment failed | Cart is no longer accessible |

### 3.2 State Transitions in eCommerce

```
     [Visitor Adds Product]
              │
              ▼
         ┌─────────┐
         │  draft  │ ◄──── Customer modifies cart
         │ (Cart)  │
         └────┬────┘
              │
              │ [Successful Payment]
              ▼
         ┌─────────┐
         │  sale   │ ──── Confirmation email sent
         │ (Order) │      Salesperson assigned
         └─────────┘
              │
              │ [Manual Cancellation]
              ▼
         ┌─────────┐
         │ cancel  │
         └─────────┘
```

### 3.3 Cart Lifecycle Events

| Event | System Actions |
|-------|----------------|
| **Product Added** | Creates new draft order (if none exists) or adds line to existing cart |
| **Quantity Updated** | Recalculates line totals, delivery costs, and taxes |
| **Address Changed** | Updates fiscal position, recalculates taxes, updates delivery options |
| **Delivery Selected** | Adds delivery line to order, calculates shipping cost |
| **Payment Submitted** | Creates payment transaction, processes with provider |
| **Payment Confirmed** | Confirms order, assigns salesperson, sends confirmation email |
| **Cart Abandoned** | After delay, marked as abandoned for recovery campaigns |

*Source: `addons/website_sale/models/sale_order.py:249-256`*

---

## 4. Cart Operations Business Logic

### 4.1 Adding Products to Cart

**Method:** `_cart_add(product_id, quantity, uom_id, **kwargs)`

**Business Logic:**
1. **Check for Existing Line:** Search for a matching line with the same product, UOM, and attributes
2. **If Match Found:** Update the existing line's quantity instead of creating a new line
3. **If No Match:** Create a new order line with the specified product and quantity
4. **Verify Quantity:** Apply any stock availability or minimum order rules
5. **Update Cart:** Recalculate totals and refresh delivery costs if applicable

**Line Matching Criteria:**
- Same product ID
- Same Unit of Measure
- Same no-variant attribute values (e.g., custom options)
- No custom text attribute values
- Not linked to a different parent line (for optional products)
- Not a combo item line

*Source: `addons/website_sale/models/sale_order.py:328-374`*

---

### 4.2 Updating Cart Line Quantity

**Method:** `_cart_update_line_quantity(line_id, quantity, **kwargs)`

**Business Logic:**
1. **Locate the Line:** Find the order line by ID within the current cart
2. **Validate Line Exists:** Return error if line not found (may have been modified in another tab)
3. **If Quantity > 0:** Verify the new quantity against availability rules
4. **If Quantity ≤ 0:** Remove the line from the cart
5. **Update and Recalculate:** Apply changes and refresh cart totals

**Special Handling for Combo Products:**
- When updating a combo product quantity, all linked combo items must also update
- If any combo item has insufficient stock, the entire combo quantity is reduced to match

**Warning Message for Missing Line:**
> "We weren't able to update your cart. Please refresh your page before trying again."

*Source: `addons/website_sale/models/sale_order.py:428-479`*

---

### 4.3 Cart Verification After Updates

**Method:** `_verify_cart_after_update()`

**Automatic Actions:**
1. **Services-Only Check:** If cart contains only services, remove any delivery line
2. **Delivery Recalculation:** If a delivery method is selected and physical products exist:
   - Recalculate the shipping rate based on current cart contents
   - If the rate cannot be calculated, remove the delivery line
3. **Session Update:** Store the current cart quantity in the user's session

*Source: `addons/website_sale/models/sale_order.py:647-664`*

---

### 4.4 Address Update Logic

**Method:** `_update_address(partner_id, fnames)`

**Business Logic When Address Changes:**
1. **Update Order Fields:** Apply the new address to specified fields (billing, shipping)
2. **Fiscal Position Check:** Recalculate fiscal position based on new address
3. **Tax Recalculation:** If fiscal position changed, recompute all line taxes
4. **Pricelist Check:** Verify if the manually selected pricelist is still valid for the new country
5. **Price Recalculation:** If pricelist changed, update all product prices
6. **Delivery Update:** If shipping address changed and a carrier is selected, recalculate delivery options

**Session Cache Updates:**
- Fiscal position ID stored for the session
- Pricelist ID stored for the session

*Source: `addons/website_sale/models/sale_order.py:279-326`*

---

## 5. Access Control

### 5.1 User Types and Cart Access

| User Type | Cart Creation | Checkout Capability | Order History |
|-----------|---------------|---------------------|---------------|
| **Public User (Guest)** | Yes - Session-based cart | Guest checkout (if enabled) | No access |
| **Portal User (Logged In)** | Yes - Linked to account | Full checkout access | View past orders |
| **Internal User** | Backend access only | N/A (uses backend Sales) | Full management |

### 5.2 Anonymous Cart Handling

**Method:** `_is_anonymous_cart()`

**Definition:** A cart is considered anonymous when:
- The cart's partner is the website's public user (guest)
- No customer address has been added yet

**Implications:**
- Anonymous carts cannot be recovered via email (no contact information)
- Checkout requires at least an email address to proceed
- Anonymous carts are not marked as "abandoned" for recovery campaigns

*Source: `addons/website_sale/models/sale_order.py:853-862`*

---

### 5.3 Product Visibility Rules

**Add to Cart Permission:**
Products can only be added to cart when:

| Condition | Requirement |
|-----------|-------------|
| Product Active | Product must not be archived |
| Website Published | Product must be published on the website |
| Website Domain | Product must match the website's product domain filters |
| Zero Price | If website prevents zero-price sales, product must have a non-zero price |
| eCommerce Access | Website must have eCommerce access enabled |

**Exception:** System administrators can add any product regardless of these restrictions.

*Source: `addons/website_sale/models/product_product.py:138-148`*

---

## 6. Pricelist Application Rules

### 6.1 Website Pricelist Availability

A pricelist can be used on a website when ANY of the following conditions is met:

| Condition | Description |
|-----------|-------------|
| **Website-Specific** | Pricelist has `website_id` matching the current website |
| **Generic + Selectable** | No `website_id` set AND marked as "Selectable" |
| **Generic + Promo Code** | No `website_id` set AND has a promotional code defined |

**Company Restriction:**
- If the pricelist has a company set, it must match the website's company
- Pricelists without a company can be used on any website

*Source: `addons/website_sale/models/product_pricelist.py:98-113`*

---

### 6.2 Country-Based Pricelist Filtering

**Method:** `_is_available_in_country(country_code)`

**Logic:**
- If pricelist has no country groups defined: Available in all countries
- If pricelist has country groups: Customer's country must be in one of the defined groups

This enables scenarios like:
- EUR pricelist for European countries
- USD pricelist for North America
- Special pricing for specific regions

*Source: `addons/website_sale/models/product_pricelist.py:115-119`*

---

## 7. Integration Points

### 7.1 Payment Provider Integration

**Order Confirmation Flow:**
1. Customer selects payment method
2. Payment transaction created and linked to cart
3. Payment processed by provider
4. On success: `action_confirm()` called on the cart
5. Cart transitions from `draft` to `sale`
6. Salesperson assigned automatically
7. Confirmation email sent using website-specific template (if configured)

*Source: `addons/website_sale/models/sale_order.py:249-262`*

---

### 7.2 Delivery Method Integration

**Getting Available Delivery Methods:**
```
1. Search for carriers where:
   - website_published = True
   - Company matches order company
2. Filter to those available for the current order
```

**Setting Delivery Method:**
1. Remove any existing delivery line
2. Calculate shipping rate with selected carrier
3. If rate calculation succeeds, add delivery line with calculated price
4. If calculation fails (e.g., address not supported), no delivery line added

*Source: `addons/website_sale/models/sale_order.py:844-849`*

---

### 7.3 Abandoned Cart Recovery Integration

**Recovery Email Eligibility:**

A cart qualifies for recovery email when ALL conditions are met:
- Customer has an email address
- No payment processing errors occurred
- At least one item has a non-zero price
- Customer hasn't completed another order since creating this cart

**Recovery Email Process:**
1. System marks cart as `is_abandoned_cart`
2. Recovery email template selected (website-specific or default)
3. Email includes secure link to resume the cart
4. After sending, `cart_recovery_email_sent` flag set to True

*Source: `addons/website_sale/models/sale_order.py:748-788`*

---

## 8. Website Configuration Impact

The following website settings affect checkout behavior:

### 8.1 Customer Account Settings

| Setting | Value | Checkout Behavior |
|---------|-------|-------------------|
| `account_on_checkout` | `optional` | Customer can checkout as guest or create account |
| `account_on_checkout` | `disabled` | Guest checkout only, no account creation |
| `account_on_checkout` | `mandatory` | Account required to complete checkout |

### 8.2 Tax Display Settings

| Setting | Value | Price Display |
|---------|-------|---------------|
| `show_line_subtotals_tax_selection` | `tax_excluded` | Prices shown without tax, tax added at totals |
| `show_line_subtotals_tax_selection` | `tax_included` | Prices shown with tax included |

### 8.3 Cart Behavior Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `add_to_cart_action` | `stay` | Whether to stay on product page or go to cart after adding |
| `cart_abandoned_delay` | 10.0 hours | Time before cart is considered abandoned |
| `prevent_zero_price_sale` | False | Whether to prevent adding zero-priced products |

*Source: `addons/website_sale/models/website.py:70-110`*

---

## 9. Error Scenarios and Handling

### 9.1 Common Checkout Errors

| Error Scenario | System Response | User Message |
|----------------|-----------------|--------------|
| Product out of stock | Quantity adjusted or line removed | Warning shown with available quantity |
| Invalid combination | Cannot add to cart | "The given combination does not exist therefore it cannot be added to cart." |
| Pricelist not available | Falls back to default pricelist | (Transparent to user) |
| Delivery calculation fails | Delivery line removed | User must select different method |
| Payment fails | Remains on payment page | Provider-specific error message |
| Session expired | Cart may be lost | User prompted to log in |

### 9.2 Cart Validation Warnings

**Shop Warning Field:** `sale.order.shop_warning`

This field stores temporary warning messages displayed to customers:
- Stock availability warnings
- Quantity adjustment notifications
- Promotional code issues

Messages are cleared after being displayed (controlled by `clear` parameter).

*Source: `addons/website_sale/models/sale_order.py:873-878`*

---

## 10. Source Code References

For technical implementation details, refer to these source files:

| Component | File Path |
|-----------|-----------|
| Website Sale Order Extension | `addons/website_sale/models/sale_order.py` |
| Pricelist Website Integration | `addons/website_sale/models/product_pricelist.py` |
| Product Website Features | `addons/website_sale/models/product_product.py` |
| Product Image/Video | `addons/website_sale/models/product_image.py` |
| Product Feed | `addons/website_sale/models/product_feed.py` |
| Website Configuration | `addons/website_sale/models/website.py` |
| Cart Controller | `addons/website_sale/controllers/cart.py` |
| Checkout Controller | `addons/website_sale/controllers/main.py` |
| Payment Controller | `addons/website_sale/controllers/payment.py` |

---

## Glossary

| Term | Definition |
|------|------------|
| **Cart** | A draft sales order created when a visitor adds products on the website |
| **Abandoned Cart** | A cart that hasn't been completed within the configured delay period |
| **Pricelist** | A set of rules that determine product prices based on conditions |
| **Fiscal Position** | Tax configuration that maps taxes based on customer location |
| **Base Unit Count** | A divisor used to calculate the price-per-unit display |
| **Combo Product** | A product that includes multiple component items sold together |
| **Portal User** | A customer with a login account on the website |
| **Public User** | The anonymous/guest user used for unauthenticated visitors |

---

*Document generated from Odoo 19.0 Community Edition source code analysis.*
*Last updated based on source files in `addons/website_sale/` module.*
