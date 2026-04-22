# PF-003: Follow-up Report Generation

---

## Metadata

| Attribute | Value |
|-----------|-------|
| **Story ID** | PF-003 |
| **Title** | Follow-up Report Generation |
| **Feature** | [FEATURE-006: Payment Follow-ups](../../features/FEATURE-006-payment-followups.md) |
| **Epic** | [EPIC-001: Enterprise Accounting Capabilities](../../EPIC-001-enterprise-accounting.md) |
| **Status** | Draft |
| **Priority** | High |
| **Story Points** | TBD (Implementation team to estimate) |
| **Personas** | Credit Controller, Business Owner |
| **Created** | 2024 |
| **Last Updated** | 2024 |

---

## 1. User Story

### 1.1 Primary User Story

**As a** Credit Controller,

**I want** to generate comprehensive follow-up reports showing customers with overdue invoices, follow-up actions taken, and collection status,

**So that** I can monitor receivables performance, prioritize collection efforts, and report on AR aging to management.

### 1.2 Secondary User Story

**As a** Business Owner,

**I want** to view summarized reports of overdue receivables and follow-up effectiveness,

**So that** I can understand cash flow impacts and make informed business decisions about credit policies and customer relationships.

---

## 2. Business Value

### 2.1 Value Statement

Follow-up report generation provides critical visibility into the receivables collection process by enabling organizations to:

- **Monitor collection performance** with comprehensive overdue receivables visibility
- **Track follow-up effectiveness** by measuring response rates and collection success at each level
- **Prioritize collection efforts** by identifying high-value overdue accounts requiring attention
- **Support management reporting** with exportable reports for executive review
- **Enable data-driven decisions** on credit policies and follow-up strategy optimization
- **Achieve 15-25% reduction in overdue receivables** through better tracking and accountability

### 2.2 Success Metrics

| Metric | Target | Rationale |
|--------|--------|-----------|
| Report generation time | <10 seconds for 500+ partners | Usability for daily operations |
| Report accuracy | 100% match with source data | Reconciliation with invoices and payments |
| Export success rate | 100% of exports complete without errors | Reliable data sharing |
| Effectiveness metrics availability | Real-time calculation | Support continuous improvement |
| Collection rate improvement | 15-25% reduction in overdue receivables | Primary epic success metric |

### 2.3 Business Rules

| Rule ID | Rule Description |
|---------|------------------|
| BR-001 | Reports must include all partners with at least one overdue invoice meeting minimum threshold criteria |
| BR-002 | Follow-up level displayed must reflect the current level based on most overdue invoice |
| BR-003 | Overdue amounts must be calculated using residual amounts after partial payments |
| BR-004 | Effectiveness metrics must be calculated from action history over the selected period |
| BR-005 | Drill-down from summary to detail must maintain data consistency |
| BR-006 | Export formats must preserve all visible data including filters applied |
| BR-007 | Reports must respect company-specific data isolation in multi-company environments |

---

## 3. Acceptance Criteria

> **Note:** All acceptance criteria follow BDD (Behavior-Driven Development) format using Given/When/Then syntax. Each scenario describes observable behavior without prescribing implementation details.

### Scenario 1: Generate Aged Receivables Follow-up Report

**Given** I have configured follow-up levels and there are customers with overdue invoices

**When** I generate the follow-up report for a specified date range

**Then** I see a list of customers with their collection-relevant information including:
  - Customer name and reference
  - Current follow-up level
  - Total overdue amount (in company currency)
  - Oldest overdue date (most past due invoice date)
  - Days since oldest overdue
  - Last action taken (action type, date, and responsible user)
  - Number of overdue invoices

**And** the list is sortable by any column

**And** the default sort order is by total overdue amount descending (highest amounts first)

**And** the report displays totals at the bottom including total overdue amount and customer count

---

### Scenario 2: Filter Report by Follow-up Level

**Given** the follow-up report is generated with customers at various follow-up levels

**When** I filter by a specific follow-up level (e.g., "Final Notice")

**Then** only customers currently at that follow-up level are displayed

**And** the filter selection is clearly indicated in the report header

**And** summary totals update to reflect only the filtered results

**And** I can select multiple follow-up levels for combined filtering

**And** I can clear the filter to return to the full customer list

