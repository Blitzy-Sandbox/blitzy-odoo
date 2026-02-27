/** @odoo-module */

/**
 * CarbonSideNav — Carbon Design System v11 Side Navigation OWL Component
 * ======================================================================
 *
 * Implements the Carbon UI Shell left-side navigation rail that replaces
 * Odoo's horizontal NavBar sections menu and mobile hamburger sidebar.
 *
 * Architecture:
 *   Consumes Odoo's menu_service for app and section menu data.
 *   Renders top-level apps as SideNavLink items (icon + label).
 *   Renders section menus as collapsible SideNavMenu groups.
 *   Three responsive states controlled by parent CarbonShell:
 *     Expanded  (256 px) — full text labels visible
 *     Rail      (48 px)  — icons only, temporarily expands on hover
 *     Mobile    (overlay) — full overlay sidebar with backdrop
 *
 * Props (from CarbonShell):
 *   isExpanded   {Boolean}  — true = full width; false = rail
 *   isMobileOpen {Boolean}  — true = mobile overlay visible
 *   onToggle     {Function} — callback to toggle expand / collapse
 *
 * Accessibility (WCAG 2.1 AA):
 *   <nav> with aria-label for landmark identification
 *   aria-current="page" on active menu links
 *   aria-expanded on collapsible submenu triggers
 *   Full keyboard navigation (Tab, Arrow, Enter / Space, Escape)
 *   Focus management for mobile sidebar open / close
 *
 * @see carbon_sidenav.xml  — QWeb template
 * @see carbon_sidenav.scss — Carbon-token-based styles
 */

import {
    Component,
    useState,
    useRef,
    useExternalListener,
    useEffect,
    onWillDestroy,
    onWillUnmount,
} from "@odoo/owl";

import { useService, useBus } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/**
 * Minimum horizontal swipe distance (CSS px) required to trigger the mobile
 * sidebar close gesture.  Mirrors the value in Odoo's NavBar component.
 * @type {number}
 */
const SWIPE_ACTIVATION_THRESHOLD = 100;

/**
 * Debounce delay (ms) for hover-to-expand in rail mode.  Prevents flickering
 * when the cursor briefly passes over the rail during normal interaction.
 * @type {number}
 */
const HOVER_EXPAND_DELAY = 150;

/**
 * Registry category key used to allow third-party modules to register
 * additional items or callbacks into the Carbon SideNav panel.
 * Mirrors the systray pattern from NavBar (registry.category("systray")).
 * @type {string}
 */
