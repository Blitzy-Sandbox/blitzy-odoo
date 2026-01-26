# Odoo 19.0 Functional Documentation

Welcome to the comprehensive functional documentation for **Odoo 19.0 Community Edition**. This documentation is designed for **customer support teams** and **business analysts** who need to understand how Odoo works from a user perspective.

---

## About This Documentation

This documentation covers the practical, day-to-day use of Odoo's core business applications. You'll find:

- **Step-by-step guides** for common business workflows
- **Screenshots** showing exactly what you'll see in the system
- **Business rules** explaining how Odoo calculates values and enforces policies
- **A glossary** of business and Odoo-specific terminology

This is **not** developer documentation. If you're looking for technical information about customizing Odoo, please visit the [official Odoo Developer Documentation](https://www.odoo.com/documentation/19.0/developer/tutorials/backend.html).

---

## Who Should Use This Documentation

| Audience | What You'll Find |
|----------|------------------|
| **Customer Support Representatives** | Guides to help troubleshoot user questions about workflows, common errors, and expected system behavior |
| **Business Analysts** | Detailed process flows, business rules, and integration points between modules |
| **End Users** | Step-by-step instructions for completing tasks with screenshots |
| **Implementation Consultants** | Comprehensive understanding of out-of-the-box functionality |

---

## Table of Contents

### 1. Capabilities Overview

Understand what Odoo can do and learn the terminology used throughout the system.

| Document | Description |
|----------|-------------|
| [Module Capabilities & Glossary](01-capabilities-overview/capabilities-inventory.md) | Complete inventory of 34 business applications, their features, integration points, and a comprehensive glossary of Odoo terms |

---

### 2. User Workflow Guides

Complete step-by-step guides for the 15 most common business processes. Each guide includes:
- Overview and business context
- Prerequisites and permissions needed
- Visual workflow diagrams
- Screenshot-illustrated step-by-step instructions
- Common variations and edge cases

#### Sales & CRM

| # | Workflow | Description | Module |
|---|----------|-------------|--------|
| 01 | [Sales: Quote to Order](02-user-flows/01-sales-quote-to-order/flow-document.md) | Create a quotation, send it to a customer, and convert it to a confirmed sales order | Sales |
| 02 | [CRM: Lead to Opportunity](02-user-flows/02-crm-lead-to-opportunity/flow-document.md) | Capture a new lead, qualify it, convert to an opportunity, and mark as won or lost | CRM |

#### Purchasing & Supply Chain

| # | Workflow | Description | Module |
|---|----------|-------------|--------|
| 03 | [Purchase: RFQ to Purchase Order](02-user-flows/03-purchase-rfq-to-po/flow-document.md) | Create a request for quotation, send to vendor, and confirm as a purchase order | Purchase |
| 04 | [Inventory: Receipt Processing](02-user-flows/04-inventory-receipt-processing/flow-document.md) | Receive goods from a vendor, validate quantities, and update inventory | Inventory |
| 05 | [Inventory: Delivery Order](02-user-flows/05-inventory-delivery-order/flow-document.md) | Process a delivery order, reserve stock, and ship products to customers | Inventory |
| 08 | [Manufacturing: Production Order](02-user-flows/08-manufacturing-production-order/flow-document.md) | Create a manufacturing order from a bill of materials, process work orders, and mark production complete | Manufacturing |
| 15 | [Inventory: Inventory Adjustment](02-user-flows/15-inventory-adjustment/flow-document.md) | Count physical inventory, record variances, and apply adjustments to stock quantities | Inventory |

#### Finance & Accounting

| # | Workflow | Description | Module |
|---|----------|-------------|--------|
| 06 | [Invoicing: Create and Collect Payment](02-user-flows/06-invoice-creation-payment/flow-document.md) | Create a customer invoice, send it, and register the payment received | Invoicing |
| 07 | [Accounts Payable: Vendor Bill Payment](02-user-flows/07-vendor-bill-payment/flow-document.md) | Receive a vendor bill, match it to a purchase order, and process payment | Invoicing |
| 14 | [Accounting: Bank Reconciliation](02-user-flows/14-bank-reconciliation/flow-document.md) | Import bank statements, match transactions to invoices and payments, and reconcile accounts | Invoicing |

