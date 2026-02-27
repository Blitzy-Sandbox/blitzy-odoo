# Carbon UI — Component Mapping Reference

Complete mapping of Odoo 19.0 Community Edition UI components to IBM Carbon Design System v11 equivalents. Each entry documents the current Odoo implementation, the target Carbon component, the SCSS import path, recommended props/variants, and the rationale for the mapping.

> **Design System**: IBM Carbon Design System v11 — "Productive" theme variant
> **Integration Path**: SCSS-only via `@carbon/styles` (no React/Angular/Vue dependencies)
> **Framework Compatibility**: OWL 2.8.1 — Carbon CSS classes applied to existing OWL component DOM
> **Module Isolation**: All changes via SCSS cascade and QWeb template inheritance — zero Odoo core modifications

---

## Version Matrix

| Technology          | Version   | Notes                                                      |
| ------------------- | --------- | ---------------------------------------------------------- |
| Odoo                | 19.0 CE   | Community Edition, LGPL-3                                  |
| OWL Framework       | 2.8.1     | Proprietary reactive JS framework                          |
| Bootstrap           | 5.3.3     | Retained but overridden by Carbon tokens                   |
| Chart.js            | 4.4.5     | Replaced by Carbon Charts for graph views                  |
| Carbon Design System| v11       | `@carbon/styles` 1.67.x SCSS package                      |
| Carbon Charts       | 1.27.x    | Vanilla JS (D3.js-based), vendored                         |
| D3.js               | 7.x       | Peer dependency for Carbon Charts                          |
| IBM Plex            | 6.x       | Primary typeface (Sans + Mono), WOFF2 self-hosted          |
| Carbon Icons        | 11.x      | 1600+ SVG icons                                            |

---

## Table of Contents

