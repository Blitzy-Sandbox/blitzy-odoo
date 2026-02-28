# Carbon UI — IBM Carbon Design System for Odoo 19.0

A standalone Odoo addon module that redesigns the **Odoo 19.0 Community Edition**
backend UI using **IBM Carbon Design System v11** with the **Productive** theme.

This module replaces the default Bootstrap 5.3.3 / Odoo-native design catalog with
Carbon's token-based theming, navigation shell, component library, and data
visualization toolkit — all delivered through standard Odoo template inheritance and
SCSS cascade. **Zero modifications** are made to Odoo core files.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Module Architecture](#module-architecture)
- [Component Mapping Summary](#component-mapping-summary)
- [Vendored Dependencies](#vendored-dependencies)
- [File Structure](#file-structure)
- [Backward Compatibility](#backward-compatibility)
- [Accessibility](#accessibility)
- [Development Notes](#development-notes)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Overview

**Carbon UI** transforms the Odoo 19.0 backend interface by applying the IBM Carbon
Design System v11 — an enterprise-grade, accessibility-first design system — to every
core screen: list views, form views, kanban boards, graph dashboards, navigation, and
more.

The module operates entirely through Odoo's standard extension mechanisms:

- **QWeb template inheritance** (`inherit_id` + `xpath`) to restructure the webclient
  shell layout.
- **SCSS asset bundle cascade** to override Odoo's `$o-*` design tokens with Carbon
  equivalents.
- **OWL component registry overrides** to register new Carbon-styled renderers (e.g.,
  Carbon Charts for graph views).

When installed, the entire backend adopts Carbon's visual language. When uninstalled,
the original Odoo interface is fully restored with zero residual artifacts.

---

## Key Features

### Complete Component Mapping

Every high-usage Odoo UI component is mapped to its Carbon Design System equivalent.
Over 20 core components — dialogs, dropdowns, notifications, tabs, pagination, form
inputs, data tables, and more — receive Carbon styling while preserving their OWL
JavaScript behavior. See [Component Mapping Summary](#component-mapping-summary) and
the full reference in [`doc/component_mapping.md`](doc/component_mapping.md).

### Navigation Overhaul

The horizontal top navbar (`NavBar` with `AppsMenu` grid dropdown and horizontal
`SectionsMenu`) is replaced with Carbon's UI Shell model:

- **Persistent left-side rail** (48px collapsed / 256px expanded) for module
  navigation, eliminating the "hidden menu" discovery problem.
- **Carbon Header** (48px height) with global search, notification bell, user avatar,
  company switcher, and theme toggle.
- **Responsive behavior**: The side-rail collapses at the `md` breakpoint (672px) and
  hides behind a hamburger menu at the `sm` breakpoint (320px).

### SCSS Token-Based Theming

Carbon design tokens override Odoo's existing `$o-*` SCSS variable pipeline through a
three-layer bridge:

```
Carbon Tokens  →  $o-* Odoo Variables  →  Bootstrap $ Variables
```

This approach means every Odoo component and third-party module that uses standard
`$o-*` variables automatically inherits Carbon styling without modification.

### Spacing and Layout Normalization

Carbon's spacing scale (based on multiples of 2, 4, and 8) replaces arbitrary spacing
values across all form views and data-heavy screens:

| Token | Value | Usage |
|-------|-------|-------|
| `$spacing-01` | 2px | Inline icon gaps |
| `$spacing-02` | 4px | Tight element spacing |
| `$spacing-03` | 8px | Component internal padding |
| `$spacing-04` | 12px | Related element grouping |
| `$spacing-05` | 16px | Standard element spacing |
| `$spacing-06` | 24px | Section spacing |
| `$spacing-07` | 32px | Layout block spacing |
| `$spacing-08` | 40px | Large section padding |
| `$spacing-09` | 48px | Header/rail height |

Carbon's responsive grid breakpoints are adopted in place of Bootstrap's defaults:

| Breakpoint | Name | Min Width | Columns | Margin |
|------------|------|-----------|---------|--------|
| Small | `sm` | 320px | 4 | 16px |
| Medium | `md` | 672px | 8 | 16px |
| Large | `lg` | 1056px | 16 | 16px |
| X-Large | `xlg` | 1312px | 16 | 16px |
| Max | `max` | 1584px | 16 | 24px |

### Data Visualization Replacement

The existing Chart.js 4.4.5 integration in Odoo's graph views is replaced with
**Carbon Charts** (D3.js-based, `@carbon/charts` v1.27.x):

- 26 chart types supported (bar, line, pie, doughnut, area, scatter, and more).
- WCAG 2.1 AA-compliant color palettes.
- Color-blind-friendly patterns and accessible tooltips.
- Consistent Carbon styling across all chart types.

### Light and Dark Mode

Full theme support through Carbon's four built-in themes:

| Theme | Background | Use Case |
|-------|-----------|----------|
| **White** | `#ffffff` | Default light mode |
| **Gray 10 (G10)** | `#f4f4f4` | Subtle light alternative |
| **Gray 90 (G90)** | `#262626` | Dark mode |
| **Gray 100 (G100)** | `#161616` | High-contrast dark mode |

Theme switching integrates with Odoo's existing `color_scheme` cookie mechanism for
session persistence. A toggle control in the Carbon header enables one-click switching.

### WCAG 2.1 AA Accessibility Compliance

- **Contrast ratios**: 4.5:1 minimum for normal text, 3:1 for large text.
- **Focus indicators**: 2px outline focus ring on all interactive elements using
  Carbon's `$focus` token.
- **Keyboard navigation**: Full keyboard support — Tab for focus movement, Enter/Space
  for activation, Escape for dismissal, Arrow keys for menu navigation.
- **Screen reader support**: Proper ARIA attributes, live regions for dynamic content,
  and semantic HTML structure.
- **Color independence**: Data visualizations use pattern fills and shape indicators in
  addition to color.

### IBM Plex Typography (Productive Theme)

IBM Plex Sans replaces Odoo's system font stack as the primary typeface:

- **Body text**: IBM Plex Sans Regular (400) at 14px / 18px line-height
  (`body-compact-01` Productive style).
- **Headings**: IBM Plex Sans SemiBold (600) at Carbon's heading scale.
- **Code**: IBM Plex Mono Regular (400) for code snippets and technical content.
- **Self-hosted**: All font files are bundled in the module (WOFF2 format) with no
  external CDN dependencies.
- **Performance**: Loaded with `font-display: swap` for instant text rendering.

---

## Requirements

| Requirement | Version |
|-------------|---------|
| Odoo | 19.0 Community Edition |
| Python | 3.10 – 3.13 |
| `web` module | Installed (ships with Odoo core) |
| Web browser | Any modern browser supporting CSS custom properties |

No additional system packages or npm toolchains are required at runtime. All Carbon
assets are pre-compiled and vendored within the module.

---

## Installation

### Method 1: Addons Path

1. Copy the `carbon_ui` folder into your Odoo addons directory:

   ```bash
   cp -r carbon_ui /path/to/odoo/addons/
   ```

2. Update the addons path in your Odoo configuration file (`odoo.conf`):

   ```ini
   [options]
   addons_path = /path/to/odoo/addons
   ```

3. Restart the Odoo server:

   ```bash
   systemctl restart odoo
   ```

4. Install the module via the **Apps** menu:
   - Navigate to **Apps** in the Odoo backend.
   - Remove the "Apps" filter from the search bar.
   - Search for **"Carbon Design System UI"**.
   - Click **Install**.

### Method 2: Command Line

Install directly via the Odoo command line:

```bash
python -m odoo \
    --addons-path=addons \
    --database=your_database \
    --db_user=odoo \
    --db_password=odoo \
    --db_host=localhost \
    --init=carbon_ui \
    --stop-after-init
```

### Uninstallation

The module can be safely uninstalled at any time:

1. Navigate to **Apps** in the Odoo backend.
2. Search for **"Carbon Design System UI"**.
3. Click **Uninstall**.

The original Odoo interface is fully restored upon uninstallation with no residual
artifacts.

---

## Configuration

### Theme Switching (Light / Dark Mode)

A theme toggle button is located in the Carbon header bar (top-right utilities area).
Click it to switch between light mode (White theme) and dark mode (G90 theme).

The selected theme is persisted via Odoo's `color_scheme` cookie, so it carries across
sessions and page reloads.

### Side Navigation

The left-side navigation rail has two display modes:

- **Rail mode** (48px width): Shows icon-only navigation. This is the default
  collapsed state.
- **Expanded mode** (256px width): Shows full text labels alongside icons.

Toggle between modes by clicking the hamburger icon in the Carbon header. The side-nav
state is persisted in the browser.

### Responsive Behavior

| Viewport | Side Navigation | Header |
|----------|----------------|--------|
| ≥ 1056px (lg) | Expanded or rail (user choice) | Full header with search |
| 672px – 1055px (md) | Rail mode (48px) | Compact header |
| < 672px (sm) | Hidden (hamburger overlay) | Minimal header |

---

## Module Architecture

### Design Principles

1. **Zero Core Modifications**: No files under `addons/web/` or `odoo/` are modified.
   All changes operate through Odoo's standard module extension mechanisms.
2. **Installable / Uninstallable**: The module can be added or removed without breaking
   the system or leaving behind artifacts.
3. **Token-Based Theming**: All visual values (colors, spacing, typography) are
   expressed through Carbon design tokens, enabling consistent theme switching.
4. **Backward Compatible**: All existing views, actions, controllers, and third-party
   modules continue to function without modification.

### SCSS Token Bridge

The theming architecture uses a three-layer override cascade:

```
┌─────────────────────────────────────────────────────┐
│  Layer 1: Carbon Design Tokens                       │
│  carbon_tokens.scss                                  │
│  Defines --cds-* CSS custom properties from Carbon   │
│  White, G10, G90, G100 theme definitions             │
├─────────────────────────────────────────────────────┤
│  Layer 2: Odoo Variable Overrides                    │
│  carbon_primary_overrides.scss                       │
│  carbon_secondary_overrides.scss                     │
│  Maps Carbon tokens → $o-* Odoo SCSS variables       │
├─────────────────────────────────────────────────────┤
│  Layer 3: Bootstrap Bridge                           │
│  carbon_bootstrap_bridge.scss                        │
│  Redirects Bootstrap $primary, $secondary, etc. to   │
│  Carbon-overridden $o-* values                       │
└─────────────────────────────────────────────────────┘
```

This approach ensures every Odoo component that references `$o-brand-primary`,
`$o-gray-*`, or any Bootstrap `$` variable automatically receives Carbon styling.

### QWeb Template Inheritance

The webclient layout is restructured via standard QWeb `inherit_id` + `xpath`:

- **`web.WebClient`** template: Wraps the root layout in a Carbon UI Shell structure
  (Header + SideNav + Content area), replacing the default `<NavBar/>` placement.
- **`web.NavBar`** template: Overridden to render Carbon Header bar components
  (global search, systray utilities, company switcher, user menu).

### OWL Component Registry

New OWL components are registered using Odoo's component registries:

- **View Registry**: `carbon_graph` view type registered as a replacement for the
  default Chart.js-based graph renderer.
- **Systray Registry**: Theme toggle and other header utilities rendered with Carbon
  styling.

### Asset Bundle Injection Points

The module injects its assets into Odoo's existing bundle system via `__manifest__.py`:

| Bundle | Purpose | Carbon Contribution |
|--------|---------|-------------------|
| `web._assets_primary_variables` | Primary SCSS variable definitions | Carbon token definitions, `$o-*` overrides |
| `web._assets_secondary_variables` | Secondary UI variables | Secondary variable overrides |
| `web.assets_backend` | Main backend JS/CSS bundle | Pre-compiled Carbon CSS, font declarations, Bootstrap bridge, utility classes, all component SCSS overrides, navigation OWL components (JS + XML + SCSS), theme toggle |
| `web.assets_web_dark` | Dark mode SCSS bundle | Carbon G90/G100 dark theme tokens, dark component overrides |
| `web.assets_backend_lazy` | Lazy-loaded bundle (graph/pivot) | D3.js, Carbon Charts JS/CSS, Carbon graph renderer (JS + XML + SCSS), graph view registration |
| `web.assets_unit_tests` | Test bundle | HOOT test files |

---

## Component Mapping Summary

The table below shows key component mappings. For the full 25+ component reference, see
[`doc/component_mapping.md`](doc/component_mapping.md).

| Odoo Component | Carbon Equivalent | Improvement |
|---------------|------------------|-------------|
| NavBar (top) | Carbon Header + SideNav | Persistent navigation reduces clicks; side-rail frees vertical space |
| Dialog | Carbon Modal | Focus trap, standard button order, Carbon motion |
| List View | Carbon DataTable | Higher density rows (48px), zebra striping, built-in sort indicators |
| Form Controls | Carbon TextInput / Select / Checkbox | Integrated label-above pattern, clearer focus states, helper text |
| Notifications | Carbon InlineNotification / ToastNotification | Action links, auto-dismiss, accessible ARIA alerts |
| Tabs (Notebook) | Carbon Tabs (line variant) | Cleaner underline indicator, auto-scroll overflow |
| Pagination (Pager) | Carbon Pagination | Items-per-page selector, page input, accessible labels |
| Dropdown | Carbon Dropdown / ComboBox | Type-ahead filtering, ARIA keyboard navigation |
| Tooltip | Carbon Tooltip | Carbon caret positioning, accessible ARIA |
| Breadcrumbs | Carbon Breadcrumb | Consistent typography, spacing tokens |
| Search Bar | Carbon Search (expandable) | Prominent header placement, expandable pattern |
| Kanban Cards | Carbon ClickableTile | Consistent tile elevation, spacing, interaction states |
| Graph Views | Carbon Charts (D3.js) | WCAG 2.1 AA colors, color-blind palettes, 26 chart types |
| Badge / Tags | Carbon Tag | Semantic color variants, dismissible, filter tag |
| File Upload | Carbon FileUploader | Drag-and-drop zone, file list, status indicators |
| Status Bar | Carbon ProgressIndicator | Step-by-step progress with accessible labels |
| Loading | Carbon Loading / InlineLoading | Accessible loading pattern, Carbon motion |
| Date Picker | Carbon DatePicker | Calendar flyout, Carbon input pattern |
| Checkbox | Carbon Checkbox | Larger click target, clear checked/indeterminate states |
| Accordion | Carbon Accordion | Collapsible sections for settings forms |

**Gap Components** (no Carbon equivalent — restyled with Carbon tokens):

| Component | Resolution |
|-----------|-----------|
| Color Picker | Retained with Carbon token styling |
| Resizable Panel | Retained with Carbon drag-handle styling |
| Signature Pad | Retained with Carbon form-item pattern |
| Calendar (FullCalendar) | Retained with Carbon color/typography overlay |
| Emoji Picker | Retained with Carbon popover pattern |

---

## Vendored Dependencies

All external dependencies are vendored within the module's `static/lib/` directory.
No npm toolchain or CDN access is required at runtime.

| Package | Version | Location | Purpose |
|---------|---------|----------|---------|
| `@carbon/styles` | v11 | `static/lib/carbon-styles/` | Pre-compiled Carbon CSS tokens and component styles |
| `@carbon/charts` | v1.27.x | `static/lib/carbon-charts/` | D3.js-based charting library (vanilla JS bundle) |
| `d3` | v7.x | `static/lib/d3/` | D3.js — peer dependency for Carbon Charts |
| `@ibm/plex` | v6.x | `static/lib/ibm-plex/` | IBM Plex Sans (7 weights) and Plex Mono (3 weights) in WOFF2 |
| `@carbon/icons` | v11.x | `static/lib/carbon-icons/` | Carbon icon SVGs at 16px, 20px, and 32px sizes |

### Vendored File Details

```
static/lib/
├── carbon-styles/
│   ├── LICENSE                    # Carbon Design System license
│   ├── README.md                  # Carbon styles package documentation
│   ├── carbon-components.css      # Pre-compiled Carbon component styles
│   ├── carbon-styles.min.css      # Minified Carbon styles bundle
│   ├── carbon-themes.min.css      # Minified Carbon theme definitions
│   ├── carbon-tokens.css          # Carbon CSS custom properties (all 4 themes)
│   └── scss/                      # Carbon SCSS source files (reference only)
├── carbon-charts/
│   ├── carbon-charts.min.js       # Carbon Charts UMD bundle
│   └── carbon-charts.min.css      # Carbon Charts CSS
├── d3/
│   └── d3.min.js                  # D3.js v7.x
├── ibm-plex/
│   ├── IBMPlexMono-Regular.woff2  # Root-level Mono Regular (primary weight)
│   ├── IBMPlexMono-SemiBold.woff2 # Root-level Mono SemiBold (emphasis weight)
│   ├── IBMPlexSans-Light.woff2    # Root-level Sans Light (thin weight)
│   ├── IBMPlexSans-Medium.woff2   # Root-level Sans Medium (medium weight)
│   ├── IBMPlexSans-Regular.woff2  # Root-level Sans Regular (body weight)
│   ├── IBMPlexSans-SemiBold.woff2 # Root-level Sans SemiBold (heading weight)
│   ├── sans/                      # IBM Plex Sans WOFF2 (Light, Regular, Text,
│   │                              #   Medium, SemiBold, Bold, Italic)
│   └── mono/                      # IBM Plex Mono WOFF2 (Regular, Medium, SemiBold)
└── carbon-icons/
    ├── 16/                        # 16px icon SVGs (68 icons)
    ├── 20/                        # 20px icon SVGs (9 icons)
    └── 32/                        # 32px icon SVGs (43 icons)
```

---

## File Structure

```
addons/carbon_ui/
├── __init__.py                              # Python package initializer (empty)
├── __manifest__.py                          # Module manifest and asset bundle config
├── README.md                                # This documentation file
│
├── doc/
│   └── component_mapping.md                 # Full component-by-component mapping
│
├── views/
│   ├── webclient_templates.xml              # QWeb template inheritance definitions
│   └── carbon_assets.xml                    # Supplementary asset registration
│
├── static/
│   ├── lib/                                 # Vendored third-party libraries
│   │   ├── carbon-styles/                   # Pre-compiled Carbon CSS + SCSS sources
│   │   ├── carbon-charts/                   # Carbon Charts JS + CSS
│   │   ├── d3/                              # D3.js
│   │   ├── ibm-plex/                        # IBM Plex Sans and Mono fonts
│   │   └── carbon-icons/                    # Carbon icon SVGs
│   │
│   ├── src/
│   │   ├── scss/                            # SCSS token bridge and overrides
│   │   │   ├── carbon_tokens.scss           # Core Carbon design token definitions
│   │   │   ├── carbon_font_face.scss        # @font-face declarations for IBM Plex
│   │   │   ├── carbon_primary_overrides.scss    # $o-* primary variable overrides
│   │   │   ├── carbon_secondary_overrides.scss  # Secondary variable overrides
│   │   │   ├── carbon_bootstrap_bridge.scss     # Bootstrap variable bridge
│   │   │   ├── carbon_utilities.scss            # Carbon utility classes
│   │   │   ├── carbon_dark_theme.scss           # G90/G100 dark mode tokens
│   │   │   ├── carbon_dark_components.scss      # Dark mode component overrides
│   │   │   └── components/                      # Per-component style overrides
│   │   │       ├── accordion.scss
│   │   │       ├── breadcrumb.scss
│   │   │       ├── checkbox.scss
│   │   │       ├── datatable.scss
│   │   │       ├── date_picker.scss
│   │   │       ├── dialog.scss
│   │   │       ├── dropdown.scss
│   │   │       ├── file_uploader.scss
│   │   │       ├── forms.scss
│   │   │       ├── kanban.scss
│   │   │       ├── loading.scss
│   │   │       ├── notification.scss
│   │   │       ├── pagination.scss
│   │   │       ├── popover.scss
│   │   │       ├── search.scss
│   │   │       ├── status_bar.scss
│   │   │       ├── tabs.scss
│   │   │       ├── tags.scss
│   │   │       └── tooltip.scss
│   │   │
│   │   ├── webclient/                       # Carbon UI Shell OWL components
│   │   │   ├── carbon_shell.js              # Root UI Shell component
│   │   │   ├── carbon_shell.xml             # Shell QWeb template
│   │   │   ├── carbon_shell.scss            # Shell layout styles
│   │   │   ├── carbon_header.js             # Header component
│   │   │   ├── carbon_header.xml            # Header template
│   │   │   ├── carbon_sidenav.js            # SideNav / SideRail component
│   │   │   ├── carbon_sidenav.xml           # SideNav template
│   │   │   ├── carbon_sidenav.scss          # SideNav styles
│   │   │   ├── carbon_global_search.js      # Global search component
│   │   │   ├── carbon_global_search.xml     # Global search template
│   │   │   ├── carbon_switcher.js           # App switcher panel component
│   │   │   ├── carbon_switcher.xml          # App switcher template
│   │   │   ├── carbon_theme_toggle.js       # Light/dark mode toggle
│   │   │   └── carbon_theme_toggle.xml      # Theme toggle template
│   │   │
│   │   └── views/
│   │       └── graph/                       # Carbon Charts graph renderer
│   │           ├── carbon_graph_renderer.js     # OWL graph renderer (Carbon Charts)
│   │           ├── carbon_graph_renderer.xml    # Graph template
│   │           ├── carbon_graph_renderer.scss   # Graph style overrides
│   │           └── carbon_graph_view.js         # View registry registration
│   │
│   └── tests/                               # HOOT framework tests
│       ├── carbon_shell.test.js             # UI Shell component tests
│       ├── carbon_graph.test.js             # Carbon Charts renderer tests
│       └── carbon_theme.test.js             # Theme switching tests
```

---

## Backward Compatibility

This module is designed for complete backward compatibility:

- **Installable / Uninstallable**: The module can be installed and uninstalled at any
  time without breaking the Odoo system or leaving residual artifacts.
- **Existing Views**: All standard views (list, form, kanban, graph, pivot, calendar,
  hierarchy) continue to render and function identically in terms of data display and
  user interaction.
- **Existing Actions and Menus**: All menu items, actions, and URL routes remain
  functional.
- **Third-Party Modules**: Any module following standard Odoo conventions (using
  `$o-*` variables and Bootstrap utilities) automatically inherits Carbon styling.
  Modules with hardcoded color values may have minor visual inconsistencies.
- **Server-Side Logic**: No Python controllers, models, RPC endpoints, or business
  logic is modified.
- **No Database Changes**: No new ORM models, migrations, or data files are introduced.
  All state (theme preference, sidebar toggle) is stored client-side via cookies or
  localStorage.
- **No Core Modifications**: Not a single file in `addons/web/` or `odoo/` is edited,
  added, or removed.

---

## Accessibility

The Carbon Design System is built with accessibility as a core principle. This module
maintains WCAG 2.1 AA compliance across all components:

### Color Contrast

All text and interactive elements meet minimum contrast ratios:

- **Normal text** (< 18px): 4.5:1 contrast ratio minimum.
- **Large text** (≥ 18px or ≥ 14px bold): 3:1 contrast ratio minimum.
- **UI components and graphical objects**: 3:1 contrast ratio minimum.

### Keyboard Navigation

Full keyboard support is implemented across all components:

| Key | Action |
|-----|--------|
| `Tab` | Move focus to the next interactive element |
| `Shift + Tab` | Move focus to the previous interactive element |
| `Enter` / `Space` | Activate focused element |
| `Escape` | Close modal, popover, or dropdown |
| `Arrow keys` | Navigate within menus, tabs, and lists |
| `/` | Open global search (header shortcut) |

### Screen Reader Support

- All interactive elements have accessible names via ARIA attributes.
- Dynamic content changes are announced via ARIA live regions.
- Form controls use Carbon's label-above pattern with proper `<label>` associations.
- Navigation landmarks (`<nav>`, `<main>`, `<header>`) provide page structure.

### Data Visualization Accessibility

Carbon Charts ensures chart accessibility:

- Color is never the sole means of conveying information.
- Accessible color palettes are used by default.
- Chart data is available in alternative formats (tooltips, accessible labels).

---

## Development Notes

### Dart Sass vs. libsass Compatibility

Odoo 19.0 uses **libsass** (via the Python `libsass` package) for SCSS compilation.
Carbon Design System v11 requires **Dart Sass**, which is incompatible with libsass.

**Resolution**: Carbon SCSS is pre-compiled to CSS during module packaging. The
pre-compiled CSS files are stored in `static/lib/carbon-styles/` and loaded into
Odoo's asset bundles directly. The module's own SCSS files consume Carbon values via
**CSS custom properties** (`var(--cds-*)`) which are valid in libsass.

```scss
/* Example: Using Carbon tokens in Odoo-compatible SCSS */
.o_form_view .o_form_sheet {
    background-color: var(--cds-layer-01);
    padding: var(--cds-spacing-05);
    color: var(--cds-text-primary);
}
```

### CSS Custom Properties Approach

Carbon tokens are emitted as CSS custom properties prefixed with `--cds-`:

- `--cds-background` — Page background color
- `--cds-text-primary` — Primary text color
- `--cds-interactive` — Interactive element color (links, buttons)
- `--cds-layer-01` — First layer surface color
- `--cds-spacing-05` — 16px spacing token
- `--cds-focus` — Focus indicator color

Theme switching swaps the root-level CSS custom property definitions, causing all
components to update automatically.

### Key Token Mappings

| Odoo Variable | Carbon Token | White Theme Value |
|--------------|-------------|-------------------|
| `$o-brand-primary` | `--cds-interactive` | `#0f62fe` (Blue 60) |
| `$o-success` | `--cds-support-success` | `#24a148` (Green 60) |
| `$o-warning` | `--cds-support-warning` | `#f1c21b` (Yellow 30) |
| `$o-danger` | `--cds-support-error` | `#da1e28` (Red 60) |
| `$o-info` | `--cds-support-info` | `#0043ce` (Blue 70) |
| `$o-webclient-background-color` | `--cds-background` | `#ffffff` |
| `$o-font-size-base` | `body-compact-01 size` | `14px` |
| `$o-system-fonts` | `--cds-font-family-sans` | `'IBM Plex Sans', sans-serif` |

### Adding New Component Overrides

To add Carbon styling for an additional Odoo component:

1. Create a new SCSS file in `static/src/scss/components/`:

   ```scss
   /* static/src/scss/components/my_component.scss */
   .o_my_component {
       background-color: var(--cds-layer-01);
       border: 1px solid var(--cds-border-subtle);
       border-radius: 0;
       padding: var(--cds-spacing-05);
       font-family: var(--cds-font-family-sans);
   }
   ```

2. Register the file in `__manifest__.py` under `web.assets_backend`:

   ```python
   'web.assets_backend': [
       # ... existing entries ...
       'carbon_ui/static/src/scss/components/my_component.scss',
   ],
   ```

3. If the component needs dark mode overrides, add a corresponding entry in
   `carbon_dark_components.scss` or create a separate dark SCSS file registered in
   `web.assets_web_dark`.

---

## Testing

### HOOT Framework Tests

The module includes tests written for Odoo's HOOT testing framework:

| Test File | Coverage |
|-----------|----------|
| `static/tests/carbon_shell.test.js` | Carbon Shell rendering, sidenav toggle, header elements |
| `static/tests/carbon_graph.test.js` | Carbon Charts renderer: data binding, chart type switching |
| `static/tests/carbon_theme.test.js` | Theme toggle: light/dark switching, token application |

### Running Tests

Execute the module's tests via Odoo's test runner:

```bash
python -m odoo \
    --addons-path=addons \
    --database=your_test_database \
    --db_user=odoo \
    --db_password=odoo \
    --db_host=localhost \
    --test-enable \
    --test-tags=/carbon_ui \
    --stop-after-init \
    --http-port=8079
```

### Manual Testing Checklist

After installation, verify the following in the browser:

- [ ] Carbon Header renders at top with 48px height.
- [ ] Side navigation rail appears on the left (48px collapsed).
- [ ] Clicking hamburger icon expands side-nav to 256px.
- [ ] All installed apps appear in the side navigation.
- [ ] Global search in header opens and queries successfully.
- [ ] Theme toggle switches between light and dark modes.
- [ ] List views render with Carbon DataTable styling.
- [ ] Form views use Carbon input styles and spacing.
- [ ] Dialogs use Carbon Modal styling with focus trap.
- [ ] Graph views render using Carbon Charts (not Chart.js).
- [ ] All text uses IBM Plex Sans font.
- [ ] Responsive layout works at all breakpoints.

---

## Troubleshooting

### Module Does Not Appear in Apps List

Ensure the `carbon_ui` directory is in a path included in Odoo's `addons_path`
configuration. Restart the Odoo server and click **Update Apps List** in the Apps menu.

### Styles Not Applied After Installation

1. Clear the browser cache (Ctrl+Shift+Delete).
2. Force asset regeneration by adding `?debug=assets` to the URL.
3. Restart the Odoo server to rebuild asset bundles.

### Font Not Loading (IBM Plex)

Verify that the font files exist in `static/lib/ibm-plex/sans/` and
`static/lib/ibm-plex/mono/`. The font files should be in WOFF2 format. Check the
browser console for 404 errors on font file requests.

### Dark Mode Not Working

Ensure the `web.assets_web_dark` bundle includes the Carbon dark theme files. Check
that the `color_scheme` cookie is being set correctly in the browser.

### Graph Views Still Using Chart.js

The Carbon Charts renderer is loaded via the `web.assets_backend_lazy` bundle. Ensure
the vendored libraries (`d3.min.js`, `carbon-charts.min.js`) are present in
`static/lib/`. Verify the graph view registration in `carbon_graph_view.js` is
correctly overriding the default graph renderer in the view registry.

### Third-Party Module Visual Issues

Modules that hardcode CSS color values (instead of using `$o-*` variables) may not
automatically adopt Carbon styling. To fix, create module-specific SCSS overrides in
the `static/src/scss/components/` directory.

---

## License

This module is licensed under the **GNU Lesser General Public License v3 (LGPL-3)**,
the same license as Odoo 19.0 Community Edition.

See the [LICENSE](https://www.gnu.org/licenses/lgpl-3.0.html) file for the full
license text.

---

## Credits

- **Design System**: [IBM Carbon Design System v11](https://carbondesignsystem.com/)
- **Typography**: [IBM Plex](https://www.ibm.com/plex/) typeface family
- **Charts**: [@carbon/charts](https://charts.carbondesignsystem.com/) (D3.js-based)
- **Icons**: [@carbon/icons](https://carbondesignsystem.com/elements/icons/library/)
- **Framework**: [Odoo OWL 2.8.1](https://github.com/odoo/owl)
