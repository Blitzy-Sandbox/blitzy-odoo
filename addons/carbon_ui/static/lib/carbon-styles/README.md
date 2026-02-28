# Carbon Styles — IBM Carbon Design System v11 (Pre-compiled)

Pre-compiled CSS assets extracted from the IBM Carbon Design System v11,
providing design tokens, component styles, typography, spacing, and theming
for the `carbon_ui` Odoo module.

## Source Attribution

These files are the combined, pre-compiled output of the following
`@carbon/*` npm packages from the Carbon Design System monorepo:

| Package | Version | Purpose |
| --- | --- | --- |
| `@carbon/styles` | 1.67.x | Master SCSS package — component styles, tokens, and utilities |
| `@carbon/themes` | 11.x | Theme token definitions (White, G10, G90, G100) |
| `@carbon/type` | 11.x | Typography tokens, IBM Plex type styles (Productive scale) |
| `@carbon/layout` | 11.x | Spacing scale, 2x grid definitions, breakpoints |
| `@carbon/colors` | 11.x | IBM Design Language color palettes (10-step swatches) |
| `@carbon/motion` | 11.x | Motion/animation curves (productive and expressive easing) |

- **Monorepo**: <https://github.com/carbon-design-system/carbon>
- **Documentation**: <https://carbondesignsystem.com/>

## License

Apache License 2.0 — see the `LICENSE` file in this directory for the
full legal text. Copyright IBM Corp. 2016, 2024.

## Why Pre-compiled

Carbon Design System v11 SCSS sources require **Dart Sass** for
compilation (the `sass` npm package). Odoo 19.0 uses **libsass** (via
the Python `libsass` binding) for runtime SCSS compilation. The two Sass
implementations are not fully compatible — Carbon's SCSS uses Dart Sass
features (module system with `@use`/`@forward`, `math.div()`, and
namespace imports) that libsass does not support.

To bridge this gap, the Carbon SCSS has been pre-compiled into plain CSS,
with all design tokens emitted as **CSS custom properties** (`--cds-*`).
The module's SCSS override files can then reference these tokens using the
standard CSS `var()` function, which libsass passes through verbatim:

```scss
// In carbon_ui SCSS files (compiled by Odoo's libsass):
$o-brand-primary: var(--cds-interactive);
background-color: var(--cds-background);
color: var(--cds-text-primary);
padding: var(--cds-spacing-05);
```

This implements **Strategy B** from the project's technical specification
(§0.3.1): "Carbon tokens are emitted as CSS custom properties (`--cds-*`)
that can be consumed in Odoo's SCSS via the `var()` function without
requiring Dart Sass at Odoo's compile time."

## Files in This Directory

### Pre-compiled CSS

- **`carbon-tokens.css`** (~81 KB)
  All Carbon design tokens for all four themes as CSS custom properties
  on `:root` (White/default) and theme-specific `[data-carbon-theme]`
  attribute selectors. Loaded in Odoo's `web.assets_backend` bundle.
  Contains:
  - Background, layer, text, link, icon, interactive, and support tokens
  - Border, field, button, notification, and tag color tokens
  - Spacing scale tokens (`--cds-spacing-01` through `--cds-spacing-13`:
    2px, 4px, 8px, 12px, 16px, 24px, 32px, 40px, 48px, 64px, 80px,
    96px, 160px)
  - Typography tokens (Productive type scale: body, heading, label,
    helper-text, legal, code, caption, display, quotation)
  - Font family tokens (`--cds-font-family-sans`, `--cds-font-family-mono`,
    `--cds-font-family-serif`)
  - Motion duration and easing tokens
  - Fluid spacing tokens
  - Layer-contextual shorthand tokens
  - High-contrast mode overrides (`forced-colors` media query)

- **`carbon-styles.min.css`** (~150 KB)
  Main pre-compiled CSS bundle containing Carbon component structural
  styles, grid system, typography utility classes, spacing utilities,
  and layout patterns. Includes CSS for:
  - Carbon 2x Grid (16-column layout with responsive breakpoints)
  - Button variants (primary, secondary, tertiary, danger, ghost)
  - Text inputs, text areas, number inputs, and form groups
  - Data table (header, rows, zebra striping, compact/short/tall)
  - Modal dialog (header, body, footer, close button, size variants)
  - Notification (inline and toast, with kind variants)
  - Tabs (line variant with underline indicator)
  - Dropdown and list box menus
  - Checkbox, radio, and toggle
  - Tag (color variants, sizes, dismissible, filter)
  - Pagination controls
  - Breadcrumb navigation
  - Search (expandable input with icon)
  - Tooltip and popover
  - Loading and inline loading indicators
  - Tile (clickable, selectable, expandable)
  - Accordion (collapsible sections)
  - Progress indicator (steps)
  - File uploader (drag-and-drop zone)
  - Date picker and time picker
  - Focus ring utilities
  - Screen reader / accessibility utilities

