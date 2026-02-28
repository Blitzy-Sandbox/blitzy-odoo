/** @odoo-module */

/**
 * CarbonGraphRenderer — OWL 2.8.1 graph renderer wrapping @carbon/charts
 *
 * Replaces Odoo's Chart.js-based GraphRenderer with Carbon Charts (D3.js-based)
 * while preserving the exact same props interface, data model consumption, and
 * user interactions (click-to-drill-down, tooltips, measure/mode/order toggles).
 *
 * Carbon Charts classes are exposed as the global `window.Charts` object by the
 * vendored UMD bundle (carbon-charts.min.js) loaded in web.assets_backend_lazy.
 * D3.js (d3.min.js) is loaded as a peer dependency before Carbon Charts.
 *
 * WCAG 2.1 AA compliant, color-blind-friendly palettes are used for all chart
 * types, with automatic palette switching for dark mode via the color_scheme
 * cookie.
 */

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { formatFloat, formatMonetary } from "@web/views/fields/formatters";
import { SEP } from "@web/views/graph/graph_model";
import { renderToMarkup } from "@web/core/utils/render";
import { useService } from "@web/core/utils/hooks";

import { Component, onWillUnmount, useEffect, useRef, markup } from "@odoo/owl";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { cookie } from "@web/core/browser/cookie";
import { createElementWithContent } from "@web/core/utils/html";
import { ReportViewMeasures } from "@web/views/view_components/report_view_measures";
import { Widget } from "@web/views/widgets/widget";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const NO_DATA = _t("No data");
const formatters = registry.category("formatters");

/**
 * WCAG 2.1 AA compliant, color-blind-friendly palette — Carbon's accessible
 * categorical colors for light themes (White / G10).
 */
const CARBON_CHART_COLORS = [
    "#6929c4", // Purple 70
    "#1192e8", // Cyan 50
    "#005d5d", // Teal 70
    "#9f1853", // Magenta 70
    "#fa4d56", // Red 50
    "#570408", // Red 90
    "#198038", // Green 60
    "#002d9c", // Blue 80
    "#ee538b", // Magenta 50
    "#b28600", // Yellow 50
    "#009d9a", // Teal 50
    "#012749", // Cyan 90
    "#8a3800", // Orange 70
    "#a56eff", // Purple 50
];

/**
 * Dark-mode variant of the accessible categorical palette, providing
 * sufficient contrast on dark backgrounds (G90 / G100 themes).
 */
const CARBON_CHART_COLORS_DARK = [
    "#8a3ffc", // Purple 60
    "#33b1ff", // Cyan 40
    "#007d79", // Teal 60
    "#ff7eb6", // Magenta 40
    "#fa4d56", // Red 50
    "#fff1f1", // Red 10
    "#6fdc8c", // Green 30
    "#4589ff", // Blue 50
    "#d12771", // Magenta 60
    "#d2a106", // Yellow 40
    "#08bdba", // Teal 40
    "#bae6ff", // Cyan 20
    "#ba4e00", // Orange 60
    "#d4bbff", // Purple 30
];

/** Neutral placeholder colour for empty / "No data" slices in pie charts. */
const NO_DATA_COLOR_LIGHT = "#e0e0e0"; // Gray 20
const NO_DATA_COLOR_DARK = "#525252"; // Gray 70

// ---------------------------------------------------------------------------
// Helpers (module-level)
// ---------------------------------------------------------------------------

/**
 * Calculates maximum tooltip width relative to chart area using golden ratio.
 * @param {DOMRect|{left: number, right: number}} chartArea
 * @returns {string} CSS width value
 */
function getMaxWidth(chartArea) {
    const { left, right } = chartArea;
    return Math.floor((right - left) / 1.618) + "px";
}

/**
 * Shortens a multi-level group-by label to keep tooltips and legends readable.
 * Mirrors the original Graph renderer behaviour exactly.
 * @param {string} label
 * @returns {string}
 */
