# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Carbon UI',
    'version': '19.0.1.0.0',
    'category': 'Hidden',
    'description': """
IBM Carbon Design System v11 integration for Odoo 19.0 backend UI.
===================================================================

Replaces Bootstrap/Odoo-native design catalog with Carbon 'Productive' theme.

Features:
* SCSS token-based theming with Carbon design tokens overriding $o-* variables
* Carbon UI Shell navigation (persistent side rail + header) replacing top navbar
* Carbon component styling for all core Odoo UI elements
* Carbon Charts (D3.js-based) replacing Chart.js for graph views
* Light and dark mode support (White, G10, G90, G100 themes)
* IBM Plex Sans/Mono typography (Productive type scale)
* WCAG 2.1 AA accessibility compliance
* Carbon responsive grid (2x Grid, 16-column layout)
* Spacing normalization using Carbon's spacing scale (2/4/8 multiples)

This is a standalone addon using template inheritance and SCSS cascade.
Zero modifications to Odoo core source code under addons/web/ or odoo/.
    """,
    'depends': ['web'],
    'data': [
        'views/webclient_templates.xml',
        'views/carbon_assets.xml',
    ],
    'assets': {
        # -----------------------------------------------------------------
        # VARIABLE SUB-BUNDLES — Correct Sass Cascade Position
        # -----------------------------------------------------------------
        # Token and override SCSS files are placed in Odoo's variable
        # sub-bundles so they are processed BEFORE Bootstrap derives
        # $primary, $secondary, etc. from the $o-* variables.
        #
        # Load order within _assets_helpers:
        #   1. Bootstrap functions/mixins
        #   2. Odoo utils.scss
        #   3. web._assets_primary_variables
        #      → carbon_tokens.scss (prepended — defines $cds-* first)
        #      → primary_variables.scss (Odoo, !default guarded)
        #      → *.variables.scss (Odoo component vars)
        #      → carbon_primary_overrides.scss (overrides $o-* explicitly)
        #   4. web._assets_secondary_variables
        #      → secondary_variables.scss (Odoo, !default guarded)
        #      → carbon_secondary_overrides.scss (overrides $o-* explicitly)
        #      → carbon_bootstrap_bridge.scss (maps to Bootstrap $vars)
        #   5. pre_variables.scss → Bootstrap _variables.scss (reads final values)
        'web._assets_primary_variables': [
            ('prepend', 'carbon_ui/static/src/scss/carbon_tokens.scss'),
            'carbon_ui/static/src/scss/carbon_primary_overrides.scss',
        ],
        'web._assets_secondary_variables': [
            'carbon_ui/static/src/scss/carbon_secondary_overrides.scss',
            'carbon_ui/static/src/scss/carbon_bootstrap_bridge.scss',
        ],

        # -----------------------------------------------------------------
        # PRIMARY BACKEND BUNDLE
        # -----------------------------------------------------------------
        # Font faces, utilities, component style overrides, and OWL
        # components. These load AFTER the variable pipeline and Bootstrap
        # have been processed, which is correct for CSS rules and classes.
        'web.assets_backend': [
            # 1. Font face declarations (CSS @font-face — no variable deps)
            'carbon_ui/static/src/scss/carbon_font_face.scss',

            # 2. Utility classes (spacing, typography, grid)
            'carbon_ui/static/src/scss/carbon_utilities.scss',

            # 3. Component style overrides (load after token bridge)
            'carbon_ui/static/src/scss/components/dialog.scss',
            'carbon_ui/static/src/scss/components/dropdown.scss',
            'carbon_ui/static/src/scss/components/tooltip.scss',
            'carbon_ui/static/src/scss/components/notification.scss',
            'carbon_ui/static/src/scss/components/tabs.scss',
            'carbon_ui/static/src/scss/components/pagination.scss',
            'carbon_ui/static/src/scss/components/forms.scss',
            'carbon_ui/static/src/scss/components/datatable.scss',
            'carbon_ui/static/src/scss/components/tags.scss',
            'carbon_ui/static/src/scss/components/breadcrumb.scss',
            'carbon_ui/static/src/scss/components/search.scss',
            'carbon_ui/static/src/scss/components/kanban.scss',
            'carbon_ui/static/src/scss/components/loading.scss',
            'carbon_ui/static/src/scss/components/popover.scss',
            'carbon_ui/static/src/scss/components/checkbox.scss',
            'carbon_ui/static/src/scss/components/file_uploader.scss',
            'carbon_ui/static/src/scss/components/date_picker.scss',
            'carbon_ui/static/src/scss/components/accordion.scss',
            'carbon_ui/static/src/scss/components/status_bar.scss',

            # 4. Navigation OWL components (JS + XML + SCSS)
            'carbon_ui/static/src/webclient/carbon_shell.js',
            'carbon_ui/static/src/webclient/carbon_shell.xml',
            'carbon_ui/static/src/webclient/carbon_shell.scss',
            'carbon_ui/static/src/webclient/carbon_header.js',
            'carbon_ui/static/src/webclient/carbon_header.xml',
            'carbon_ui/static/src/webclient/carbon_sidenav.js',
            'carbon_ui/static/src/webclient/carbon_sidenav.xml',
            'carbon_ui/static/src/webclient/carbon_sidenav.scss',
            'carbon_ui/static/src/webclient/carbon_global_search.js',
            'carbon_ui/static/src/webclient/carbon_global_search.xml',
            'carbon_ui/static/src/webclient/carbon_switcher.js',
            'carbon_ui/static/src/webclient/carbon_switcher.xml',
            'carbon_ui/static/src/webclient/carbon_theme_toggle.js',
            'carbon_ui/static/src/webclient/carbon_theme_toggle.xml',
        ],

        # -----------------------------------------------------------------
        # DARK MODE BUNDLE
        # -----------------------------------------------------------------
        'web.assets_web_dark': [
            'carbon_ui/static/src/scss/carbon_dark_theme.scss',
            'carbon_ui/static/src/scss/carbon_dark_components.scss',
        ],

        # -----------------------------------------------------------------
        # LAZY-LOADED BUNDLE (Graph/Pivot views)
        # -----------------------------------------------------------------
        # Vendored D3.js, Carbon Charts CSS/JS, and Carbon graph renderer
        # components are loaded lazily alongside Odoo's graph/pivot views.
        # Carbon Charts CSS is included here (not in the main backend bundle)
        # because it is only needed when graph views are displayed.
        'web.assets_backend_lazy': [
            'carbon_ui/static/lib/carbon-charts/carbon-charts.min.css',
            'carbon_ui/static/lib/d3/d3.min.js',
            'carbon_ui/static/lib/carbon-charts/carbon-charts.min.js',
            'carbon_ui/static/src/views/graph/carbon_graph_renderer.js',
            'carbon_ui/static/src/views/graph/carbon_graph_renderer.xml',
            'carbon_ui/static/src/views/graph/carbon_graph_renderer.scss',
            'carbon_ui/static/src/views/graph/carbon_graph_view.js',
        ],

        # -----------------------------------------------------------------
        # LAZY-LOADED DARK BUNDLE (Graph/Pivot dark mode)
        # -----------------------------------------------------------------
        # Dark mode overrides for lazy-loaded chart/graph views.
        # Active when Odoo's color_scheme cookie is "dark".
        # Provides explicit dark-mode token adjustments for Carbon Charts
        # SVG rendering, tooltips, legends, and toolbar elements.
        'web.assets_backend_lazy_dark': [
            'carbon_ui/static/src/views/graph/carbon_graph_renderer.dark.scss',
        ],

        # -----------------------------------------------------------------
        # TEST BUNDLE
        # -----------------------------------------------------------------
        'web.assets_unit_tests': [
            'carbon_ui/static/tests/**/*',
        ],
    },
    'author': 'Odoo S.A.',
    'license': 'LGPL-3',
    'auto_install': False,
}
