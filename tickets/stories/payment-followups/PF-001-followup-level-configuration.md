# PF-001: Follow-up Level Configuration

---

## Metadata

| Attribute | Value |
|-----------|-------|
| **Story ID** | PF-001 |
| **Title** | Follow-up Level Configuration |
| **Feature** | [FEATURE-006: Payment Follow-ups](../../features/FEATURE-006-payment-followups.md) |
| **Epic** | [EPIC-001: Enterprise Accounting Capabilities](../../EPIC-001-enterprise-accounting.md) |
| **Status** | Draft |
| **Priority** | High |
| **Story Points** | TBD (Implementation team to estimate) |
| **Personas** | Accountant, Credit Controller |
| **Created** | 2024 |
| **Last Updated** | 2024 |

---

## 1. User Story

### 1.1 Primary User Story

**As an** Accountant,
**I want** to configure multiple follow-up levels with different delays, actions, and communication templates,
**So that** I can implement a systematic escalation process for collecting overdue receivables that aligns with company policies.

### 1.2 Secondary User Story

**As a** Credit Controller,
**I want** to define the tone and urgency of communications at each follow-up level,
**So that** customer relationships are maintained while progressively encouraging payment.

---

## 2. Business Value

### 2.1 Value Statement

Configurable follow-up levels provide the foundation for systematic payment collection by enabling organizations to define:

- **Escalation timing** - How many days after the due date each level triggers
- **Communication templates** - Appropriate messaging for each escalation stage
- **Action types** - Whether follow-ups should be automatic or require manual review
- **Business rules** - Thresholds and conditions for triggering follow-ups

### 2.2 Success Metrics

| Metric | Target | Rationale |
|--------|--------|-----------|
| Configuration time | <15 minutes to set up complete follow-up workflow | Accountants can quickly implement collection policies |
| Level flexibility | Support 2-10 configurable levels | Accommodates simple to complex collection workflows |
| Company customization | 100% of levels can differ per company | Multi-company deployments can have unique policies |

### 2.3 Business Rules

| Rule ID | Rule Description |
|---------|------------------|
| BR-001 | Follow-up levels must have a unique sequence number within each company |
| BR-002 | Delay days must be greater than or equal to zero |
| BR-003 | Levels with lower sequence numbers should have lower delay values (soft validation/warning) |
| BR-004 | At least one follow-up level must exist before follow-up processing can execute |
| BR-005 | Minimum amount thresholds must be non-negative monetary values |

---

## 3. Acceptance Criteria

### Scenario 1: Create Follow-up Level

**Given** I am in the payment follow-up configuration
**When** I create a new follow-up level with name, sequence, delay (days after due date), and description
**Then** the level is saved and appears in the follow-up level list in sequence order

**Example Data:**
| Field | Value |
|-------|-------|
| Name | First Reminder |
| Sequence | 10 |
| Delay (days) | 7 |
| Description | Friendly reminder that payment is due |

---

### Scenario 2: Configure Default Follow-up Levels

**Given** I install the payment follow-up module
**When** the module initializes
**Then** default follow-up levels are created with the following configuration:

| Level Name | Sequence | Delay (Days) | Description |
|------------|----------|--------------|-------------|
| First Reminder | 10 | 7 | Initial friendly reminder |
| Second Reminder | 20 | 14 | Follow-up reminder |
| Warning | 30 | 21 | Formal warning notice |
| Final Notice | 40 | 30 | Final notice before escalation |

---

### Scenario 3: Associate Email Template with Level

**Given** I have a follow-up level configured
**When** I associate an email template with that level
**Then** that template will be used when automated emails are generated for customers at this level

**Additional Criteria:**
- The template selection should display only templates associated with the follow-up partner model
- Templates can be left empty for levels that require only manual action
- Multiple levels can share the same email template if desired

---

### Scenario 4: Set Manual vs Automatic Actions

**Given** I am configuring a follow-up level
**When** I set the action type to "Automatic" or "Manual"
**Then** the follow-up processing behavior changes accordingly:

| Action Type | Behavior |
|-------------|----------|
| Automatic | Follow-up emails are sent without user intervention when scheduled |
| Manual | Follow-up actions are queued for review and explicit user approval before sending |

---

### Scenario 5: Configure Level-Specific Actions

**Given** I am editing a follow-up level
**When** I configure additional actions such as:
- Block further sales
- Add to collection list
- Notify sales representative
- Change partner trust level

**Then** those actions are triggered when a customer reaches this follow-up level

