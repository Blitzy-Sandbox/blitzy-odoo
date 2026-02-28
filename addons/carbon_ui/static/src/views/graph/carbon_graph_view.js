/** @odoo-module */

/**
 * Carbon Graph View Registration
 *
 * Registers the Carbon Charts-based graph view in Odoo's view registry,
 * overriding the default Chart.js "graph" entry. When the carbon_ui module
 * is installed, all <graph> view definitions automatically render with
 * Carbon Charts (D3.js-based) instead of Chart.js.
 *
 * Only the Renderer is replaced — Controller, Model, ArchParser, SearchModel,
 * and buttonTemplate are all reused from the original @web/views/graph/ module,
 * preserving full data-fetching, search, and interaction compatibility.
 */

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { GraphArchParser } from "@web/views/graph/graph_arch_parser";
import { GraphModel } from "@web/views/graph/graph_model";
import { GraphController } from "@web/views/graph/graph_controller";
import { GraphSearchModel } from "@web/views/graph/graph_search_model";
import { CarbonGraphRenderer } from "./carbon_graph_renderer";

const viewRegistry = registry.category("views");

/**
 * Carbon-powered graph view definition.
 *
 * Mirrors the original graphView (addons/web/static/src/views/graph/graph_view.js)
 * with CarbonGraphRenderer substituted for GraphRenderer. All other properties
 * remain identical to ensure backward-compatible data handling and user interaction.
 *
 * @type {import("@web/views/view").ViewDefinition}
 */
export const carbonGraphView = {
    /** View type identifier — must be "graph" to handle <graph> arch definitions */
    type: "graph",

    /** Reused Odoo graph controller (Layout, SearchBar, CogMenu, action hooks) */
    Controller: GraphController,

    /** Carbon Charts OWL renderer replacing the default Chart.js GraphRenderer */
    Renderer: CarbonGraphRenderer,

    /** Reused Odoo graph data model (read_group fetching, dataset preparation) */
    Model: GraphModel,

    /** Reused Odoo graph arch XML parser (mode, measure, groupBy, stacked, etc.) */
    ArchParser: GraphArchParser,

    /** Reused graph-specific search model (favorite and group-by handling) */
    SearchModel: GraphSearchModel,

    /** Search menu types available in the graph view search bar */
    searchMenuTypes: ["filter", "groupBy", "favorite"],

    /** Reused button template for measure selector, mode toggles, and order controls */
    buttonTemplate: "web.GraphView.Buttons",

    /**
     * Transforms generic view props into graph-specific props consumed by the
     * Controller and Renderer. Parses the arch definition to extract graph
     * configuration (mode, measure, groupBy, stacked, cumulated, order, title)
     * and assembles modelParams for the GraphModel.
     *
     * Logic is identical to the original graph_view.js props function to ensure
     * CarbonGraphRenderer receives the exact same data contract.
     *
     * @param {Object} genericProps - Standard view props (arch, fields, resModel, state)
     * @param {Object} view - The view definition object (provides ArchParser, Model, etc.)
     * @returns {Object} Assembled props with modelParams, Model, Renderer, buttonTemplate
     */
    props: (genericProps, view) => {
        let modelParams;
        if (genericProps.state) {
            modelParams = genericProps.state.metaData;
        } else {
            const { arch, fields, resModel } = genericProps;
            const parser = new view.ArchParser();
            const archInfo = parser.parse(arch, fields);
            modelParams = {
                disableLinking: Boolean(archInfo.disableLinking),
                fieldAttrs: archInfo.fieldAttrs,
                fields: fields,
                groupBy: archInfo.groupBy,
                measure: archInfo.measure || "__count",
                viewMeasures: archInfo.measures,
                mode: archInfo.mode || "bar",
                order: archInfo.order || null,
                resModel: resModel,
                stacked: "stacked" in archInfo ? archInfo.stacked : true,
                cumulated: archInfo.cumulated || false,
                cumulatedStart: archInfo.cumulatedStart || false,
                title: archInfo.title || _t("Untitled"),
            };
        }

        return {
            ...genericProps,
            modelParams,
            Model: view.Model,
            Renderer: view.Renderer,
            buttonTemplate: view.buttonTemplate,
        };
    },
};

/**
 * Register under the "graph" key to override the default Chart.js-based graph
 * view. Since Odoo loads module assets in dependency order and carbon_ui depends
 * on web, this registration executes after the original graph_view.js, effectively
 * replacing it with the Carbon Charts-based renderer.
 */
viewRegistry.add("graph", carbonGraphView, { force: true });
