# [STORY-ID] [Story Title]

<!-- 
================================================================================
USER STORY TEMPLATE
================================================================================
This template follows BDD (Behavior-Driven Development) and INVEST principles 
for creating high-quality user stories.

INSTRUCTIONS:
1. Replace all placeholders in [brackets] with actual content
2. Ensure 3-6 acceptance criteria scenarios per story
3. Validate against INVEST principles before marking Ready
4. Keep acceptance criteria focused on observable behavior, not implementation

For questions, refer to the Agent Action Plan Section 0.4.2 and R-001/R-002 rules.
================================================================================
-->

| Attribute       | Value                                                    |
|-----------------|----------------------------------------------------------|
| **Story ID**    | [STORY-ID]                                               |
| **Title**       | [Story Title]                                            |
| **Parent Feature** | [FEATURE-XXX-feature-name](../features/FEATURE-XXX-feature-name.md) |
| **Status**      | Draft / Ready / In Progress / Done                       |
| **Priority**    | Critical / High / Medium / Low                           |
| **Estimate**    | [Story Points or T-Shirt Size]                           |

---

## User Story

<!--
INVEST PRINCIPLES REMINDER:
- Independent: Can be developed without completing other stories first
- Negotiable: Describes outcomes, not implementations
- Valuable: Clear business value stated in "So that" clause
- Estimable: Appropriately sized for estimation
- Small: Completable within one sprint/iteration
- Testable: Objective pass/fail determination possible

PERSONA OPTIONS: CFO, Finance Director, Accountant, Bookkeeper, Controller, Auditor, Business Owner
-->

**As a** [user persona]

**I want** [capability/feature description]

**So that** [business value/benefit statement]

---

## Acceptance Criteria

<!--
BDD ACCEPTANCE CRITERIA GUIDELINES:
- Write 3-6 scenarios per story (optimal per BDD best practices)
- Use Given/When/Then format consistently
- Given: Describe preconditions (initial state, context)
- When: Single action/trigger ONLY (no compound actions)
- Then: Observable outcomes ONLY (user-verifiable results)

ANTI-PATTERNS TO AVOID:
✗ Multiple triggers in When clause → Split into separate scenarios
✗ UI element references (e.g., "click button") → Describe behavior instead
✗ Implementation details in Then clause → Focus on observable outcomes
✗ Compound actions → Break into focused, testable scenarios
✗ Ambiguous conditions → Be specific and measurable

EXAMPLE:
Scenario: User generates report for specific date range
- Given a fiscal period with posted journal entries
- When I request a report for the fiscal period
- Then the report displays all posted entries within that period

NOT:
- When I click the Generate button and select PDF format (compound action)
- Then the SQL query returns matching records (implementation detail)
- Then the report button turns green (UI detail)
-->

### Scenario 1: [Descriptive scenario name]

- **Given** [precondition(s) describing initial state]
  <!-- List one or more conditions that must be true before the action -->
- **When** [single trigger/action]
  <!-- One discrete action that triggers the behavior - NO compound actions -->
- **Then** [observable outcome(s)]
  <!-- User-verifiable results - NOT implementation details -->

### Scenario 2: [Descriptive scenario name]

- **Given** [precondition(s) describing initial state]
- **When** [single trigger/action]
- **Then** [observable outcome(s)]

### Scenario 3: [Descriptive scenario name]

- **Given** [precondition(s) describing initial state]
- **When** [single trigger/action]
- **Then** [observable outcome(s)]

<!-- 
Add additional scenarios as needed (recommended: 3-6 total)
Copy the scenario template below:

### Scenario N: [Descriptive scenario name]

- **Given** [precondition(s) describing initial state]
- **When** [single trigger/action]
- **Then** [observable outcome(s)]
-->

---

## Constraints

<!--
MANDATORY CONSTRAINTS: All stories must comply with these constraints.
These are non-negotiable requirements derived from project rules R-001 through R-007.
Check each box when you've verified compliance.
-->

### License and Compliance

- [ ] **AGPL-3.0 Compatibility**: Module/feature must be distributed under AGPL-3.0 compatible license
- [ ] **No Enterprise Dependencies**: No imports or dependencies on Odoo Enterprise edition modules
- [ ] **OCA Coding Standards**: Implementation must follow Odoo and OCA (Odoo Community Association) coding standards

### Version Compatibility

- [ ] **Target Version**: Odoo 18.0 compatibility required
- [ ] **Repository Note**: Current repository is Odoo 19.0; implementation should be version-agnostic where possible

<!--
IMPORTANT: If any constraint cannot be met, document the exception and escalate 
for review before proceeding with implementation.
-->

---

## Technical Discovery Notes

<!--
DISCOVERY-DEFERRED DECISIONS:
Per project guidelines (D-001 through D-005), implementation details are determined 
through codebase analysis, NOT prescribed in user stories. This section provides 
guidance for implementing agents on WHAT to analyze, not HOW to implement.

Stories describe WHAT and WHY; implementation emerges from agent discovery.
-->

### Codebase Analysis Areas

<!-- List specific areas of the codebase that implementing agents should examine -->

| Area | Files/Modules to Examine | Analysis Focus |
|------|-------------------------|----------------|
| [Area 1] | [File paths or module names] | [What to look for] |
| [Area 2] | [File paths or module names] | [What to look for] |

### Relevant Existing Modules

<!-- Identify Odoo modules that may provide patterns or integration points -->

- `addons/account/` - [Specific relevance to this story]
- `addons/analytic/` - [Specific relevance to this story, if applicable]
- [Other relevant modules]