- **`carbon-themes.min.css`** (~44 KB)
  Theme-specific CSS custom property overrides for all four Carbon
  themes. Identical token names are redefined with theme-appropriate
  values under attribute selectors:
  - `:root, [data-carbon-theme="white"]` — Default light theme
    (White background `#ffffff`)
  - `[data-carbon-theme="g10"]` — Alternative light theme
    (Gray 10 background `#f4f4f4`)
  - `[data-carbon-theme="g90"]` — Dark theme
    (Gray 90 background `#262626`)
  - `[data-carbon-theme="g100"]` — Deep dark theme
    (Gray 100 background `#161616`)

- **`carbon-components.css`** (~840 KB)
  Full unminified Carbon component CSS output for reference and
  debugging. Not loaded in production asset bundles. Contains the
  complete compiled output of `@carbon/styles` component partials.

### License and Documentation

- **`LICENSE`** — Apache License 2.0 (IBM Corp. 2016, 2024)
- **`README.md`** — This file

### SCSS Sources (Reference Only)

- **`scss/`** — Directory containing 243 original Carbon SCSS source
  files from `@carbon/styles`. These are provided for reference and
  local development only — they **cannot** be compiled by Odoo's
  libsass runtime. Subdirectories include:
  - `scss/components/` — Per-component SCSS partials (72 directories)
  - `scss/grid/` — Grid system SCSS
  - `scss/type/` — Typography SCSS
  - `scss/theme/` — Theme configuration SCSS
  - `scss/layer/` — Layer token SCSS
  - `scss/utilities/` — Utility class SCSS
  - `scss/compat/` — Compatibility helpers
  - `scss/fonts/` — Font-face declaration SCSS
  - Top-level partials: `_theme.scss`, `_themes.scss`, `_config.scss`,
    `_layout.scss`, `_spacing.scss`, `_motion.scss`, `_reset.scss`,
    `_breakpoint.scss`, `_colors.scss`, `_layer.scss`, `_zone.scss`,
    `_feature-flags.scss`, `_carbon-utilities.scss`

## Integration with Odoo

### Asset Bundle Loading

The pre-compiled CSS files are loaded into Odoo via the
`web.assets_backend` asset bundle, declared in the `carbon_ui` module's
`__manifest__.py`:

```python
'assets': {
    'web.assets_backend': [
        # Pre-compiled Carbon CSS (tokens + component styles)
        'carbon_ui/static/lib/carbon-styles/carbon-tokens.css',
        # ... followed by the module's SCSS override files
        'carbon_ui/static/src/scss/carbon_font_face.scss',
        'carbon_ui/static/src/scss/carbon_bootstrap_bridge.scss',
        # ...
    ],
}
```

**Load order is critical**: the pre-compiled CSS files must be loaded
**before** the module's SCSS override files (`carbon_tokens.scss`,
`carbon_primary_overrides.scss`, `carbon_secondary_overrides.scss`, etc.)
so that the `--cds-*` custom properties are defined on `:root` before
any SCSS file references them via `var()`.

### Theme Switching

Theme switching between light and dark modes is achieved by changing the
`data-carbon-theme` attribute on the document's root element:

```javascript
// Switch to dark mode (Gray 90)
document.documentElement.setAttribute('data-carbon-theme', 'g90');

// Switch to light mode (White — the default)
document.documentElement.setAttribute('data-carbon-theme', 'white');

// Switch to alternative light (Gray 10)
document.documentElement.setAttribute('data-carbon-theme', 'g10');

// Switch to deep dark (Gray 100)
document.documentElement.setAttribute('data-carbon-theme', 'g100');
```

This integrates with Odoo's existing `color_scheme` cookie mechanism for
persisting the user's theme preference across sessions.

## CSS Custom Property Naming Convention

All Carbon design tokens use the `--cds-` prefix (Carbon Design System),
following the same pattern as Bootstrap's `--bs-*` prefix used in
`addons/web/static/lib/bootstrap/dist/css/bootstrap.css`.