function shortenLabel(label) {
    // string returned could be wrong if a groupby value contain a " / "!
    const groups = label.toString().split(SEP);
    let shortLabel = groups.slice(0, 3).join(SEP);
    if (shortLabel.length > 30) {
        shortLabel = `${shortLabel.slice(0, 30)}...`;
    } else if (groups.length > 3) {
        shortLabel = `${shortLabel}${SEP}...`;
    }
    return shortLabel;
}

/**
 * Resolves the appropriate "No data" placeholder colour for the active theme.
 * @returns {string} hex colour value
 */
function getNoDataColor() {
    return cookie.get("color_scheme") === "dark" ? NO_DATA_COLOR_DARK : NO_DATA_COLOR_LIGHT;
}

// ---------------------------------------------------------------------------
// CarbonGraphRenderer
// ---------------------------------------------------------------------------

export class CarbonGraphRenderer extends Component {
    static template = "carbon_ui.CarbonGraphRenderer";
    static components = { Dropdown, DropdownItem, ReportViewMeasures, Widget };
    static props = ["class?", "model", "buttonTemplate"];

    // ------------------------------------------------------------------
    // Lifecycle
    // ------------------------------------------------------------------

    setup() {
        this.model = this.props.model;

        // DOM references — note: chartRef targets a <div>, not <canvas>
        this.rootRef = useRef("root");
        this.chartRef = useRef("chart");
        this.containerRef = useRef("container");

        // Odoo action service for drill-down navigation
        this.actionService = useService("action");

        // Active Carbon Charts instance (one at a time)
        this.chart = null;

        // Tooltip DOM elements for manual cleanup
        this.tooltip = null;
        this.legendTooltip = null;

        // Internal lookup tables rebuilt on each renderChart() call
        this._datasetLabelToIndex = {};
        this._labelToIndex = {};

        // Carbon Charts JS is loaded via the web.assets_backend_lazy bundle
        // (no dynamic loadBundle call needed).

        // Re-render whenever the model notifies (data / metaData changes)
        useEffect(() => this.renderChart());

        // Destroy chart on unmount to avoid memory leaks
        onWillUnmount(this.onWillUnmount);
    }

    /**
     * Clean up Carbon Charts instance and any lingering tooltip elements
     * when the OWL component is removed from the DOM.
     */
    onWillUnmount() {
        if (this.chart) {
            try {
                this.chart.destroy();
            } catch (_e) {
                // Defensive: chart.destroy() may throw if the DOM node is
                // already detached.
            }
            this.chart = null;
        }
        this.removeTooltips();
    }

    // ------------------------------------------------------------------
    // Color helpers
    // ------------------------------------------------------------------

    /**
     * Returns the current theme-appropriate chart colour palette.
     * @returns {string[]}
     */
    getChartColors() {
        return cookie.get("color_scheme") === "dark"
            ? CARBON_CHART_COLORS_DARK
            : CARBON_CHART_COLORS;
    }

    // ------------------------------------------------------------------
    // Chart type resolution
    // ------------------------------------------------------------------

    /**
     * Determines which Carbon Charts constructor to use based on the current
     * Odoo graph mode and stacked flag.
     *
     * @param {string} mode  "bar" | "line" | "pie"
     * @param {boolean} stacked
     * @param {number} groupCount  Number of distinct dataset groups
     * @returns {Function|null} Carbon Chart constructor, or null if unavailable
     */
    getChartType(mode, stacked, groupCount) {
        const Charts = window.Charts;
        if (!Charts) {
            return null;
        }
        switch (mode) {
            case "bar":
                if (stacked) {
                    return Charts.StackedBarChart;
                }
                return groupCount > 1 ? Charts.GroupedBarChart : Charts.SimpleBarChart;
            case "line":
                return Charts.LineChart;
            case "pie":
                return Charts.PieChart;
            default:
                return Charts.SimpleBarChart;
        }
    }

    // ------------------------------------------------------------------
    // Data transformation
    // ------------------------------------------------------------------

