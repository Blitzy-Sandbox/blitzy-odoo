/** @odoo-module */

/**
 * CarbonShell — Root Carbon UI Shell OWL Component
 * =================================================
 *
 * Wraps the entire Odoo webclient in the IBM Carbon Design System v11
 * UI Shell layout pattern: a fixed 48 px header at the top, a collapsible
 * side-navigation rail on the left, and a scrollable main content area
 * on the right.
 *
 * Architecture:
 *   This component is rendered as a child of the original `WebClient`
 *   component via an OWL template override (see carbon_shell.xml for the
 *   template, and the `web.WebClient` template extension handled by a
 *   separate XML file loaded in the `web.assets_backend` bundle).
 *
 *   WebClient retains all of its original responsibilities:
 *     - URL routing (loadRouterState)
 *     - Default app loading (_loadDefaultApp)
 *     - Global click handling (onGlobalClick)
 *     - Service worker registration
 *     - WEB_CLIENT_READY event emission
 *     - Debug menu registration
 *
 *   CarbonShell adds ONLY layout management:
 *     - Header rendering (CarbonHeader child)
 *     - Side navigation rendering (CarbonSideNav child)
 *     - Fullscreen mode detection (hiding header + sidenav)
 *     - Side-nav expanded / rail / mobile overlay state
 *     - Responsive breakpoint handling (Carbon grid breakpoints)
 *     - Persistent user preference for side-nav state (localStorage)
 *
 * Child Components:
 *   CarbonHeader            — Fixed 48 px header with hamburger toggle,
 *                              product name, global search, systray, theme
 *                              toggle, and app switcher button
 *   CarbonSideNav           — Left navigation rail with app/section menus
 *   ActionContainer         — Odoo's action/view renderer (preserved)
 *   MainComponentsContainer — Dialogs, notifications, overlays (preserved)
 *
 * Responsive Behavior (Carbon 2x Grid breakpoints):
 *   sm  (< 672 px)  — Side-nav fully hidden; hamburger shows overlay
 *   md  (672–1055 px) — Side-nav collapsed to 48 px rail
 *   lg  (≥ 1056 px) — Side-nav respects saved preference (default: expanded)
 *
 * Accessibility (WCAG 2.1 AA):
 *   Skip-to-content link as the first focusable element
 *   ARIA landmarks: banner (header), navigation (sidenav), main (content)
 *   Focus management for mobile overlay open/close
 *   Keyboard-accessible hamburger toggle
 *
 * Module Isolation:
 *   This file belongs to the carbon_ui addon module. Zero modifications
 *   to any file under addons/web/ or odoo/. When carbon_ui is uninstalled
 *   the original WebClient layout is fully restored.
 *
 * @see carbon_shell.xml       — QWeb template for this component
 * @see carbon_header.js       — CarbonHeader child component
 * @see carbon_sidenav.js      — CarbonSideNav child component
 * @see webclient.js (web)     — Original WebClient (preserved as parent)
 * @see webclient_templates.xml — Server-side QWeb inheritance
 */

// ---------------------------------------------------------------------------
// External Imports — @odoo/owl (OWL 2.8.1 reactive framework)
// ---------------------------------------------------------------------------

import {
    Component,
    useState,
    useRef,
    useExternalListener,
    onWillDestroy,
} from "@odoo/owl";

// ---------------------------------------------------------------------------
// Odoo Core Imports
// ---------------------------------------------------------------------------

import { useService, useBus } from "@web/core/utils/hooks";
import { debounce } from "@web/core/utils/timing";
import { browser } from "@web/core/browser/browser";
import { MainComponentsContainer } from "@web/core/main_components_container";
import { ActionContainer } from "@web/webclient/actions/action_container";

// ---------------------------------------------------------------------------
// Internal Module Imports — Carbon UI Shell children
// ---------------------------------------------------------------------------

import { CarbonHeader } from "./carbon_header";
import { CarbonSideNav } from "./carbon_sidenav";

// ---------------------------------------------------------------------------
// WebClient Integration — OWL component patching
// ---------------------------------------------------------------------------

import { WebClient } from "@web/webclient/webclient";
import { patch } from "@web/core/utils/patch";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/**
 * Carbon responsive grid breakpoints (px).
 *
 * These DIFFER from Bootstrap's defaults (576, 768, 992, 1200, 1400) and
 * are the canonical breakpoints from the Carbon Design System 2x Grid:
 *   sm  = 320 px   (4 columns,  16 px margin)
 *   md  = 672 px   (8 columns,  16 px margin)
 *   lg  = 1056 px  (16 columns, 16 px margin)
 *   xlg = 1312 px  (16 columns, 16 px margin)
 *   max = 1584 px  (16 columns, 24 px margin)
 *
 * For side-nav behaviour we primarily use md (672) and lg (1056):
 *   < 672  → mobile: sidenav hidden, hamburger shows overlay
 *   672–1055 → medium: sidenav defaults to rail (48 px)
 *   ≥ 1056 → large: sidenav follows user preference (expanded or rail)
 *
 * @see https://carbondesignsystem.com/elements/2x-grid/overview/
 * @type {number}
 */
