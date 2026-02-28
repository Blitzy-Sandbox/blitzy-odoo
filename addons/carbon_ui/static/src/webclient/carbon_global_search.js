/** @odoo-module */

/**
 * CarbonGlobalSearch — Global Search OWL Component for Carbon UI Shell Header
 *
 * Provides a persistent, prominent search input in the Carbon header center area.
 * This component acts as a visual gateway to Odoo's existing command palette
 * service (Ctrl+K / ⌘K), offering a Carbon-styled expandable search field that
 * delegates actual search execution to the command palette providers (menus,
 * commands, debug actions, etc.).
 *
 * Architecture Notes:
 * - The Odoo SearchBar (addons/web/static/src/search/search_bar/) is a VIEW-level
 *   search component bound to env.searchModel for filtering within a specific view.
 * - CarbonGlobalSearch is an APPLICATION-level search that queries across all apps,
 *   menus, commands, and actions via the command palette service.
 * - The command service (`openMainPalette`) is the integration point:
 *   it accepts a `searchValue` to pre-fill the palette's search input.
 *
 * Carbon Design Compliance:
 * - Follows Carbon's Search component specification (large size, 48px height)
 * - Uses `cds--search` class family for styling
 * - Carbon focus ring on keyboard focus
 * - Expandable pattern: icon-only on small screens, full input on large screens
 *
 * Responsive Behavior (Carbon breakpoints):
 * - sm (<672px): icon-only, click opens command palette directly
 * - md (672–1055px): collapsed by default, expandable on click
 * - lg (≥1056px): always expanded, full search input visible
 */