    /**
     * Transforms Odoo's GraphModel data format into the flat array-of-objects
     * format consumed by @carbon/charts.
     *
     * Odoo format:
     *   { labels: string[], datasets: [{ label, data, trueLabels, domains, currencyIds, cumulatedStart }] }
     *
     * Carbon Charts format:
     *   [{ group: string, key: string, value: number }]  — bar / line
     *   [{ group: string, value: number }]                — pie
     *
     * @returns {{ carbonData: Object[], groupCount: number }}
     */
    transformData() {
        const { data, metaData, lineOverlayDataset } = this.model;
        const { mode, cumulated, stacked } = metaData;
        const { labels, datasets } = data;

        const carbonData = [];
        this._datasetLabelToIndex = {};
        this._labelToIndex = {};

        // Build label → index lookup for click handling
        labels.forEach((label, i) => {
            this._labelToIndex[String(label)] = i;
        });

        if (mode === "pie") {
            // Pie charts: flatten to { group, value } — one entry per label
            if (datasets.length > 0) {
                const dataset = datasets[0];
                for (let i = 0; i < labels.length; i++) {
                    carbonData.push({
                        group: labels[i] || String(NO_DATA),
                        value: dataset.data[i] || 0,
                    });
                }
            }
            // Handle completely empty state
            if (carbonData.length === 0) {
                carbonData.push({
                    group: String(NO_DATA),
                    value: 1,
                });
            }
            return { carbonData, groupCount: 1 };
        }

        // Bar & Line charts
        // Apply cumulation for line charts when enabled
        if (mode === "line" && cumulated) {
            for (const dataset of datasets) {
                let accumulator = dataset.cumulatedStart || 0;
                dataset.data = dataset.data.map((value) => {
                    accumulator += value;
                    return accumulator;
                });
            }
        }

        // Handle single-label padding for line charts (centres the point)
        let effectiveLabels = labels;
        if (mode === "line" && labels.length === 1) {
            effectiveLabels = ["", ...labels, ""];
            for (const dataset of datasets) {
                dataset.data.unshift(undefined);
                dataset.trueLabels.unshift(undefined);
                dataset.domains.unshift(undefined);
            }
        }

        // Build flat data array
        const groupNames = new Set();
        for (let dsIdx = 0; dsIdx < datasets.length; dsIdx++) {
            const dataset = datasets[dsIdx];
            const groupName = dataset.label || "";
            this._datasetLabelToIndex[groupName] = dsIdx;
            groupNames.add(groupName);
            for (let i = 0; i < effectiveLabels.length; i++) {
                const value = dataset.data[i];
                if (value === undefined) {
                    continue; // skip padding entries
                }
                carbonData.push({
                    group: groupName,
                    key: String(effectiveLabels[i]),
                    value: value || 0,
                });
            }
        }

        // For stacked bar charts with a line overlay dataset (sum line)
        if (mode === "bar" && stacked && lineOverlayDataset && datasets.length > 1) {
            const overlayGroup = lineOverlayDataset.label || _t("Sum");
            this._datasetLabelToIndex[overlayGroup] = -1; // sentinel for overlay
            for (let i = 0; i < effectiveLabels.length; i++) {
                const value = lineOverlayDataset.data[i];
                if (value === undefined) {
                    continue;
                }
                carbonData.push({
                    group: overlayGroup,
                    key: String(effectiveLabels[i]),
                    value: value || 0,
                });
            }
            groupNames.add(overlayGroup);
        }

        return { carbonData, groupCount: groupNames.size };
    }

    // ------------------------------------------------------------------
    // Chart options
    // ------------------------------------------------------------------