const CARBON_BREAKPOINT_MD = 672;
const CARBON_BREAKPOINT_LG = 1056;

/**
 * localStorage key for persisting the user's side-nav expanded/collapsed
 * preference across page reloads and browser sessions.
 *
 * Stored as a string: "true" (expanded, 256 px) or "false" (rail, 48 px).
 * When the key is absent, the default behaviour is expanded.
 *
 * @type {string}
 */
const SIDENAV_STATE_KEY = "carbon_sidenav_expanded";

/**
 * Debounce delay (ms) for the window resize handler.
 *
 * Prevents excessive breakpoint recalculation during active window
 * resizing. 200 ms provides a responsive feel while avoiding layout
 * thrashing on rapid resize events (e.g., dragging a window edge).
 *
 * @type {number}
 */
const RESIZE_DEBOUNCE_MS = 200;

// ---------------------------------------------------------------------------
// CarbonShell Component
// ---------------------------------------------------------------------------

export class CarbonShell extends Component {
    /**
     * QWeb template name. Must match the `t-name` attribute in
     * `carbon_shell.xml` exactly.
     * @type {string}
     */
    static template = "carbon_ui.CarbonShell";

    /**
     * Child OWL component classes referenced in the QWeb template.
     * OWL resolves `<ComponentName/>` tags against this map.
     *
     * ActionContainer and MainComponentsContainer are passed through
     * from the original WebClient — CarbonShell simply wraps them in
     * the Carbon layout structure.
     */
    static components = {
        ActionContainer,
        MainComponentsContainer,
        CarbonHeader,
        CarbonSideNav,
    };

    /**
     * OWL 2.x prop validation schema.
     *
     * CarbonShell receives no props — it is self-contained and obtains
     * all data from services and its own reactive state. The parent
     * WebClient renders it as `<CarbonShell/>` without any attributes.
     */
    static props = {};

    // -----------------------------------------------------------------------
    // Lifecycle — setup()
    // -----------------------------------------------------------------------

