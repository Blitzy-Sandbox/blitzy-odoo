# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Carbon UI',
    'version': '1.0',
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
        # PRIMARY BACKEND BUNDLE
        # -----------------------------------------------------------------
        # All Carbon SCSS and OWL components load AFTER Odoo's existing
        # variable pipeline (primary_variables.scss, secondary_variables.scss,
        # bootstrap_overridden.scss) to properly cascade and override.
        'web.assets_backend': [
            # 1. Vendored pre-compiled CSS (load first as pre-compiled)
            'carbon_ui/static/lib/carbon-charts/carbon-charts.min.css',

            # 2. SCSS token bridge (load after Odoo's variable pipeline)
            'carbon_ui/static/src/scss/carbon_tokens.scss',
            'carbon_ui/static/src/scss/carbon_font_face.scss',
            'carbon_ui/static/src/scss/carbon_primary_overrides.scss',
            'carbon_ui/static/src/scss/carbon_secondary_overrides.scss',
            'carbon_ui/static/src/scss/carbon_bootstrap_bridge.scss',
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

            # 5. Remove dark mode files from light bundle
            ('remove', 'carbon_ui/static/src/scss/carbon_dark_theme.scss'),
            ('remove', 'carbon_ui/static/src/scss/carbon_dark_components.scss'),
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
        # Vendored D3.js and Carbon Charts JS plus Carbon graph renderer
        # components are loaded lazily alongside Odoo's graph/pivot views.
        'web.assets_backend_lazy': [
            'carbon_ui/static/lib/d3/d3.min.js',
            'carbon_ui/static/lib/carbon-charts/carbon-charts.min.js',
            'carbon_ui/static/src/views/graph/carbon_graph_renderer.js',
            'carbon_ui/static/src/views/graph/carbon_graph_renderer.xml',
            'carbon_ui/static/src/views/graph/carbon_graph_renderer.scss',
            'carbon_ui/static/src/views/graph/carbon_graph_view.js',
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