#### Retail & eCommerce

| # | Workflow | Description | Module |
|---|----------|-------------|--------|
| 09 | [Point of Sale: Session and Transaction](02-user-flows/09-pos-session-transaction/flow-document.md) | Open a POS session, process customer sales and payments, and close the session | Point of Sale |
| 13 | [eCommerce: Website Checkout](02-user-flows/13-website-ecommerce-checkout/flow-document.md) | Browse products online, add to cart, complete checkout, and place an order | eCommerce |

#### Human Resources

| # | Workflow | Description | Module |
|---|----------|-------------|--------|
| 11 | [HR: Employee Leave Request](02-user-flows/11-employee-leave-request/flow-document.md) | Submit a time-off request, manager approval process, and calendar updates | Time Off |
| 12 | [HR: Expense Claim Reimbursement](02-user-flows/12-expense-claim-reimbursement/flow-document.md) | Submit an expense report, attach receipts, get approval, and receive reimbursement | Expenses |

#### Project Management

| # | Workflow | Description | Module |
|---|----------|-------------|--------|
| 10 | [Project: Task Management](02-user-flows/10-project-task-management/flow-document.md) | Create projects, add and assign tasks, track progress through stages, and mark complete | Project |

---

### 3. Business Rules Reference

Detailed documentation of the rules and logic that govern how Odoo calculates values, validates data, and controls access.

#### Sales & CRM Rules

| Document | Description |
|----------|-------------|
| [Sales Quote to Order Rules](04-business-rules/sales-quote-to-order-rules.md) | Order states, required fields, price calculations, and discount policies |
| [CRM Lead to Opportunity Rules](04-business-rules/crm-lead-to-opportunity-rules.md) | Lead scoring, stage progression, probability calculations, and win/loss tracking |

#### Purchasing & Supply Chain Rules

| Document | Description |
|----------|-------------|
| [Purchase RFQ to PO Rules](04-business-rules/purchase-rfq-to-po-rules.md) | Approval thresholds, vendor terms, and order confirmation rules |
| [Inventory Receipt Rules](04-business-rules/inventory-receipt-rules.md) | Quantity validation, backorder handling, and putaway rules |
| [Inventory Delivery Rules](04-business-rules/inventory-delivery-rules.md) | Stock reservation, shipping policies, and partial delivery handling |
| [Manufacturing Rules](04-business-rules/manufacturing-rules.md) | Bill of materials, component consumption, work order sequencing |
| [Inventory Adjustment Rules](04-business-rules/inventory-adjustment-rules.md) | Count validation, variance limits, and stock valuation impact |

#### Finance & Accounting Rules

| Document | Description |
|----------|-------------|
| [Invoice and Payment Rules](04-business-rules/invoice-payment-rules.md) | Invoice posting, payment matching, and reconciliation rules |
| [Vendor Bill Rules](04-business-rules/vendor-bill-rules.md) | Three-way matching, duplicate detection, and payment processing |
| [Bank Reconciliation Rules](04-business-rules/bank-reconciliation-rules.md) | Matching algorithms, tolerance thresholds, and auto-reconciliation |

#### Retail & eCommerce Rules

| Document | Description |
|----------|-------------|
| [POS Session Rules](04-business-rules/pos-session-rules.md) | Cash control, session balancing, and closing procedures |
| [eCommerce Checkout Rules](04-business-rules/ecommerce-checkout-rules.md) | Cart management, abandoned cart detection, and checkout validation |

#### Human Resources Rules

| Document | Description |
|----------|-------------|
| [Leave Request Rules](04-business-rules/leave-request-rules.md) | Allocation balances, approval hierarchy, and accrual calculations |
| [Expense Claim Rules](04-business-rules/expense-claim-rules.md) | Receipt requirements, approval workflow, and reimbursement processing |

#### Project Management Rules

| Document | Description |
|----------|-------------|
| [Project Task Rules](04-business-rules/project-task-rules.md) | Task dependencies, stage transitions, and deadline handling |

---

### 4. Bug Findings

Issues discovered during documentation analysis that represent discrepancies between expected and actual system behavior.