    /**
     * Initialises services, reactive state, responsive behaviour, and
     * event listeners.
     *
     * Service integration mirrors the WebClient's own setup() to ensure
     * the same data is available for child components — menuService for
     * navigation, actionService for view loading, and title for the
     * browser tab title.
     *
     * CRITICAL: This method must NOT duplicate WebClient's routing,
     * service worker, or global click handling — those remain in the
     * original WebClient.setup().
     */
    setup() {
        // -- Odoo services --------------------------------------------------
        // Wire up the same services as the original WebClient so they are
        // available in the template scope and can be passed to children.

        /**
         * Menu service providing application and menu data.
         * API: getCurrentApp(), getApps(), selectMenu(), getMenu(),
         *      getMenuAsTree(), getAll(), setCurrentMenu(), reload()
         * @type {Object}
         */
        this.menuService = useService("menu");

        /**
         * Action service for programmatic view/action loading.
         * API: doAction(), loadState(), currentController
         * @type {Object}
         */
        this.actionService = useService("action");

        /**
         * Title service for setting the browser tab title.
         * Used by child components to update the page title when
         * navigating between views.
         * @type {Object}
         */
        this.title = useService("title");

        // -- DOM reference --------------------------------------------------

        /**
         * Reference to the root `<div class="cds--ui-shell">` element,
         * corresponding to `t-ref="shellRoot"` in the QWeb template.
         * Available for programmatic DOM queries and dimension calculations.
         * @type {import("@odoo/owl").Ref}
         */
        this.shellRef = useRef("shellRoot");

        // -- Reactive state -------------------------------------------------

        /**
         * Read the user's saved side-nav preference from localStorage.
         *
         * Default to expanded (true) when:
         *   - The key does not exist in localStorage
         *   - localStorage is unavailable (e.g., privacy mode)
         *   - The stored value is anything other than "false"
         *
         * The preference is only applied at the lg breakpoint (≥ 1056 px).
         * At smaller breakpoints, the sidenav state is overridden by
         * responsive rules in _applyBreakpoint().
         */
        let savedExpanded = true;
        try {
            const stored = browser.localStorage.getItem(SIDENAV_STATE_KEY);
            if (stored !== null) {
                savedExpanded = stored !== "false";
            }
        } catch {
            // localStorage unavailable — use default (expanded)
        }

        /**
         * Reactive state driving the Carbon Shell layout.
         *
         * @property {boolean} isSideNavExpanded
         *   true = side-nav expanded at 256 px with full text labels
         *   false = side-nav collapsed to 48 px rail (icons only)
         *   Persisted to localStorage for cross-session continuity.
         *
         * @property {boolean} isMobileSideNavOpen
         *   true = mobile overlay sidebar is visible (< md breakpoint)
         *   false = mobile sidebar is hidden
         *   Not persisted — always starts closed on page load.
         *
         * @property {boolean} isFullscreen
         *   true = fullscreen mode active (header and sidenav hidden)
         *   Triggered by ACTION_MANAGER:UI-UPDATED bus event when an
         *   action requests "fullscreen" mode (e.g., PoS, presentation).
         *   Mirrors the behaviour of WebClient.state.fullscreen.
         */
        this.state = useState({
            isSideNavExpanded: savedExpanded,
            isMobileSideNavOpen: false,
            isFullscreen: false,
        });

        // Apply initial responsive state based on current viewport width.
        // This ensures the sidenav starts in the correct mode even if the
        // saved preference says "expanded" but the viewport is narrow.
        this._applyBreakpoint(window.innerWidth);

        // -- Fullscreen mode detection --------------------------------------

        /**
         * Listen for the ACTION_MANAGER:UI-UPDATED bus event.
         *
         * This event is emitted by Odoo's action manager whenever the UI
         * mode changes. The `detail` property is one of:
         *   "current"    — normal inline view rendering
         *   "fullscreen" — action requests maximum viewport (e.g., PoS)
         *   "new"        — new action stacked on top (ignored)
         *
         * When fullscreen mode activates, the header and sidenav are
         * hidden (via `t-if="!state.isFullscreen"` in the template) to
         * give the action the entire viewport. This mirrors the original
         * WebClient behaviour where NavBar is hidden during fullscreen.
         *
         * The "new" mode is explicitly ignored (following WebClient's
         * pattern) to prevent briefly hiding the shell when stacking
         * actions (e.g., opening a form from a list view).
         */
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", ({ detail: mode }) => {
            if (mode !== "new") {
                this.state.isFullscreen = mode === "fullscreen";
            }
        });

        // -- Responsive resize handling -------------------------------------

        /**
         * Debounced window resize handler.
         *
         * Re-evaluates the current viewport width against Carbon's
         * responsive breakpoints and adjusts the sidenav state
         * accordingly. The debounce prevents layout thrashing during
         * rapid resize events.
         *
         * Cleanup: The debounce timer is cancelled in onWillDestroy to
         * prevent stale callbacks firing after the component is removed
         * from the DOM. This follows the pattern from Odoo's NavBar:
         *   const debouncedAdapt = debounce(this.adapt.bind(this), 250);
         *   onWillDestroy(() => debouncedAdapt.cancel());
         */
        const debouncedResize = debounce(this.onResize.bind(this), RESIZE_DEBOUNCE_MS);
        useExternalListener(window, "resize", debouncedResize);
        onWillDestroy(() => debouncedResize.cancel());
    }

    // -----------------------------------------------------------------------
    // Public Methods
    // -----------------------------------------------------------------------

    /**
     * Toggles the side navigation between expanded and collapsed states.
     *
     * Behaviour varies by viewport size:
     *
     *   Mobile (< 672 px):
     *     Toggles the mobile overlay sidebar on/off. Does NOT change the
     *     `isSideNavExpanded` preference because mobile always defaults
     *     to hidden on page load regardless of the stored preference.
     *     When opening: focus moves to sidenav (handled by CarbonSideNav).
     *     When closing: focus returns to hamburger (handled by CarbonHeader).
     *
     *   Tablet/Desktop (≥ 672 px):
     *     Toggles between expanded (256 px) and rail (48 px) modes.
     *     Persists the new state to localStorage so it survives page
     *     reloads and is restored at the lg breakpoint on next visit.
     *
     * This method is called by:
     *   - CarbonHeader's hamburger button (via `onToggleSideNav` prop)
     *   - CarbonSideNav's close button on mobile (via `onToggle` prop)
     *   - Keyboard shortcut handlers (if implemented in children)
     */
    toggleSideNav() {
        const width = window.innerWidth;

        if (width < CARBON_BREAKPOINT_MD) {
            // -- Mobile: toggle overlay sidebar --
            this.state.isMobileSideNavOpen = !this.state.isMobileSideNavOpen;
        } else {
            // -- Desktop/Tablet: toggle expanded ↔ rail --
            this.state.isSideNavExpanded = !this.state.isSideNavExpanded;

            // Persist preference to localStorage for cross-session continuity
            this._persistSideNavState(this.state.isSideNavExpanded);
        }
    }

    /**
     * Handles window resize events by recalculating the appropriate
     * side-nav state for the current viewport width.
     *
     * Called by the debounced resize listener set up in setup().
     * The debounce (200 ms) ensures this runs at most 5 times per second
     * during active resizing, preventing layout thrashing.
     *
     * Carbon responsive breakpoints are used instead of Bootstrap's:
     *   md = 672 px (Bootstrap: 768 px)
     *   lg = 1056 px (Bootstrap: 992 px)
     *
     * This is a public method to satisfy the exports schema requirement
     * (members_exposed: "onResize()") and to allow programmatic
     * breakpoint recalculation from parent or sibling components.
     */
    onResize() {
        this._applyBreakpoint(window.innerWidth);
    }

    // -----------------------------------------------------------------------
    // Private Methods
    // -----------------------------------------------------------------------

    /**
     * Applies the correct side-nav state for a given viewport width.
     *
     * Three breakpoint zones exist:
     *
     *   1. Small (width < 672 px — below Carbon md):
     *      Side-nav is completely hidden. Mobile overlay is closed.
     *      The user must explicitly tap the hamburger to open the overlay.
     *      This provides maximum content area on small screens.
     *
     *   2. Medium (672 px ≤ width < 1056 px — between md and lg):
     *      Side-nav defaults to rail mode (48 px, icons only).
     *      Mobile overlay is closed (not applicable at this width).
     *      The user can hover the rail to temporarily expand it
     *      (handled by CarbonSideNav's hover-expand behaviour).
     *
     *   3. Large (width ≥ 1056 px — at or above Carbon lg):
     *      Side-nav respects the user's saved preference from localStorage.
     *      If no preference is saved, defaults to expanded (256 px).
     *      Mobile overlay is closed (not applicable at this width).
     *
     * @param {number} width — Current viewport width in CSS pixels
     * @private
     */
    _applyBreakpoint(width) {
        if (width < CARBON_BREAKPOINT_MD) {
            // Small viewport: collapse everything, hide overlay
            this.state.isSideNavExpanded = false;
            this.state.isMobileSideNavOpen = false;
        } else if (width < CARBON_BREAKPOINT_LG) {
            // Medium viewport: default to rail mode
            this.state.isSideNavExpanded = false;
            this.state.isMobileSideNavOpen = false;
        } else {
            // Large viewport: restore user preference
            let savedExpanded = true;
            try {
                const stored = browser.localStorage.getItem(SIDENAV_STATE_KEY);
                if (stored !== null) {
                    savedExpanded = stored !== "false";
                }
            } catch {
                // localStorage unavailable — default to expanded
            }
            this.state.isSideNavExpanded = savedExpanded;
            this.state.isMobileSideNavOpen = false;
        }
    }

    /**
     * Persists the side-nav expanded/collapsed state to localStorage.
     *
     * Wrapped in a try-catch because localStorage may be unavailable in
     * privacy modes, iframe sandboxes, or storage-full conditions. In
     * such cases the preference is silently lost — the default (expanded)
     * will be used on next page load, which is a safe degradation.
     *
     * @param {boolean} isExpanded — Whether the side-nav is expanded
     * @private
     */
    _persistSideNavState(isExpanded) {
        try {
            browser.localStorage.setItem(SIDENAV_STATE_KEY, String(isExpanded));
        } catch {
            // Silently ignore storage failures — preference is non-critical
        }
    }
}