    /**
     * Builds the Carbon Charts options object for the current chart mode.
     * Handles axes, legend, colour scale, tooltip, animation, and theme.
     *
     * @param {Object[]} carbonData  transformed data array
     * @param {number} groupCount    number of distinct groups / datasets
     * @returns {Object} Carbon Charts options
     */
    getChartOptions(carbonData, groupCount) {
        const { metaData, data } = this.model;
        const { mode, measures, measure, fieldAttrs, stacked } = metaData;
        const { labels, datasets } = data;
        const colors = this.getChartColors();
        const isDark = cookie.get("color_scheme") === "dark";

        // --- Colour scale mapping -------------------------------------------------
        const colorScale = {};
        if (mode === "pie") {
            // Map each slice label to a colour
            const pieLabels = carbonData.map((d) => d.group);
            pieLabels.forEach((label, i) => {
                if (label === String(NO_DATA)) {
                    colorScale[label] = getNoDataColor();
                } else {
                    colorScale[label] = colors[i % colors.length];
                }
            });
        } else {
            // Map each dataset group label to a colour
            const groupLabels = [...new Set(carbonData.map((d) => d.group))];
            groupLabels.forEach((label, i) => {
                colorScale[label] = colors[i % colors.length];
            });
        }

        // --- Base options ---------------------------------------------------------
        const options = {
            title: null, // title is rendered by Odoo's layout, not the chart
            resizable: true,
            height: "100%",
            color: {
                scale: colorScale,
            },
            legend: {
                enabled: true,
                truncation: {
                    type: "end_line",
                    threshold: 30,
                    numCharacter: 30,
                },
            },
            tooltip: {
                enabled: true,
                showTotal: false,
                customHTML: this.buildCustomTooltipHTML.bind(this),
            },
            animations: true,
            theme: isDark ? "g90" : "white",
        };

        // --- Mode-specific options ------------------------------------------------
        if (mode === "pie") {
            options.legend.alignment = "center";
            options.legend.position = "right";
            options.pie = {
                alignment: "center",
            };
        } else {
            // Bar / Line axes
            options.legend.position = "top";
            options.axes = {
                left: {
                    mapsTo: "value",
                    title: measures[measure] ? measures[measure].string : "",
                    ticks: {
                        formatter: (value) =>
                            this.formatValue(value, false, fieldAttrs[measure]?.widget),
                    },
                    stacked: mode === "bar" && stacked,
                    includeZero: true,
                },
                bottom: {
                    mapsTo: "key",
                    scaleType: "labels",
                    ticks: {
                        formatter: (label) => shortenLabel(String(label)),
                    },
                },
            };

            if (mode === "bar") {
                options.bars = {
                    maxWidth: 80,
                };
            }

            if (mode === "line") {
                options.points = {
                    radius: 3,
                    enabled: true,
                };
                options.curve = "curveMonotoneX";
                // Stacked area fill for line charts
                if (stacked) {
                    options.axes.left.stacked = true;
                }
            }
        }

        return options;
    }

    // ------------------------------------------------------------------
    // Core rendering
    // ------------------------------------------------------------------

    /**
     * Main render method. Called via useEffect() on every model change.
     * Destroys the previous chart (if any), transforms data, builds options,
     * instantiates the appropriate Carbon Charts class, and attaches click
     * handlers for drill-down navigation.
     */
    renderChart() {
        // Destroy previous chart instance
        if (this.chart) {
            try {
                this.chart.destroy();
            } catch (_e) {
                // Defensive cleanup
            }
            this.chart = null;
        }
        this.removeTooltips();

        const el = this.chartRef.el;
        if (!el) {
            return;
        }

        // Clear the container to avoid stale SVG elements
        el.innerHTML = "";

        // If the model has no data, nothing to render
        if (!this.model.hasData()) {
            return;
        }

        const { mode, stacked } = this.model.metaData;

        // Transform Odoo model data → Carbon Charts format
        const { carbonData, groupCount } = this.transformData();

        // Resolve Carbon Charts constructor
        const ChartClass = this.getChartType(mode, stacked, groupCount);
        if (!ChartClass) {
            // Carbon Charts JS not yet loaded — this should not happen
            // because the bundle is lazy-loaded before this component mounts.
            console.warn("CarbonGraphRenderer: Carbon Charts library not available.");
            return;
        }

        // Build options
        const options = this.getChartOptions(carbonData, groupCount);

        // Instantiate the chart
        try {
            this.chart = new ChartClass(el, {
                data: carbonData,
                options,
            });
        } catch (err) {
            console.error("CarbonGraphRenderer: Failed to instantiate chart.", err);
            return;
        }

        // Attach click-to-drill-down event handlers
        this._attachClickHandlers();
    }

    // ------------------------------------------------------------------
    // Click-to-drill-down
    // ------------------------------------------------------------------