### Token Categories and Examples

| Category | Example Token | White Value | Purpose |
| --- | --- | --- | --- |
| Background | `--cds-background` | `#ffffff` | Page background color |
| Layer | `--cds-layer-01` | `#f4f4f4` | First-layer surface color |
| Text | `--cds-text-primary` | `#161616` | Primary text color |
| Link | `--cds-link-primary` | `#0f62fe` | Link text color |
| Icon | `--cds-icon-primary` | `#161616` | Primary icon color |
| Interactive | `--cds-interactive` | `#0f62fe` | Interactive element color |
| Focus | `--cds-focus` | `#0f62fe` | Focus ring color |
| Support | `--cds-support-error` | `#da1e28` | Error/danger semantic color |
| Support | `--cds-support-success` | `#24a148` | Success semantic color |
| Support | `--cds-support-warning` | `#f1c21b` | Warning semantic color |
| Support | `--cds-support-info` | `#0043ce` | Informational semantic color |
| Border | `--cds-border-strong-01` | `#8d8d8d` | Strong border color |
| Border | `--cds-border-subtle-01` | `#c6c6c6` | Subtle border color |
| Field | `--cds-field-01` | `#f4f4f4` | Form field background |
| Button | `--cds-button-primary` | `#0f62fe` | Primary button color |
| Spacing | `--cds-spacing-05` | `1rem` (16px) | Standard spacing unit |
| Typography | `--cds-body-compact-01-font-size` | `0.875rem` (14px) | Body text size |
| Typography | `--cds-heading-compact-01-font-weight` | `600` | Heading weight |
| Font Family | `--cds-font-family-sans` | `'IBM Plex Sans', ...` | Sans-serif stack |
| Motion | `--cds-duration-fast-01` | `70ms` | Fast animation duration |
| Motion | `--cds-ease-productive-standard` | `cubic-bezier(...)` | Standard easing |
| Overlay | `--cds-overlay` | `rgba(0,0,0,0.6)` | Modal overlay color |

### Usage in SCSS

```scss
// Reference tokens via var() — passes through libsass unchanged
.my-component {
  background-color: var(--cds-layer-01);
  color: var(--cds-text-primary);
  border-bottom: 1px solid var(--cds-border-subtle-01);
  padding: var(--cds-spacing-05);
  font-size: var(--cds-body-compact-01-font-size);
  font-weight: var(--cds-body-compact-01-font-weight);
  line-height: var(--cds-body-compact-01-line-height);
  transition: background-color var(--cds-duration-fast-01)
              var(--cds-ease-productive-standard);
}
```

## Generation Method

These CSS files were generated through the following process:

1. Install `@carbon/styles` v1.67.x and all peer dependencies via npm
2. Compile the Carbon SCSS sources using **Dart Sass** (`sass` npm package)
3. Extract CSS custom property declarations for all four theme variants
4. Bundle component CSS with token references via `var(--cds-*)`
5. Minify the output (preserving custom property names)
6. Include all four theme variant token sets (White, G10, G90, G100)

To regenerate these files (e.g., when upgrading Carbon versions):

```bash
# 1. Install dependencies
npm install @carbon/styles@1.67 sass

# 2. Create an entry SCSS file that imports all Carbon styles
echo '@use "@carbon/styles";' > carbon-entry.scss

# 3. Compile with Dart Sass
npx sass carbon-entry.scss carbon-styles.min.css --style=compressed \
    --load-path=node_modules

# 4. Extract theme tokens (compile theme-specific entry files)
# See the carbon_ui module's build scripts for the complete process
```

## Relationship to Other Vendored Libraries

| Library | Location | Relationship |
| --- | --- | --- |
| Bootstrap 5.3.3 | `addons/web/static/lib/bootstrap/` | Retained; Carbon tokens override Bootstrap variables via the SCSS bridge |
| IBM Plex fonts | `addons/carbon_ui/static/lib/ibm-plex/` | Font files referenced by Carbon's `--cds-font-family-sans/mono/serif` tokens |
| Carbon Icons | `addons/carbon_ui/static/lib/carbon-icons/` | SVG icons used alongside Carbon component styles |
| Carbon Charts | `addons/carbon_ui/static/lib/carbon-charts/` | D3.js-based charting library styled with Carbon tokens |
| D3.js 7.x | `addons/carbon_ui/static/lib/d3/` | Peer dependency of Carbon Charts |