**Filter Options:**
| Filter Type | Options |
|-------------|---------|
| Follow-up Level | All configured levels (multi-select) |
| No Follow-up | Customers with overdue invoices but no follow-up level assigned |

---

### Scenario 3: Drill-down to Customer Detail

**Given** I am viewing the follow-up report with a list of customers

**When** I click on a customer name or select a customer row

**Then** I can view the detailed follow-up information for that customer including:
  - Complete list of overdue invoices with individual amounts and due dates
  - Aging breakdown by bucket (1-30, 31-60, 61-90, 90+ days)
  - Complete action history timeline (date, action type, user, outcome)
  - Customer contact information for follow-up
  - Payment terms and credit limit information
  - Notes or promises recorded from previous follow-up actions

**And** I can navigate back to the summary report while preserving my filter selections

**And** I can navigate directly to the next/previous customer in the filtered list

---

### Scenario 4: Export Report to PDF Format

**Given** the follow-up report is generated with current filters applied

**When** I select export to PDF format

**Then** a PDF document is generated containing:
  - Report title with company name and generation date/time
  - Applied filters clearly stated
  - All visible data in tabular format maintaining column structure
  - Summary totals section
  - Page numbers and professional formatting

**And** the PDF is downloaded or made available for printing

**And** the PDF layout is optimized for standard paper sizes (A4/Letter)

**And** large reports are paginated appropriately with headers repeated on each page

---

### Scenario 5: Export Report to Excel Format

**Given** the follow-up report is generated with current filters applied

**When** I select export to Excel format

**Then** an Excel workbook is generated containing:
  - Summary sheet with all customers and their follow-up status
  - Column headers matching the on-screen report
  - Proper data types (dates as dates, amounts as numbers with currency formatting)
  - Filter metadata in a header section or separate sheet

**And** the Excel file is downloaded with appropriate filename including date

**And** numeric columns support Excel filtering and sorting

**And** large datasets (1000+ rows) export successfully without timeout

---

### Scenario 6: View Follow-up Effectiveness Summary

**Given** follow-up actions have been executed over a period and payments have been received

**When** I view the effectiveness summary section of the follow-up report

**Then** I see key performance metrics including:

| Metric | Description |
|--------|-------------|
| Total Overdue | Sum of all overdue invoice residual amounts |
| Total Overdue Recovered | Sum of payments received for previously overdue invoices |
| Recovery Rate | Percentage of overdue amounts recovered |
| Average Days to Payment | Mean days between follow-up action and payment receipt |
| Response Rate by Level | Percentage of customers who paid after each follow-up level |
| Active Follow-ups | Count of customers currently in each follow-up level |

**And** metrics are calculated for the selected date range

**And** I can compare metrics between different time periods (e.g., this month vs. last month)

**And** metrics that show improvement are visually highlighted (e.g., positive trend indicators)

---

### Scenario 7: Filter by Date Range and Amount Threshold

**Given** I am generating or viewing the follow-up report

**When** I apply date range and/or amount filters

**Then** the report displays only customers matching the filter criteria:

| Filter | Behavior |
|--------|----------|
| Date Range (From/To) | Shows customers with invoices having due dates within the range |
| Minimum Overdue Amount | Excludes customers with total overdue below threshold |
| Maximum Overdue Amount | Excludes customers with total overdue above threshold |

**And** multiple filters can be combined with AND logic

**And** filter values are validated (e.g., From date must be before To date)

**And** default date range is configurable (e.g., last 90 days)

---

### Scenario 8: Group Report by Salesperson or Region

**Given** customers are assigned to salespeople or have regional/territory classifications

**When** I group the follow-up report by salesperson or region

**Then** the report displays customers organized under their assigned grouping

**And** subtotals are shown for each group (total overdue, customer count)

**And** I can expand/collapse groups to show/hide individual customers

**And** the grouping can be combined with other filters

**Grouping Options:**
| Grouping | Based On |
|----------|----------|
| Salesperson | Customer's assigned salesperson |
| Sales Team | Salesperson's team |
| Region/Territory | Customer's geographic classification |
| Follow-up Level | Current follow-up level (default view) |
| Aging Bucket | Based on oldest overdue invoice age |

---

## 4. Technical Notes