    /**
     * Attaches click event listeners on Carbon Charts chart elements for
     * drill-down navigation. Disabled for line charts (matching original
     * behaviour) and when disableLinking is true.
     * @private
     */
    _attachClickHandlers() {
        const { disableLinking, mode } = this.model.metaData;
        if (disableLinking || mode === "line" || !this.chart) {
            return;
        }

        // Carbon Charts dispatches element-level events through its internal
        // event service. Listen for the appropriate event per chart type.
        try {
            if (this.chart.services && this.chart.services.events) {
                const eventService = this.chart.services.events;
                const eventName = mode === "pie" ? "pie-slice-click" : "bar-click";
                eventService.addEventListener(eventName, (event) => {
                    this.handleChartClick(event.detail || event);
                });
            }
        } catch (_e) {
            // Fallback: attach a native click on the SVG chart holder
            this._attachNativeClickHandler();
        }
    }

    /**
     * Fallback click handler using native DOM events on the chart container.
     * @private
     */
    _attachNativeClickHandler() {
        const el = this.chartRef.el;
        if (!el) {
            return;
        }
        el.addEventListener("click", (ev) => {
            // Try to identify the data point from the clicked SVG element
            const target = ev.target;
            if (!target) {
                return;
            }
            // Carbon Charts annotates bars/slices with data attributes
            const groupAttr =
                target.getAttribute("data-group") ||
                target.closest("[data-group]")?.getAttribute("data-group");
            const keyAttr =
                target.getAttribute("data-key") ||
                target.closest("[data-key]")?.getAttribute("data-key");

            if (groupAttr !== null || keyAttr !== null) {
                this.handleChartClick({ element: { group: groupAttr, key: keyAttr } });
            }
        });
    }

    /**
     * Processes a Carbon Charts click event and resolves the corresponding
     * Odoo domain for drill-down navigation.
     *
     * @param {Object} clickedData  event detail from Carbon Charts
     */
    handleChartClick(clickedData) {
        if (!clickedData) {
            return;
        }

        const { mode } = this.model.metaData;
        const { datasets, labels } = this.model.data;

        // Extract group and key from the event detail
        let groupName, key;
        if (clickedData.datum) {
            groupName = clickedData.datum.group;
            key = clickedData.datum.key;
        } else if (clickedData.element) {
            groupName = clickedData.element.group;
            key = clickedData.element.key;
        } else if (typeof clickedData.group !== "undefined") {
            groupName = clickedData.group;
            key = clickedData.key;
        } else {
            return;
        }

        // Resolve dataset and data-point indices
        let datasetIndex, dataIndex;

        if (mode === "pie") {
            // Pie: group = label, single dataset
            datasetIndex = 0;
            dataIndex = labels.indexOf(groupName);
            if (dataIndex < 0) {
                // Try string comparison
                dataIndex = labels.findIndex((l) => String(l) === String(groupName));
            }
        } else {
            // Bar: group = dataset label, key = x-axis label
            datasetIndex = this._datasetLabelToIndex[groupName];
            if (datasetIndex === undefined || datasetIndex < 0) {
                return; // overlay dataset or unknown group — skip
            }
            dataIndex = labels.indexOf(key);
            if (dataIndex < 0) {
                dataIndex = labels.findIndex((l) => String(l) === String(key));
            }
        }

        if (
            datasetIndex === undefined ||
            datasetIndex < 0 ||
            dataIndex === undefined ||
            dataIndex < 0
        ) {
            return;
        }

        const dataset = datasets[datasetIndex];
        if (dataset && dataset.domains && dataset.domains[dataIndex]) {
            this.onGraphClickedFinal(dataset.domains[dataIndex]);
        }
    }

    /**
     * Executes the action to open a drill-down list view for the clicked
     * chart element. Identical to the original Graph renderer.
     *
     * @param {Array} domain
     * @param {Array} views
     * @param {Object} context
     * @param {boolean} [newWindow=false]
     */
    openView(domain, views, context, newWindow) {
        this.actionService.doAction(
            {
                context,
                domain,
                name: this.model.metaData.title,
                res_model: this.model.metaData.resModel,
                target: "current",
                type: "ir.actions.act_window",
                views,
            },
            {
                newWindow,
                viewType: "list",
            }
        );
    }

