# Carbon Icons — IBM Carbon Design System Icons v11.x

## Source Attribution

| Field            | Value                                                                                          |
| ---------------- | ---------------------------------------------------------------------------------------------- |
| **npm package**  | [`@carbon/icons`](https://www.npmjs.com/package/@carbon/icons) v11.x                           |
| **GitHub**       | [carbon-design-system/carbon](https://github.com/carbon-design-system/carbon) — `packages/icons/` |
| **Documentation**| [Carbon Icon Library](https://carbondesignsystem.com/guidelines/icons/library/)                 |
| **Copyright**    | © IBM Corp. 2018, 2024                                                                         |

## License

Apache License 2.0 — see the [LICENSE](LICENSE) file in this directory for the full legal text.

## Description

This directory contains an **extracted subset** of IBM Carbon Design System icons used by
the `carbon_ui` Odoo module. The icons are provided in two formats:

1. **SVG sprite sheet** (`carbon-icons.svg`) — a single file containing all icons as
   `<symbol>` elements, referenced at runtime via SVG `<use>` fragment identifiers.
2. **Individual SVG files** — organised into size-specific subdirectories (`16/`, `20/`,
   `32/`) for direct use in build tools, documentation, or contexts where the sprite
   sheet is not suitable.

> **Important — Scope Clarification**
>
> This is **NOT** a full icon migration from FontAwesome 4.7.  Carbon Icons are used
> **only** for the new Carbon UI Shell components (header, side-navigation, switcher,
> theme toggle) and for Carbon-styled component overrides introduced by this module.
> All existing FontAwesome icons consumed by Odoo core and third-party modules are
> retained and continue to function unchanged.

## Directory Contents

```
carbon-icons/
├── LICENSE                 Apache 2.0 license (IBM Corp.)
├── README.md               This documentation file
├── carbon-icons.svg        SVG sprite sheet (49 symbols, 32×32 viewBox)
├── 16/                     68 individual SVG icons at 16×16
├── 20/                     9 individual SVG icons at 20×20
└── 32/                     43 individual SVG icons at 32×32
```

### Sprite Sheet Format

`carbon-icons.svg` is a hidden root `<svg>` element (`style="display:none"`)
containing `<symbol>` children.  Each symbol carries:

* A unique `id` following the `icon--{name}` naming convention.
* A `viewBox="0 0 32 32"` attribute (Carbon's standard 32×32 grid).
* Paths using `fill="currentColor"` so the icon inherits the text colour of its
  parent CSS context.

Icons are referenced at runtime with an SVG `<use>` element and a fragment identifier:

```html
<svg width="20" height="20" viewBox="0 0 32 32">
  <use href="/carbon_ui/static/lib/carbon-icons/carbon-icons.svg#icon--close"/>
</svg>
```

Because the `viewBox` is always `0 0 32 32`, the icon scales cleanly to any rendered
size (16×16, 20×20, 24×24, 32×32, etc.) via the `width` and `height` attributes on the
outer `<svg>`.

## Icons Included — Sprite Sheet Symbol IDs

The sprite sheet contains **49 icons** organised into the following functional
categories.

### Navigation

| Symbol ID              | Description                              |
| ---------------------- | ---------------------------------------- |
| `icon--menu`           | Hamburger menu (three horizontal lines)  |
| `icon--close`          | Close / dismiss (×)                      |
| `icon--chevron--down`  | Chevron pointing down                    |
| `icon--chevron--up`    | Chevron pointing up                      |
| `icon--chevron--left`  | Chevron pointing left                    |
| `icon--chevron--right` | Chevron pointing right                   |
| `icon--chevron--sort`  | Bi-directional chevron (sortable column) |
| `icon--home`           | House / home dashboard                   |

### Header Utilities

| Symbol ID              | Description                              |
| ---------------------- | ---------------------------------------- |
| `icon--search`         | Magnifying glass (global search)         |
| `icon--notification`   | Bell (notification indicator)            |
| `icon--user--avatar`   | Person silhouette (user menu)            |
| `icon--switcher`       | 3×3 grid of squares (app switcher)       |
| `icon--settings`       | Gear / cog (settings access)             |

### Actions

| Symbol ID                        | Description                           |
| -------------------------------- | ------------------------------------- |
| `icon--overflow-menu--vertical`  | Three vertical dots (overflow menu)   |
| `icon--overflow-menu--horizontal`| Three horizontal dots (overflow menu) |
| `icon--add`                      | Plus sign (create / add)              |
| `icon--subtract`                 | Minus sign (remove / collapse)        |
| `icon--edit`                     | Pencil (edit mode)                    |
| `icon--trash-can`                | Trash can (delete)                    |
| `icon--filter`                   | Funnel (search / filter)              |

### Directional / Data Table

| Symbol ID              | Description                              |
| ---------------------- | ---------------------------------------- |
| `icon--arrow--up`      | Arrow up (sort ascending)                |
| `icon--arrow--down`    | Arrow down (sort descending)             |
| `icon--arrow--left`    | Arrow left (navigate back)               |
| `icon--arrow--right`   | Arrow right (navigate forward)           |
| `icon--arrows--vertical`| Up + down arrows (unsorted column)      |
| `icon--caret--down`    | Small caret down (dropdown indicator)    |
| `icon--caret--up`      | Small caret up (dropdown indicator)      |

### Notifications / Status

| Symbol ID                | Description                              |
| ------------------------ | ---------------------------------------- |
| `icon--information`      | "i" in circle outline (info)             |
| `icon--warning--alt`     | Triangle with "!" (warning)              |
| `icon--warning`          | Diamond with "!" (caution)               |
| `icon--checkmark--filled`| Checkmark in filled circle (success)     |
| `icon--error--filled`    | "×" in filled circle (error)             |

### Theme Toggle

| Symbol ID     | Description                          |
| ------------- | ------------------------------------ |
| `icon--light` | Sun (light mode indicator)           |
| `icon--asleep`| Moon / crescent (dark mode indicator)|

### File / Content

| Symbol ID       | Description                    |
| --------------- | ------------------------------ |
| `icon--launch`  | External link arrow            |
| `icon--copy`    | Copy / duplicate               |
| `icon--download`| Download arrow                 |
| `icon--upload`  | Upload arrow                   |
| `icon--document`| Document page                  |
| `icon--folder`  | Folder                         |

### UI Controls

| Symbol ID            | Description                        |
| -------------------- | ---------------------------------- |
| `icon--drag-vertical`| Vertical drag handle (two dot cols)|
| `icon--maximize`     | Maximise / expand                  |
| `icon--minimize`     | Minimise / collapse                |
| `icon--view`         | Eye (visibility toggle)            |
| `icon--logout`       | Logout / sign-out arrow            |

### Views / Layout

| Symbol ID        | Description                       |
| ---------------- | --------------------------------- |
| `icon--dashboard`| Dashboard tile layout             |
| `icon--list`     | List layout                       |
| `icon--grid`     | Grid layout                       |
| `icon--calendar` | Calendar                          |

## Usage in OWL Templates

### QWeb Template — Static Reference

```xml
<svg class="cds--icon" width="20" height="20" viewBox="0 0 32 32">
    <use href="/carbon_ui/static/lib/carbon-icons/carbon-icons.svg#icon--close"/>
</svg>
```

### QWeb Template — Dynamic Reference (OWL `t-att-href`)

```xml
<svg class="cds--icon" width="20" height="20" viewBox="0 0 32 32"
     aria-hidden="true" focusable="false">
    <use t-att-href="'/carbon_ui/static/lib/carbon-icons/carbon-icons.svg#icon--' + iconName"/>
</svg>
```

### Sizing

The `viewBox="0 0 32 32"` on each symbol means the icon scales to whatever
`width` / `height` you set on the outer `<svg>` element.  Common sizes used in
the Carbon UI module:

| Context               | `width` × `height` |
| --------------------- | ------------------- |
| Inline text icons     | 16 × 16             |
| Header utility icons  | 20 × 20             |
| SideNav icons         | 20 × 20             |
| Large action icons    | 24 × 24             |
| Full-size reference   | 32 × 32             |

### Accessibility

When an icon is purely decorative, add `aria-hidden="true"` and
`focusable="false"` to the `<svg>` element.  When an icon conveys meaning
without adjacent text, add a `<title>` child and reference it with
`aria-labelledby`:

```xml
<svg class="cds--icon" width="20" height="20" viewBox="0 0 32 32"
     aria-labelledby="icon-title-close" role="img">
    <title id="icon-title-close">Close</title>
    <use href="/carbon_ui/static/lib/carbon-icons/carbon-icons.svg#icon--close"/>
</svg>
```

## Integration Context — Consuming OWL Components

The following Carbon UI OWL components and SCSS files reference icons from this
sprite sheet:

| Component File(s)                                         | Icons Used                                                   |
| --------------------------------------------------------- | ------------------------------------------------------------ |
| `carbon_header.js` / `carbon_header.xml`                  | `menu`, `search`, `notification`, `user--avatar`, `switcher`, `settings` |
| `carbon_sidenav.js` / `carbon_sidenav.xml`                | `chevron--down`, `chevron--up`, `chevron--right`, `home`, `dashboard`, `grid` |
| `carbon_switcher.js` / `carbon_switcher.xml`              | `switcher`, `close`, `launch`                                |
| `carbon_theme_toggle.js` / `carbon_theme_toggle.xml`      | `light`, `asleep`                                            |
| `carbon_global_search.js` / `carbon_global_search.xml`    | `search`, `close`                                            |
| `scss/components/datatable.scss`                           | `arrow--up`, `arrow--down`, `arrows--vertical`, `chevron--sort` |
| `scss/components/dialog.scss`                              | `close`                                                      |
| `scss/components/notification.scss`                        | `information`, `warning--alt`, `checkmark--filled`, `error--filled` |
| `scss/components/pagination.scss`                          | `chevron--left`, `chevron--right`                            |
| `scss/components/dropdown.scss`                            | `chevron--down`, `close`                                     |
| `scss/components/file_uploader.scss`                       | `upload`, `close`                                            |

All paths above are relative to `addons/carbon_ui/static/src/`.

## Individual SVG Files

In addition to the sprite sheet, standalone SVG files are available in
size-specific subdirectories.  These follow Carbon's recommended size tiers:

| Directory | Icon Count | Intended Use                              |
| --------- | ---------- | ----------------------------------------- |
| `16/`     | 68         | Small inline icons, table cells, metadata |
| `20/`     | 9          | Default interactive icons, buttons        |
| `32/`     | 43         | Large display icons, empty states         |

File names mirror the Carbon naming convention with double-dashes for compound
names (e.g., `chevron--down.svg`, `user--avatar.svg`, `overflow-menu--vertical.svg`).

## Extraction Method

These icons were extracted from the
[`@carbon/icons`](https://www.npmjs.com/package/@carbon/icons) npm package v11.x.
The official SVG paths come directly from Carbon's icon library source at
[`packages/icons/src/svg/`](https://github.com/carbon-design-system/carbon/tree/main/packages/icons/src/svg).

Processing steps applied during extraction:

1. Individual SVG files were copied from the npm package's `svg/16/`, `svg/20/`,
   and `svg/32/` directories — only icons relevant to the Carbon UI module were
   selected (120 total across all sizes).
2. A single SVG sprite sheet (`carbon-icons.svg`) was assembled from the 32×32
   variants, converting each icon into a `<symbol>` with an `id` attribute.
3. All `fill` attributes were normalised to `currentColor` for CSS colour
   inheritance.
4. No paths were modified, simplified, or approximated — every SVG path is an
   exact copy of the corresponding Carbon source icon.

## Relationship to FontAwesome 4.7

Odoo 19.0 Community Edition ships with FontAwesome 4.7 as its primary icon
system.  The `carbon_ui` module does **not** replace FontAwesome.  Instead:

* **Carbon Icons** are used exclusively by new OWL components introduced by the
  `carbon_ui` module (Carbon Header, SideNav, Switcher, Theme Toggle, and
  Carbon-styled component overrides).
* **FontAwesome 4.7** continues to serve all existing Odoo core views, field
  widgets, action buttons, and third-party module icons.

When the `carbon_ui` module is uninstalled, no Carbon icon references remain in
the UI — all rendering reverts to the default FontAwesome-based interface.