**Action Options:**
| Action | Description |
|--------|-------------|
| Block Sales | Sets partner flag to prevent new sales orders |
| Collection List | Adds partner to collection report |
| Notify Sales Rep | Sends notification to assigned salesperson |
| Update Trust | Changes partner trust level (e.g., to "Bad Debtor") |

---

### Scenario 6: Set Minimum Overdue Amount Threshold

**Given** I am configuring follow-up levels
**When** I set a minimum amount threshold for a level (e.g., 500.00)
**Then** customers with overdue amounts below this threshold are excluded from this level's follow-up actions

**Validation Rules:**
- Threshold must be a non-negative monetary value
- Threshold is evaluated in the company's base currency
- Customers below threshold are skipped during follow-up processing for this level

---

## 4. Technical Notes

> **Purpose:** These notes guide implementing agents in their codebase analysis. Stories describe WHAT and WHY; implementation details emerge from agent discovery.

### 4.1 Codebase Analysis Areas

| File/Module | Analysis Purpose | Key Patterns to Reference |
|-------------|------------------|---------------------------|
| `addons/account/models/partner.py` | Partner credit data patterns | Lines 514-521: `credit_limit` field (company-dependent, monetary); Line 565: `trust` selection field pattern |
| `addons/account/models/account_payment_term.py` | Configuration model patterns | Sequence field, company relationship, One2many line relationships |
| `addons/account/data/mail_template_data.xml` | Email template definition patterns | QWeb template structure, dynamic field references |
| `addons/account/views/partner_view.xml` | Partner form view integration | Placement of accounting-related fields |

### 4.2 Design Considerations

| Consideration | Notes |
|---------------|-------|
| Model design | Evaluate whether to create new `account.followup.level` model or extend existing models |
| Company dependency | Follow-up levels should be company-dependent (like payment terms) to support multi-company |
| Sequence ordering | Use sequence field pattern from `account.payment.term` (line 29 in source) |
| Email template association | Use `Many2one` relationship to `mail.template` model |
| Data migration | Consider XML data file for default levels (similar to payment term defaults) |

### 4.3 Integration Points

| Integration | Description |
|-------------|-------------|
| `mail.template` | Email template association for each level |
| `res.partner` | Partner trust field updates when actions trigger |
| `ir.cron` | Scheduled actions for automatic follow-up processing |
| Security groups | Access control for level configuration (Accountant role) |

### 4.4 Field Patterns from Source Analysis

Based on source file analysis, recommended field patterns:

| Field | Type | Pattern Reference |
|-------|------|-------------------|
| `name` | `fields.Char` | Required, translatable (like payment term name) |
| `sequence` | `fields.Integer` | Required, default=10, for ordering |
| `delay` | `fields.Integer` | Days after due date |
| `company_id` | `fields.Many2one` | `res.company`, company-dependent configuration |
| `email_template_id` | `fields.Many2one` | `mail.template`, optional |
| `action_type` | `fields.Selection` | `[('automatic', 'Automatic'), ('manual', 'Manual')]` |
| `min_amount` | `fields.Monetary` | Minimum threshold, currency-dependent |
| `description` | `fields.Text` | Internal notes about the level |
| `active` | `fields.Boolean` | Default True, for archiving |

---

## 5. Dependencies

### 5.1 Story Dependencies

| Dependency Type | Related Item | Notes |
|-----------------|--------------|-------|
| **None** | N/A | This is a foundational configuration story |

### 5.2 Downstream Dependencies

Stories that depend on PF-001:

| Story ID | Story Title | Dependency Reason |
|----------|-------------|-------------------|
| PF-002 | Automated Email Generation | Requires follow-up levels to be defined for email triggers |
| PF-004 | Action History Tracking | Actions are recorded in context of follow-up levels |

### 5.3 External Dependencies

| Dependency | Description |
|------------|-------------|
| `mail.template` | Odoo mail template model for email association |
| `res.company` | Company model for multi-company support |
| `res.partner` | Partner model for trust field updates |

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

### 6.3 Coding Standards

| Constraint | Requirement |
|------------|-------------|
| **Odoo Guidelines** | Follow Odoo coding standards for model and view design |
| **OCA Standards** | Adhere to OCA module guidelines for potential contribution |

### 6.4 Multi-Company Support

| Constraint | Requirement |
|------------|-------------|
| **Company-Specific Levels** | Support company-specific follow-up level configurations |
| **Company Isolation** | Each company can have independent follow-up levels |

---

## 7. Test Requirements

### 7.1 Coverage Requirement

| Requirement | Target |
|-------------|--------|
| **Minimum Test Coverage** | 80% test coverage for level configuration logic |

### 7.2 Test Scenarios

