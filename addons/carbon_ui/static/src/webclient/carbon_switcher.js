/** @odoo-module */

/**
 * CarbonSwitcher — App Selector Panel OWL Component
 * ==================================================
 *
 * Replaces Odoo's grid-icon AppsMenu dropdown with a Carbon Design System v11
 * Switcher panel. The panel slides in from the right side of the header bar and
 * presents a vertically scrollable list of every installed Odoo application.
 *
 * Layout follows Carbon's UI Shell Switcher anatomy:
 *   - Fixed-position overlay panel anchored to the right of the header
 *   - Width: 256 px (matching the expanded SideNav width)
 *   - Background: `--cds-layer-01` token
 *   - Items styled as `cds--switcher__item` with hover / focus / selected states
 *
 * Data Source:
 *   Uses `menuService.getApps()` to retrieve the same application list consumed
 *   by the original `AppsMenu` component in `addons/web/static/src/webclient/
 *   navbar/navbar.js`. Each app object carries `id`, `name`, `xmlid`,
 *   `actionID`, `actionPath`, `webIconData`, and `webIcon` fields.
 *
 * Navigation:
 *   `menuService.selectMenu(app)` executes the app's default action with
 *   `clearBreadcrumbs: true`, which is the identical navigation path used by
 *   the original NavBar (`onNavBarDropdownItemSelection`).
 *
 * Keyboard Accessibility (WCAG 2.1 AA):
 *   - Escape     → closes the panel and returns focus to the toggle button
 *   - ArrowDown  → moves focus to the next app item (wraps around)
 *   - ArrowUp    → moves focus to the previous app item (wraps around)
 *   - Enter      → activates the currently focused app
 *   - Home       → moves focus to the first app
 *   - End        → moves focus to the last app
 *   - Tab        → trapped within the panel while open
 *
 * Click-Outside:
 *   `useExternalListener` on `window` detects clicks outside the panel element
 *   and triggers the `onClose` callback to dismiss the panel. Clicks on the
 *   header's switcher toggle button are excluded to avoid double-toggle.
 *
 * Props (received from CarbonHeader):
 *   @prop {Boolean} isOpen   — whether the panel is currently visible
 *   @prop {Function} onClose — callback to request panel dismissal
 *
 * @see addons/web/static/src/webclient/navbar/navbar.js   — original app menu
 * @see addons/web/static/src/webclient/menus/menu_service.js — menu API
 * @see addons/carbon_ui/static/src/webclient/carbon_header.xml — parent usage
 */