### OCA Module Compatibility

<!-- Reference OCA modules that may be relevant for patterns or integration -->

| OCA Repository | Module | Compatibility Consideration |
|----------------|--------|----------------------------|
| [OCA/repo-name] | [module_name] | [Integration vs. replacement consideration] |

<!--
REMINDER: Do NOT prescribe:
- Module names or structure
- Model inheritance approach
- View architecture decisions
- Report engine technology
- UI component structure
- Database schema details

These emerge from implementation agent discovery.
-->

---

## Dependencies

<!--
Document relationships with other stories, features, and external systems.
This helps with sprint planning and identifies potential blockers.
-->

### Story Dependencies

| Dependency Type | Story ID | Story Title | Relationship |
|-----------------|----------|-------------|--------------|
| Parent Feature | [FEATURE-XXX] | [Feature Title] | This story is part of this feature |
| Blocks | [STORY-XXX] | [Story Title] | This story must complete before... |
| Blocked By | [STORY-XXX] | [Story Title] | Cannot start until this story completes |
| Related | [STORY-XXX] | [Story Title] | Shares functionality or data with... |

### External Dependencies

<!-- List dependencies on external systems, APIs, or standards -->

| Dependency | Type | Notes |
|------------|------|-------|
| [Dependency name] | [System/API/Standard] | [How it affects this story] |

### Integration Points

<!-- Identify existing Odoo models/modules this story will integrate with -->

| Odoo Model/Module | Integration Type | Purpose |
|-------------------|------------------|---------|
| `account.move` | [Read/Write/Extend] | [Purpose of integration] |
| `account.move.line` | [Read/Write/Extend] | [Purpose of integration] |
| [Other models] | [Type] | [Purpose] |

---

## Test Requirements

<!--
MANDATORY: All stories require minimum 80% test coverage (Rule R-006).
Map acceptance criteria scenarios to test types for implementation guidance.
-->

### Coverage Requirement

| Metric | Requirement | Notes |
|--------|-------------|-------|
| **Minimum Test Coverage** | **80%** | Mandatory for all new functionality |
| Unit Test Coverage | 80%+ | Business logic, model methods |
| Integration Test Coverage | 80%+ | Module interactions, data flow |

### Unit Test Scenarios

<!-- Derive unit test scenarios from acceptance criteria -->

| Acceptance Scenario | Unit Test Focus | Key Assertions |
|---------------------|-----------------|----------------|
| Scenario 1 | [Component/method to test] | [What to verify] |
| Scenario 2 | [Component/method to test] | [What to verify] |
| Scenario 3 | [Component/method to test] | [What to verify] |

### Integration Test Considerations

<!-- Identify integration test needs based on dependencies -->

- [ ] Test integration with `account.move` model
- [ ] Test integration with `account.move.line` model
- [ ] Test cross-module functionality
- [ ] [Additional integration test considerations]

### Acceptance Test Mapping

<!-- Map BDD scenarios to automated acceptance tests -->

| BDD Scenario | Test Method Name | Test Type |
|--------------|------------------|-----------|
| Scenario 1: [Name] | `test_[scenario_name]` | Acceptance |
| Scenario 2: [Name] | `test_[scenario_name]` | Acceptance |
| Scenario 3: [Name] | `test_[scenario_name]` | Acceptance |

---

## Definition of Done

<!--
CHECKLIST: All items must be checked before the story can be marked as Done.
This ensures consistent quality across all user stories.
-->

### Implementation Checklist

- [ ] All acceptance criteria scenarios pass
- [ ] 80% minimum test coverage achieved
- [ ] Unit tests written and passing
- [ ] Integration tests written and passing

### Compliance Checklist

- [ ] No Enterprise module dependencies introduced
- [ ] AGPL-3.0 license compliance verified
- [ ] Code follows OCA coding standards
- [ ] Code reviewed and approved

### Documentation Checklist

- [ ] Code documentation (docstrings, comments) complete
- [ ] User-facing documentation updated (if applicable)
- [ ] Technical documentation updated (if applicable)

### Quality Checklist

- [ ] No critical or high-severity bugs
- [ ] Performance acceptable (no significant degradation)
- [ ] Security considerations addressed

---

## Revision History

<!--
OPTIONAL: Track changes to this user story document.
Useful for understanding story evolution during refinement.
-->

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | [YYYY-MM-DD] | [Author Name] | Initial story creation |
| [X.X] | [YYYY-MM-DD] | [Author Name] | [Description of changes] |

---

## Notes

<!--
Use this section for any additional information that doesn't fit elsewhere.
Examples: clarifications from stakeholders, design decisions, edge cases discussed.
-->

[Additional notes, clarifications, or context]

---

<!--
================================================================================
TEMPLATE USAGE CHECKLIST
================================================================================
Before submitting this story for review, verify:

□ All [placeholders] have been replaced with actual content
□ User story follows "As a / I want / So that" format
□ 3-6 acceptance criteria scenarios are defined
□ All scenarios use Given/When/Then format correctly
□ No implementation details in acceptance criteria
□ No UI element references in acceptance criteria
□ All mandatory constraints are acknowledged
□ Technical discovery notes guide (not prescribe) implementation
□ Dependencies are documented
□ Test requirements specify 80% minimum coverage
□ Definition of Done checklist is complete

INVEST Validation:
□ Independent - Can be developed standalone
□ Negotiable - Describes outcomes, not solutions
□ Valuable - Business value is clear
□ Estimable - Can be sized for planning
□ Small - Fits within one sprint
□ Testable - Pass/fail can be determined objectively
================================================================================
-->