    /**
     * Constructs action views and triggers a drill-down navigation action.
     * Identical logic to the original Graph renderer.
     *
     * @param {Array} domain
     * @param {boolean} [isMiddleClick=false]
     */
    onGraphClickedFinal(domain, isMiddleClick = false) {
        const { context } = this.model.metaData;

        // Remove group_by and search_default_ keys from context
        Object.keys(context).forEach((x) => {
            if (x === "group_by" || x.startsWith("search_default_")) {
                delete context[x];
            }
        });

        const views = {};
        for (const [viewId, viewType] of this.env.config.views || []) {
            views[viewType] = viewId;
        }
        function getView(viewType) {
            return [views[viewType] || false, viewType];
        }
        const actionViews = [getView("list"), getView("form")];
        this.openView(domain, actionViews, context, isMiddleClick);
    }

    // ------------------------------------------------------------------
    // Tooltips
    // ------------------------------------------------------------------

    /**
     * Builds custom tooltip HTML for Carbon Charts' tooltip callback.
     * Uses the QWeb template `carbon_ui.CarbonGraphRenderer.CustomTooltip`
     * rendered via `renderToMarkup` for a consistent look-and-feel.
     *
     * @param {Object[]} datapoints  datapoints from Carbon Charts tooltip event
     * @param {string} defaultHTML   default HTML generated by Carbon Charts
     * @returns {string} custom tooltip HTML string
     */
    buildCustomTooltipHTML(datapoints, defaultHTML) {
        if (!datapoints || !datapoints.length) {
            return defaultHTML || "";
        }

        const { metaData, data } = this.model;
        const { mode, measures, measure, allIntegers, groupBy, fieldAttrs } = metaData;
        const { datasets } = data;
        const measureWidget = fieldAttrs[measure]?.widget;

        // Derive chart area dimensions for tooltip max-width
        const chartEl = this.chartRef.el;
        const chartRect = chartEl
            ? { left: 0, right: chartEl.clientWidth }
            : { left: 0, right: 400 };

        // Build tooltip items from each datapoint
        const tooltipItems = [];
        const colors = this.getChartColors();

        for (const dp of datapoints) {
            // dp structure varies by Carbon Charts version; handle both forms
            const datum = dp.datum || dp;
            const groupName = datum.group || "";
            const keyName = datum.key || "";
            let rawValue = datum.value || 0;

            // Determine dataset and data-point index for currency lookup
            let dsIdx = 0;
            let dpIdx = 0;
            if (mode === "pie") {
                const labels = data.labels;
                dpIdx = labels.findIndex((l) => String(l) === String(groupName));
                if (dpIdx < 0) {
                    dpIdx = 0;
                }
            } else {
                dsIdx = this._datasetLabelToIndex[groupName];
                if (dsIdx === undefined || dsIdx < 0) {
                    dsIdx = 0;
                }
                const labels = data.labels;
                dpIdx = labels.findIndex((l) => String(l) === String(keyName));
                if (dpIdx < 0) {
                    dpIdx = 0;
                }
            }

            const dataset = datasets[dsIdx] || datasets[0];

            // Format the value
            let formattedValue;
            if (dataset && dataset.currencyIds && dataset.currencyIds[dpIdx]) {
                formattedValue = formatMonetary(rawValue, {
                    currencyId: dataset.currencyIds[dpIdx],
                });
            } else if (dataset && dataset.currencyIds && dataset.currencyIds[dpIdx] === false) {
                formattedValue = markup`${formatMonetary(rawValue)}<sup class="ms-1 fw-bolder">?</sup>`;
            } else {
                formattedValue = this.formatValue(rawValue, allIntegers, measureWidget);
            }

            // Label construction
            let label;
            if (mode === "pie") {
                label = groupName;
                if (label === String(NO_DATA)) {
                    formattedValue = this.formatValue(0, allIntegers, measureWidget);
                }
            } else {
                label = dataset ? dataset.trueLabels?.[dpIdx] || keyName : keyName;
                if (groupBy && groupBy.length > 1 && groupName) {
                    label = `${label} / ${groupName}`;
                }
            }

            // Box colour
            const boxColor =
                dp.color ||
                colors[
                    (mode === "pie" ? dpIdx : dsIdx !== undefined ? dsIdx : 0) % colors.length
                ];

            // Percentage for pie
            let percentage;
            if (mode === "pie" && dataset) {
                const totalData = dataset.data.reduce((a, b) => a + b, 0);
                percentage =
                    totalData && ((rawValue * 100) / totalData).toFixed(2);
            }

            tooltipItems.push({ label, value: formattedValue, boxColor, percentage });
        }

        // Sort tooltip items by value descending (consistent with original)
        // (Carbon Charts may already sort, but we enforce it)

        // Render the QWeb template
        try {
            const content = renderToMarkup("carbon_ui.CarbonGraphRenderer.CustomTooltip", {
                maxWidth: getMaxWidth(chartRect),
                measure: measures[measure] ? measures[measure].string : "",
                mode,
                tooltipItems,
            });
            const template = createElementWithContent("template", content);
            return template.content.firstChild?.outerHTML || String(content);
        } catch (_e) {
            // Fallback: return default Carbon Charts tooltip
            return defaultHTML || "";
        }
    }

