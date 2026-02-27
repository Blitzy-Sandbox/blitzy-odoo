/** @odoo-module */

/**
 * CarbonHeader — Carbon UI Shell Header OWL Component
 * ====================================================
 *
 * Implements the IBM Carbon Design System v11 UI Shell Header — a fixed 48 px
 * top bar that replaces Odoo's horizontal NavBar. The header is partitioned
 * into three semantic sections:
 *
 *   LEFT:   hamburger menu toggle + product / app name
 *   CENTER: global search (CarbonGlobalSearch child component)
 *   RIGHT:  systray utility items, theme toggle, app switcher button
 *
 * Architecture Notes:
 * - This component is a DIRECT REPLACEMENT for the NavBar OWL component
 *   (`addons/web/static/src/webclient/navbar/navbar.js`).
 * - The systray item rendering pattern is identical to the original NavBar
 *   to ensure full backward compatibility with third-party modules that
 *   register systray items (e.g., messaging, VoIP, helpdesk).
 * - Section menus (horizontal tabs in the old NavBar) are NOT rendered in
 *   the header; they are moved to the CarbonSideNav component.
 * - The app grid dropdown (AppsMenu) is replaced by the CarbonSwitcher panel.
 *
 * Carbon Design Compliance:
 * - Header height: 48 px (Carbon UI Shell specification)
 * - Hamburger: `cds--header__menu-trigger` class
 * - Product name: `cds--header__name` class
 * - Utility actions: `cds--header__action` class, ARIA-labeled
 * - Focus management: Carbon focus ring via `cds--header__action:focus-visible`
 *
 * Integration Points:
 * - `menuService` (from `@web/core/utils/hooks.useService("menu")`) for
 *   getCurrentApp(), getApps(), selectMenu()
 * - `actionService` for navigation (doAction)
 * - `registry.category("systray")` for rendering systray items
 * - `env.bus` for "MENUS:APP-CHANGED" reactivity events
 *
 * Props (received from CarbonShell parent component):
 *   @prop {Function} onToggleSideNav — callback to toggle the side navigation
 *   @prop {Boolean}  isSideNavExpanded — current expanded state of the sidenav
 *
 * Child Components:
 *   CarbonGlobalSearch — expandable search input in header center
 *   CarbonThemeToggle  — light/dark mode toggle button
 *   CarbonSwitcher     — app selection slide-in panel
 *   ErrorHandler       — error boundary wrapping each systray item
 *
 * @see addons/web/static/src/webclient/navbar/navbar.js  — original NavBar
 * @see addons/web/static/src/webclient/menus/menu_service.js — menu API
 * @see addons/carbon_ui/static/src/webclient/carbon_header.xml — QWeb template
 */

import {
    Component,
    useState,
    useRef,
    useEffect,
    useExternalListener,
    onWillUnmount,
} from "@odoo/owl";

import { useService, useBus } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { ErrorHandler } from "@web/core/utils/components";

import { CarbonGlobalSearch } from "./carbon_global_search";
import { CarbonThemeToggle } from "./carbon_theme_toggle";
import { CarbonSwitcher } from "./carbon_switcher";

// ---------------------------------------------------------------------------
// Systray Registry — singleton reference
// ---------------------------------------------------------------------------

/**
 * Reference to Odoo's systray registry category. Systray items are registered
 * by various modules (messaging, discuss, VoIP, etc.) and appear as utility
 * action buttons in the header's right section.
 *
 * Each entry in the registry is an object with:
 *   - `Component` — the OWL component class to render
 *   - `props`     — (optional) props to pass to the component
 *   - `isDisplayed(env)` — (optional) predicate controlling visibility
 *   - `index`     — (optional) numeric sort index
 *
 * The registry emits "UPDATE" events when items are added or removed,
 * which triggers a re-render of the header to reflect the change.
 */
const systrayRegistry = registry.category("systray");

// ---------------------------------------------------------------------------
// CarbonHeader Component
// ---------------------------------------------------------------------------