import { Component, useState, useRef, useExternalListener } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class CarbonSwitcher extends Component {
    static template = "carbon_ui.CarbonSwitcher";

    /**
     * OWL 2.x prop validation.
     *
     * `isOpen`  — Boolean flag mirroring the parent CarbonHeader's
     *             `state.isSwitcherOpen`. The component is typically only
     *             mounted when `isOpen` is true (via `t-if` in the parent
     *             template), so this prop acts as an additional safety guard.
     *
     * `onClose` — Callback that the panel invokes when it wants the parent
     *             to close it (click-outside, Escape key, app navigation).
     *             The `.bind` QWeb directive in the parent binds this to
     *             `CarbonHeader.closeSwitcher()`.
     */
    static props = {
        isOpen: { type: Boolean },
        onClose: { type: Function },
    };

    // ─────────────────────────────────────────────────────────────────────────
    //  Lifecycle
    // ─────────────────────────────────────────────────────────────────────────

    setup() {
        // ── Odoo services ────────────────────────────────────────────────
        // Menu service: getApps(), getCurrentApp(), selectMenu()
        this.menuService = useService("menu");
        // Action service: doAction() — used indirectly through menuService.selectMenu()
        this.actionService = useService("action");

        // ── DOM reference ────────────────────────────────────────────────
        // Reference to the root <aside> element of the switcher panel.
        // Used by onOutsideClick to determine if a click was inside or outside.
        this.switcherRef = useRef("switcherPanel");

        // ── Reactive state ───────────────────────────────────────────────
        // `focusedIndex` tracks which app item currently has keyboard focus.
        // A value of -1 means no item is focused (initial state).
        this.state = useState({
            focusedIndex: -1,
        });

        // ── External event listeners ─────────────────────────────────────
        // These listeners are automatically cleaned up when the component
        // unmounts (which happens when the parent's `t-if` removes it).
        useExternalListener(window, "click", this.onOutsideClick, { capture: true });
        useExternalListener(window, "keydown", this.onKeyDown);
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  Getters — App Data Access
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * Returns every installed Odoo application as a flat array.
     *
     * Delegates to `menuService.getApps()` which returns the children of the
     * root menu node. Each app object contains:
     *   - `id`          {Number}  — menu record ID
     *   - `name`        {String}  — human-readable display name
     *   - `xmlid`       {String}  — module-qualified XML ID
     *   - `actionID`    {Number}  — default ir.actions ID
     *   - `actionPath`  {String}  — client URL path segment
     *   - `webIconData` {String}  — base64 data-URI icon (if custom icon uploaded)
     *   - `webIcon`     {String}  — comma-separated "class,color,bg" fallback
     *   - `appID`       {Number}  — same as `id` for top-level apps
     *
     * @returns {Array<Object>} list of application menu objects
     */
    get apps() {
        return this.menuService.getApps();
    }

    /**
     * Returns the currently active Odoo application, or `undefined` if no app
     * is selected (e.g. on the home screen / app switcher initial state).
     *
     * Used to highlight the active app in the switcher list with the
     * `cds--switcher__item--selected` CSS class.
     *
     * @returns {Object|undefined} the current app menu object
     */
    get currentApp() {
        return this.menuService.getCurrentApp();
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  Methods — Navigation and URL computation
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * Computes the client-side URL for a given app/menu item.
     *
     * This mirrors the exact implementation in the original NavBar component
     * (`addons/web/static/src/webclient/navbar/navbar.js` line 210-212):
     *
     *     getMenuItemHref(payload) {
     *         return `/odoo/${payload.actionPath || "action-" + payload.actionID}`;
     *     }
     *
     * The URL is used as the `href` attribute on the anchor element wrapping
     * each app item, enabling right-click "Open in new tab" and progressive
     * enhancement for the `<a>` element.
     *
     * @param {Object} menu — app object with `actionPath` and/or `actionID`
     * @returns {String} absolute URL path (e.g. "/odoo/contacts" or "/odoo/action-123")
     */
    getMenuItemHref(menu) {
        if (!menu) {
            return "/odoo";
        }
        return `/odoo/${menu.actionPath || "action-" + menu.actionID}`;
    }

    /**
     * Handles selection of an app from the switcher panel.
     *
     * Delegates to `menuService.selectMenu(app)` which internally calls
     * `actionService.doAction(menu.actionID, { clearBreadcrumbs: true })`,
     * navigating the user to the app's default action and clearing the
     * breadcrumb trail.
     *
     * After navigation is triggered the panel is closed via `props.onClose()`.
     *
     * @param {Object} app — the selected app menu object
     */
    async onAppSelect(app) {
        if (!app || !app.actionID) {
            return;
        }
        await this.menuService.selectMenu(app);
        this.state.focusedIndex = -1;
        if (this.props.onClose) {
            this.props.onClose();
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  Methods — Panel Management (close, outside click, keyboard)
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * Handles window-level click events to implement click-outside-to-close.
     *
     * The listener is registered with `{ capture: true }` so it fires before
     * the click reaches children. It compares the event target against the
     * panel's DOM element:
     *   - Click inside the panel → no action (the item's own handler fires)
     *   - Click on the header's switcher toggle → ignored (parent handles toggle)
     *   - Click anywhere else → close the panel
     *
     * @param {MouseEvent} ev — the captured click event
     */
    onOutsideClick(ev) {
        if (!this.props.isOpen) {
            return;
        }
        const panelEl = this.switcherRef.el;
        if (!panelEl) {
            return;
        }
        // Click was inside the switcher panel — do nothing
        if (panelEl.contains(ev.target)) {
            return;
        }
        // Click was on the header's switcher toggle button — let the parent
        // handle it to avoid a close-then-reopen race condition
        const toggleBtn = ev.target.closest(".cds--header__action--switcher");
        if (toggleBtn) {
            return;
        }
        if (this.props.onClose) {
            this.props.onClose();
        }
    }

    /**
     * Keyboard navigation handler for the switcher panel.
     *
     * Implements Carbon's keyboard interaction model for the Switcher:
     *   - Escape     → close panel, reset focus index
     *   - ArrowDown  → advance focus to next item (wraps to first)
     *   - ArrowUp    → move focus to previous item (wraps to last)
     *   - Enter      → select the focused app and navigate
     *   - Home       → jump focus to the first app item
     *   - End        → jump focus to the last app item
     *
     * @param {KeyboardEvent} ev — the keydown event
     */
    onKeyDown(ev) {
        if (!this.props.isOpen) {
            return;
        }
        const appsList = this.apps;
        const len = appsList.length;
        if (!len) {
            // No apps available — only handle Escape
            if (ev.key === "Escape") {
                ev.preventDefault();
                ev.stopPropagation();
                if (this.props.onClose) {
                    this.props.onClose();
                }
            }
            return;
        }

        switch (ev.key) {
            case "Escape":
                ev.preventDefault();
                ev.stopPropagation();
                this.state.focusedIndex = -1;
                if (this.props.onClose) {
                    this.props.onClose();
                }
                // Return focus to the toggle button in the header
                this._focusToggleButton();
                break;

            case "ArrowDown":
                ev.preventDefault();
                ev.stopPropagation();
                this.state.focusedIndex =
                    this.state.focusedIndex < len - 1
                        ? this.state.focusedIndex + 1
                        : 0;
                this._scrollFocusedIntoView();
                break;

            case "ArrowUp":
                ev.preventDefault();
                ev.stopPropagation();
                this.state.focusedIndex =
                    this.state.focusedIndex <= 0
                        ? len - 1
                        : this.state.focusedIndex - 1;
                this._scrollFocusedIntoView();
                break;

            case "Enter":
                ev.preventDefault();
                ev.stopPropagation();
                if (
                    this.state.focusedIndex >= 0 &&
                    this.state.focusedIndex < len
                ) {
                    this.onAppSelect(appsList[this.state.focusedIndex]);
                }
                break;

            case "Home":
                ev.preventDefault();
                ev.stopPropagation();
                this.state.focusedIndex = 0;
                this._scrollFocusedIntoView();
                break;

            case "End":
                ev.preventDefault();
                ev.stopPropagation();
                this.state.focusedIndex = len - 1;
                this._scrollFocusedIntoView();
                break;

            case "Tab":
                // Trap focus within the panel while it is open.
                // Allow Tab to cycle between items without leaving the panel.
                ev.preventDefault();
                ev.stopPropagation();
                if (ev.shiftKey) {
                    // Shift+Tab → move focus backward
                    this.state.focusedIndex =
                        this.state.focusedIndex <= 0
                            ? len - 1
                            : this.state.focusedIndex - 1;
                } else {
                    // Tab → move focus forward
                    this.state.focusedIndex =
                        this.state.focusedIndex < len - 1
                            ? this.state.focusedIndex + 1
                            : 0;
                }
                this._scrollFocusedIntoView();
                break;

            default:
                // No-op for other keys
                break;
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    //  Internal Helpers
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * Scrolls the currently focused app item into the visible area of the
     * switcher panel. Uses `scrollIntoView({ block: "nearest" })` to minimise
     * disruptive scrolling — only scrolls if the item is outside the viewport
     * of the panel's scrollable area.
     *
     * The focused item is located via a `data-switcher-index` attribute that
     * the QWeb template sets on each `cds--switcher__item` element.
     *
     * @private
     */
    _scrollFocusedIntoView() {
        const panelEl = this.switcherRef.el;
        if (!panelEl) {
            return;
        }
        // Allow the DOM to update before querying
        requestAnimationFrame(() => {
            const focusedEl = panelEl.querySelector(
                `[data-switcher-index="${this.state.focusedIndex}"]`
            );
            if (focusedEl) {
                focusedEl.scrollIntoView({ block: "nearest", behavior: "smooth" });
                focusedEl.focus({ preventScroll: true });
            }
        });
    }

    /**
     * Returns focus to the app switcher toggle button in the Carbon Header.
     * Called after the panel is closed via Escape to provide a logical focus
     * return target.
     *
     * @private
     */
    _focusToggleButton() {
        requestAnimationFrame(() => {
            const toggleBtn = document.querySelector(
                ".cds--header__action--switcher"
            );
            if (toggleBtn) {
                toggleBtn.focus();
            }
        });
    }
}