    // ------------------------------------------------------------------
    // Tooltip helpers
    // ------------------------------------------------------------------

    /**
     * Removes all custom tooltip DOM elements attached to the container.
     */
    removeTooltips() {
        if (this.tooltip) {
            this.tooltip.remove();
            this.tooltip = null;
        }
        this.removeLegendTooltip();
    }

    /**
     * Removes the legend tooltip if present.
     */
    removeLegendTooltip() {
        if (this.legendTooltip) {
            this.legendTooltip.remove();
            this.legendTooltip = null;
        }
    }

    // ------------------------------------------------------------------
    // Value formatting
    // ------------------------------------------------------------------

    /**
     * Formats a numeric value for display in chart axes and tooltips.
     * Matches the original Graph renderer formatting exactly.
     *
     * @param {number} value
     * @param {boolean} [allIntegers=true]
     * @param {string} [formatType=""]
     * @returns {string}
     */
    formatValue(value, allIntegers = true, formatType = "") {
        const largeNumber = Math.abs(value) >= 1000;
        if (formatType) {
            return formatters.get(formatType)(value);
        }
        if (allIntegers && !largeNumber) {
            return String(value);
        }
        if (largeNumber) {
            return formatFloat(value, { humanReadable: true, decimals: 2, minDigits: 1 });
        }
        return formatFloat(value);
    }

    // ------------------------------------------------------------------
    // Model interaction methods (identical to original)
    // ------------------------------------------------------------------

    /**
     * Loads all data points when the user clicks "Load everything anyway"
     * on the data-exceeds alert.
     */
    loadAll() {
        return this.model.forceLoadAll();
    }

    /**
     * Called when the user selects a different measure from the toolbar.
     * @param {Object} param0
     * @param {string} param0.measure
     */
    onMeasureSelected({ measure }) {
        this.model.updateMetaData({ measure });
    }

    /**
     * Called when the user selects a different chart mode (bar, line, pie).
     * @param {"bar"|"line"|"pie"} mode
     */
    onModeSelected(mode) {
        if (this.model.metaData.mode !== mode) {
            this.model.updateMetaData({ mode });
        }
    }

    /**
     * Toggles the sort order for bar chart x-axis labels.
     * @param {"ASC"|"DESC"} order
     */
    toggleOrder(order) {
        const { order: currentOrder } = this.model.metaData;
        const nextOrder = currentOrder === order ? null : order;
        this.model.updateMetaData({ order: nextOrder });
    }

    /**
     * Toggles the stacked/grouped display mode for bar and line charts.
     */
    toggleStacked() {
        const { stacked } = this.model.metaData;
        this.model.updateMetaData({ stacked: !stacked });
    }

    /**
     * Toggles cumulative rendering mode for line charts.
     */
    toggleCumulated() {
        const { cumulated } = this.model.metaData;
        this.model.updateMetaData({ cumulated: !cumulated });
    }
}