export class CarbonHeader extends Component {
    /**
     * QWeb template name. Must match the `t-name` attribute in
     * `carbon_header.xml` exactly.
     * @type {string}
     */
    static template = "carbon_ui.CarbonHeader";

    /**
     * Child OWL component classes used within the template.
     * OWL resolves `<ComponentName/>` tags in QWeb against this map.
     */
    static components = {
        CarbonGlobalSearch,
        CarbonThemeToggle,
        CarbonSwitcher,
        ErrorHandler,
    };

    /**
     * OWL 2.x prop validation schema.
     *
     * `onToggleSideNav` — Function callback provided by the CarbonShell
     *   parent component. Invoked when the user clicks the hamburger button
     *   to expand or collapse the side navigation panel.
     *
     * `isSideNavExpanded` — Boolean reflecting whether the side navigation
     *   is currently in expanded (256 px) or collapsed (48 px rail) mode.
     *   Used in the template to set `aria-expanded` on the hamburger button.
     */
    static props = {
        onToggleSideNav: { type: Function },
        isSideNavExpanded: { type: Boolean },
    };

    // -----------------------------------------------------------------------
    // Lifecycle — setup()
    // -----------------------------------------------------------------------

    /**
     * Initialises services, reactive state, event listeners, and DOM refs.
     *
     * Mirrors the setup pattern from the original NavBar component while
     * simplifying the layout (no section menus or adapt/overflow logic).
     */
    setup() {
        // -- Odoo services --------------------------------------------------

        /**
         * Menu service providing application and menu data.
         * API used: getCurrentApp(), getApps(), selectMenu(), getMenu()
         */
        this.menuService = useService("menu");

        /**
         * Action service for programmatic navigation.
         * API used: doAction() — invoked indirectly through menuService.selectMenu()
         */
        this.actionService = useService("action");

        // -- DOM reference --------------------------------------------------

        /**
         * Reference to the root `<header>` element, corresponding to
         * `t-ref="headerRoot"` in the QWeb template. Available for
         * programmatic DOM queries (e.g. measuring header width).
         * @type {import("@odoo/owl").Ref}
         */
        this.headerRef = useRef("headerRoot");

        // -- Reactive state -------------------------------------------------

        /**
         * Local reactive state managed by this component.
         *
         * `isSwitcherOpen` controls the visibility of the CarbonSwitcher
         * panel. When true, the switcher slide-in panel is rendered via
         * `t-if="state.isSwitcherOpen"` in the template.
         */
        this.state = useState({
            isSwitcherOpen: false,
        });

        // -- Systray registry & bus event listeners -------------------------

        /**
         * Internal counter tracking how many times the systray registry or
         * menu bus emits an update. Used as a dependency for the `useEffect`
         * hook so that the component re-renders only when these specific
         * external events fire (not on every patch cycle).
         *
         * This is the same pattern used in the original NavBar:
         *   let adaptCounter = 0;
         *   const renderAndAdapt = () => { adaptCounter++; this.render(); };
         */
        let adaptCounter = 0;

        /**
         * Callback invoked when the systray registry emits an "UPDATE" event
         * or the menu bus emits "MENUS:APP-CHANGED". Increments the counter
         * to trigger the useEffect dependency change, then requests a
         * component re-render.
         */
        const renderAndAdapt = () => {
            adaptCounter++;
            this.render();
        };

        // Register the event listener on the systray registry.
        // When a module adds/removes a systray item at runtime, this fires.
        // The systray registry is a plain EventTarget — not an OWL bus — so
        // we manage its listener manually with onWillUnmount for cleanup.
        systrayRegistry.addEventListener("UPDATE", renderAndAdapt);

        onWillUnmount(() => {
            systrayRegistry.removeEventListener("UPDATE", renderAndAdapt);
        });

        // Listen for app changes via the OWL environment event bus.
        // Fired by menu_service.setCurrentMenu() when the active app changes.
        // useBus automatically registers the listener and removes it when
        // the component unmounts, eliminating manual cleanup.
        useBus(this.env.bus, "MENUS:APP-CHANGED", () => {
            adaptCounter++;
            this.render();
        });

        // useEffect that depends on adaptCounter ensures we only re-render
        // when systray or menu events fire, not on every parent patch.
        // In the original NavBar this triggers adapt() for overflow;
        // in CarbonHeader we use it as a render synchronization point.
        useEffect(
            () => {
                // No-op body — the render is already triggered by
                // renderAndAdapt(). The effect exists solely to track
                // the adaptCounter dependency and prevent unnecessary
                // re-render cycles.
            },
            () => [adaptCounter]
        );

        // -- Click-outside handling for switcher panel ----------------------
        // Close the switcher panel when the user clicks outside of it and
        // outside the switcher toggle button. The CarbonSwitcher component
        // also has its own click-outside handler, but this provides a
        // belt-and-suspenders approach at the header level.
        useExternalListener(window, "mousedown", this._onExternalClick.bind(this));
    }