| Test Category | Test Scenario | Priority |
|---------------|---------------|----------|
| **CRUD Operations** | Create follow-up level with valid data | High |
| **CRUD Operations** | Read and list follow-up levels in sequence order | High |
| **CRUD Operations** | Update follow-up level fields | High |
| **CRUD Operations** | Delete (archive) follow-up level | Medium |
| **Sequence Ordering** | Levels display in sequence order | High |
| **Sequence Ordering** | Sequence uniqueness per company enforced | High |
| **Level Transitions** | Verify levels with increasing delays | Medium |
| **Email Template Association** | Associate template with level | High |
| **Email Template Association** | Remove template association | Medium |
| **Email Template Association** | Multiple levels share same template | Medium |
| **Minimum Threshold** | Threshold filtering excludes low-amount partners | High |
| **Minimum Threshold** | Zero threshold includes all partners | Medium |
| **Default Levels** | Module installation creates default levels | High |
| **Default Levels** | Default levels have correct sequence and delays | High |
| **Multi-Company** | Levels isolated per company | High |
| **Multi-Company** | Different companies have different level configurations | Medium |
| **Action Configuration** | Automatic vs manual action type persistence | High |
| **Action Configuration** | Additional actions (block sales, notify) stored correctly | Medium |

### 7.3 Integration Test Scenarios

| Test Scenario | Modules Involved |
|---------------|------------------|
| Follow-up level with email template | `mail.template`, follow-up module |
| Level configuration with partner credit data | `res.partner`, follow-up module |
| Multi-company level isolation | `res.company`, follow-up module |

### 7.4 Acceptance Test Mapping

| Acceptance Scenario | Corresponding Test |
|--------------------|-------------------|
| Scenario 1: Create Follow-up Level | `test_create_followup_level_valid_data` |
| Scenario 2: Configure Default Levels | `test_module_install_creates_default_levels` |
| Scenario 3: Associate Email Template | `test_associate_email_template_with_level` |
| Scenario 4: Manual vs Automatic Actions | `test_action_type_automatic_manual` |
| Scenario 5: Level-Specific Actions | `test_configure_additional_actions` |
| Scenario 6: Minimum Amount Threshold | `test_minimum_threshold_filtering` |

---

## 8. Out of Scope

The following items are explicitly **NOT** included in this story:

| Item | Reason | Related Story |
|------|--------|---------------|
| Executing follow-up actions | Separate story for email generation | PF-002 |
| Calculating overdue amounts | Separate story for overdue calculation | PF-005 |
| Recording follow-up history | Separate story for action tracking | PF-004 |
| Follow-up report generation | Separate story for reporting | PF-003 |
| Real-time bank feed integration | Out of epic scope | N/A |
| AI-powered collection recommendations | Out of epic scope | N/A |

---

## 9. Assumptions and Decisions

### 9.1 Assumptions

| Assumption | Rationale |
|------------|-----------|
| Follow-up levels are company-specific | Multi-company deployments need independent configurations |
| At least 2 levels are typically needed | Reminder → Final Notice is minimum useful workflow |
| Email templates are optional per level | Some levels may require only manual action |
| Sequence determines processing order | Lower sequence = earlier in escalation process |

### 9.2 Open Questions

| Question | Status | Decision |
|----------|--------|----------|
| Should levels be date-effective (valid from/to)? | Open | Implementation team decision |
| Should levels support recurring follow-ups (e.g., remind every 7 days)? | Open | Consider for future enhancement |

---

## 10. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024 | Enterprise Accounting Team | Initial story creation |

---

## 11. References

### 11.1 Source Code References

| Reference | Purpose |
|-----------|---------|
| `addons/account/models/partner.py` (lines 514-521) | Credit limit field patterns |
| `addons/account/models/partner.py` (line 565) | Trust selection field pattern |
| `addons/account/models/account_payment_term.py` | Payment term configuration patterns |
| `addons/account/data/mail_template_data.xml` | Email template data structure |

### 11.2 Related Documentation

| Document | Relationship |
|----------|--------------|
| [FEATURE-006: Payment Follow-ups](../../features/FEATURE-006-payment-followups.md) | Parent feature |
| [EPIC-001: Enterprise Accounting](../../EPIC-001-enterprise-accounting.md) | Parent epic |
| [PF-002: Automated Email Generation](./PF-002-automated-email-generation.md) | Downstream dependency |
| [PF-004: Action History Tracking](./PF-004-action-history-tracking.md) | Downstream dependency |

### 11.3 External References

| Reference | Description |
|-----------|-------------|
| Odoo Coding Guidelines | Standard Odoo development practices |
| OCA Module Guidelines | OCA contribution standards |
| AGPL-3.0 License | Module licensing requirements |