| Document | Description |
|----------|-------------|
| [Discovered Issues](05-bug-findings/discovered-issues.md) | Documented bugs and inconsistencies found during the analysis process |

> **Note:** This documentation describes actual system behavior. Where documented bugs may affect a workflow, they are referenced in the relevant user guide.

---

## Documentation Conventions

### Screenshot Naming

All screenshots follow a consistent naming pattern:

```
[FlowNumber]-[StepNumber]-[description].png
```

**Examples:**
- `01-01-create-quotation.png` - First step of Flow 01 (Sales Quote)
- `06-03-register-payment.png` - Third step of Flow 06 (Invoice Payment)

### Workflow Diagrams

This documentation uses **Mermaid diagrams** to visualize processes. These diagrams show:

- **Sequence Diagrams**: Show the interaction between the user, the screen, and the system
- **State Diagrams**: Show how a document moves through different statuses

If you're viewing this documentation on GitHub, GitLab, or a compatible Markdown viewer, diagrams render automatically. If diagrams appear as code, you can use a [Mermaid Live Editor](https://mermaid.live/) to view them.

### Terminology

- **Bold terms** indicate the first use of a term that's defined in the [Glossary](01-capabilities-overview/capabilities-inventory.md#7-domain-terminology-glossary)
- `Monospace text` indicates field names, button labels, or menu items you'll see in the system
- *Italic text* indicates emphasis or notes

### User Actions

All step-by-step instructions are written from the user's perspective:

> "The user clicks `Create` to start a new quotation"

rather than technical language like:

> "The system calls the create() method on the sale.order model"

---

## Quick Navigation

### By Module

| Module | User Flows | Business Rules |
|--------|------------|----------------|
| **Sales** | [Quote to Order](02-user-flows/01-sales-quote-to-order/flow-document.md) | [Rules](04-business-rules/sales-quote-to-order-rules.md) |
| **CRM** | [Lead to Opportunity](02-user-flows/02-crm-lead-to-opportunity/flow-document.md) | [Rules](04-business-rules/crm-lead-to-opportunity-rules.md) |
| **Purchase** | [RFQ to PO](02-user-flows/03-purchase-rfq-to-po/flow-document.md) | [Rules](04-business-rules/purchase-rfq-to-po-rules.md) |
| **Inventory** | [Receipts](02-user-flows/04-inventory-receipt-processing/flow-document.md), [Deliveries](02-user-flows/05-inventory-delivery-order/flow-document.md), [Adjustments](02-user-flows/15-inventory-adjustment/flow-document.md) | [Receipt Rules](04-business-rules/inventory-receipt-rules.md), [Delivery Rules](04-business-rules/inventory-delivery-rules.md), [Adjustment Rules](04-business-rules/inventory-adjustment-rules.md) |
| **Invoicing** | [Customer Invoice](02-user-flows/06-invoice-creation-payment/flow-document.md), [Vendor Bill](02-user-flows/07-vendor-bill-payment/flow-document.md), [Bank Reconciliation](02-user-flows/14-bank-reconciliation/flow-document.md) | [Invoice Rules](04-business-rules/invoice-payment-rules.md), [Vendor Bill Rules](04-business-rules/vendor-bill-rules.md), [Reconciliation Rules](04-business-rules/bank-reconciliation-rules.md) |
| **Manufacturing** | [Production Order](02-user-flows/08-manufacturing-production-order/flow-document.md) | [Rules](04-business-rules/manufacturing-rules.md) |
| **Point of Sale** | [POS Session](02-user-flows/09-pos-session-transaction/flow-document.md) | [Rules](04-business-rules/pos-session-rules.md) |
| **Project** | [Task Management](02-user-flows/10-project-task-management/flow-document.md) | [Rules](04-business-rules/project-task-rules.md) |
| **Time Off** | [Leave Request](02-user-flows/11-employee-leave-request/flow-document.md) | [Rules](04-business-rules/leave-request-rules.md) |
| **Expenses** | [Expense Claim](02-user-flows/12-expense-claim-reimbursement/flow-document.md) | [Rules](04-business-rules/expense-claim-rules.md) |
| **eCommerce** | [Website Checkout](02-user-flows/13-website-ecommerce-checkout/flow-document.md) | [Rules](04-business-rules/ecommerce-checkout-rules.md) |