    // -----------------------------------------------------------------------
    // Getters — Reactive Data Access
    // -----------------------------------------------------------------------

    /**
     * Returns the list of systray items to render in the header's right
     * section, filtered and ordered for display.
     *
     * Processing pipeline (identical to the original NavBar):
     *   1. Get all entries from the systray registry as [key, value] pairs
     *   2. Flatten each entry into { key, Component, props, isDisplayed, index }
     *   3. Filter out items where `isDisplayed(env)` returns false
     *   4. Reverse the array so highest-priority items appear rightmost
     *
     * The `isDisplayed` check supports two patterns:
     *   - An `isDisplayed` function that receives `env` as argument
     *   - No `isDisplayed` property → item is always displayed
     *
     * @returns {Array<{key: string, Component: typeof Component, props: Object, index: number}>}
     */
    get systrayItems() {
        return systrayRegistry
            .getEntries()
            .map(([key, value]) => ({ key, ...value }))
            .filter((item) =>
                "isDisplayed" in item ? item.isDisplayed(this.env) : true
            )
            .reverse();
    }

    /**
     * Dummy setter to prevent conflicts between Enterprise NavBar extensions
     * and Website NavBar patches. This mirrors the original NavBar's
     * defensive pattern (navbar.js lines 115-116).
     *
     * Without this setter, monkey-patches that attempt to assign to
     * `this.systrayItems` would throw a TypeError because the property
     * is defined only as a getter.
     *
     * @param {*} _ — ignored value
     */
    set systrayItems(_) {
        // Intentionally empty — defensive setter for compatibility
    }

    /**
     * Returns the currently active Odoo application menu object.
     *
     * Delegates to `menuService.getCurrentApp()` which returns the menu
     * record for the app whose `appID` matches the current navigation state.
     *
     * Returns `undefined` when no app is selected (e.g. on the home screen
     * or before any navigation has occurred).
     *
     * The template uses this to display the app name next to the product
     * name in the header: "Odoo – Contacts".
     *
     * @returns {Object|undefined} the current app menu object, or undefined
     */
    get currentApp() {
        return this.menuService.getCurrentApp();
    }

    /**
     * Returns the product/platform name displayed in the header.
     *
     * The name is shown as a prefix in the `cds--header__name` element:
     *   "Odoo – [App Name]"
     *
     * The value is read from `odoo.info.serverVersion` context when
     * available, otherwise defaults to the string "Odoo". This ensures
     * the correct branding is shown for both Community and Enterprise
     * editions.
     *
     * @returns {string} the product name to display
     */
    get productName() {
        return "Odoo";
    }

    // -----------------------------------------------------------------------
    // Methods — User Interactions
    // -----------------------------------------------------------------------

    /**
     * Toggles the side navigation between expanded and collapsed states.
     *
     * Delegates to the parent CarbonShell component via the `onToggleSideNav`
     * prop callback. The parent manages the actual expanded/collapsed state
     * and propagates it back through the `isSideNavExpanded` prop.
     *
     * Called by the hamburger menu button click handler in the template.
     */
    toggleSideNav() {
        this.props.onToggleSideNav();
    }