> **Purpose:** These notes guide implementing agents in their codebase analysis. Stories describe WHAT and WHY; implementation details emerge from agent discovery.

### 4.1 Codebase Analysis Areas

| File/Module | Analysis Purpose | Key Patterns to Reference |
|-------------|------------------|---------------------------|
| `addons/account/report/account_invoice_report.py` | Existing report model patterns | SQL-based aggregation views, `_auto = False` pattern, `_table_query` for computed reports |
| `addons/account/models/partner.py` | Partner credit data integration | `credit`, `debit`, `total_invoiced` computed fields, `days_sales_outstanding` calculation |
| `addons/account/data/mail_template_data.xml` | Template patterns for exports | QWeb report structure, dynamic formatting |
| `addons/account/views/account_report_view.xml` | Report wizard UI patterns | Wizard-based report parameter collection |
| `addons/web/static/src/views/list/` | List view export patterns | Excel/PDF export mechanisms |

### 4.2 Design Considerations

| Consideration | Notes |
|---------------|-------|
| Report architecture | Evaluate wizard-based vs. direct menu action approach for report parameters |
| Data aggregation | Consider SQL view (like `account.invoice.report`) for performance with large datasets |
| Export mechanism | Use existing Odoo report infrastructure (QWeb for PDF, `xlsx` export utilities) |
| Drill-down implementation | Evaluate action-based navigation vs. embedded detail views |
| Effectiveness calculations | May require scheduled computation for complex metrics to avoid real-time performance issues |
| Multi-company | Ensure report respects company record rules and user permissions |

### 4.3 Integration Points

| Integration | Description |
|-------------|-------------|
| PF-001 (Follow-up Levels) | Report displays customers by configured follow-up levels |
| PF-004 (Action History) | Report includes action history data for drill-down and effectiveness metrics |
| PF-005 (Overdue Calculation) | Report relies on overdue calculation logic for aging buckets and level assignment |
| `res.partner` | Customer data including credit information, salesperson, region |
| `account.move` | Invoice data including amounts, due dates, payment state |
| `ir.actions.report` | Odoo report action framework for PDF generation |

### 4.4 Existing Report Patterns from Source Analysis

Based on `account_invoice_report.py` analysis, recommended patterns:

| Pattern | Source Reference | Application |
|---------|------------------|-------------|
| SQL View Model | `_auto = False`, `_table_query` property | Efficient aggregation for large datasets |
| Group By Support | `_read_group` method usage | Grouping by salesperson, region, level |
| Multi-currency | `company_currency_id`, amount conversion | Report in company currency |
| Partner aggregation | `partner_id`, `commercial_partner_id` fields | Roll-up to commercial partner |
| Date filtering | `invoice_date`, `invoice_date_due` fields | Date range filtering |

### 4.5 Performance Considerations

| Consideration | Approach |
|---------------|----------|
| Large partner counts | Use pagination or lazy loading for 1000+ partners |
| Complex aggregations | Pre-compute with SQL view rather than ORM computed fields |
| Export timeouts | Use background job for large exports (>5000 rows) |
| Effectiveness metrics | Consider nightly batch computation with result caching |
| Database indexes | Ensure indexes on `partner_id`, `invoice_date_due`, `amount_residual` |

---

## 5. Dependencies

### 5.1 Story Dependencies

| Dependency Type | Story | Dependency Reason |
|-----------------|-------|-------------------|
| **Requires** | [PF-001: Follow-up Level Configuration](PF-001-followup-level-configuration.md) | Report filters and displays customers by configured follow-up levels |
| **Requires** | [PF-004: Action History Tracking](PF-004-action-history-tracking.md) | Report displays action history for drill-down and calculates effectiveness metrics |
| **Requires** | [PF-005: Overdue Calculation](PF-005-overdue-calculation.md) | Report relies on overdue calculation for aging buckets and level assignment |

### 5.2 Downstream Dependencies

Stories that depend on PF-003:

| Story ID | Story Title | Dependency Reason |
|----------|-------------|-------------------|
| None | N/A | This is a terminal/reporting story with no downstream dependencies |

### 5.3 External Dependencies

