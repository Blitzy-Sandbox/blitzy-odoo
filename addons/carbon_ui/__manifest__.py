# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Carbon Design System UI',
    'version': '19.0.1.0.0',
    'category': 'Hidden/Tools',
    'summary': 'IBM Carbon Design System v11 UI redesign for Odoo backend',
    'description': """
Carbon Design System UI for Odoo
=================================

Replaces the default Odoo backend UI with IBM Carbon Design System v11
(Productive theme). Features include:

* SCSS token-based theming with Carbon design tokens
* Carbon UI Shell navigation (persistent side rail + header)
* Carbon component styling for all core Odoo UI elements
* Carbon Charts (D3.js-based) replacing Chart.js for graph views
* Light and dark mode support (White, G10, G90, G100 themes)
* IBM Plex Sans/Mono typography
* WCAG 2.1 AA accessibility compliance
* Carbon responsive grid (2x Grid, 16-column layout)

This module is a standalone addon using template inheritance and SCSS
cascade — zero modifications to Odoo core.
    """,
    'author': 'Odoo S.A.',
    'website': 'https://www.odoo.com',
    'depends': ['web'],
    'data': [
        'views/webclient_templates.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            ('prepend',
             'carbon_ui/static/src/scss/carbon_tokens.scss'),
            'carbon_ui/static/src/scss/carbon_primary_overrides.scss',
        ],
        'web._assets_secondary_variables': [
            'carbon_ui/static/src/scss/carbon_secondary_overrides.scss',
        ],
        'web.assets_backend': [
            # Pre-compiled Carbon CSS (tokens + component styles)
            'carbon_ui/static/lib/carbon-styles/carbon-tokens.css',
            # Font face declarations
            'carbon_ui/static/src/scss/carbon_font_face.scss',
            # Bootstrap bridge
            'carbon_ui/static/src/scss/carbon_bootstrap_bridge.scss',
            # Carbon utility classes
            'carbon_ui/static/src/scss/carbon_utilities.scss',
            # Component style overrides
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
            # Navigation shell OWL components
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
            # Theme toggle
            'carbon_ui/static/src/webclient/carbon_theme_toggle.js',
            'carbon_ui/static/src/webclient/carbon_theme_toggle.xml',
        ],
        'web.assets_web_dark': [
            'carbon_ui/static/src/scss/carbon_dark_theme.scss',
            'carbon_ui/static/src/scss/carbon_dark_components.scss',
        ],
        'web.assets_backend_lazy': [
            # D3.js and Carbon Charts for graph views
            'carbon_ui/static/lib/d3/d3.min.js',
            'carbon_ui/static/lib/carbon-charts/carbon-charts.min.js',
            'carbon_ui/static/lib/carbon-charts/carbon-charts.min.css',
            # Carbon graph renderer
            'carbon_ui/static/src/views/graph/carbon_graph_renderer.js',
            'carbon_ui/static/src/views/graph/carbon_graph_renderer.xml',
            'carbon_ui/static/src/views/graph/carbon_graph_renderer.scss',
            'carbon_ui/static/src/views/graph/carbon_graph_view.js',
        ],
        # Note: Test assets will be registered here once test files are created
        # 'web.assets_unit_tests': [
        #     'carbon_ui/static/tests/carbon_shell.test.js',
        #     'carbon_ui/static/tests/carbon_graph.test.js',
        #     'carbon_ui/static/tests/carbon_theme.test.js',
        # ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}