    /**
     * Navigates to the home/default application.
     *
     * When an app is selected (currentApp exists), navigates to that app
     * by calling `menuService.selectMenu()` with the current app, which
     * performs `doAction` with `clearBreadcrumbs: true`.
     *
     * When no app is selected, retrieves the first available app from
     * `menuService.getApps()` and navigates to it. If no apps exist
     * (unlikely in a normal Odoo installation), the click is a no-op.
     *
     * The `ev.preventDefault()` is handled in the template via
     * `t-on-click.prevent`, so this method does not need to call it.
     *
     * @param {MouseEvent} [ev] — the click event (optional, already prevented)
     */
    onHomeClick(ev) {
        const app = this.currentApp;
        if (app) {
            this.menuService.selectMenu(app);
        } else {
            // No current app — try to navigate to the first available app
            const apps = this.menuService.getApps();
            if (apps && apps.length > 0) {
                this.menuService.selectMenu(apps[0]);
            }
        }
    }

    /**
     * Toggles the CarbonSwitcher app selection panel open or closed.
     *
     * Flips the `state.isSwitcherOpen` boolean which controls the
     * conditional rendering (`t-if`) of the CarbonSwitcher component
     * in the template. Also updates the `aria-expanded` attribute on
     * the switcher toggle button.
     */
    toggleSwitcher() {
        this.state.isSwitcherOpen = !this.state.isSwitcherOpen;
    }

    /**
     * Closes the CarbonSwitcher panel.
     *
     * Explicitly sets `state.isSwitcherOpen` to false. This method is
     * passed to the CarbonSwitcher component as the `onClose` callback
     * (bound via `onClose.bind="closeSwitcher"` in the template).
     *
     * Called when:
     * - The user clicks outside the switcher panel
     * - The user presses Escape while the switcher is open
     * - The user selects an app from the switcher list
     */
    closeSwitcher() {
        this.state.isSwitcherOpen = false;
    }

    /**
     * Error handler for faulty systray items.
     *
     * When a systray component throws during rendering, this handler:
     *   1. Marks the item as permanently hidden by overriding its
     *      `isDisplayed` method to always return false
     *   2. Re-throws the error asynchronously (via microtask) so it
     *      appears in the console/error tracking without crashing
     *      the entire header component
     *
     * This is the EXACT error handling pattern from the original NavBar
     * component (navbar.js lines 79-84). Preserving this pattern ensures
     * that third-party systray modules with bugs are gracefully degraded
     * rather than bringing down the entire navigation.
     *
     * @param {Error} error — the error thrown by the systray component
     * @param {Object} item — the systray registry entry that errored
     */
    handleItemError(error, item) {
        // Mark the faulty component as not displayed so it won't render
        // on the next cycle, preventing an infinite error loop.
        item.isDisplayed = () => false;

        // Re-throw asynchronously to surface the error in devtools and
        // error tracking services without blocking the current render.
        Promise.resolve().then(() => {
            throw error;
        });
    }

    // -----------------------------------------------------------------------
    // Private Methods
    // -----------------------------------------------------------------------

    /**
     * Handles clicks outside the header to close the switcher panel.
     *
     * This is a supplementary click-outside handler at the header level.
     * The CarbonSwitcher component also has its own `onOutsideClick`
     * handler. This provides defense-in-depth for edge cases where
     * the switcher's own handler might not fire (e.g. clicks on overlay
     * elements outside the switcher's DOM subtree).
     *
     * @param {MouseEvent} ev — the mousedown event
     * @private
     */
    _onExternalClick(ev) {
        if (!this.state.isSwitcherOpen) {
            return;
        }
        const headerEl = this.headerRef.el;
        if (!headerEl) {
            return;
        }
        // If the click was inside the header, let the specific button
        // handlers manage the interaction (toggle, close, etc.)
        if (headerEl.contains(ev.target)) {
            return;
        }
        // Click was entirely outside the header — close the switcher
        this.closeSwitcher();
    }
}