| Dependency | Description |
|------------|-------------|
| `account.move` | Invoice model for overdue amounts and due dates |
| `res.partner` | Partner model for customer information and credit data |
| `ir.actions.report` | Odoo report action framework for PDF export |
| Excel export utilities | Odoo's built-in Excel export (via `xlsxwriter` or similar) |

---

## 6. Constraints

### 6.1 License Constraint

| Constraint | Requirement |
|------------|-------------|
| **Module License** | Module distributed under AGPL-3.0 compatible license |

### 6.2 Dependency Constraints

| Constraint | Requirement |
|------------|-------------|
| **No Enterprise Dependencies** | No imports or dependencies on Odoo Enterprise modules |
| **No account_followup** | Specifically no dependency on Enterprise `account_followup` module |
| **No account_reports** | Specifically no dependency on Enterprise `account_reports` module |

### 6.3 Coding Standards

| Constraint | Requirement |
|------------|-------------|
| **Odoo Guidelines** | Follow Odoo coding standards for report model and wizard design |
| **OCA Standards** | Adhere to OCA module guidelines for potential contribution |
| **Report Conventions** | Follow existing Odoo report patterns (QWeb for PDF, proper action definitions) |

### 6.4 Performance Constraints

| Constraint | Requirement |
|------------|-------------|
| **Report Generation Time** | Follow-up report generation completes in <10 seconds for 500 partners |
| **Export Performance** | PDF/Excel export completes in <30 seconds for 1000 rows |
| **No N+1 Queries** | Avoid N+1 query patterns in report data retrieval |

### 6.5 Data Access Constraints

| Constraint | Requirement |
|------------|-------------|
| **Multi-Company Isolation** | Report respects company-specific data access rules |
| **Security Groups** | Report accessible to Accountant and Manager roles |
| **Data Privacy** | Partner contact details only visible to authorized users |

---

## 7. Test Requirements

### 7.1 Coverage Requirement

| Requirement | Target |
|-------------|--------|
| **Minimum Test Coverage** | 80% test coverage for report generation logic |

### 7.2 Test Scenarios

| Test Category | Test Scenario | Priority |
|---------------|---------------|----------|
| **Report Generation** | Generate report with customers at various follow-up levels | High |
| **Report Generation** | Generate report with no overdue customers (empty state) | Medium |
| **Report Generation** | Generate report with 1000+ partners (performance test) | High |
| **Filtering** | Filter by single follow-up level | High |
| **Filtering** | Filter by multiple follow-up levels | High |
| **Filtering** | Filter by date range | High |
| **Filtering** | Filter by minimum amount threshold | High |
| **Filtering** | Combine multiple filters | Medium |
| **Filtering** | Clear filters returns full dataset | Medium |
| **Drill-down** | Navigate to customer detail from summary | High |
| **Drill-down** | Customer detail shows all overdue invoices | High |
| **Drill-down** | Customer detail shows action history | High |
| **Drill-down** | Navigate back preserves filter state | Medium |
| **Export PDF** | Export report to PDF format | High |
| **Export PDF** | PDF includes all visible columns | High |
| **Export PDF** | PDF respects applied filters | High |
| **Export PDF** | Large report pagination works correctly | Medium |
| **Export Excel** | Export report to Excel format | High |
| **Export Excel** | Excel includes proper data types | High |
| **Export Excel** | Large dataset export (1000+ rows) | High |
| **Effectiveness Metrics** | Calculate recovery rate correctly | High |
| **Effectiveness Metrics** | Calculate average days to payment | High |
| **Effectiveness Metrics** | Response rate by follow-up level | High |
| **Effectiveness Metrics** | Metrics respect date range filter | Medium |
| **Grouping** | Group by salesperson | Medium |
| **Grouping** | Group by follow-up level | Medium |
| **Grouping** | Subtotals calculate correctly | High |
| **Data Accuracy** | Report totals match invoice data | High |
| **Data Accuracy** | Aging buckets sum to total overdue | High |
| **Data Accuracy** | Follow-up level assignment is correct | High |
| **Multi-Company** | Report isolates data by company | High |
| **Multi-Company** | User sees only authorized company data | High |
| **Security** | Report respects user access rights | High |
| **Security** | Export respects user access rights | Medium |

### 7.3 Performance Test Criteria