import { Component, useState, useRef, useExternalListener, onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { debounce } from "@web/core/utils/timing";

/**
 * Delay in milliseconds before triggering a search after the user stops typing.
 * Prevents excessive command palette invocations on rapid keystrokes.
 * @type {number}
 */
const SEARCH_DEBOUNCE_DELAY = 400;

/**
 * Carbon responsive breakpoint for large screens (in pixels).
 * At this width and above, the search input is always visible/expanded.
 * @type {number}
 */
const CARBON_BREAKPOINT_LG = 1056;

/**
 * Carbon responsive breakpoint for medium screens (in pixels).
 * Between md and lg, the search is collapsed to icon-only, expanding on click.
 * @type {number}
 */
const CARBON_BREAKPOINT_MD = 672;

export class CarbonGlobalSearch extends Component {
    static template = "carbon_ui.CarbonGlobalSearch";
    static props = {};

    /**
     * Sets up the component's reactive state, service integrations, hotkey
     * registration, debounced search handler, click-outside listener, and
     * initial responsive state.
     */
    setup() {
        // -- Reactive state --------------------------------------------------
        /**
         * @type {{ query: string, isExpanded: boolean, showResults: boolean }}
         */
        this.state = useState({
            /** Current search text entered by the user */
            query: "",
            /** Whether the search input is visually expanded (responsive) */
            isExpanded: false,
            /** Whether the results area is currently displayed */
            showResults: false,
        });

        // -- DOM reference for programmatic focus ----------------------------
        /**
         * Reference to the search <input> element for programmatic focus
         * management when expanding the search or activating via hotkey.
         * @type {import("@odoo/owl").Ref}
         */
        this.searchInputRef = useRef("searchInput");

        // -- Service integrations --------------------------------------------
        /**
         * Odoo's command service providing `openMainPalette(config)` to open
         * the command palette dialog with pre-filled search text and default
         * providers (menus, commands, debug actions).
         */
        this.commandService = useService("command");

        /**
         * Odoo's UI service providing `isSmall` for responsive breakpoint
         * detection. Used alongside window width checks for Carbon-specific
         * breakpoints that differ from Odoo's default Bootstrap breakpoints.
         */
        this.ui = useService("ui");

        // -- Hotkey registration ---------------------------------------------
        // Register Ctrl+K / ⌘K to expand and focus the search input.
        // Odoo's hotkey service handles platform detection (Ctrl on
        // Windows/Linux, ⌘ on macOS). The global command palette handler
        // already uses this shortcut; our component-scoped registration
        // provides a focused expand behavior when the header is in context.
        useHotkey("control+k", () => this.expandSearch(), {
            bypassEditableProtection: true,
            global: true,
        });

        // -- Debounced search trigger ----------------------------------------
        /**
         * Debounced version of `_executeSearch` that prevents the command
         * palette from being opened on every keystroke. Waits for the user
         * to stop typing for SEARCH_DEBOUNCE_DELAY ms before triggering.
         * @type {Function & { cancel: Function }}
         */
        this._debouncedSearch = debounce(
            this._executeSearch.bind(this),
            SEARCH_DEBOUNCE_DELAY
        );

        // -- Click-outside-to-collapse behavior ------------------------------
        // When the user clicks outside the search component, collapse the
        // search input on responsive screens where it was manually expanded.
        useExternalListener(window, "mousedown", this._onClickOutside.bind(this));

        // -- Initial responsive state ----------------------------------------
        // Set the initial expanded state based on the current viewport width.
        // On large screens (≥1056px), the search is always expanded.
        onMounted(() => {
            this._updateResponsiveState();
        });
    }

    // =========================================================================
    // PUBLIC METHODS (members_exposed per schema)
    // =========================================================================

    /**
     * Expands the search input and programmatically focuses it.
     * Called when:
     * - The user clicks the search magnifier icon (on collapsed views)
     * - The Ctrl+K / ⌘K hotkey is triggered
     * - The search input receives focus on small screens
     */
    expandSearch() {
        this.state.isExpanded = true;
        // Schedule focus for the next microtask to ensure the DOM has updated
        // after the reactive state change reveals the input element.
        Promise.resolve().then(() => {
            const inputEl = this.searchInputRef.el;
            if (inputEl) {
                inputEl.focus();
            }
        });
    }

    /**
     * Collapses the search input and clears all search state.
     * Called when:
     * - The user presses Escape while the search input is focused
     * - The user clicks outside the search component
     * - The search is programmatically dismissed
     */
    collapseSearch() {
        this.state.isExpanded = this._shouldBeAlwaysExpanded();
        this.state.query = "";
        this.state.showResults = false;
        this._debouncedSearch.cancel();
        // Clear the input element's value directly to keep DOM in sync
        const inputEl = this.searchInputRef.el;
        if (inputEl) {
            inputEl.value = "";
            inputEl.blur();
        }
    }

    /**
     * Handles user input in the search field. Updates the reactive query state
     * and triggers a debounced search when the query is non-empty.
     *
     * @param {InputEvent} ev - The native input event from the search field
     */
    onSearchInput(ev) {
        const value = ev.target.value;
        this.state.query = value;

        if (value.trim().length > 0) {
            this.state.showResults = true;
            this._debouncedSearch();
        } else {
            this.state.showResults = false;
            this._debouncedSearch.cancel();
        }
    }

    /**
     * Handles keyboard events within the search input for navigation and
     * action dispatch.
     *
     * Key mappings:
     * - Escape: Collapse the search and clear the input
     * - Enter: Open the command palette with the current query text
     *
     * @param {KeyboardEvent} ev - The native keydown event
     */
    onKeyDown(ev) {
        switch (ev.key) {
            case "Escape":
                ev.preventDefault();
                ev.stopPropagation();
                if (this.state.query.length > 0) {
                    // First Escape: clear the search text
                    this.clearSearch();
                } else {
                    // Second Escape (or empty input): collapse entirely
                    this.collapseSearch();
                }
                break;

            case "Enter":
                ev.preventDefault();
                ev.stopPropagation();
                this.triggerSearch();
                break;

            case "ArrowDown":
            case "ArrowUp":
                // Delegate arrow key navigation to the command palette.
                // If the palette is not yet open, trigger the search to open it.
                if (this.state.query.trim().length > 0) {
                    ev.preventDefault();
                    this.triggerSearch();
                }
                break;

            default:
                // Let the default input behavior handle all other keys
                break;
        }
    }

    /**
     * Handles focus events on the search input. On small/medium screens,
     * this expands the search to full width. On all screens, it ensures
     * the expanded state is set for proper visual display.
     */
    onFocus() {
        this.state.isExpanded = true;
    }

    /**
     * Clears the search query text while keeping the search input expanded
     * and focused. Used when the user clicks the clear (×) button.
     */
    clearSearch() {
        this.state.query = "";
        this.state.showResults = false;
        this._debouncedSearch.cancel();

        // Clear the input DOM element and maintain focus
        const inputEl = this.searchInputRef.el;
        if (inputEl) {
            inputEl.value = "";
            inputEl.focus();
        }
    }

    /**
     * Opens Odoo's command palette with the current search query as the
     * initial search value. This delegates the actual search execution to
     * the command palette's existing providers, which search across:
     * - Menus and apps (via menu_providers.js)
     * - Registered commands
     * - Debug actions (when debug mode is active)
     *
     * After triggering the search, the component collapses and clears
     * its local state since the command palette takes over the interaction.
     */
    triggerSearch() {
        const searchValue = this.state.query.trim();

        // Cancel any pending debounced search
        this._debouncedSearch.cancel();

        // Open the command palette with the current query
        // The commandService.openMainPalette merges the searchValue into
        // the palette's default configuration with all registered providers.
        this.commandService.openMainPalette({
            searchValue: searchValue,
        });

        // Reset the local search state since the command palette now
        // owns the search interaction
        this.state.showResults = false;
    }

    // =========================================================================
    // PRIVATE / INTERNAL METHODS
    // =========================================================================

    /**
     * Executes the debounced search by opening the command palette with
     * the current query. This is the function wrapped by `_debouncedSearch`.
     * @private
     */
    _executeSearch() {
        if (this.state.query.trim().length > 0) {
            this.triggerSearch();
        }
    }

    /**
     * Handles click-outside events to collapse the search input on
     * responsive layouts where it was manually expanded.
     *
     * @param {MouseEvent} ev - The window-level mousedown event
     * @private
     */
    _onClickOutside(ev) {
        // Do not collapse if the search should always be expanded (large screens)
        if (this._shouldBeAlwaysExpanded()) {
            return;
        }

        // Check if the click target is inside the search component's DOM tree
        const searchRoot = this.searchInputRef.el?.closest(".cds--search");
        if (searchRoot && searchRoot.contains(ev.target)) {
            return;
        }

        // Click was outside — collapse the search
        if (this.state.isExpanded) {
            this.collapseSearch();
        }
    }

    /**
     * Determines whether the search input should be permanently expanded
     * based on the current viewport width. On large screens (≥ Carbon lg
     * breakpoint of 1056px), the search is always visible.
     *
     * @returns {boolean} True if the viewport is wide enough for persistent expansion
     * @private
     */
    _shouldBeAlwaysExpanded() {
        if (typeof window !== "undefined") {
            return window.innerWidth >= CARBON_BREAKPOINT_LG;
        }
        return false;
    }

    /**
     * Updates the search expansion state based on the current viewport width.
     * Called on initial mount and could be called on window resize if needed.
     *
     * Carbon responsive behavior:
     * - ≥ 1056px (lg): always expanded
     * - 672–1055px (md): collapsed by default, expandable on user action
     * - < 672px (sm): collapsed, opens palette directly on icon click
     * @private
     */
    _updateResponsiveState() {
        if (this._shouldBeAlwaysExpanded()) {
            this.state.isExpanded = true;
        } else {
            this.state.isExpanded = false;
        }
    }

    /**
     * Handles click on the search magnifier icon. On small screens where
     * the input is hidden, this directly opens the command palette instead
     * of expanding the search input (since there's limited screen space).
     * On medium+ screens, it expands and focuses the search input.
     *
     * @param {MouseEvent} ev - The click event on the magnifier icon
     */
    onSearchIconClick(ev) {
        ev.preventDefault();
        ev.stopPropagation();

        if (this.ui.isSmall) {
            // On small screens, skip the search input and open the
            // command palette directly for a better mobile experience
            this.commandService.openMainPalette({});
        } else if (!this.state.isExpanded) {
            // On medium screens, expand and focus the search input
            this.expandSearch();
        } else {
            // Already expanded — focus the input
            const inputEl = this.searchInputRef.el;
            if (inputEl) {
                inputEl.focus();
            }
        }
    }
}