### By Task

| I want to... | Go to... |
|--------------|----------|
| Create a sales quote | [Sales: Quote to Order](02-user-flows/01-sales-quote-to-order/flow-document.md) |
| Follow up on a sales lead | [CRM: Lead to Opportunity](02-user-flows/02-crm-lead-to-opportunity/flow-document.md) |
| Order products from a supplier | [Purchase: RFQ to Purchase Order](02-user-flows/03-purchase-rfq-to-po/flow-document.md) |
| Receive a shipment | [Inventory: Receipt Processing](02-user-flows/04-inventory-receipt-processing/flow-document.md) |
| Ship products to a customer | [Inventory: Delivery Order](02-user-flows/05-inventory-delivery-order/flow-document.md) |
| Send an invoice to a customer | [Invoicing: Create and Collect Payment](02-user-flows/06-invoice-creation-payment/flow-document.md) |
| Pay a vendor bill | [Accounts Payable: Vendor Bill Payment](02-user-flows/07-vendor-bill-payment/flow-document.md) |
| Manufacture products | [Manufacturing: Production Order](02-user-flows/08-manufacturing-production-order/flow-document.md) |
| Process a retail sale | [Point of Sale: Session and Transaction](02-user-flows/09-pos-session-transaction/flow-document.md) |
| Manage project tasks | [Project: Task Management](02-user-flows/10-project-task-management/flow-document.md) |
| Request time off | [HR: Employee Leave Request](02-user-flows/11-employee-leave-request/flow-document.md) |
| Submit an expense report | [HR: Expense Claim Reimbursement](02-user-flows/12-expense-claim-reimbursement/flow-document.md) |
| Set up online store checkout | [eCommerce: Website Checkout](02-user-flows/13-website-ecommerce-checkout/flow-document.md) |
| Reconcile bank transactions | [Accounting: Bank Reconciliation](02-user-flows/14-bank-reconciliation/flow-document.md) |
| Adjust inventory counts | [Inventory: Inventory Adjustment](02-user-flows/15-inventory-adjustment/flow-document.md) |
| Look up Odoo terminology | [Glossary](01-capabilities-overview/capabilities-inventory.md#7-domain-terminology-glossary) |
| Understand what modules are available | [Module Capabilities](01-capabilities-overview/capabilities-inventory.md) |

---

## Related Resources

### Official Odoo Documentation

| Resource | Link | Description |
|----------|------|-------------|
| Odoo User Documentation | [www.odoo.com/documentation/19.0/applications](https://www.odoo.com/documentation/19.0/applications.html) | Official application documentation |
| Odoo eLearning | [www.odoo.com/slides](https://www.odoo.com/slides) | Video tutorials and training courses |
| Odoo Help Forum | [www.odoo.com/forum/help-1](https://www.odoo.com/forum/help-1) | Community support forum |
| Odoo Security Policy | [www.odoo.com/security-report](https://www.odoo.com/security-report) | Security vulnerability reporting |

### Getting Started

If you're new to Odoo, we recommend:

1. Start with the [Module Capabilities & Glossary](01-capabilities-overview/capabilities-inventory.md) to understand what Odoo can do
2. Review the workflow guide for your primary business area (Sales, Inventory, Accounting, etc.)
3. Reference the corresponding business rules document when you need to understand why Odoo behaves a certain way

---

## Version Information

| Item | Value |
|------|-------|
| **Odoo Version** | 19.0 Community Edition |
| **Documentation Version** | 1.0 |
| **Last Updated** | January 2026 |

---

## Feedback

This documentation is part of a continuous improvement effort. If you find:

- **Errors or outdated information**: Document the discrepancy
- **Missing workflows**: Note the business process that should be covered
- **Confusing explanations**: Suggest clearer language

All feedback helps make this documentation more useful for everyone.

---

*This documentation covers Odoo 19.0 Community Edition functionality. Features marked as "Enterprise Only" in the capabilities inventory require the Odoo Enterprise subscription.*