// ---------------------------------------------------------------------------
// WebClient Integration — Register CarbonShell as a child component
// ---------------------------------------------------------------------------

/**
 * Patch the WebClient class to include CarbonShell in its static
 * components map. This is necessary because the OWL template override
 * for `web.WebClient` (defined in a separate XML file loaded via
 * `web.assets_backend`) replaces the original `<NavBar/> +
 * <ActionContainer/> + <MainComponentsContainer/>` rendering with a
 * single `<CarbonShell/>` tag.
 *
 * OWL resolves `<CarbonShell/>` in a template by looking up the name
 * in the component's `static components` map. Without this registration
 * OWL would throw: "Cannot find the definition of component 'CarbonShell'".
 *
 * The patch approach is used instead of modifying any file in addons/web/
 * to maintain the Module Isolation Rule: zero core modifications.
 *
 * When the carbon_ui module is uninstalled:
 *   1. This JS file is removed from the asset bundle
 *   2. The patch is no longer applied
 *   3. The template override is also removed (XML file gone)
 *   4. WebClient renders its original template with NavBar as before
 *   ➜ Full backward compatibility preserved
 */
patch(WebClient.prototype, {
    setup() {
        super.setup(...arguments);
        // No additional setup needed — CarbonShell manages its own state.
        // This patch hook exists solely to ensure the prototype chain is
        // correct for any future patches that may need to call super.
    },
});

// Register CarbonShell as a recognized child component of WebClient.
// This is a static property assignment, not a prototype patch, because
// OWL resolves component names from the class's static `components` map.
WebClient.components = Object.assign({}, WebClient.components, {
    CarbonShell,
});
