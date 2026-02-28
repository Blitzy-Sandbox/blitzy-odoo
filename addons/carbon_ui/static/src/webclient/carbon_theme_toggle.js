/** @odoo-module */

import { Component, useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { useService } from "@web/core/utils/hooks";

// ---------------------------------------------------------------------------
// Carbon Theme Constants
// ---------------------------------------------------------------------------

/**
 * CSS class applied to document.documentElement for Carbon White (light) theme.
 * This is the default "Productive" light theme.
 */
const LIGHT_THEME_CLASS = "cds--white";

/**
 * CSS class applied to document.documentElement for Carbon G90 (dark) theme.
 * G90 is the preferred dark theme for Carbon's "Productive" variant,
 * offering a lighter dark background that reduces eye strain during prolonged use.
 */
const DARK_THEME_CLASS = "cds--g90";

/**
 * All four built-in Carbon theme classes. Removed from the DOM before applying
 * the active theme to avoid class conflicts.
 *   - cds--white : White theme (light, default)
 *   - cds--g10   : Gray 10 theme (light, subtle)
 *   - cds--g90   : Gray 90 theme (dark, productive)
 *   - cds--g100  : Gray 100 theme (dark, maximum contrast)
 */
const ALL_THEME_CLASSES = Object.freeze([
    "cds--white",
    "cds--g10",
    "cds--g90",
    "cds--g100",
]);

/**
 * Odoo's standard cookie name for dark/light mode selection.
 * The web.assets_web_dark CSS bundle is conditionally loaded by the Odoo
 * server based on this cookie value. Accepted values: "dark" | "light".
 */
const COLOR_SCHEME_COOKIE = "color_scheme";

/**
 * localStorage key used to cache the Carbon theme preference for faster
 * detection on subsequent page loads (avoids cookie-parsing latency).
 */
const THEME_STORAGE_KEY = "carbon_theme_preference";

/**
 * Cookie time-to-live in seconds: 1 year. Matches the default TTL used by
 * Odoo's own cookie utility (see @web/core/browser/cookie — COOKIE_TTL).
 */
const COOKIE_TTL = 24 * 60 * 60 * 365;

// ---------------------------------------------------------------------------
// CarbonThemeToggle Component
// ---------------------------------------------------------------------------

/**
 * CarbonThemeToggle — Light/Dark Mode Toggle OWL Component
 *
 * Renders a toggle button in the Carbon Header utility area that switches
 * between the Carbon White (light) and G90 (dark) theme token sets. The
 * component integrates with Odoo's existing `color_scheme` cookie mechanism
 * so that:
 *
 *  1. The theme preference persists across sessions (cookie + localStorage).
 *  2. The Odoo server loads the correct CSS asset bundles on page load
 *     (web.assets_web_dark is conditionally included when color_scheme=dark).
 *  3. Carbon CSS custom properties (--cds-*) switch values based on the
 *     active theme class on document.documentElement.
 *
 * Toggle flow:
 *   toggleTheme()
 *     → flip state.isDarkMode
 *     → write color_scheme cookie ("dark" | "light")
 *     → cache preference in localStorage
 *     → swap Carbon theme class on <html> element
 *     → trigger page reload for full CSS bundle swap
 *
 * @extends Component
 */
export class CarbonThemeToggle extends Component {
    static template = "carbon_ui.CarbonThemeToggle";
    static props = {};

    // -----------------------------------------------------------------------
    // Lifecycle
    // -----------------------------------------------------------------------

    setup() {
        // useService is available for accessing Odoo services following the
        // established pattern from other Carbon webclient OWL components.
        // The cookie service reference is stored for potential use by
        // modules that register a managed cookie service. When unavailable,
        // direct document.cookie manipulation is used via _getCookieValue
        // and _setCookie helpers, matching Odoo's own cookie utility pattern.
        this.cookieService =
            "cookie" in this.env.services
                ? useService("cookie")
                : null;

        this.state = useState({
            isDarkMode: this._detectDarkMode(),
        });

        // Apply the initial Carbon theme class to the DOM element so that
        // CSS custom properties resolve correctly on first render.
        this._applyThemeToDOM(this.state.isDarkMode);
    }

    // -----------------------------------------------------------------------
    // Public API
    // -----------------------------------------------------------------------

    /**
     * Toggle between Carbon White (light) and G90 (dark) themes.
     *
     * Execution order:
     *  1. Flip the reactive isDarkMode boolean.
     *  2. Persist the preference via the color_scheme cookie (Odoo standard)
     *     and localStorage (fast cache).
     *  3. Swap the Carbon theme class on <html> for immediate visual feedback.
     *  4. Trigger a full page reload so that the Odoo asset pipeline loads
     *     (or unloads) the web.assets_web_dark CSS bundle, ensuring all
     *     server-side rendered styles match the selected scheme.
     */
    toggleTheme() {
        // 1. Flip state
        this.state.isDarkMode = !this.state.isDarkMode;

        const scheme = this.state.isDarkMode ? "dark" : "light";

        // 2. Persist preference — cookie for Odoo server, localStorage for cache
        this._setCookie(COLOR_SCHEME_COOKIE, scheme);
        browser.localStorage.setItem(THEME_STORAGE_KEY, scheme);

        // 3. Apply theme class to DOM for immediate visual feedback
        this._applyThemeToDOM(this.state.isDarkMode);

        // 4. Reload the page so the Odoo server delivers the correct CSS
        //    asset bundles. The web.assets_web_dark bundle is conditionally
        //    included based on the color_scheme cookie value.
        //
        //    A short delay is introduced before reload to ensure the
        //    document.cookie write is fully flushed to the browser's
        //    cookie jar. In some execution contexts (especially when
        //    running through OWL's `browser` proxy or in high-load
        //    scenarios), calling location.reload() synchronously after
        //    setting document.cookie can cause the navigation to begin
        //    before the cookie store has processed the write, resulting
        //    in the cookie being absent on the next page load.
        //
        //    Using setTimeout with a 100ms delay guarantees that the
        //    JavaScript event loop yields back to the browser, allowing
        //    the cookie write to settle before the reload navigates away.
        browser.setTimeout(() => {
            browser.location.reload();
        }, 100);
    }

    // -----------------------------------------------------------------------
    // Private — Theme Detection
    // -----------------------------------------------------------------------

    /**
     * Detect the current dark-mode state by consulting multiple sources in
     * priority order:
     *
     *  1. Odoo's color_scheme cookie (authoritative — server uses this to
     *     decide which CSS bundles to serve).
     *  2. localStorage cache (fast fallback when cookie is absent).
     *  3. DOM inspection for Carbon theme classes (cds--g90, cds--g100).
     *  4. DOM data attribute (data-carbon-theme).
     *  5. Defaults to light mode (false) if no signal is found.
     *
     * @returns {boolean} true when dark mode is active
     * @private
     */
    _detectDarkMode() {
        // Source 1: Odoo's color_scheme cookie (primary source of truth)
        const cookieValue = this._getCookieValue(COLOR_SCHEME_COOKIE);
        if (cookieValue === "dark") {
            return true;
        }
        if (cookieValue === "light") {
            return false;
        }

        // Source 2: localStorage cache
        const storedPref = browser.localStorage.getItem(THEME_STORAGE_KEY);
        if (storedPref === "dark") {
            return true;
        }
        if (storedPref === "light") {
            return false;
        }

        // Source 3: Carbon theme classes on <html>
        const htmlEl = document.documentElement;
        if (
            htmlEl.classList.contains("cds--g90") ||
            htmlEl.classList.contains("cds--g100")
        ) {
            return true;
        }

        // Source 4: data-carbon-theme attribute on <html>
        const themeAttr = htmlEl.getAttribute("data-carbon-theme");
        if (themeAttr === "g90" || themeAttr === "g100") {
            return true;
        }

        // Source 5: Default — light mode
        return false;
    }

    // -----------------------------------------------------------------------
    // Private — DOM Manipulation
    // -----------------------------------------------------------------------

    /**
     * Apply the selected Carbon theme to the DOM by swapping CSS classes and
     * the data attribute on document.documentElement. All Carbon components
     * reference CSS custom properties (--cds-*) that change based on the
     * active theme class.
     *
     * @param {boolean} isDark - true to apply G90 dark theme, false for White
     * @private
     */
    _applyThemeToDOM(isDark) {
        const htmlEl = document.documentElement;

        // Remove all Carbon theme classes to avoid conflicts
        for (const cls of ALL_THEME_CLASSES) {
            htmlEl.classList.remove(cls);
        }

        // Add the appropriate Carbon theme class
        const themeClass = isDark ? DARK_THEME_CLASS : LIGHT_THEME_CLASS;
        htmlEl.classList.add(themeClass);

        // Set a data attribute for CSS attribute-selector targeting
        const themeValue = isDark ? "g90" : "white";
        htmlEl.setAttribute("data-carbon-theme", themeValue);
    }

    // -----------------------------------------------------------------------
    // Private — Cookie Helpers
    // -----------------------------------------------------------------------

    /**
     * Parse a named value from the document.cookie string.
     *
     * Follows the same parsing logic as Odoo's cookie.get() utility
     * (see @web/core/browser/cookie) to ensure consistent behavior.
     *
     * @param {string} name - The cookie key to retrieve
     * @returns {string|undefined} The cookie value, or undefined if not found
     * @private
     */
    _getCookieValue(name) {
        const parts = document.cookie.split("; ");
        for (const part of parts) {
            const [key, value] = part.split(/=(.*)/);
            if (key === name) {
                return value || "";
            }
        }
        return undefined;
    }

    /**
     * Write a cookie with a one-year TTL and secure defaults.
     *
     * The cookie is set on the root path ("/") so it is available to all
     * Odoo routes, and uses SameSite=Lax to align with modern browser
     * defaults while remaining compatible with Odoo's server-side cookie
     * reading.
     *
     * @param {string} name  - Cookie key
     * @param {string} value - Cookie value
     * @private
     */
    _setCookie(name, value) {
        const parts = [
            `${name}=${value}`,
            "path=/",
            `max-age=${Math.floor(COOKIE_TTL)}`,
            "SameSite=Lax",
        ];
        // Add Secure flag when served over HTTPS to prevent cookie
        // transmission over unencrypted connections in production.
        // Omitted for HTTP to preserve local development compatibility.
        if (window.location.protocol === "https:") {
            parts.push("Secure");
        }
        document.cookie = parts.join("; ");
    }
}