const SIDENAV_REGISTRY_KEY = "carbon_sidenav_items";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export class CarbonSideNav extends Component {
    static template = "carbon_ui.CarbonSideNav";

    static props = {
        isExpanded: { type: Boolean },
        isMobileOpen: { type: Boolean },
        onToggle: { type: Function },
    };

    // ─── Setup ─────────────────────────────────────────────────────────

    setup() {
        // -- Service injection -----------------------------------------
        /** @type {import("@web/webclient/menus/menu_service").MenuService} */
        this.menuService = useService("menu");
        this.actionService = useService("action");

        // -- DOM reference for scroll management -----------------------
        this.sideNavRef = useRef("sideNav");

        // -- Registry access for extensibility -------------------------
        // Third-party modules can register extra items into this category
        // using registry.category("carbon_sidenav_items").add(...).
        this.sideNavRegistry = registry.category(SIDENAV_REGISTRY_KEY);

        // -- Reactive state -------------------------------------------
        this.state = useState({
            /** @type {Object<number, boolean>} Tracks submenu open states */
            expandedSubmenus: {},
            /** @type {boolean} Rail is temporarily expanded on hover */
            isHoverExpanded: false,
        });

        // -- Swipe tracking for mobile close gesture ------------------
        /** @type {number|null} */
        this.swipeStartX = null;

        // -- Hover-expand debounce timer reference --------------------
        /** @type {number|null} */
        this._hoverTimer = null;

        // -- Bus listener: re-render when active app changes ----------
        // Matches NavBar's this.env.bus.addEventListener("MENUS:APP-CHANGED")
        useBus(this.env.bus, "MENUS:APP-CHANGED", this._onAppChanged.bind(this));

        // -- Registry change listener (mirrors systray pattern) -------
        const _onRegistryUpdate = () => this.render();
        this.sideNavRegistry.addEventListener("UPDATE", _onRegistryUpdate);
        onWillUnmount(() => {
            this.sideNavRegistry.removeEventListener("UPDATE", _onRegistryUpdate);
        });

        // -- Auto-expand active section when current app changes ------
        useEffect(
            () => {
                this._autoExpandActiveSection();
            },
            () => [this.currentApp?.id]
        );

        // -- Keyboard handler for sidenav-specific shortcuts ----------
        useExternalListener(window, "keydown", this._onKeyDown.bind(this));

        // -- Clean up debounce timer on destroy -----------------------
        onWillDestroy(() => {
            if (this._hoverTimer !== null) {
                clearTimeout(this._hoverTimer);
                this._hoverTimer = null;
            }
        });
    }

    // ─── Getters ───────────────────────────────────────────────────────

    /**
     * Returns the currently active Odoo application menu item.
     *
     * Delegates directly to menuService.getCurrentApp(), which tracks
     * the active app via the MENUS:APP-CHANGED bus event and the
     * sessionStorage "menu_id" key.
     *
     * @returns {Object|undefined} The current app menu object, or undefined
     */
    get currentApp() {
        return this.menuService.getCurrentApp();
    }

    /**
     * Returns the section-level (child) menus for the currently active app.
     *
     * Each section may have its own childrenTree for nested sub-menus.
     * If no app is currently selected, returns an empty array so that the
     * template can safely iterate without null-checks.
     *
     * Mirrors NavBar's:
     *   this.menuService.getMenuAsTree(this.currentApp.id).childrenTree || []
     *
     * @returns {Array<Object>} Section menu items (may be empty)
     */
    get currentAppSections() {
        if (!this.currentApp) {
            return [];
        }
        const tree = this.menuService.getMenuAsTree(this.currentApp.id);
        return (tree && tree.childrenTree) || [];
    }

    /**
     * Whether the side-nav should appear visually expanded.
     * True when explicitly expanded by the parent OR when temporarily
     * expanded via hover in rail mode.
     *
     * @returns {boolean}
     */
    get isVisuallyExpanded() {
        return this.props.isExpanded || this.state.isHoverExpanded;
    }

    /**
     * Returns additional sidenav items registered by other modules via
     * the registry.category("carbon_sidenav_items") extension point.
     *
     * @returns {Array<Object>}
     */
    get extraItems() {
        return this.sideNavRegistry
            .getEntries()
            .map(([key, value]) => ({ key, ...value }))
            .filter((item) =>
                "isDisplayed" in item ? item.isDisplayed(this.env) : true
            );
    }

    /**
     * Returns the full list of installed Odoo applications from the
     * menu service.
     *
     * @returns {Array<Object>} Top-level app menu items
     */
    get apps() {
        return this.menuService.getApps();
    }

    // ─── Menu Item Interaction ─────────────────────────────────────────

    /**
     * Handles a click or keyboard activation on a menu item.
     *
     * Delegates navigation to the menu service's selectMenu, which calls
     * actionService.doAction with clearBreadcrumbs: true.  After
     * navigation, closes the mobile sidebar overlay if it was open.
     *
     * @param {Object} menu — Menu item object from menu_service
     */
    async onMenuClick(menu) {
        if (!menu) {
            return;
        }
        await this.menuService.selectMenu(menu);
        // On mobile, close the sidebar overlay after navigation
        if (this.props.isMobileOpen) {
            this.props.onToggle();
        }
    }

    /**
     * Computes the URL href for a menu item.  Used as the href attribute on
     * <a> elements so that ctrl+click / middle-click opens in a new tab.
     *
     * Mirrors the NavBar.getMenuItemHref pattern:
     *   `/odoo/${payload.actionPath || "action-" + payload.actionID}`
     *
     * @param {Object} menu — Menu item with actionPath or actionID
     * @returns {string} URL path for the menu action
     */
    getMenuItemHref(menu) {
        if (!menu) {
            return "#";
        }
        return `/odoo/${menu.actionPath || "action-" + menu.actionID}`;
    }

    /**
     * Determines whether a given menu item is currently active.
     *
     * For top-level apps:
     *   Checks if the menu is itself an app and its ID matches currentApp.id
     *
     * For section menus:
     *   Checks if the menu's appID matches the current app AND the menu's
     *   actionID matches the last loaded action (best-effort since
     *   menu_service only tracks appId, not the specific section).
     *
     * @param {Object} menu — Menu item to check
     * @returns {boolean} true if the menu is the active item
     */
    isMenuActive(menu) {
        if (!menu || !this.currentApp) {
            return false;
        }
        // Top-level app match: the menu IS an app root
        const isApp = menu.id === menu.appID;
        if (isApp) {
            return menu.appID === this.currentApp.id;
        }
        // Section-level match: same app + specific action match
        if (menu.appID === this.currentApp.id) {
            return this._isMenuInActivePath(menu);
        }
        return false;
    }

    // ─── Submenu Management ────────────────────────────────────────────

    /**
     * Toggles the expanded / collapsed state of a section's submenu.
     *
     * Implements accordion behaviour at the top level: expanding one
     * section collapses all siblings at the same nesting level to reduce
     * visual clutter in the navigation rail.
     *
     * @param {Object} section — Section menu item to toggle
     */
    toggleSubmenu(section) {
        if (!section) {
            return;
        }
        const sectionId = section.id;
        const isCurrentlyExpanded = !!this.state.expandedSubmenus[sectionId];

        if (!isCurrentlyExpanded) {
            // Accordion: collapse top-level siblings before expanding
            const siblings = this.currentAppSections;
            for (const sibling of siblings) {
                if (sibling.id !== sectionId && this.state.expandedSubmenus[sibling.id]) {
                    this.state.expandedSubmenus[sibling.id] = false;
                }
            }
        }
        this.state.expandedSubmenus[sectionId] = !isCurrentlyExpanded;
    }

    /**
     * Returns whether a section's submenu is currently expanded.
     *
     * @param {Object} section — Section menu item to check
     * @returns {boolean} true if the section's children are visible
     */
    isSubmenuExpanded(section) {
        if (!section) {
            return false;
        }
        return !!this.state.expandedSubmenus[section.id];
    }

    // ─── Hover-to-Expand (Rail Mode) ──────────────────────────────────

    /**
     * Handles mouse entering the sidenav in rail mode.
     * After a short debounce, temporarily expands to show full labels.
     */
    onMouseEnter() {
        if (this.props.isExpanded) {
            // Already fully expanded by parent — nothing to do
            return;
        }
        this._hoverTimer = setTimeout(() => {
            this.state.isHoverExpanded = true;
        }, HOVER_EXPAND_DELAY);
    }

    /**
     * Handles mouse leaving the sidenav in rail mode.
     * Cancels any pending hover expansion and collapses back to rail.
     */
    onMouseLeave() {
        if (this._hoverTimer !== null) {
            clearTimeout(this._hoverTimer);
            this._hoverTimer = null;
        }
        if (this.state.isHoverExpanded) {
            this.state.isHoverExpanded = false;
        }
    }

    // ─── Helper: App Icon Rendering ───────────────────────────────────

    /**
     * Retrieves the icon display data for an application menu item.
     *
     * Supports two icon modes from Odoo's menu data:
     *   1. webIconData — base64 data-URI image (most common)
     *   2. webIcon — comma-separated "iconClass,color,backgroundColor"
     *
     * Falls back to the default Odoo app icon if no icon data is provided.
     *
     * Pattern from menu_helpers.js computeAppsAndMenuItems.
     *
     * @param {Object} app — Application menu item
     * @returns {Object} { type: 'img'|'icon'|'fallback', src?, iconClass?, color?, backgroundColor? }
     */
    getAppIcon(app) {
        if (!app) {
            return { type: "fallback" };
        }
        if (app.webIconData) {
            return { type: "img", src: app.webIconData };
        }
        if (app.webIcon) {
            // webIcon can be a string "iconClass,color,bgColor" or already parsed
            const parts =
                typeof app.webIcon === "string"
                    ? app.webIcon.split(",")
                    : [
                          app.webIcon.iconClass || "",
                          app.webIcon.color || "",
                          app.webIcon.backgroundColor || "",
                      ];
            const [iconClass, color, backgroundColor] = parts;
            if (backgroundColor !== undefined && backgroundColor !== "") {
                return {
                    type: "icon",
                    iconClass: iconClass || "",
                    color: color || "",
                    backgroundColor: backgroundColor || "",
                };
            }
        }
        // Fallback: Odoo default app icon
        return { type: "img", src: "/web/static/img/default_icon_app.png" };
    }

    /**
     * Checks whether a section has nested children that should render as
     * a collapsible submenu group.
     *
     * @param {Object} section — Section menu item
     * @returns {boolean} true if the section has child menu items
     */
    hasChildren(section) {
        return !!(section && section.childrenTree && section.childrenTree.length > 0);
    }

    // ─── Mobile Sidebar Controls ──────────────────────────────────────

    /**
     * Closes the mobile overlay sidebar.
     */
    closeMobileSidebar() {
        if (this.props.isMobileOpen) {
            this.props.onToggle();
        }
    }

    /**
     * Handles the backdrop click to close the mobile sidebar.
     *
     * @param {MouseEvent} ev
     */
    onBackdropClick(ev) {
        ev.stopPropagation();
        this.closeMobileSidebar();
    }

    // ─── Private: Bus / Event Handlers ────────────────────────────────

    /**
     * Handles the MENUS:APP-CHANGED bus event.  Re-expands the appropriate
     * section submenu and triggers a re-render to reflect the new app state.
     * @private
     */
    _onAppChanged() {
        this._autoExpandActiveSection();
        this.render();
    }

    /**
     * Auto-expands the submenu section that contains the currently active
     * app's children.  Called on initial mount and whenever the active app
     * changes via the bus event.
     *
     * Strategy: expand the first section with children, giving the user
     * immediate visibility into the current app's sub-navigation.
     * @private
     */
    _autoExpandActiveSection() {
        const sections = this.currentAppSections;
        if (!sections || sections.length === 0) {
            // No sections — reset expanded state
            this.state.expandedSubmenus = {};
            return;
        }
        // Reset previous expansion state for a clean slate
        const newExpanded = {};
        // Expand the first section that has children
        for (const section of sections) {
            if (section.childrenTree && section.childrenTree.length > 0) {
                newExpanded[section.id] = true;
                break;
            }
        }
        this.state.expandedSubmenus = newExpanded;
    }

    /**
     * Determines if a menu item is in the "active path" — i.e. its action
     * matches the action currently displayed in the main content area.
     *
     * Since Odoo's menu_service only exposes currentAppId (not the specific
     * section), we compare the menu's actionID with the action service's
     * currently loaded action for a best-effort match.
     *
     * @param {Object} menu — Menu item to check
     * @returns {boolean}
     * @private
     */
    _isMenuInActivePath(menu) {
        if (!menu.actionID) {
            return false;
        }
        try {
            const currentController = this.actionService.currentController;
            if (currentController && currentController.action) {
                const currentActionId = currentController.action.id;
                if (currentActionId && menu.actionID === currentActionId) {
                    return true;
                }
                // Also check actionPath for string-based action references
                const currentActionPath = currentController.action.path;
                if (currentActionPath && menu.actionPath === currentActionPath) {
                    return true;
                }
            }
        } catch (_e) {
            // Silently ignore if action service doesn't expose currentController
            // This is a graceful degradation — the section simply won't highlight
        }
        return false;
    }

    /**
     * Handles touch-start for mobile swipe-to-close gesture.
     * Records the initial X coordinate for delta calculation.
     *
     * @param {TouchEvent} ev
     * @private
     */
    _onSwipeStart(ev) {
        if (!this.props.isMobileOpen) {
            return;
        }
        if (ev.changedTouches && ev.changedTouches.length > 0) {
            this.swipeStartX = ev.changedTouches[0].clientX;
        }
    }

    /**
     * Handles touch-end for mobile swipe-to-close gesture.
     * A leftward swipe exceeding SWIPE_ACTIVATION_THRESHOLD closes the
     * mobile sidebar, matching NavBar's existing behaviour.
     *
     * @param {TouchEvent} ev
     * @private
     */
    _onSwipeEnd(ev) {
        if (!this.props.isMobileOpen || this.swipeStartX === null) {
            return;
        }
        if (ev.changedTouches && ev.changedTouches.length > 0) {
            const deltaX = this.swipeStartX - ev.changedTouches[0].clientX;
            if (deltaX > SWIPE_ACTIVATION_THRESHOLD) {
                this.closeMobileSidebar();
            }
        }
        this.swipeStartX = null;
    }

    /**
     * Global keyboard event handler for sidenav-specific shortcuts.
     *
     * Escape:
     *   If mobile sidebar is open → close it
     *   Else if any submenu is expanded → collapse all
     *
     * @param {KeyboardEvent} ev
     * @private
     */
    _onKeyDown(ev) {
        if (ev.key !== "Escape") {
            return;
        }
        // Priority 1: close mobile sidebar
        if (this.props.isMobileOpen) {
            this.closeMobileSidebar();
            ev.preventDefault();
            return;
        }
        // Priority 2: collapse all expanded submenus
        const hasExpanded = Object.values(this.state.expandedSubmenus).some(Boolean);
        if (hasExpanded) {
            for (const key of Object.keys(this.state.expandedSubmenus)) {
                this.state.expandedSubmenus[key] = false;
            }
            ev.preventDefault();
        }
    }

    /**
     * Handles keyboard activation on sidenav items.
     * Enter and Space trigger the same action as click.
     * ArrowDown / ArrowUp move focus between sibling items.
     *
     * @param {KeyboardEvent} ev
     * @param {Object} menu — Menu item associated with the focused element
     */
    onItemKeyDown(ev, menu) {
        switch (ev.key) {
            case "Enter":
            case " ":
                ev.preventDefault();
                if (this.hasChildren(menu)) {
                    this.toggleSubmenu(menu);
                } else {
                    this.onMenuClick(menu);
                }
                break;
            case "ArrowDown": {
                ev.preventDefault();
                const next = ev.target.nextElementSibling;
                if (next) {
                    next.focus();
                }
                break;
            }
            case "ArrowUp": {
                ev.preventDefault();
                const prev = ev.target.previousElementSibling;
                if (prev) {
                    prev.focus();
                }
                break;
            }
            default:
                break;
        }
    }

    /**
     * Handles keyboard activation on submenu child items.
     * ArrowDown / ArrowUp navigate within the submenu group.
     * Escape collapses the parent submenu.
     *
     * @param {KeyboardEvent} ev
     * @param {Object} childMenu — Child menu item
     * @param {Object} parentSection — Parent section
     */
    onSubItemKeyDown(ev, childMenu, parentSection) {
        switch (ev.key) {
            case "Enter":
            case " ":
                ev.preventDefault();
                if (this.hasChildren(childMenu)) {
                    this.toggleSubmenu(childMenu);
                } else {
                    this.onMenuClick(childMenu);
                }
                break;
            case "ArrowDown": {
                ev.preventDefault();
                const next = ev.target.nextElementSibling;
                if (next) {
                    next.focus();
                }
                break;
            }
            case "ArrowUp": {
                ev.preventDefault();
                const prev = ev.target.previousElementSibling;
                if (prev) {
                    prev.focus();
                }
                break;
            }
            case "Escape":
                ev.preventDefault();
                if (parentSection) {
                    this.state.expandedSubmenus[parentSection.id] = false;
                }
                break;
            default:
                break;
        }
    }
}
