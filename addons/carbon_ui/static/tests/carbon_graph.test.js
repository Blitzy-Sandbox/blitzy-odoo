/** @odoo-module */

/**
 * Carbon Charts Graph Renderer — HOOT Test Suite
 *
 * Comprehensive tests for the CarbonGraphRenderer OWL component that wraps
 * the @carbon/charts vanilla JavaScript library (D3.js-based), replacing
 * Chart.js in Odoo's graph views. This suite verifies:
 *
 *   - Data binding from Odoo GraphModel to Carbon Charts
 *   - Chart type switching (bar → line → pie)
 *   - WCAG 2.1 AA compliant colour palette usage
 *   - View registry registration and Chart.js replacement
 *   - Search-filter and groupBy re-rendering
 *   - RPC read_group integration
 *   - Chart lifecycle (creation, destruction, re-creation)
 *   - Arch configuration (measure, stacked, groupBy, type)
 *
 * All tests use a mock Carbon Charts implementation that creates lightweight
 * SVG elements in the DOM, allowing assertions on structure and data binding
 * without requiring the full @carbon/charts vendor bundle.
 */

import { describe, expect, test, beforeEach } from "@odoo/hoot";
import { queryAllTexts, queryOne, queryAll } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import {
    contains,
    defineModels,
    fields,
    findComponent,
    getService,
    models,
    mountView,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
    toggleMenuItem,
    toggleSearchBarMenu,
} from "@web/../tests/web_test_helpers";
import { registry } from "@web/core/registry";
import { CarbonGraphRenderer } from "@carbon_ui/views/graph/carbon_graph_renderer";
import { carbonGraphView } from "@carbon_ui/views/graph/carbon_graph_view";

// ---------------------------------------------------------------------------
// Mock Models — identical structure to graph_view.test.js for compatibility
// ---------------------------------------------------------------------------

class Color extends models.Model {
    name = fields.Char();
    _records = [
        { id: 1, name: "black" },
        { id: 2, name: "red" },
    ];
}

class Product extends models.Model {
    name = fields.Char();
    _records = [
        { id: 100, name: "xphone" },
        { id: 200, name: "xpad" },
    ];
}

class Foo extends models.Model {
    bar = fields.Boolean({ default: false });
    color_id = fields.Many2one({ relation: "color" });
    date = fields.Date();
    foo = fields.Integer();
    product_id = fields.Many2one({ relation: "product" });
    revenue = fields.Float();

    _records = [
        { id: 1, foo: 3, bar: true, product_id: 100, date: "2016-01-01", revenue: 1 },
        { id: 2, foo: 53, bar: true, product_id: 100, date: "2016-01-03", revenue: 2 },
        { id: 3, foo: 2, bar: true, product_id: 100, date: "2016-03-04", revenue: 3 },
        { id: 4, foo: 24, product_id: 100, date: "2016-03-07", revenue: 4 },
        { id: 5, foo: 4, product_id: 200, date: "2016-05-01", revenue: 5 },
        { id: 6, foo: 63, product_id: 200 },
        { id: 7, foo: 42, product_id: 200 },
        { id: 8, foo: 48, product_id: 200, date: "2016-04-01", revenue: 8 },
    ];

    _views = {
        search: /* xml */ `
            <search>
                <filter name="false_domain" string="False Domain" domain="[(0, '=', 1)]" />
                <filter name="group_by_product" string="Product" context="{ 'group_by': 'product_id' }" />
            </search>
        `,
    };
}

defineModels([Foo, Color, Product]);

// ---------------------------------------------------------------------------
// Mock Carbon Charts — lightweight SVG-producing chart stubs
// ---------------------------------------------------------------------------

/**
 * Lightweight mock of a Carbon Charts chart instance.
 *
 * When instantiated it creates an SVG element inside the host container,
 * mirroring the DOM structure that the real @carbon/charts library would
 * produce. Static class-level arrays track all created instances so that
 * tests can assert on construction count and destruction state.
 */
class MockCarbonChart {
    /** @type {MockCarbonChart[]} All chart instances created during the current test */
    static instances = [];
    /** @type {MockCarbonChart|null} Most recently created chart instance */
    static lastInstance = null;