| Test | Criteria | Expected Result |
|------|----------|-----------------|
| Report generation (500 partners) | Measure response time | <10 seconds |
| Report generation (1000 partners) | Measure response time | <20 seconds |
| PDF export (500 rows) | Measure export time | <15 seconds |
| Excel export (1000 rows) | Measure export time | <30 seconds |
| Effectiveness calculation | Measure computation time | <5 seconds |
| Drill-down navigation | Measure response time | <3 seconds |

### 7.4 Data Test Requirements

| Requirement | Description |
|-------------|-------------|
| Test data volume | Test with 500+ partners with varying overdue invoices |
| Edge cases | Partners with zero overdue, single invoice, many invoices |
| Partial payments | Invoices with partial payment history |
| Multi-currency | Partners with invoices in different currencies |
| Date variations | Invoices at various aging stages (1 day to 180+ days) |

---

## 8. UI/UX Considerations

> **Note:** This section describes user experience expectations without prescribing implementation. UI implementation details emerge from agent discovery.

### 8.1 Report Access

| Consideration | Expectation |
|---------------|-------------|
| Menu Location | Accessible from Invoicing/Accounting menu under Reporting section |
| Quick Access | Optionally accessible from partner form via smart button |
| Dashboard Widget | Summary statistics optionally displayable on accounting dashboard |

### 8.2 Report Usability

| Consideration | Expectation |
|---------------|-------------|
| Clear Visual Hierarchy | High-priority (high amount, final notice) customers visually prominent |
| Responsive Design | Report viewable on various screen sizes |
| Loading Indicators | Clear feedback during report generation and export |
| Error Handling | Clear error messages for failed exports or empty results |
| Column Customization | Users can show/hide columns based on preferences |

### 8.3 Drill-down Experience

| Consideration | Expectation |
|---------------|-------------|
| Context Preservation | Filters maintained when drilling down and returning |
| Navigation | Clear breadcrumb or back navigation |
| Action Availability | Ability to initiate follow-up action directly from detail view |
| Related Records | Easy navigation to related invoices, payments, communications |

---

## 9. Related Documentation

### 9.1 Feature Documentation

- [FEATURE-006: Payment Follow-ups](../../features/FEATURE-006-payment-followups.md)
- [EPIC-001: Enterprise Accounting Capabilities](../../EPIC-001-enterprise-accounting.md)

### 9.2 Related Stories

- [PF-001: Follow-up Level Configuration](PF-001-followup-level-configuration.md) - Defines the levels used for filtering and display
- [PF-002: Automated Email Generation](PF-002-automated-email-generation.md) - Actions that appear in effectiveness metrics
- [PF-004: Action History Tracking](PF-004-action-history-tracking.md) - Provides data for action history drill-down
- [PF-005: Overdue Calculation](PF-005-overdue-calculation.md) - Provides aging bucket calculations

### 9.3 Related Features

- [FEATURE-001: Financial Reporting](../../features/FEATURE-001-financial-reporting.md) - Aged Receivables report (FR-006) provides complementary data

### 9.4 Source Code References

| Reference | Purpose |
|-----------|---------|
| `addons/account/report/account_invoice_report.py` | Report model pattern |
| `addons/account/models/partner.py` | Partner credit fields (lines 507-534) |
| `addons/account/data/mail_template_data.xml` | Report template patterns |

---

## 10. Open Questions

> **Note:** These questions may be addressed during implementation discovery or require stakeholder clarification.

| Question ID | Question | Stakeholder | Status |
|-------------|----------|-------------|--------|
| Q-001 | Should effectiveness metrics be calculated in real-time or batch-processed nightly? | Product Owner | Open |
| Q-002 | What is the maximum historical period for action history in drill-down (e.g., 24 months)? | Compliance | Open |
| Q-003 | Should the report support scheduled email delivery (e.g., weekly report to CFO)? | Business Owner | Open |
| Q-004 | Is there a requirement for comparative reporting (this period vs. last period)? | Finance Director | Open |
| Q-005 | Should disputed invoices be included in reports with a flag, or completely excluded? | Accountant | Open |

---

## 11. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024 | Blitzy Platform | Initial story creation |

---

*This user story is part of the Enterprise Accounting Capabilities epic, implementing follow-up report generation for Odoo Community Edition to bridge the gap with Enterprise functionality.*