1. [Navigation Components](#1-navigation-components)
   - [1.1 Top NavBar → Carbon Header + SideNav](#11-top-navbar--carbon-header--sidenav)
   - [1.2 Apps Menu → SideNav with SideNavItems](#12-apps-menu--sidenav-with-sidenavitems)
   - [1.3 Section Menus → SideNavMenu (Nested)](#13-section-menus--sidenavmenu-nested)
   - [1.4 Search Bar → Carbon Search (Global)](#14-search-bar--carbon-search-global)
   - [1.5 Breadcrumbs → Carbon Breadcrumb](#15-breadcrumbs--carbon-breadcrumb)
   - [1.6 Company Switcher → HeaderGlobalAction + Dropdown](#16-company-switcher--headerglobalaction--dropdown)
   - [1.7 User Menu → HeaderGlobalAction + OverflowMenu](#17-user-menu--headerglobalaction--overflowmenu)
   - [1.8 Burger Menu → Carbon Responsive SideNav Collapse](#18-burger-menu--carbon-responsive-sidenav-collapse)
2. [Core UI Components](#2-core-ui-components)
   - [2.1 Dialog/Modal → Carbon Modal](#21-dialogmodal--carbon-modal)
   - [2.2 Confirmation Dialog → Carbon Modal (Danger)](#22-confirmation-dialog--carbon-modal-danger)
   - [2.3 Dropdown → Carbon Dropdown / OverflowMenu](#23-dropdown--carbon-dropdown--overflowmenu)
   - [2.4 Popover → Carbon Popover](#24-popover--carbon-popover)
   - [2.5 Tooltip → Carbon Tooltip / Toggletip](#25-tooltip--carbon-tooltip--toggletip)
   - [2.6 Notebook/Tabs → Carbon Tabs (Line)](#26-notebooktabs--carbon-tabs-line)
   - [2.7 Pager → Carbon Pagination](#27-pager--carbon-pagination)
   - [2.8 Select Menu → Carbon Dropdown / Select](#28-select-menu--carbon-dropdown--select)
   - [2.9 Checkbox → Carbon Checkbox](#29-checkbox--carbon-checkbox)
   - [2.10 Badge → Carbon Tag](#210-badge--carbon-tag)
   - [2.11 Tags List → Carbon Tag Group](#211-tags-list--carbon-tag-group)
   - [2.12 Autocomplete → Carbon ComboBox](#212-autocomplete--carbon-combobox)
   - [2.13 DateTime Picker → Carbon DatePicker + TimePicker](#213-datetime-picker--carbon-datepicker--timepicker)
   - [2.14 Notifications → Carbon Notification](#214-notifications--carbon-notification)
   - [2.15 File Input / Upload → Carbon FileUploader](#215-file-input--upload--carbon-fileuploader)
   - [2.16 File Viewer → Carbon-Styled Viewer](#216-file-viewer--carbon-styled-viewer)
   - [2.17 Code Editor → Carbon CodeSnippet Wrapper](#217-code-editor--carbon-codesnippet-wrapper)
   - [2.18 Avatar → Custom Carbon-Styled Avatar](#218-avatar--custom-carbon-styled-avatar)
   - [2.19 Command Palette → Carbon-Styled Palette](#219-command-palette--carbon-styled-palette)
   - [2.20 Bottom Sheet → Carbon ActionableNotification](#220-bottom-sheet--carbon-actionablenotification)
   - [2.21 Loading Indicator → Carbon Loading](#221-loading-indicator--carbon-loading)
   - [2.22 Resizable Panel → Carbon-Styled Splitter (Gap)](#222-resizable-panel--carbon-styled-splitter-gap)
   - [2.23 Color Picker → Carbon-Styled Picker (Gap)](#223-color-picker--carbon-styled-picker-gap)
   - [2.24 Emoji Picker → Carbon-Styled Picker (Gap)](#224-emoji-picker--carbon-styled-picker-gap)
   - [2.25 Signature Pad → Carbon-Styled Signature (Gap)](#225-signature-pad--carbon-styled-signature-gap)
3. [View Types](#3-view-types)
   - [3.1 List View → Carbon DataTable](#31-list-view--carbon-datatable)
   - [3.2 Form View → Carbon Form Layout + CSS Grid](#32-form-view--carbon-form-layout--css-grid)
   - [3.3 Form Inputs → Carbon TextInput / NumberInput / TextArea / Select](#33-form-inputs--carbon-textinput--numberinput--textarea--select)
   - [3.4 Kanban View → Carbon Tile](#34-kanban-view--carbon-tile)
   - [3.5 Kanban Column Headers → StructuredList Heading](#35-kanban-column-headers--structuredlist-heading)
   - [3.6 Graph View → Carbon Charts (D3.js)](#36-graph-view--carbon-charts-d3js)
   - [3.7 Pivot View → Carbon DataTable (Structured)](#37-pivot-view--carbon-datatable-structured)
   - [3.8 Calendar View → FullCalendar + Carbon Overlay (Gap)](#38-calendar-view--fullcalendar--carbon-overlay-gap)
   - [3.9 Status Bar → Carbon ProgressIndicator](#39-status-bar--carbon-progressindicator)
   - [3.10 View Dialogs → Carbon Modal Variants](#310-view-dialogs--carbon-modal-variants)
4. [Token Mapping (Odoo → Carbon)](#4-token-mapping-odoo--carbon)
5. [Gap Analysis](#5-gap-analysis)
6. [Accessibility (WCAG 2.1 AA)](#6-accessibility-wcag-21-aa)
7. [Responsive Grid Reference](#7-responsive-grid-reference)
8. [Dark Mode Theme Mapping](#8-dark-mode-theme-mapping)
9. [Compliance Summary](#9-compliance-summary)

---

## 1. Navigation Components

The navigation overhaul replaces Odoo's current horizontal top-navbar paradigm with Carbon's UI Shell model: a persistent left-side rail for module navigation and a prominently placed global search in the header.

### 1.1 Top NavBar → Carbon Header + SideNav

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `NavBar` OWL component at `addons/web/static/src/webclient/navbar/navbar.js`. Uses Bootstrap navbar pattern with `AppsMenu` grid-icon dropdown and horizontal `SectionsMenu`. Component uses `useService('menu')` for app/section data, responsive overflow via DOM width measurement (`getBoundingClientRect`), systray registry (`registry.category("systray")`) for utility items. Includes swipe gesture support (`SWIPE_ACTIVATION_THRESHOLD = 100`) and mobile sidebar state (`isAppMenuSidebarOpened`). |
| **Carbon Target**  | `Header` (48px fixed top bar) + `SideNav` (256px expanded / 48px rail)                                  |
| **Import**         | `@carbon/styles/scss/components/ui-shell`                                                                |
| **Props/Variants** | SideNav: `isRail`, `isPersistent`, `isFixedNav`; Header: `aria-label`, `prefix="cds"`                   |
| **SCSS Targets**   | `.o_navbar`, `.o_menu_apps`, `.o_menu_sections`, systray elements                                       |
| **Improvement**    | Persistent side-rail navigation eliminates hidden dropdown discovery; frees vertical space for content; reduces clicks for app switching; consistent Carbon UI Shell accessibility (ARIA landmarks, keyboard navigation) |

### 1.2 Apps Menu → SideNav with SideNavItems

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `AppsMenu` rendered as a CSS grid icon list inside a `Dropdown` in `navbar.xml`. Users must click the grid icon (waffle) to see all installed apps. Hidden by default — requires intentional discovery. |
| **Carbon Target**  | `SideNavItems` with `SideNavLink` entries for each Odoo app, rendered inside the `SideNav` component    |
| **Import**         | `@carbon/styles/scss/components/ui-shell`                                                                |
| **Props/Variants** | `SideNavLink`: `renderIcon`, `href`, `isActive`; `SideNavItems`: grouped by app category                |
| **Improvement**    | Always-visible app list in side rail; no hidden dropdown discovery; icons + labels for scannability; hierarchical organization; keyboard-navigable with arrow keys |

### 1.3 Section Menus → SideNavMenu (Nested)

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `SectionsMenu` in `navbar.xml` — horizontal overflow tabs with a "More" dropdown for items that overflow the viewport width. Uses DOM measurement to determine overflow breakpoints. |
| **Carbon Target**  | `SideNavMenu` with collapsible nested categories per app                                                 |
| **Import**         | `@carbon/styles/scss/components/ui-shell`                                                                |
| **Props/Variants** | `SideNavMenu`: `title`, `isActive`, `defaultExpanded`; contains `SideNavMenuItem` children               |
| **Improvement**    | Hierarchical nesting is clearer than horizontal overflow with "More" dropdown; no overflow issues regardless of menu count; collapsible sections reduce cognitive load |

### 1.4 Search Bar → Carbon Search (Global)

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `SearchBar` OWL component at `addons/web/static/src/search/search_bar/search_bar.js`. Inline form search with autocomplete suggestions, facets, field/operator/value parsing. Uses `dialog`, `orm`, and `ui` services. Integrates `DomainSelectorDialog`, `fuzzyTest` for matching, and `Dropdown`/`DropdownItem` for suggestion rendering. |
| **Carbon Target**  | Carbon `Search` component with `size="lg"`, global placement in header area                              |
| **Import**         | `@carbon/styles/scss/components/search`                                                                  |
| **Props/Variants** | `size="lg"`, `expandable`, `labelText`, `closeButtonLabelText`, `placeHolderText`                        |
| **SCSS Targets**   | `.o_searchview`, `.o_searchview_input`, `.o_searchview_facet`                                            |
| **Improvement**    | Prominent header placement; Carbon search interaction patterns (expand on click/hotkey); Carbon focus ring and clear affordances; accessible `role="search"` landmark |

### 1.5 Breadcrumbs → Carbon Breadcrumb

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `Breadcrumbs` OWL component at `addons/web/static/src/search/breadcrumbs/breadcrumbs.js`. Renders breadcrumb navigation UI with `Dropdown` and `DropdownItem` subcomponents for overflow items. Generates tooltips via `getBreadcrumbTooltip()` with context-aware messages (e.g., "Back to form" vs "Back to list"). |
| **Carbon Target**  | Carbon `Breadcrumb` with `BreadcrumbItem` components                                                     |
| **Import**         | `@carbon/styles/scss/components/breadcrumb`                                                              |
| **Props/Variants** | `noTrailingSlash`, `aria-label="breadcrumb"`                                                             |
| **SCSS Targets**   | `.o_breadcrumb`, `.breadcrumb-item`, `.active`                                                           |
| **Improvement**    | Consistent Carbon typography tokens; forward-slash separators; proper spacing tokens from `$spacing-03`; current-page styling without link treatment; ARIA `nav` landmark |

### 1.6 Company Switcher → HeaderGlobalAction + Dropdown

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `SwitchCompanyMenu` dropdown at `addons/web/static/src/webclient/switch_company_menu/`                   |
| **Carbon Target**  | `HeaderGlobalAction` button triggering Carbon `Dropdown` with `type="inline"`                            |
| **Import**         | `@carbon/styles/scss/components/dropdown`, `@carbon/styles/scss/components/ui-shell`                     |
| **Props/Variants** | `HeaderGlobalAction`: `aria-label`, `tooltipAlignment`; `Dropdown`: `type="inline"`, `selectedItem`      |
| **Improvement**    | Carbon dropdown accessibility (ARIA `listbox` role, keyboard navigation with arrow keys), focus trap, proper `$interactive` token for active company indicator |

### 1.7 User Menu → HeaderGlobalAction + OverflowMenu

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `UserMenu` dropdown at `addons/web/static/src/webclient/user_menu/`                                     |
| **Carbon Target**  | `HeaderGlobalAction` triggering `OverflowMenu` with `flipped` variant                                   |
| **Import**         | `@carbon/styles/scss/components/overflow-menu`                                                           |
| **Props/Variants** | `flipped`, `renderIcon`, `iconDescription`, `selectorPrimaryFocus`                                       |
| **Improvement**    | Accessible overflow menu with focus trap, Carbon `$productive-heading-01` for menu header, motion tokens for open/close animation, ARIA `menu`/`menuitem` roles |

### 1.8 Burger Menu → Carbon Responsive SideNav Collapse

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `BurgerMenu` at `addons/web/static/src/webclient/burger_menu/` — standalone hamburger toggle that opens a mobile sidebar overlay. Separate component from the desktop NavBar. |
| **Carbon Target**  | SideNav responsive collapse behavior built into Carbon UI Shell — no separate component needed            |
| **Import**         | `@carbon/styles/scss/components/ui-shell` (responsive breakpoints built-in)                              |
| **Responsive**     | `lg+` (≥1056px): Full SideNav 256px; `md` (672–1055px): Rail mode 48px; `sm` (<672px): Hamburger overlay |
| **Improvement**    | Unified responsive behavior built into Carbon UI Shell; eliminates the need for a separate mobile component; consistent animation with Carbon motion tokens (`$duration-moderate-01`, `$ease-entrance-productive`) |

---

## 2. Core UI Components

Every core OWL component is restyled using Carbon SCSS tokens applied to existing DOM class selectors. OWL JavaScript behavior is preserved — only visual presentation changes.

### 2.1 Dialog/Modal → Carbon Modal

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `Dialog` OWL component at `addons/web/static/src/core/dialog/dialog.js`. Supports sizes `["sm","md","lg","xl","fs","fullscreen"]`, draggable header via `useDialogDraggable`, Escape/Ctrl+Enter hotkeys (`useHotkey`), `useActiveElement` focus management, `useChildSubEnv({ inDialog: true })`. Uses Bootstrap `.modal-content`, `.modal-header`, `.modal-footer` classes. Props include `contentClass`, `bodyClass`, `fullscreen`, `footer`, `header`, `technical`, `title`, `withBodyPadding`, `onExpand`. Default size is `"lg"`. |
| **Carbon Target**  | Carbon `Modal` with `size="md"` (default), `danger` variant for confirmations                            |
| **Import**         | `@carbon/styles/scss/components/modal`                                                                   |
| **Props/Variants** | `size` ("xs"/"sm"/"md"/"lg"), `danger` boolean, `preventCloseOnClickOutside`                             |
| **SCSS Targets**   | `.o_dialog`, `.modal-content`, `.modal-header`, `.modal-body`, `.modal-footer`                           |
| **Size Mapping**   | Odoo `sm` → Carbon `xs` (320px); Odoo `md` → Carbon `sm` (480px); Odoo `lg` → Carbon `md` (672px); Odoo `xl` → Carbon `lg` (960px); Odoo `fullscreen` → full-viewport overlay |
| **Improvement**    | Built-in focus trap (`aria-modal="true"`), standard button order (secondary left, primary right), Carbon motion/animation (`$duration-moderate-02`), WCAG 2.1 AA focus indicators, `$overlay` token for backdrop |

### 2.2 Confirmation Dialog → Carbon Modal (Danger)

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `ConfirmationDialog` at `addons/web/static/src/core/confirmation_dialog/` — extends `Dialog` with confirm/cancel action callbacks |
| **Carbon Target**  | Carbon `Modal` with `danger` variant — red primary action button using `$support-error` token             |
| **Import**         | `@carbon/styles/scss/components/modal`                                                                   |
| **Props/Variants** | `danger: true`, `primaryButtonText`, `secondaryButtonText`                                               |
| **Improvement**    | Clear danger visual signaling via Carbon `$support-error` (#da1e28) and `$button-danger-primary` tokens; consistent destructive-action pattern across all confirmation dialogs |

### 2.3 Dropdown → Carbon Dropdown / OverflowMenu

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `Dropdown` OWL component at `addons/web/static/src/core/dropdown/dropdown.js`. Generic popover-based dropdown with `DropdownItem`, `DropdownGroup` subcomponents. Uses `usePopover` with `DropdownPopover` for positioning, `useDropdownGroup` and `useDropdownNesting` for nested dropdowns, `useNavigation` for keyboard support. Props include `menuClass`, `position`, `items` (array of `{label, onSelected}`). |
| **Carbon Target**  | Carbon `Dropdown` for select-like behavior, `OverflowMenu` for action menus                              |
| **Import**         | `@carbon/styles/scss/components/dropdown`, `@carbon/styles/scss/components/overflow-menu`                |
| **SCSS Targets**   | `.o-dropdown`, `.dropdown-menu`, `.dropdown-item`, `.o-dropdown--group`                                  |
| **Improvement**    | Keyboard focus management (arrow keys, Home/End), divider styling via `$border-subtle` token, icon support, Carbon motion tokens (`$duration-fast-01`), consistent `$layer-hover` for hover states |

### 2.4 Popover → Carbon Popover

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `Popover` OWL component at `addons/web/static/src/core/popover/popover.js`. Positioned popover using `usePosition` hook (Popper.js-based). Supports click-away dismissal via `useClickAway`, hotkey escape via `useHotkey`, and `useActiveElement` for focus management. Uses `OVERLAY_SYMBOL` for overlay container integration. |
| **Carbon Target**  | Carbon `Popover` with caret and alignment options                                                        |
| **Import**         | `@carbon/styles/scss/components/popover`                                                                 |
| **Props/Variants** | `align` ("top"/"bottom"/"left"/"right"/"top-left"/"top-right"/"bottom-left"/"bottom-right"), `caret` boolean, `dropShadow` |
| **Improvement**    | Standard positioning tokens, Carbon animation (`$duration-fast-01`, `$ease-entrance-productive`), consistent caret styling with `$layer-01` background, `$border-subtle` border, `$shadow` elevation |

### 2.5 Tooltip → Carbon Tooltip / Toggletip

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `Tooltip` OWL component at `addons/web/static/src/core/tooltip/tooltip.js`. Simple component with `close` function, optional `tooltip` text, optional `template` for rich content, and `info` prop for template context. Template is `"web.Tooltip"`. |
| **Carbon Target**  | Carbon `Tooltip` (icon/element trigger, plain text) or `Toggletip` (interactive rich content)            |
| **Import**         | `@carbon/styles/scss/components/tooltip`                                                                 |
| **Props/Variants** | `align` ("top"/"bottom"/"left"/"right"), `direction`, `description`                                      |
| **SCSS Targets**   | `.o_popover.o-tooltip`, tooltip content elements                                                         |
| **Styling**        | Background: `$background-inverse` (Gray 80/100); text: `$text-inverse`; max-width: 288px; Carbon type `$label-01` (12px) |
| **Improvement**    | Carbon caret positioning, accessible `role="tooltip"` with `aria-describedby`, consistent theming across light/dark modes, `$spacing-03` padding |

### 2.6 Notebook/Tabs → Carbon Tabs (Line)

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `Notebook` OWL component at `addons/web/static/src/core/notebook/notebook.js`. Tabbed UI with slot-based and prop-based pages. Supports `isVisible`/`isDisabled` per page, `orientation` prop (default `"horizontal"`), `invalidPages` Set for field validation tracking, `onPageUpdate` callback. Pages can define custom `index` for ordering. Uses `activePane` ref for CSS animation (`.show` class). |
| **Carbon Target**  | Carbon `Tabs` with `type="line"` variant                                                                 |
| **Import**         | `@carbon/styles/scss/components/tabs`                                                                    |
| **Props/Variants** | `type="line"`, `contained` (false for line), auto-scrollable overflow tabs                               |
| **SCSS Targets**   | `.o_notebook`, `.nav-tabs`, `.nav-link`, `.nav-link.active`, `.tab-content`, `.tab-pane`                 |
| **Improvement**    | Cleaner 2px underline indicator using `$border-interactive` token, auto-scroll tab overflow with gradient fade, Carbon `$spacing-05` (16px) padding, accessible `role="tablist"`/`role="tab"`/`role="tabpanel"` ARIA pattern, `$text-secondary` for inactive tabs |

### 2.7 Pager → Carbon Pagination

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `Pager` OWL component at `addons/web/static/src/core/pager/pager.js`. Offset/limit/total-based pagination with inline value editing (click to type range like "1-20"), previous/next navigation buttons, wrapping support. Broadcasts `PAGER_UPDATED_EVENT` via `pagerBus` for mobile synchronization. Props: `offset`, `limit`, `total`, `onUpdate`, `isEditable`, `withAccessKey`. |
| **Carbon Target**  | Carbon `Pagination` with page-size selector and page number input                                        |
| **Import**         | `@carbon/styles/scss/components/pagination`                                                              |
| **Props/Variants** | `pageSize`, `pageSizes` array, `totalItems`, `page`, `backwardText`, `forwardText`, `itemsPerPageText`   |
| **SCSS Targets**   | `.o_pager`, `.o_pager_value`, `.o_pager_next`, `.o_pager_previous`                                       |
| **Improvement**    | Items-per-page selector dropdown, direct page number input field, accessible labels (`aria-label` for navigation), Carbon `$spacing-05` padding, `$icon-primary` for navigation arrows |

### 2.8 Select Menu → Carbon Dropdown / Select

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `SelectMenu` OWL component at `addons/web/static/src/core/select_menu/select_menu.js`. Searchable select with `choices`, `groups`, and `sections` arrays. Supports `multiSelect` mode, `fuzzyLookup` for search filtering, `TagsList` integration for multi-select display. Uses `Dropdown`/`DropdownItem` for rendering. Props include `searchable`, `autoSort`, `required`, `disabled`. |
| **Carbon Target**  | Carbon `Dropdown` (single select) or `MultiSelect` (multi-select mode)                                   |
| **Import**         | `@carbon/styles/scss/components/dropdown`, `@carbon/styles/scss/components/multi-select`                 |
| **Props/Variants** | `filterable`, `titleText`, `label`, `helperText`, `type` ("default"/"inline")                            |
| **SCSS Targets**   | `.o_select_menu`, `.o_select_menu_toggler`, `.o_select_menu_menu`                                        |
| **Improvement**    | Type-ahead filtering with `$field-01` background, accessibility labels (`aria-expanded`, `aria-haspopup="listbox"`), Carbon focus states with 2px `$focus` ring, `$layer-hover` for option hover |

### 2.9 Checkbox → Carbon Checkbox

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `CheckBox` OWL component at `addons/web/static/src/core/checkbox/checkbox.js`. Custom checkbox with auto-incrementing `nextId`, `indeterminate` state support, `useHotkey` for keyboard toggle, `useRef` for DOM access. Props: `id`, `disabled`, `value`, `onChange`, `className`, `name`, `indeterminate`. |
| **Carbon Target**  | Carbon `Checkbox` with `labelText`                                                                       |
| **Import**         | `@carbon/styles/scss/components/checkbox`                                                                |
| **Props/Variants** | `labelText`, `checked`, `indeterminate`, `disabled`, `hideLabel`                                         |
| **SCSS Targets**   | `.o_checkbox`, `.form-check`, `.form-check-input`, `.form-check-label`                                   |
| **Improvement**    | Larger 20×20px click target (minimum 44px touch target with padding), clear checked state with `$icon-primary` checkmark, visible indeterminate dash, Carbon focus ring (`$focus` 2px), `$interactive` border color |

### 2.10 Badge → Carbon Tag

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `Badge` OWL component at `addons/web/static/src/core/badge/badge.js`                                    |
| **Carbon Target**  | Carbon `Tag` with semantic color variants                                                                |
| **Import**         | `@carbon/styles/scss/components/tag`                                                                     |
| **Props/Variants** | `type` ("blue"/"green"/"red"/"teal"/"purple"/"cyan"/"magenta"/"gray"/"warm-gray"/"cool-gray"/"high-contrast"/"outline"), `filter`, `size` ("sm"/"md") |
| **SCSS Targets**   | `.badge`, `.rounded-pill`, `.text-bg-*` Bootstrap badge classes                                          |
| **Improvement**    | Consistent semantic colors from Carbon palette tokens, filterable tag variant with close affordance, accessible `role="status"`, Carbon `$label-01` typography |

### 2.11 Tags List → Carbon Tag Group

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `TagsList` OWL component at `addons/web/static/src/core/tags_list/tags_list.js`. Renders a list of tags with `visibleItemsLimit` for overflow truncation. Shows visible tags up to the limit, with remaining tags accessible via tooltip (`tooltipInfo` JSON). Props: `displayText`, `visibleItemsLimit`, `tags` (array of objects). |
| **Carbon Target**  | Group of Carbon `Tag` components with `dismissible` prop                                                 |
| **Import**         | `@carbon/styles/scss/components/tag`                                                                     |
| **Props/Variants** | `dismissible`, `onClose`, `size="sm"`, overflow "+N" indicator                                           |
| **SCSS Targets**   | `.o_tag`, `.o_tags_list`, `.o_delete`                                                                    |
| **Improvement**    | Dismiss button with `$icon-primary` close icon, Carbon color tokens for tag backgrounds, accessible dismiss action with `aria-label="Remove"`, `$spacing-02` (4px) gap between tags |

### 2.12 Autocomplete → Carbon ComboBox

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `AutoComplete` OWL component at `addons/web/static/src/core/autocomplete/autocomplete.js`. Input with dropdown suggestions from multiple `sources`, each with `options` (static array or async function). Supports `autoSelect`, `resetOnSelect`, `searchOnInputClick`, `inputDebounceDelay` (250ms), `selectOnBlur`. Uses `usePosition` for dropdown placement, `useDebounced` for input throttling, and `useAutofocus`. |
| **Carbon Target**  | Carbon `ComboBox` with `filterable` behavior                                                             |
| **Import**         | `@carbon/styles/scss/components/combo-box`                                                               |
| **Props/Variants** | `filterable`, `placeholder`, `titleText`, `helperText`, `shouldFilterItem`                               |
| **SCSS Targets**   | `.o-autocomplete`, `.o-autocomplete--dropdown-menu`, `.o-autocomplete--dropdown-item`                    |
| **Improvement**    | Better dropdown with type-ahead filtering, clear selection button (×), Carbon focus management with `$focus` ring, `$field-01` input background, `$layer-hover` for suggestion hover states |

### 2.13 DateTime Picker → Carbon DatePicker + TimePicker

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `DateTimePicker` OWL component at `addons/web/static/src/core/datetime/datetime_picker.js`. Combined date and time selection with `luxon` DateTime integration. Supports `range` mode, `minDate`/`maxDate` limits (`DateLimit` type), precision levels (`"days"`/`"months"`/`"years"`/`"decades"`), `rounding` (5-minute default), week number display, `TimePicker` subcomponent, and custom day validation via `isDateValid` callback. |
| **Carbon Target**  | Carbon `DatePicker` with `datePickerType="single"` + Carbon `TimePicker`                                 |
| **Import**         | `@carbon/styles/scss/components/date-picker`, `@carbon/styles/scss/components/time-picker`               |
| **Props/Variants** | `datePickerType` ("single"/"range"), `dateFormat`, `minDate`, `maxDate`, `locale`                        |
| **SCSS Targets**   | `.o_datetime_picker`, `.o_date_item_cell`, `.o_time_picker`, calendar grid elements                      |
| **Improvement**    | Calendar flyout panel with Carbon `$layer-01` background, Carbon input pattern integration (label-above), accessible date entry with `role="application"`, `$interactive` for selected date, `$text-disabled` for out-of-range dates |

### 2.14 Notifications → Carbon Notification

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `NotificationContainer` at `addons/web/static/src/core/notifications/notification_container.js`. Renders `Notification` components within a `.o_notification_manager` container using `Transition` for fade animation. Notifications are stored in a reactive `notifications` state object. Each notification receives props including `className` and transition classes. |
| **Carbon Target**  | `InlineNotification` (contextual, within page flow) and `ToastNotification` (global, overlay)            |
| **Import**         | `@carbon/styles/scss/components/notification`                                                            |
| **Props/Variants** | `kind` ("info"/"success"/"warning"/"error"), `title`, `subtitle`, `caption`, `actionButtonLabel`, `lowContrast`, `hideCloseButton` |
| **SCSS Targets**   | `.o_notification_manager`, `.o_notification`, `.o_notification_title`, `.o_notification_body`, `.o_notification_close` |
| **Improvement**    | Semantic `kind` variants with Carbon token colors (`$support-info`, `$support-success`, `$support-warning`, `$support-error`), action links within notifications, auto-dismiss with configurable timer, accessible ARIA `role="status"` (toast) and `role="alert"` (inline), left border accent |

### 2.15 File Input / Upload → Carbon FileUploader

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `FileInput` at `addons/web/static/src/core/file_input/file_input.js`. Custom file input with `acceptedFileExtensions` (default `"*"`), `multiUpload` support, `route` for upload endpoint (default `/web/binary/upload_attachment`), `useFileUploader` hook, `beforeOpen` async guard, and disable state during upload. |
| **Carbon Target**  | Carbon `FileUploader` with drag-and-drop zone                                                            |
| **Import**         | `@carbon/styles/scss/components/file-uploader`                                                           |
| **Props/Variants** | `accept`, `multiple`, `buttonLabel`, `buttonKind`, `filenameStatus`, `iconDescription`                   |
| **SCSS Targets**   | `.o_file_input`, `input[type="file"]`, file button elements                                              |
| **Improvement**    | Drag-and-drop zone with `$border-strong` dashed border, file list display with status indicators (uploading/complete/error), Carbon `$button-primary` for upload button, `$text-helper` for file type hints |

### 2.16 File Viewer → Carbon-Styled Viewer

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `FileViewer` at `addons/web/static/src/core/file_viewer/` — file preview overlay component              |
| **Carbon Target**  | Custom viewer styled with Carbon tokens — no direct Carbon equivalent                                    |
| **Tokens Applied** | `$layer-01` for background, `$text-primary` for content, `$spacing-05` (16px) for padding, `$overlay` for backdrop, `$icon-primary` for navigation arrows |
| **SCSS Targets**   | `.o_file_viewer`, `.o_viewer_content`, `.o_viewer_toolbar`                                               |
| **Improvement**    | Consistent dark overlay with `$overlay` token, IBM Plex Mono for any code/text previews, Carbon `$spacing-05` padding, `$icon-primary` toolbar icons |

### 2.17 Code Editor → Carbon CodeSnippet Wrapper

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `CodeEditor` at `addons/web/static/src/core/code_editor/` — wraps the Ace editor library                |
| **Carbon Target**  | Carbon `CodeSnippet` with `type="multi"` wrapping the Ace editor instance                                |
| **Import**         | `@carbon/styles/scss/components/code-snippet`                                                            |
| **Props/Variants** | `type="multi"`, `copyButtonDescription`, `feedback`                                                      |
| **Improvement**    | Carbon code styling with IBM Plex Mono font (`$font-family-mono`), `$field-01` background, copy-to-clipboard button, line numbering gutter with `$layer-accent-01` |

### 2.18 Avatar → Custom Carbon-Styled Avatar

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `Avatar` at `addons/web/static/src/core/avatar/` — user/record avatar display component                 |
| **Carbon Target**  | Custom component — no direct Carbon equivalent                                                           |
| **Tokens Applied** | `$spacing-05`/`$spacing-06`/`$spacing-07` for sizing (16px/24px/32px), `$border-subtle` for border, `$layer-02` for fallback background, `$text-on-color` for initials text, `$interactive` for link variant |
| **Improvement**    | Consistent sizing via Carbon spacing scale, proper contrast for initials on colored backgrounds, `$border-subtle` ring for image avatars |

### 2.19 Command Palette → Carbon-Styled Palette

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `CommandPalette` at `addons/web/static/src/core/commands/command_palette.js`. Keyboard-driven command search using `Dialog` as container. Supports namespaced providers, `fuzzyLookup` for matching, `highlightText` for result emphasis, `KeepLast`/`Race` for async debouncing (default 250ms). Opens via global hotkey. |
| **Carbon Target**  | Custom component styled with Carbon `Search` input + `StructuredList` for results                        |
| **Import**         | `@carbon/styles/scss/components/search`, `@carbon/styles/scss/components/structured-list`                |
| **SCSS Targets**   | `.o_command_palette`, `.o_command`, `.o_command_name`, `.o_command_hotkey`                                |
| **Improvement**    | Carbon `Search` styling for input (expandable, clear button), `StructuredList` row pattern for results with `$layer-hover` on hover, `$text-primary` for command names, `$text-secondary` for keyboard shortcut hints, `$highlight` token for matched text |

### 2.20 Bottom Sheet → Carbon ActionableNotification

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `BottomSheet` at `addons/web/static/src/core/bottom_sheet/` — mobile slide-up panel                     |
| **Carbon Target**  | Carbon `ActionableNotification` or custom bottom panel                                                   |
| **Tokens Applied** | `$layer-01` for panel background, `$overlay` for backdrop, `$border-subtle` for top border, Carbon motion tokens (`$duration-moderate-01`, `$ease-entrance-productive`) for slide animation |
| **Note**           | Primarily a mobile pattern; no direct Carbon equivalent for bottom sheets. Style with Carbon layer and motion tokens for visual consistency. |

### 2.21 Loading Indicator → Carbon Loading

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `LoadingIndicator` at `addons/web/static/src/webclient/loading_indicator/` — global page loading indicator |
| **Carbon Target**  | Carbon `Loading` (full-page overlay) or `InlineLoading` (contextual, inline)                             |
| **Import**         | `@carbon/styles/scss/components/loading`, `@carbon/styles/scss/components/inline-loading`                |
| **Props/Variants** | `Loading`: `withOverlay`, `description`; `InlineLoading`: `description`, `status` ("active"/"finished"/"error") |
| **SCSS Targets**   | `.o_loading_indicator`, loading spinner elements                                                         |
| **Improvement**    | Accessible loading pattern with `role="status"` and `aria-live="assertive"`, Carbon animated spinner (productive motion curve), overlay using `$overlay` token, `$interactive` spinner color |

### 2.22 Resizable Panel → Carbon-Styled Splitter (Gap)

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `ResizablePanel` at `addons/web/static/src/core/resizable_panel/` — draggable divider for split-panel resizing |
| **Carbon Target**  | **GAP** — No Carbon equivalent component exists                                                          |
| **Resolution**     | Retain Odoo's `ResizablePanel` OWL component and JavaScript behavior. Apply Carbon tokens for drag-handle styling: `$border-subtle` for divider line, `$icon-secondary` for grip icon, `$layer-hover` for handle hover state, `$spacing-02` (4px) handle width, `cursor: col-resize`. |

### 2.23 Color Picker → Carbon-Styled Picker (Gap)

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `ColorPicker` at `addons/web/static/src/core/color_picker/` — color selection grid                      |
| **Carbon Target**  | **GAP** — No Carbon color picker component exists                                                        |
| **Resolution**     | Retain Odoo's `ColorPicker` OWL component. Restyle with Carbon tokens: `$layer-01` background, `$border-subtle` for swatch borders, `$spacing-03` (8px) between swatches, `$interactive` for selected swatch indicator, Carbon Popover pattern for picker container. |

### 2.24 Emoji Picker → Carbon-Styled Picker (Gap)

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `EmojiPicker` at `addons/web/static/src/core/emoji_picker/` — emoji selection grid with categories       |
| **Carbon Target**  | **GAP** — No Carbon emoji picker component exists                                                        |
| **Resolution**     | Retain Odoo's `EmojiPicker` OWL component. Restyle with Carbon Popover pattern for container, `$field-01` background for search input, `$text-secondary` for category headers, `$layer-hover` for emoji hover state, `$spacing-03` grid gap. |

### 2.25 Signature Pad → Carbon-Styled Signature (Gap)

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `NameAndSignature` at `addons/web/static/src/core/signature/` — signature capture using `signature_pad` library |
| **Carbon Target**  | **GAP** — No Carbon signature capture component exists                                                   |
| **Resolution**     | Retain Odoo's `NameAndSignature` OWL component with `signature_pad` library. Wrap with Carbon `FormItem` pattern: label-above positioning using `$label-01` typography, `$text-helper` for instructions, `$field-01` background for canvas area, `$border-strong` for canvas border, `$spacing-05` padding. |

---

## 3. View Types

View types are the primary data screens in Odoo. Each view is restyled using Carbon component patterns while preserving all data binding, sorting, filtering, and editing behavior from OWL renderers.

### 3.1 List View → Carbon DataTable

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `ListRenderer` at `addons/web/static/src/views/list/list_renderer.js`. Bootstrap `<table>` with custom SCSS. Features sortable columns (click header), inline editing, selection checkboxes (`CheckBox` component), optional row grouping, `Pager` integration, field decorations, `useSortable` for drag reorder, column width calculation via `useMagicColumnWidths`. Imports `CheckBox`, `Dropdown`, `DropdownItem`, `Pager`, `Field`, `ViewButton`, `Widget`, `ActionHelper`. |
| **Carbon Target**  | Carbon `DataTable` with structured list pattern                                                          |
| **Import**         | `@carbon/styles/scss/components/data-table`                                                              |
| **Props/Variants** | `sortable`, `selectable`, `expandable`, `size` ("xs"/"sm"/"md"/"lg"/"xl")                                |
| **SCSS Targets**   | `.o_list_view`, `.o_list_table`, `.o_list_table thead`, `.o_data_row`, `.o_data_cell`, `.o_column_sortable`, `.o_list_record_selector` |
| **Sizing**         | Compact row height: 48px (`size="md"`); header height: 48px; checkbox column: 44px width                |
| **Improvement**    | Higher density with 48px compact rows vs Bootstrap default, better zebra striping using `$layer-accent-01`/`$layer-01` alternation, built-in sort indicator icons (`$icon-primary`), accessible column headers with `aria-sort`, `$border-subtle` for row borders |

### 3.2 Form View → Carbon Form Layout + CSS Grid

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `FormRenderer` at `addons/web/static/src/views/form/form_renderer.js`. Bootstrap grid with `$o-form-*` variables. Integrates `Notebook` for tabs, `Field` for all field widgets, `FormLabel` for labels, `ButtonBox` for action buttons, `StatusBarButtons` for workflow status, `InnerGroup`/`OuterGroup` for field grouping, `Setting` for configuration fields. Form sheet has `$o-form-sheet-min-width: 990px`. |
| **Carbon Target**  | CSS Grid with Carbon 16-column 2x grid + Carbon spacing scale                                           |
| **Import**         | `@carbon/styles/scss/grid`                                                                               |
| **Layout**         | Carbon grid breakpoints — sm: 4 columns, md: 8 columns, lg: 16 columns                                 |
| **SCSS Targets**   | `.o_form_view`, `.o_form_sheet`, `.o_group`, `.o_inner_group`, `.o_form_label`, `.oe_button_box`, `.o_statusbar` |
| **Improvement**    | Consistent `$spacing-05` (16px) gutters, improved label density with Carbon `$label-01` type token (12px labels), responsive breakpoints matching Carbon grid (1056px `lg`), form sheet background using `$layer-01` |

### 3.3 Form Inputs → Carbon TextInput / NumberInput / TextArea / Select

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | Bootstrap `form-control` styled inputs within form views — text, number, textarea, and select elements   |
| **Carbon Target**  | Carbon `TextInput` (`size="md"`), `NumberInput`, `TextArea`, `Select`                                    |
| **Import**         | `@carbon/styles/scss/components/text-input`, `@carbon/styles/scss/components/number-input`, `@carbon/styles/scss/components/textarea`, `@carbon/styles/scss/components/select` |
| **SCSS Targets**   | `.o_field_widget input`, `.o_field_widget textarea`, `.o_field_widget select`, `.o_input`, `.form-control` |
| **Props/Variants** | `size="md"` (40px height), `labelText`, `helperText`, `invalidText`, `warn`, `warnText`, `readOnly`, `disabled` |
| **Improvement**    | Integrated label-above pattern (label always above input), clearer focus states (2px `$focus` ring), `$text-helper` for helper text below input, validation states with `$support-error` border and message, `$field-01` background (transparent in light theme) |

### 3.4 Kanban View → Carbon Tile

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `KanbanRenderer` at `addons/web/static/src/views/kanban/kanban_renderer.js`. Card-based kanban columns with `KanbanRecord` for individual cards, `KanbanHeader` for column headers, `KanbanColumnQuickCreate`/`KanbanRecordQuickCreate` for inline creation. Supports `ConfirmationDialog` for destructive actions, `useSortable` for drag-and-drop, `ColumnProgress` for column metrics. |
| **Carbon Target**  | Carbon `ClickableTile` with `light` variant for kanban cards                                             |
| **Import**         | `@carbon/styles/scss/components/tile`                                                                    |
| **Props/Variants** | `light` variant (white background on `$layer-01`), `href` for clickable behavior                         |
| **SCSS Targets**   | `.o_kanban_view`, `.o_kanban_group`, `.o_kanban_record`, `.o_kanban_header`                               |
| **Improvement**    | Consistent tile elevation using `$shadow` token, `$spacing-05` (16px) padding, hover lift interaction with `$layer-hover`, Carbon `$productive-heading-01` for card titles, `$border-subtle` for card borders |

### 3.5 Kanban Column Headers → StructuredList Heading

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `KanbanHeader` component in kanban columns — column title, record count, fold/unfold toggle              |
| **Carbon Target**  | Carbon `StructuredList` heading pattern for column headers                                                |
| **Import**         | `@carbon/styles/scss/components/structured-list`                                                         |
| **Note**           | **Gap**: Carbon `Tile` component does not include a column-header concept. Adapted from `StructuredList` row-header pattern. |
| **SCSS Targets**   | `.o_kanban_header`, `.o_kanban_header_title`, `.o_kanban_counter`                                        |
| **Improvement**    | Carbon `$heading-compact-01` typography for column titles, `$text-secondary` for record counts, `$spacing-05` bottom padding, `$border-strong` bottom border |

### 3.6 Graph View → Carbon Charts (D3.js)

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `GraphRenderer` at `addons/web/static/src/views/graph/graph_renderer.js`. Wraps Chart.js 4.4.5 with custom `gridOnTop` plugin for line charts, tooltip rendering via OWL template (`web.GraphRenderer.CustomTooltip`), color theme integration via `color_scheme` cookie. Supports 3 chart modes: bar, line, pie. Uses `loadBundle('web.chartjs_lib')` for async Chart.js loading. Color generation via `getColor`/`getCustomColor` from `@web/core/colors/colors`. Includes `ReportViewMeasures` and `Widget` for toolbar controls. |
| **Carbon Target**  | Carbon Charts (`@carbon/charts` v1.27.x, vanilla JS) — 26 chart types, D3.js-based                     |
| **Vendored Files** | `static/lib/carbon-charts/carbon-charts.min.js`, `static/lib/carbon-charts/carbon-charts.min.css`, `static/lib/d3/d3.min.js` |
| **Type Mapping**   | Odoo `bar` → `BarChart` (grouped/stacked); Odoo `line` → `LineChart`; Odoo `pie` → `PieChart`/`DonutChart` |
| **Improvement**    | WCAG 2.1 AA color palettes with `$support-*` token colors, color-blind-friendly pattern fills, better tooltip rendering with Carbon `$layer-01` background, accessible legends with keyboard navigation, 26+ chart types available for future extension |

### 3.7 Pivot View → Carbon DataTable (Structured)

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `PivotRenderer` at `addons/web/static/src/views/pivot/pivot_renderer.js` — multi-level header table with expand/collapse groups, measure aggregation |
| **Carbon Target**  | Carbon `DataTable` with structured/expandable headers                                                    |
| **Import**         | `@carbon/styles/scss/components/data-table`                                                              |
| **Props/Variants** | `useExpandedRows`, `useHeaders` (multi-level), `sortable`                                                |
| **SCSS Targets**   | `.o_pivot`, `.o_pivot_header_cell_opened`, `.o_pivot_header_cell_closed`, `.o_pivot_cell_value`           |
| **Improvement**    | Carbon header grouping with `$layer-accent-01` for grouped header rows, consistent `$spacing-03` cell padding, sortable column indicators, expandable row pattern with `$icon-primary` chevron |

### 3.8 Calendar View → FullCalendar + Carbon Overlay (Gap)

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `CalendarRenderer` at `addons/web/static/src/views/calendar/calendar_renderer.js` using FullCalendar 6.1.11 |
| **Carbon Target**  | **GAP** — No Carbon calendar/scheduler equivalent exists                                                 |
| **Resolution**     | Retain FullCalendar 6.1.11 entirely. Overlay Carbon color tokens, typography (IBM Plex Sans), and spacing on FullCalendar's CSS via custom property overrides. |
| **Token Overlays** | `--fc-border-color` → `$border-subtle`; `--fc-today-bg-color` → `$layer-selected-01`; `--fc-neutral-bg-color` → `$layer-01`; `--fc-page-bg-color` → `$background`; event colors → Carbon semantic palette (`$support-info`, `$support-success`, etc.); `--fc-button-bg-color` → `$interactive`; header font → IBM Plex Sans via `$font-family-sans` |

### 3.9 Status Bar → Carbon ProgressIndicator

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | `StatusBarButtons` at `addons/web/static/src/views/form/status_bar_buttons/` — workflow stage indicator with clickable status buttons in form views |
| **Carbon Target**  | Carbon `ProgressIndicator` with `currentIndex`                                                           |
| **Import**         | `@carbon/styles/scss/components/progress-indicator`                                                      |
| **Props/Variants** | `currentIndex` (active step), `vertical` (boolean), `spaceEqually`                                       |
| **SCSS Targets**   | `.o_statusbar`, `.o_statusbar_status`, `.o_arrow_button`, `.o_status`                                    |
| **Improvement**    | Step-by-step progress visualization with `$interactive` for completed steps, `$text-primary` labels, `$icon-primary` checkmarks for completed states, accessible step announcements via `aria-current="step"` |

### 3.10 View Dialogs → Carbon Modal Variants

| Attribute          | Detail                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| **Current**        | Various view dialogs at `addons/web/static/src/views/view_dialogs/` — `SelectCreateDialog`, `FormViewDialog`, etc. |
| **Carbon Target**  | Carbon `Modal` with appropriate size and variant per dialog type                                          |
| **Import**         | `@carbon/styles/scss/components/modal`                                                                   |
| **Mapping**        | `SelectCreateDialog` → Carbon `Modal` size `lg`; `FormViewDialog` → Carbon `Modal` size `lg` with full form content; selection dialogs → Carbon `Modal` with integrated `DataTable` |
| **Improvement**    | Consistent modal sizing, focus trap, and button ordering across all view dialog types; Carbon `$layer-01` for modal body background |

---

## 4. Token Mapping (Odoo → Carbon)

Comprehensive mapping from Odoo's `$o-*` SCSS variable system to Carbon Design Tokens. This mapping is the foundation for the SCSS token bridge (`carbon_primary_overrides.scss`, `carbon_secondary_overrides.scss`, `carbon_bootstrap_bridge.scss`).

### 4.1 Color Tokens

| Category    | Odoo Variable                    | Odoo Value            | Carbon Token         | Carbon Value (White) | Resolution    |
| ----------- | -------------------------------- | --------------------- | -------------------- | -------------------- | ------------- |
| Brand       | `$o-brand-primary`               | `#71639e` (purple)    | `$interactive`       | `#0f62fe` (Blue 60)  | Remap         |
| Brand       | `$o-brand-secondary`             | derived               | `$background-brand`  | `#0f62fe`            | Remap         |
| Semantic    | `$o-success`                     | `#28a745`             | `$support-success`   | `#24a148` (Green 60) | Snap          |
| Semantic    | `$o-info`                        | `#17a2b8`             | `$support-info`      | `#0043ce` (Blue 70)  | Remap         |
| Semantic    | `$o-warning`                     | `#ffac00`             | `$support-warning`   | `#f1c21b` (Yellow 30)| Remap         |
| Semantic    | `$o-danger`                      | `#dc3545`             | `$support-error`     | `#da1e28` (Red 60)   | Snap          |
| Background  | `$o-webclient-background-color`  | `$o-gray-100` (#f8f9fa)| `$background`       | `#ffffff` (White)    | Remap         |
| Background  | `$o-view-background-color`       | `$o-gray-200`         | `$layer-01`          | `#f4f4f4` (Gray 10)  | Snap          |
| Community   | `$o-community-color`             | `#71639e`             | `$interactive`       | `#0f62fe`            | Remap         |

### 4.2 Gray Scale Tokens

| Odoo Variable   | Odoo Value  | Carbon Token          | Carbon Value       | Notes                           |
| ---------------- | ----------- | --------------------- | ------------------- | ------------------------------- |
| `$o-gray-100`   | `#f8f9fa`   | `$layer-01`           | `#f4f4f4` (Gray 10) | Lightest surface                |
| `$o-gray-200`   | `#e9ecef`   | `$layer-02`           | `#e0e0e0` (Gray 20) | Secondary surface               |
| `$o-gray-300`   | `#dee2e6`   | `$border-subtle`      | `#c6c6c6` (Gray 30) | Subtle borders                  |
| `$o-gray-400`   | `#ced4da`   | `$border-strong`      | `#8d8d8d` (Gray 50) | Strong borders                  |
| `$o-gray-500`   | `#adb5bd`   | `$icon-secondary`     | `#525252` (Gray 70) | Secondary icons                 |
| `$o-gray-600`   | `#6c757d`   | `$text-secondary`     | `#525252` (Gray 70) | Secondary text                  |
| `$o-gray-700`   | `#495057`   | `$text-primary`       | `#161616` (Gray 100)| Primary text                    |
| `$o-gray-800`   | `#343a40`   | `$icon-primary`       | `#161616` (Gray 100)| Primary icons                   |
| `$o-gray-900`   | `#212529`   | `$text-primary`       | `#161616` (Gray 100)| Darkest text                    |

### 4.3 Typography Tokens

| Category       | Odoo Variable              | Odoo Value                    | Carbon Token              | Carbon Value             | Resolution    |
| -------------- | -------------------------- | ----------------------------- | ------------------------- | ------------------------ | ------------- |
| Font Family    | `$o-system-fonts`          | System font stack             | `$font-family-sans`       | `'IBM Plex Sans', sans-serif` | Remap    |
| Font Family    | (monospace)                | `monospace`                   | `$font-family-mono`       | `'IBM Plex Mono', monospace`  | Remap    |
| Base Size      | `$o-font-size-base`        | `14px`                        | `body-compact-01` size    | `14px`                   | Exact match   |
| Line Height    | `$o-line-height-base`      | `1.5`                         | `body-compact-01` lh      | `1.29` (18px/14px)       | Remap (denser)|
| Weight Normal  | `$o-font-weight-normal`    | `400`                         | `body` weight             | `400`                    | Exact match   |
| Weight Bold    | `$o-font-weight-bold`      | `700`                         | `heading` weight          | `600` (semibold)         | Snap          |
| Heading 1      | —                          | —                             | `$heading-03`             | `20px / 600`             | Productive    |
| Heading 2      | —                          | —                             | `$heading-02`             | `16px / 600`             | Productive    |
| Body Long      | —                          | —                             | `$body-long-01`           | `14px / 20px / 400`      | Productive    |
| Body Compact   | —                          | —                             | `$body-compact-01`        | `14px / 18px / 400`      | Productive    |
| Label          | —                          | —                             | `$label-01`               | `12px / 16px / 400`      | Form labels   |
| Helper Text    | —                          | —                             | `$helper-text-01`         | `12px / 16px / 400`      | Input helpers |

### 4.4 Spacing Tokens

| Odoo Variable               | Odoo Value | Carbon Token    | Carbon Value | Notes                          |
| --------------------------- | ---------- | --------------- | ------------ | ------------------------------ |
| `$o-horizontal-padding`     | computed   | `$spacing-05`   | `16px`       | Standard horizontal padding    |
| `$o-form-sheet-min-width`   | `990px`    | Grid `lg` bp    | `1056px`     | Carbon large breakpoint        |
| `$o-form-group-cols`        | `2`        | 16-col grid     | 8 cols each  | Two groups in 16-col grid      |
| (general gap)               | varies     | `$spacing-03`   | `8px`        | Compact gap between elements   |
| (section gap)               | varies     | `$spacing-05`   | `16px`       | Standard section spacing       |
| (page gap)                  | varies     | `$spacing-07`   | `32px`       | Large section margins          |

**Carbon Spacing Scale Reference**:

| Token          | Value  | Usage                                    |
| -------------- | ------ | ---------------------------------------- |
| `$spacing-01`  | `2px`  | Micro spacing (icon padding)             |
| `$spacing-02`  | `4px`  | Tight spacing (tag gaps)                 |
| `$spacing-03`  | `8px`  | Compact element spacing                  |
| `$spacing-04`  | `12px` | Input internal padding                   |
| `$spacing-05`  | `16px` | Standard padding/margins                 |
| `$spacing-06`  | `24px` | Section spacing                          |
| `$spacing-07`  | `32px` | Large section margins                    |
| `$spacing-08`  | `40px` | Form group spacing                       |
| `$spacing-09`  | `48px` | Component height (compact row, header)   |
| `$spacing-10`  | `64px` | Large component spacing                  |
| `$spacing-11`  | `80px` | Layout spacing                           |
| `$spacing-12`  | `96px` | Layout spacing                           |
| `$spacing-13`  | `160px`| Maximum layout spacing                   |

### 4.5 Border Radius Tokens

| Odoo / Bootstrap    | Current Value       | Carbon Token      | Carbon Value | Notes                                      |
| ------------------- | ------------------- | ----------------- | ------------ | ------------------------------------------ |
| `$border-radius`    | `0.375rem` (6px)    | (none)            | `0`          | Carbon uses sharp corners by default        |
| `$border-radius-sm` | `0.25rem` (4px)     | (none)            | `0`          | Override option: set to `4px` for continuity|
| `$border-radius-lg` | `0.5rem` (8px)      | (none)            | `0`          | Adopt sharp corners per Carbon spec         |
| `$border-radius-pill`| `50rem`            | —                 | `50%`        | Retained for avatars and pill badges        |

> **Note**: Carbon Design System defaults to `0` border-radius (sharp corners). The module provides an optional override to `4px` for a softer appearance that aligns more closely with Odoo's current rounded-corner aesthetic. This is configurable via the `$carbon-border-radius-override` variable.

---

## 5. Gap Analysis

Components with no direct Carbon Design System equivalent. Each gap lists the resolution strategy.

| Element                  | Gap Description                                              | Resolution Strategy                                                                                                                           | Carbon Tokens Applied                                                          |
| ------------------------ | ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| **Color Picker**         | No Carbon color picker component                             | Retain Odoo's `ColorPicker` OWL component; restyle with Carbon tokens for backgrounds, borders, spacing, and typography                       | `$layer-01`, `$border-subtle`, `$spacing-03`, `$interactive`                   |
| **Resizable Panel**      | No Carbon splitter/resizable panel                           | Retain Odoo's `ResizablePanel`; apply Carbon drag-handle styling and spacing tokens                                                           | `$border-subtle`, `$icon-secondary`, `$layer-hover`, `$spacing-02`             |
| **Signature Pad**        | No Carbon signature capture component                        | Retain Odoo's `NameAndSignature` with `signature_pad` library; wrap with Carbon `FormItem` pattern (label-above, helper text)                 | `$label-01`, `$text-helper`, `$field-01`, `$border-strong`, `$spacing-05`      |
| **Calendar View**        | No Carbon calendar/scheduler equivalent to FullCalendar      | Retain FullCalendar 6.1.11; overlay Carbon color tokens, typography (IBM Plex Sans), and spacing on its CSS via custom property overrides      | `$border-subtle`, `$layer-selected-01`, `$font-family-sans`, `$interactive`    |
| **Emoji Picker**         | No Carbon emoji picker                                       | Retain Odoo's `EmojiPicker`; restyle with Carbon popover pattern and tokens                                                                   | `$layer-01`, `$field-01`, `$text-secondary`, `$layer-hover`, `$spacing-03`    |
| **Kanban Column Headers**| Carbon Tile has no column-header concept                     | Use Carbon `StructuredList` heading pattern for Kanban column headers                                                                         | `$heading-compact-01`, `$text-secondary`, `$border-strong`, `$spacing-05`      |
| **App Grid View**        | Carbon Switcher is a list, not a grid                        | Create custom Carbon-styled grid layout for app selection using Carbon `Tile` components in a CSS grid                                        | `$layer-01`, `$interactive`, `$spacing-05`, `$shadow`                          |
| **Border Radius**        | Carbon defaults to 0 border-radius; Odoo uses rounded corners| Provide configurable `$carbon-border-radius-override` variable (default: `0`, option: `4px` for softer appearance)                            | —                                                                              |

**Coverage Summary**: Out of approximately 25 high-usage Odoo UI components mapped above, Carbon provides direct equivalents for 20 components (~80% coverage). The remaining 5 components (Color Picker, Resizable Panel, Signature Pad, Calendar, Emoji Picker) plus 3 pattern gaps (Kanban Column Headers, App Grid View, Border Radius) are handled through token-based restyling of existing OWL components.

---

## 6. Accessibility (WCAG 2.1 AA)

All component mappings in this document enforce WCAG 2.1 Level AA compliance. Carbon Design System v11 is designed with accessibility as a core principle.

### 6.1 Contrast Ratios

| Requirement          | Ratio    | Carbon Implementation                                                    |
| -------------------- | -------- | ------------------------------------------------------------------------ |
| Normal text (<18px)  | ≥ 4.5:1 | `$text-primary` (#161616) on `$background` (#ffffff) = 15.4:1           |
| Large text (≥18px or ≥14px bold) | ≥ 3:1 | `$text-secondary` (#525252) on `$background` = 7.4:1            |
| UI components        | ≥ 3:1   | `$interactive` (#0f62fe) on `$background` = 4.6:1                       |
| Disabled elements    | exempt   | `$text-disabled` (#a8a8a8) — exempt from contrast requirements          |

### 6.2 Focus Indicators

All interactive Carbon components include visible focus indicators:

- **Focus ring**: 2px solid outline using `$focus` token color (`#0f62fe` in White theme)
- **Focus inset**: 1px inset on components with borders (inputs, buttons)
- **Focus offset**: 2px offset from element edge for visibility
- **High contrast**: Focus ring color changes to `$focus-inverse` in dark themes
- **Implementation**: CSS `outline: 2px solid var(--cds-focus)` on `:focus-visible`

### 6.3 Keyboard Navigation

| Component        | Tab       | Enter/Space      | Escape        | Arrow Keys              | Home/End    |
| ---------------- | --------- | ---------------- | ------------- | ----------------------- | ----------- |
| Modal            | Trap focus| Close (footer btn)| Close modal  | —                       | —           |
| Dropdown         | Open/close| Select item      | Close         | Navigate items          | First/last  |
| Tabs             | Focus tab | Activate tab     | —             | Navigate tabs           | First/last  |
| SideNav          | Focus link| Navigate to page | —             | Navigate links          | First/last  |
| DataTable        | Focus cell| Sort/select      | —             | Navigate rows/columns   | First/last  |
| Search           | Focus input| —               | Clear/close   | Navigate suggestions    | —           |
| Pagination       | Focus control| Activate      | —             | —                       | First/last  |
| Breadcrumb       | Focus link| Navigate         | —             | —                       | —           |
| Notification     | Focus action| Trigger action | Dismiss       | —                       | —           |
| Checkbox         | Focus     | Toggle           | —             | —                       | —           |
| ComboBox         | Open/close| Select item      | Close         | Navigate items          | First/last  |
| DatePicker       | Focus input| Open calendar   | Close         | Navigate dates          | —           |

### 6.4 ARIA Attributes

| Component        | Required ARIA                                                                    |
| ---------------- | -------------------------------------------------------------------------------- |
| Modal            | `role="dialog"`, `aria-modal="true"`, `aria-labelledby`, `aria-describedby`      |
| Dropdown         | `role="listbox"`, `aria-expanded`, `aria-haspopup`, `aria-activedescendant`      |
| Tabs             | `role="tablist"`, `role="tab"`, `role="tabpanel"`, `aria-selected`, `aria-controls` |
| SideNav          | `role="navigation"`, `aria-label`, `aria-expanded` (for collapsible)             |
| DataTable        | `role="table"`, `aria-sort`, `aria-selected`, `aria-rowcount`, `aria-colcount`   |
| Search           | `role="search"`, `role="combobox"`, `aria-expanded`, `aria-autocomplete`         |
| Pagination       | `role="navigation"`, `aria-label`, `aria-current="page"`                         |
| Breadcrumb       | `nav` element with `aria-label="Breadcrumb"`                                     |
| Notification     | `role="status"` (toast), `role="alert"` (inline)                                 |
| Loading          | `role="status"`, `aria-live="assertive"`, `aria-label`                           |
| Checkbox         | `role="checkbox"`, `aria-checked` ("true"/"false"/"mixed")                       |
| Tooltip          | `role="tooltip"`, `aria-describedby` on trigger element                          |

### 6.5 Color-Blind Considerations

- **Data Visualizations**: Carbon Charts uses pattern fills in addition to color to differentiate data series. The accessible palette avoids red/green adjacency.
- **Semantic Colors**: Carbon's `$support-*` tokens are designed to be distinguishable by shape (icon) and position (left border), not solely by color.
- **Notifications**: Each notification `kind` has a unique icon (info ℹ, success ✓, warning ⚠, error ✕) in addition to its color.
- **Tags/Badges**: Carbon Tag variants use text labels alongside color backgrounds to convey meaning.

---

## 7. Responsive Grid Reference

Carbon's responsive grid replaces Bootstrap's default breakpoints. The 2x Grid with 16-column layout at large breakpoints is the target layout system.

### 7.1 Carbon Breakpoints

| Breakpoint | Carbon Name | Min Width  | Columns | Margin  | Gutter  | Bootstrap Equivalent |
| ---------- | ----------- | ---------- | ------- | ------- | ------- | -------------------- |
| Small      | `sm`        | 320px      | 4       | 16px    | 32px    | `xs` (0) + `sm` (576px) |
| Medium     | `md`        | 672px      | 8       | 16px    | 32px    | `md` (768px)         |
| Large      | `lg`        | 1056px     | 16      | 16px    | 32px    | `lg` (992px)         |
| X-Large    | `xlg`       | 1312px     | 16      | 16px    | 32px    | `xl` (1200px)        |
| Max        | `max`       | 1584px     | 16      | 24px    | 32px    | `xxl` (1400px)       |

### 7.2 Grid CSS Classes

```scss
// Carbon 2x Grid classes
.cds--grid          // Grid container
.cds--col           // Auto-width column
.cds--col-sm-4      // 4 columns at small (full width)
.cds--col-md-4      // 4 columns at medium (half width)
.cds--col-lg-8      // 8 columns at large (half width)
.cds--col-lg-16     // 16 columns at large (full width)

// Grid modifiers
.cds--grid--condensed   // 1px gutters (for DataTable)
.cds--grid--narrow      // 16px gutters (for dense content)
.cds--grid--full-width  // No max-width constraint
```

### 7.3 Side Navigation Responsive Behavior

| Breakpoint Range      | SideNav State              | Width   | Content Area Offset |
| --------------------- | -------------------------- | ------- | ------------------- |
| `lg+` (≥1056px)       | Full SideNav (expanded)    | 256px   | `margin-left: 256px`|
| `md` (672–1055px)     | Rail mode (collapsed)      | 48px    | `margin-left: 48px` |
| `sm` (<672px)          | Hamburger overlay          | 0px     | `margin-left: 0`    |

When in rail mode (48px), the SideNav shows only icons. Hovering or clicking expands to full 256px width as an overlay without shifting content. At the `sm` breakpoint, the SideNav is hidden behind a hamburger menu in the Carbon Header.

### 7.4 Form View Grid Mapping

| Odoo Form Layout       | Carbon Grid Equivalent                              |
| ----------------------- | --------------------------------------------------- |
| Single-column group     | `cds--col-lg-16` (full width)                       |
| Two-column groups       | `cds--col-lg-8` each (half width at `lg`)           |
| Field + label inline    | Label: `cds--col-lg-4`, Field: `cds--col-lg-12`     |
| Full-width field        | `cds--col-lg-16`                                    |
| Chatter (side panel)    | `cds--col-lg-6` beside `cds--col-lg-10` form sheet  |

---

## 8. Dark Mode Theme Mapping

Carbon provides four built-in themes with corresponding token values. Dark mode is achieved by swapping the active theme token set.

### 8.1 Carbon Themes

| Theme    | Use Case              | `$background`    | `$text-primary`   | `$layer-01`     | `$interactive`   | `$border-subtle` |
| -------- | --------------------- | ---------------- | ----------------- | --------------- | ---------------- | ----------------- |
| **White**| Default light mode    | `#ffffff`        | `#161616`         | `#f4f4f4`       | `#0f62fe`        | `#e0e0e0`         |
| **G10**  | Alternative light     | `#f4f4f4`        | `#161616`         | `#ffffff`       | `#0f62fe`        | `#e0e0e0`         |
| **G90**  | Dark mode             | `#262626`        | `#f4f4f4`         | `#393939`       | `#4589ff`        | `#525252`         |
| **G100** | Darkest mode          | `#161616`        | `#f4f4f4`         | `#262626`       | `#4589ff`        | `#393939`         |

### 8.2 Theme Selection Strategy

| Mode         | Primary Theme | Fallback Theme | Notes                                              |
| ------------ | ------------- | -------------- | -------------------------------------------------- |
| Light Mode   | **White**     | G10            | White is the default for maximum contrast           |
| Dark Mode    | **G90**       | G100           | G90 provides comfortable dark without full black    |

### 8.3 Odoo Integration

Dark mode integrates with Odoo's existing `color_scheme` cookie mechanism:

```
Cookie: color_scheme=light  →  Apply Carbon White theme tokens
Cookie: color_scheme=dark   →  Apply Carbon G90 theme tokens
```

- **Toggle Component**: `CarbonThemeToggle` OWL component placed in Carbon Header utilities area
- **CSS Custom Properties**: Theme tokens are emitted as `--cds-*` CSS custom properties, enabling runtime switching without page reload
- **Asset Bundle**: Dark mode SCSS injected into `web.assets_web_dark` and `web.assets_backend_lazy_dark` bundles
- **Persistence**: Theme preference stored via Odoo's `color_scheme` cookie (existing mechanism) for cross-session persistence

### 8.4 Dark Mode Token Overrides

Key token changes when switching from White to G90:

| Token                     | White Theme    | G90 Theme      | Purpose                    |
| ------------------------- | -------------- | -------------- | -------------------------- |
| `$background`             | `#ffffff`      | `#262626`      | Page background            |
| `$layer-01`               | `#f4f4f4`      | `#393939`      | Card/panel surfaces        |
| `$layer-02`               | `#e0e0e0`      | `#525252`      | Elevated surfaces          |
| `$text-primary`           | `#161616`      | `#f4f4f4`      | Primary body text          |
| `$text-secondary`         | `#525252`      | `#c6c6c6`      | Secondary/muted text       |
| `$interactive`            | `#0f62fe`      | `#4589ff`      | Links, active elements     |
| `$border-subtle`          | `#e0e0e0`      | `#525252`      | Subtle borders             |
| `$field-01`               | `#f4f4f4`      | `#393939`      | Input backgrounds          |
| `$support-error`          | `#da1e28`      | `#ff8389`      | Error states               |
| `$support-success`        | `#24a148`      | `#42be65`      | Success states             |
| `$support-warning`        | `#f1c21b`      | `#f1c21b`      | Warning states (unchanged) |
| `$support-info`           | `#0043ce`      | `#4589ff`      | Info states                |
| `$focus`                  | `#0f62fe`      | `#ffffff`      | Focus indicator            |
| `$overlay`                | `rgba(22,22,22,0.5)` | `rgba(22,22,22,0.7)` | Modal/overlay backdrop |

---

## 9. Compliance Summary

### 9.1 Coverage Statistics

| Metric                          | Value                                                    |
| ------------------------------- | -------------------------------------------------------- |
| Total Odoo components mapped    | 35 (25 core + 10 view types)                             |
| Direct Carbon equivalents       | 28 (~80%)                                                |
| Gap components (restyled)       | 7 (~20%)                                                 |
| Token categories mapped         | 5 (color, gray, typography, spacing, border-radius)      |
| WCAG 2.1 AA compliance          | All 35 components                                        |
| Dark mode support               | Full (G90 primary, G100 secondary)                       |
| Responsive grid coverage        | 5 breakpoints (sm/md/lg/xlg/max)                         |

### 9.2 Integration Constraints

| Constraint                    | Compliance                                                                |
| ----------------------------- | ------------------------------------------------------------------------- |
| Zero core modifications       | All changes via SCSS cascade and QWeb `inherit_id` template inheritance   |
| Backward compatibility        | All existing views, actions, and third-party modules continue functioning |
| OWL 2.8.1 compatibility       | Carbon CSS applied to existing OWL component DOM; no framework change     |
| Sass compilation (libsass)    | Carbon tokens pre-compiled or emitted as CSS custom properties (`--cds-*`)|
| Self-hosted assets            | All fonts, icons, and libraries vendored in `static/lib/`                 |
| Installable/uninstallable     | Module removal fully restores original Odoo interface                     |

### 9.3 File Reference Map

| Module File                                        | Purpose                                    | Section Reference         |
| -------------------------------------------------- | ------------------------------------------ | ------------------------- |
| `static/src/scss/carbon_tokens.scss`               | Core token definitions                     | §4 Token Mapping          |
| `static/src/scss/carbon_primary_overrides.scss`    | Override `$o-*` primary variables           | §4.1–4.3 Color/Type      |
| `static/src/scss/carbon_secondary_overrides.scss`  | Override secondary UI variables             | §4.1 Color, §4.4 Spacing |
| `static/src/scss/carbon_bootstrap_bridge.scss`     | Redirect Bootstrap vars to Carbon tokens    | §4 Token Mapping          |
| `static/src/scss/carbon_font_face.scss`            | IBM Plex font declarations                  | §4.3 Typography           |
| `static/src/scss/carbon_utilities.scss`            | Carbon utility classes                      | §7 Responsive Grid        |
| `static/src/scss/carbon_dark_theme.scss`           | Dark mode token set                         | §8 Dark Mode              |
| `static/src/scss/components/dialog.scss`           | Modal styling                               | §2.1–2.2 Dialog           |
| `static/src/scss/components/dropdown.scss`         | Dropdown styling                            | §2.3 Dropdown             |
| `static/src/scss/components/tooltip.scss`          | Tooltip styling                             | §2.5 Tooltip              |
| `static/src/scss/components/notification.scss`     | Notification styling                        | §2.14 Notifications       |
| `static/src/scss/components/tabs.scss`             | Tabs styling                                | §2.6 Notebook/Tabs        |
| `static/src/scss/components/pagination.scss`       | Pagination styling                          | §2.7 Pager                |
| `static/src/scss/components/forms.scss`            | Form controls styling                       | §3.3 Form Inputs          |
| `static/src/scss/components/datatable.scss`        | DataTable styling                           | §3.1 List View            |
| `static/src/scss/components/tags.scss`             | Tag styling                                 | §2.10–2.11 Badge/Tags     |
| `static/src/scss/components/breadcrumb.scss`       | Breadcrumb styling                          | §1.5 Breadcrumbs          |
| `static/src/scss/components/search.scss`           | Search styling                              | §1.4 Search Bar           |
| `static/src/scss/components/kanban.scss`           | Kanban tile styling                         | §3.4 Kanban View          |
| `static/src/scss/components/checkbox.scss`         | Checkbox styling                            | §2.9 Checkbox             |
| `static/src/scss/components/file_uploader.scss`    | File uploader styling                       | §2.15 File Upload         |
| `static/src/scss/components/date_picker.scss`      | Date picker styling                         | §2.13 DateTime Picker     |
| `static/src/scss/components/loading.scss`          | Loading indicator styling                   | §2.21 Loading             |
| `static/src/scss/components/popover.scss`          | Popover styling                             | §2.4 Popover              |
| `static/src/scss/components/accordion.scss`        | Accordion styling                           | Settings form             |
| `static/src/scss/components/status_bar.scss`       | Progress indicator styling                  | §3.9 Status Bar           |
| `static/src/webclient/carbon_shell.js`             | Carbon UI Shell component                   | §1.1 Top NavBar           |
| `static/src/webclient/carbon_header.js`            | Carbon Header component                     | §1.1 Top NavBar           |
| `static/src/webclient/carbon_sidenav.js`           | Carbon SideNav component                    | §1.2–1.3 Apps/Sections    |
| `static/src/webclient/carbon_global_search.js`     | Global search component                     | §1.4 Search Bar           |
| `static/src/webclient/carbon_switcher.js`          | App switcher component                      | §1.2 Apps Menu            |
| `static/src/webclient/carbon_theme_toggle.js`      | Theme toggle component                      | §8 Dark Mode              |
| `static/src/views/graph/carbon_graph_renderer.js`  | Carbon Charts renderer                      | §3.6 Graph View           |
| `views/webclient_templates.xml`                    | QWeb template inheritance                   | §1.1 Navigation Shell     |

---

*This document is part of the `carbon_ui` Odoo module. For installation and configuration, see [README.md](../README.md).*