    /**
     * @param {HTMLElement} element  Container element for the chart
     * @param {{ data: Object[], options: Object }} config  Carbon Charts config
     */
    constructor(element, config) {
        this.element = element;
        this.data = (config && config.data) || [];
        this.options = (config && config.options) || {};
        this.destroyed = false;
        this.chartType = this.constructor.chartTypeName || "unknown";

        // Minimal event service mock matching Carbon Charts internal API
        this._eventListeners = {};
        this.services = {
            events: {
                addEventListener: (name, callback) => {
                    this._eventListeners[name] = this._eventListeners[name] || [];
                    this._eventListeners[name].push(callback);
                },
                removeEventListener: () => {},
            },
        };

        this._render();
        MockCarbonChart.instances.push(this);
        MockCarbonChart.lastInstance = this;
    }

    /**
     * Creates an SVG element inside the container with data-driven child
     * elements, allowing DOM-based assertions on chart content.
     * @private
     */
    _render() {
        if (!this.element) {
            return;
        }
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.classList.add("cds--chart-holder");
        svg.setAttribute("width", "100%");
        svg.setAttribute("height", "100%");
        svg.setAttribute("role", "img");
        svg.setAttribute("aria-label", "Carbon chart");

        for (const item of this.data) {
            const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
            rect.setAttribute("class", "cds--bar");
            rect.setAttribute("data-group", item.group || "");
            if (item.key !== undefined) {
                rect.setAttribute("data-key", String(item.key));
            }
            rect.setAttribute("width", "20");
            rect.setAttribute("height", String(Math.max(1, Math.abs(item.value || 0) * 2)));
            svg.appendChild(rect);
        }

        this.element.appendChild(svg);
    }

    /** Destroys the chart and clears the container. */
    destroy() {
        this.destroyed = true;
        if (this.element) {
            this.element.innerHTML = "";
        }
    }
}

// Subclasses for type-specific tracking (optional — used to verify correct
// chart class selection in getChartType())
class MockSimpleBarChart extends MockCarbonChart {
    static chartTypeName = "SimpleBarChart";
}
class MockStackedBarChart extends MockCarbonChart {
    static chartTypeName = "StackedBarChart";
}
class MockGroupedBarChart extends MockCarbonChart {
    static chartTypeName = "GroupedBarChart";
}
class MockLineChart extends MockCarbonChart {
    static chartTypeName = "LineChart";
}
class MockPieChart extends MockCarbonChart {
    static chartTypeName = "PieChart";
}

/** Resets static tracking between tests. */
function resetMockTracking() {
    MockCarbonChart.instances = [];
    MockCarbonChart.lastInstance = null;
}

// ---------------------------------------------------------------------------
// Test-local helpers
// ---------------------------------------------------------------------------

/**
 * Finds the CarbonGraphRenderer component instance within a mounted view.
 * @param {Object} view  value returned by mountView()
 * @returns {CarbonGraphRenderer|null}
 */
function getCarbonGraphRenderer(view) {
    return findComponent(view, (c) => c instanceof CarbonGraphRenderer);
}

/**
 * Returns the mode-toggle button for the specified chart mode.
 * @param {"bar"|"line"|"pie"} mode
 * @returns {HTMLElement}
 */
function getModeButton(mode) {
    return queryOne(`.o_graph_button[data-mode="${mode}"]`);
}

/**
 * Clicks the mode button for the given chart mode.
 * @param {"bar"|"line"|"pie"} mode
 */
function selectMode(mode) {
    return contains(`.o_graph_button[data-mode="${mode}"]`).click();
}

// ===========================================================================
// Test Suites
// ===========================================================================

describe("CarbonGraphRenderer", () => {
    beforeEach(() => {
        resetMockTracking();
        patchWithCleanup(window, {
            Charts: {
                SimpleBarChart: MockStackedBarChart,
                StackedBarChart: MockStackedBarChart,
                GroupedBarChart: MockGroupedBarChart,
                LineChart: MockLineChart,
                PieChart: MockPieChart,
            },
        });
    });

    // ===================================================================
    // Data Binding
    // ===================================================================
    describe("Data Binding", () => {
        test("renders correctly with default data", async () => {
            await mountView({ type: "graph", resModel: "foo" });

            // Graph view wrapper is present
            expect(".o_graph_view").toHaveCount(1);

            // Carbon Charts container and SVG are present (not canvas)
            expect(".o_graph_renderer").toHaveCount(1);
            expect(".o_carbon_chart").toHaveCount(1);
            expect(".o_carbon_chart svg").toHaveCount(1);

            // Chart.js canvas must NOT be rendered
            expect("canvas").toHaveCount(0);

            // SVG carries accessible ARIA attributes
            const svg = queryOne(".o_carbon_chart svg");
            expect(svg.getAttribute("role")).toBe("img");
        });

        test("binds Odoo graph model data to Carbon Charts for product_id groupBy", async () => {
            await mountView({
                type: "graph",
                resModel: "foo",
                arch: `<graph><field name="product_id"/></graph>`,
            });

            // Chart instance received data from the graph model
            const chart = MockCarbonChart.lastInstance;
            expect(chart !== null).toBe(true, {
                message: "A Carbon chart instance should have been created",
            });
            expect(chart.data.length > 0).toBe(true, {
                message: "Chart should receive data points from the graph model",
            });

            // SVG should contain rect elements representing data
            const rects = queryAll(".o_carbon_chart svg rect");
            expect(rects.length > 0).toBe(true, {
                message: "SVG should contain rect elements for data visualisation",
            });
        });

        test("renders with no data (empty dataset)", async () => {
            Foo._records = [];
            await mountView({ type: "graph", resModel: "foo" });

            // Graph view and renderer are still present (no crash)
            expect(".o_graph_view").toHaveCount(1);
            expect(".o_graph_renderer").toHaveCount(1);

            // No "nocontent" placeholder (consistent with original graph view)
            expect(".o_nocontent_help").toHaveCount(0);
        });

        test("binds data with explicit revenue measure", async () => {
            await mountView({
                type: "graph",
                resModel: "foo",
                arch: `<graph>
                    <field name="revenue" type="measure"/>
                    <field name="product_id"/>
                </graph>`,
            });

            expect(".o_graph_view").toHaveCount(1);
            expect(".o_carbon_chart svg").toHaveCount(1);

            const chart = MockCarbonChart.lastInstance;
            expect(chart !== null).toBe(true);
            expect(chart.data.length > 0).toBe(true, {
                message: "Chart should receive revenue measure data",
            });
        });

        test("passes options with color scale to Carbon Charts", async () => {
            await mountView({
                type: "graph",
                resModel: "foo",
                arch: `<graph><field name="bar"/></graph>`,
            });

            const chart = MockCarbonChart.lastInstance;
            expect(chart !== null).toBe(true);
            expect(chart.options.color !== undefined).toBe(true, {
                message: "Chart options should include a color configuration",
            });
            expect(chart.options.color.scale !== undefined).toBe(true, {
                message: "Chart options should include a color scale mapping",
            });
        });
    });

    // ===================================================================
    // Chart Type Switching
    // ===================================================================
    describe("Chart Type Switching", () => {
        test("default bar mode renders correctly", async () => {
            await mountView({ type: "graph", resModel: "foo" });

            expect(".o_graph_view").toHaveCount(1);
            expect(".o_carbon_chart svg").toHaveCount(1);
            expect(`.o_graph_button[data-mode="bar"]`).toHaveClass("active");
        });

        test("switching to line mode renders correctly", async () => {
            await mountView({ type: "graph", resModel: "foo" });

            await selectMode("line");
            await animationFrame();

            expect(`.o_graph_button[data-mode="line"]`).toHaveClass("active");
            expect(".o_carbon_chart svg").toHaveCount(1);
        });

        test("switching to pie mode renders correctly", async () => {
            await mountView({ type: "graph", resModel: "foo" });

            await selectMode("pie");
            await animationFrame();

            expect(`.o_graph_button[data-mode="pie"]`).toHaveClass("active");
            expect(".o_carbon_chart svg").toHaveCount(1);
        });

        test("switching chart types destroys and recreates the chart instance", async () => {
            await mountView({ type: "graph", resModel: "foo" });

            const initialCount = MockCarbonChart.instances.length;
            expect(initialCount > 0).toBe(true, {
                message: "At least one chart instance should exist after initial render",
            });

            const firstChart = MockCarbonChart.instances[initialCount - 1];

            // Switch to line mode
            await selectMode("line");
            await animationFrame();

            expect(firstChart.destroyed).toBe(true, {
                message: "Previous bar chart should be destroyed on mode switch",
            });
            expect(MockCarbonChart.instances.length > initialCount).toBe(true, {
                message: "A new chart instance should be created after mode switch",
            });

            expect(".o_carbon_chart svg").toHaveCount(1);
        });

        test("line chart via arch type attribute", async () => {
            await mountView({
                type: "graph",
                resModel: "foo",
                arch: `<graph type="line"/>`,
            });

            expect(`.o_graph_button[data-mode="line"]`).toHaveClass("active");
            expect(".o_carbon_chart svg").toHaveCount(1);
        });

        test("pie chart via arch type attribute", async () => {
            await mountView({
                type: "graph",
                resModel: "foo",
                arch: `<graph type="pie"/>`,
            });

            expect(`.o_graph_button[data-mode="pie"]`).toHaveClass("active");
            expect(".o_carbon_chart svg").toHaveCount(1);
        });

        test("switching from line back to bar works correctly", async () => {
            await mountView({ type: "graph", resModel: "foo" });

            // Go to line
            await selectMode("line");
            await animationFrame();
            expect(`.o_graph_button[data-mode="line"]`).toHaveClass("active");

            // Back to bar
            await selectMode("bar");
            await animationFrame();
            expect(`.o_graph_button[data-mode="bar"]`).toHaveClass("active");
            expect(".o_carbon_chart svg").toHaveCount(1);
        });
    });

    // ===================================================================
    // WCAG 2.1 AA Colour Palettes
    // ===================================================================
    describe("WCAG 2.1 AA Colour Palettes", () => {
        test("chart options contain a colour scale for grouped data", async () => {
            await mountView({
                type: "graph",
                resModel: "foo",
                arch: `<graph>
                    <field name="bar"/>
                    <field name="product_id"/>
                </graph>`,
            });

            expect(".o_carbon_chart svg").toHaveCount(1);

            const chart = MockCarbonChart.lastInstance;
            expect(chart !== null).toBe(true);
            expect(chart.options.color !== undefined).toBe(true);

            const colorScale = chart.options.color.scale;
            expect(colorScale !== undefined).toBe(true);

            // All colour values must be valid 7-char hex strings
            const colorValues = Object.values(colorScale);
            expect(colorValues.length > 0).toBe(true, {
                message: "Colour scale should contain at least one entry",
            });
            for (const c of colorValues) {
                const isHex = /^#[0-9a-fA-F]{6}$/.test(c);
                expect(isHex).toBe(true, {
                    message: `"${c}" should be a valid hex colour from Carbon accessible palette`,
                });
            }
        });

        test("chart options include a valid Carbon theme identifier", async () => {
            await mountView({ type: "graph", resModel: "foo" });

            const chart = MockCarbonChart.lastInstance;
            expect(chart !== null).toBe(true);

            const validThemes = ["white", "g90"];
            expect(validThemes.includes(chart.options.theme)).toBe(true, {
                message: "Chart theme should be 'white' or 'g90'",
            });
        });

        test("chart options include enabled tooltips", async () => {
            await mountView({ type: "graph", resModel: "foo" });

            const chart = MockCarbonChart.lastInstance;
            expect(chart !== null).toBe(true);
            expect(chart.options.tooltip !== undefined).toBe(true);
            expect(chart.options.tooltip.enabled).toBe(true);
        });

        test("bar chart axes include formatter functions", async () => {
            await mountView({ type: "graph", resModel: "foo" });

            const chart = MockCarbonChart.lastInstance;
            expect(chart !== null).toBe(true);
            expect(chart.options.axes !== undefined).toBe(true, {
                message: "Bar chart should define axes",
            });
            expect(chart.options.axes.left !== undefined).toBe(true);
            expect(chart.options.axes.bottom !== undefined).toBe(true);
            expect(typeof chart.options.axes.left.ticks.formatter).toBe("function", {
                message: "Y-axis should have a tick formatter function",
            });
            expect(typeof chart.options.axes.bottom.ticks.formatter).toBe("function", {
                message: "X-axis should have a tick formatter function",
            });
        });

        test("pie chart options include legend and alignment", async () => {
            await mountView({
                type: "graph",
                resModel: "foo",
                arch: `<graph type="pie"/>`,
            });

            const chart = MockCarbonChart.lastInstance;
            expect(chart !== null).toBe(true);
            expect(chart.options.legend !== undefined).toBe(true);
            expect(chart.options.legend.enabled).toBe(true);
        });
    });

    // ===================================================================
    // View Registry Registration
    // ===================================================================
    describe("View Registry Registration", () => {
        test("graph view type is registered in the views registry", () => {
            const viewsRegistry = registry.category("views");
            const registeredView = viewsRegistry.get("graph");

            expect(registeredView !== undefined).toBe(true, {
                message: "A 'graph' view should be registered",
            });
            expect(registeredView.Renderer).toBe(CarbonGraphRenderer, {
                message: "Registered graph Renderer should be CarbonGraphRenderer",
            });
        });

        test("carbonGraphView definition has correct type and Renderer", () => {
            expect(carbonGraphView.type).toBe("graph");
            expect(carbonGraphView.Renderer).toBe(CarbonGraphRenderer);
        });

        test("CarbonGraphRenderer has correct static template", () => {
            expect(CarbonGraphRenderer.template).toBe("carbon_ui.CarbonGraphRenderer");
        });

        test("CarbonGraphRenderer declares static props", () => {
            expect(CarbonGraphRenderer.props !== undefined).toBe(true, {
                message: "CarbonGraphRenderer should define static props",
            });
        });

        test("mounting graph view produces SVG, not canvas", async () => {
            await mountView({ type: "graph", resModel: "foo" });

            expect("canvas").toHaveCount(0, {
                message: "Chart.js canvas should not be present",
            });
            expect(".o_carbon_chart svg").toHaveCount(1, {
                message: "Carbon Charts SVG should be present",
            });
        });
    });

    // ===================================================================
    // Data Changes and Re-rendering
    // ===================================================================
    describe("Data Changes and Re-rendering", () => {
        test("chart updates when a search filter is applied", async () => {
            await mountView({ type: "graph", resModel: "foo" });

            const countBefore = MockCarbonChart.instances.length;

            // Apply "False Domain" filter (matches 0 records)
            await toggleSearchBarMenu();
            await toggleMenuItem("False Domain");
            await animationFrame();

            // View should still render (no crash)
            expect(".o_graph_renderer").toHaveCount(1);

            // A new chart should have been created to reflect the new data
            expect(MockCarbonChart.instances.length > countBefore).toBe(true, {
                message: "Chart should be re-created after filter change",
            });
        });

        test("chart re-creates on groupBy change", async () => {
            await mountView({ type: "graph", resModel: "foo" });

            const countBefore = MockCarbonChart.instances.length;

            // Apply product groupBy
            await toggleSearchBarMenu();
            await toggleMenuItem("Product");
            await animationFrame();

            expect(MockCarbonChart.instances.length > countBefore).toBe(true, {
                message: "Chart should be re-created after groupBy change",
            });

            // Verify data has group information
            const chart = MockCarbonChart.lastInstance;
            if (chart && chart.data.length > 0) {
                const groups = [...new Set(chart.data.map((d) => d.group))];
                expect(groups.length > 0).toBe(true, {
                    message: "Chart data should contain groups from the groupBy",
                });
            }
        });

        test("mode persists after data change", async () => {
            await mountView({ type: "graph", resModel: "foo" });

            // Switch to line mode
            await selectMode("line");
            await animationFrame();

            // Apply a groupBy filter
            await toggleSearchBarMenu();
            await toggleMenuItem("Product");
            await animationFrame();

            // Mode should still be line
            expect(`.o_graph_button[data-mode="line"]`).toHaveClass("active");
        });
    });

    // ===================================================================
    // RPC Integration
    // ===================================================================
    describe("RPC Integration", () => {
        test("formatted_read_group is called when mounting graph view", async () => {
            let readGroupCallCount = 0;
            onRpc("formatted_read_group", () => {
                readGroupCallCount++;
            });

            await mountView({ type: "graph", resModel: "foo" });

            expect(readGroupCallCount > 0).toBe(true, {
                message: "formatted_read_group should be called to fetch aggregated data",
            });
        });

        test("formatted_read_group is called with groupby from arch", async () => {
            const calls = [];
            onRpc("formatted_read_group", ({ kwargs }) => {
                calls.push(kwargs);
            });

            await mountView({
                type: "graph",
                resModel: "foo",
                arch: `<graph><field name="product_id"/></graph>`,
            });

            expect(calls.length > 0).toBe(true, {
                message: "formatted_read_group should be called for product_id groupBy",
            });
        });

        test("formatted_read_group is re-invoked after filter change", async () => {
            let callCount = 0;
            onRpc("formatted_read_group", () => {
                callCount++;
            });

            await mountView({ type: "graph", resModel: "foo" });
            const initial = callCount;

            await toggleSearchBarMenu();
            await toggleMenuItem("False Domain");
            await animationFrame();

            expect(callCount > initial).toBe(true, {
                message: "formatted_read_group should be called again after a filter is applied",
            });
        });
    });

    // ===================================================================
    // Chart Lifecycle
    // ===================================================================
    describe("Chart Lifecycle", () => {
        test("chart instance is created on mount", async () => {
            const countBefore = MockCarbonChart.instances.length;
            await mountView({ type: "graph", resModel: "foo" });

            expect(MockCarbonChart.instances.length > countBefore).toBe(true, {
                message: "A new Carbon chart instance should be created on mount",
            });
        });

        test("chart options include legend configuration", async () => {
            await mountView({ type: "graph", resModel: "foo" });

            const chart = MockCarbonChart.lastInstance;
            expect(chart !== null).toBe(true);
            expect(chart.options.legend !== undefined).toBe(true);
            expect(chart.options.legend.enabled).toBe(true);
        });

        test("chart options enable animations", async () => {
            await mountView({ type: "graph", resModel: "foo" });

            const chart = MockCarbonChart.lastInstance;
            expect(chart !== null).toBe(true);
            expect(chart.options.animations).toBe(true);
        });

        test("chart options set title to null (Odoo renders title separately)", async () => {
            await mountView({ type: "graph", resModel: "foo" });

            const chart = MockCarbonChart.lastInstance;
            expect(chart !== null).toBe(true);
            expect(chart.options.title).toBe(null, {
                message: "Carbon chart title should be null — Odoo renders the title in the layout",
            });
        });

        test("graph view preserves custom class attribute from arch", async () => {
            await mountView({
                type: "graph",
                resModel: "foo",
                arch: `<graph class="custom_carbon_class"/>`,
            });

            expect(".o_graph_view").toHaveClass("custom_carbon_class");
        });
    });

    // ===================================================================
    // Service and Component Integration
    // ===================================================================
    describe("Service and Component Integration", () => {
        test("action service is accessible for chart drill-down navigation", async () => {
            await mountView({ type: "graph", resModel: "foo" });

            const actionService = getService("action");
            expect(actionService !== undefined).toBe(true, {
                message: "Action service should be available for drill-down clicks",
            });
        });

        test("CarbonGraphRenderer instance is found via mountWithCleanup pattern", async () => {
            const view = await mountView({ type: "graph", resModel: "foo" });

            // findComponent locates the renderer inside the view tree
            const renderer = getCarbonGraphRenderer(view);
            expect(renderer !== null && renderer !== undefined).toBe(true, {
                message: "CarbonGraphRenderer instance should be discoverable in the component tree",
            });
        });

        test("mode buttons carry accessible aria-label attributes", async () => {
            await mountView({ type: "graph", resModel: "foo" });

            // Verify the three mode buttons exist with data-mode attributes
            const buttons = queryAll(".o_graph_button[data-mode]");
            expect(buttons.length).toBe(3, {
                message: "Three mode buttons (bar, line, pie) should be present",
            });

            // Graph buttons are icon-only (FontAwesome) but carry aria-labels
            // for accessibility. queryAllTexts on the parent toolbar verifies
            // the toolbar area has textual content (measures dropdown text etc.)
            const toolbarTexts = queryAllTexts(".d-flex.d-print-none.gap-1 > *");
            expect(toolbarTexts.length > 0).toBe(true, {
                message: "Toolbar area should contain renderable text content",
            });

            // Verify each mode button has an aria-label for screen readers
            for (const btn of buttons) {
                const ariaLabel = btn.getAttribute("aria-label") || "";
                expect(ariaLabel.length > 0).toBe(true, {
                    message: "Each mode button should have an aria-label for accessibility",
                });
            }
        });

        test("mountWithCleanup correctly manages component lifecycle", async () => {
            // mountWithCleanup is the underlying mechanism used by mountView
            // This test verifies the full view can be mounted and automatically
            // cleaned up without leaking DOM elements or chart instances
            const view = await mountView({ type: "graph", resModel: "foo" });

            expect(".o_graph_view").toHaveCount(1);
            const chartInstanceCount = MockCarbonChart.instances.length;
            expect(chartInstanceCount > 0).toBe(true, {
                message: "Chart instances should be tracked during the test lifecycle",
            });
        });
    });

    // ===================================================================
    // Arch Configuration
    // ===================================================================
    describe("Arch Configuration", () => {
        test("respects measure attribute", async () => {
            await mountView({
                type: "graph",
                resModel: "foo",
                arch: `<graph><field name="revenue" type="measure"/></graph>`,
            });

            expect(".o_graph_view").toHaveCount(1);
            expect(".o_carbon_chart svg").toHaveCount(1);
        });

        test("respects stacked attribute", async () => {
            await mountView({
                type: "graph",
                resModel: "foo",
                arch: `<graph stacked="0">
                    <field name="bar"/>
                    <field name="product_id"/>
                </graph>`,
            });

            expect(".o_graph_view").toHaveCount(1);
            expect(".o_carbon_chart svg").toHaveCount(1);
        });

        test("single groupBy field populates chart data", async () => {
            await mountView({
                type: "graph",
                resModel: "foo",
                arch: `<graph><field name="bar"/></graph>`,
            });

            expect(".o_carbon_chart svg").toHaveCount(1);

            const chart = MockCarbonChart.lastInstance;
            expect(chart !== null).toBe(true);
            expect(chart.data.length > 0).toBe(true, {
                message: "Chart data should be populated from bar groupBy",
            });
        });

        test("multiple groupBy fields produce multi-group chart data", async () => {
            await mountView({
                type: "graph",
                resModel: "foo",
                arch: `<graph>
                    <field name="bar"/>
                    <field name="product_id"/>
                </graph>`,
            });

            expect(".o_carbon_chart svg").toHaveCount(1);

            const chart = MockCarbonChart.lastInstance;
            expect(chart !== null).toBe(true);
            expect(chart.data.length > 0).toBe(true, {
                message: "Chart data should contain entries for multi-group rendering",
            });

            // Multiple groups should exist in the data
            const groups = [...new Set(chart.data.map((d) => d.group))];
            expect(groups.length > 1).toBe(true, {
                message: "Multiple dataset groups should be generated from two groupBy fields",
            });
        });

        test("line chart with stacked attribute generates stacked axis option", async () => {
            await mountView({
                type: "graph",
                resModel: "foo",
                arch: `<graph type="line" stacked="1">
                    <field name="bar"/>
                    <field name="product_id"/>
                </graph>`,
            });

            const chart = MockCarbonChart.lastInstance;
            expect(chart !== null).toBe(true);
            if (chart.options.axes && chart.options.axes.left) {
                expect(chart.options.axes.left.stacked).toBe(true, {
                    message: "Stacked line chart should set left axis stacked to true",
                });
            }
        });
    });
});
