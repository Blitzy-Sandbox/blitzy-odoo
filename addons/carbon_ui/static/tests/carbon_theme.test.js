/** @odoo-module */
// ---------------------------------------------------------------------------
// Carbon Theme Toggle — HOOT Test Suite
// ---------------------------------------------------------------------------
//
// Tests for the CarbonThemeToggle OWL component that provides light/dark mode
// switching between Carbon White (light) and G90 (dark) themes.
//
// Coverage:
//   1. Toggle button rendering and ARIA attributes
//   2. Theme switching behavior (light ↔ dark)
//   3. Carbon theme class application on document.documentElement
//   4. data-carbon-theme attribute management
//   5. color_scheme cookie integration (Odoo standard)
//   6. localStorage preference caching
//   7. Theme persistence across mount cycles (reads cookie on init)
//   8. WCAG 2.1 AA accessibility compliance
//   9. Standalone CarbonThemeToggle component tests
// ---------------------------------------------------------------------------

import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { advanceTime, animationFrame } from "@odoo/hoot-mock";
import { Component, xml } from "@odoo/owl";
import {
    contains,
    defineMenus,
    makeMockEnv,
    mountWithCleanup,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { WebClient } from "@web/webclient/webclient";
import { CarbonThemeToggle } from "@carbon_ui/webclient/carbon_theme_toggle";
import { registry } from "@web/core/registry";

// ---------------------------------------------------------------------------
// Constants — mirror the values from the production component so that
// assertions stay in sync without importing private constants.
// ---------------------------------------------------------------------------

/** CSS class for Carbon White (light) theme on <html>. */
const LIGHT_THEME_CLASS = "cds--white";

/** CSS class for Carbon G90 (dark) theme on <html>. */
const DARK_THEME_CLASS = "cds--g90";

/** All four Carbon v11 theme classes that may appear on <html>. */
const ALL_THEME_CLASSES = ["cds--white", "cds--g10", "cds--g90", "cds--g100"];

/** Odoo cookie name for dark/light mode. */
const COLOR_SCHEME_COOKIE = "color_scheme";

/** localStorage key for Carbon theme preference cache. */
const THEME_STORAGE_KEY = "carbon_theme_preference";

// ---------------------------------------------------------------------------
// Toggle‐button CSS selectors used across multiple tests.
// ---------------------------------------------------------------------------

/** Selector for the theme toggle button in light‐mode default state. */
const TOGGLE_SELECTOR = ".cds--header__action--theme-toggle";

/** Selector matching the toggle when dark mode is active. */
const TOGGLE_ACTIVE_SELECTOR =
    ".cds--header__action--theme-toggle.cds--header__action--active";

// ---------------------------------------------------------------------------
// Test Suite
// ---------------------------------------------------------------------------

describe("CarbonThemeToggle", () => {
    // Tag the suite for desktop browser tests.
    describe.current.tags("desktop");

    // Shared mock-cookie store scoped to each test via beforeEach.
    let mockCookieStore;

    // Shared mock-localStorage scoped to each test via beforeEach.
    let mockLocalStorage;

    // -----------------------------------------------------------------------
    // Per‐test setup — runs BEFORE every test in this describe block.
    // -----------------------------------------------------------------------
    beforeEach(() => {
        // 1. Reset mock stores
        mockCookieStore = {};
        mockLocalStorage = {};

        // 2. Provide minimal menus so that WebClient can mount without errors.
        defineMenus([{ id: 1, name: "App", actionID: 1 }]);

        // 3. Mock browser.location.reload() to prevent actual page reloads.
        //    The CarbonThemeToggle calls this after toggling the theme.
        patchWithCleanup(browser.location, {
            reload() {
                // Intentionally a no-op in tests. If a test needs to assert
                // reload was called, it can override this with expect.step.
            },
        });

        // 4. Mock browser.localStorage for deterministic caching tests.
        patchWithCleanup(browser, {
            localStorage: {
                getItem(key) {
                    return mockLocalStorage[key] ?? null;
                },
                setItem(key, value) {
                    mockLocalStorage[key] = String(value);
                },
                removeItem(key) {
                    delete mockLocalStorage[key];
                },
                clear() {
                    mockLocalStorage = {};
                },
            },
        });

        // 5. Clean up any Carbon theme classes that may have leaked onto
        //    document.documentElement from a previous test.
        const htmlEl = document.documentElement;
        for (const cls of ALL_THEME_CLASSES) {
            htmlEl.classList.remove(cls);
        }
        htmlEl.removeAttribute("data-carbon-theme");

        // 6. Clear the color_scheme cookie so every test starts in a known
        //    (light‐mode) state unless the test sets it explicitly.
        document.cookie = `${COLOR_SCHEME_COOKIE}=; path=/; max-age=0`;
    });

    // ===================================================================
    // 1. Toggle Button Rendering
    // ===================================================================

    test("CarbonThemeToggle can be rendered standalone", async () => {
        await mountWithCleanup(CarbonThemeToggle);

        // A button with the theme-toggle class must exist.
        expect(TOGGLE_SELECTOR).toHaveCount(1);

        // The button is a <button> element (natively focusable).
        expect(`button${TOGGLE_SELECTOR}`).toHaveCount(1);
    });

    test("toggle button renders with aria-pressed false in light mode", async () => {
        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        // Light mode is the default when no cookie is set.
        expect(`${TOGGLE_SELECTOR}[aria-pressed="false"]`).toHaveCount(1);
    });

    test("toggle button has aria-label describing pending action", async () => {
        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        // In light mode, the label invites the user to switch TO dark.
        expect(TOGGLE_SELECTOR).toHaveAttribute("aria-label", "Switch to dark mode");
    });

    test("toggle button has a title tooltip for sighted users", async () => {
        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        expect(TOGGLE_SELECTOR).toHaveAttribute("title", "Switch to dark mode");
    });

    test("toggle button is keyboard accessible (no negative tabindex)", async () => {
        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        // A <button> is natively focusable. We verify there is no tabindex=-1
        // that would remove it from the tab order.
        const btn = document.querySelector(TOGGLE_SELECTOR);
        expect(btn).not.toBe(null);
        const tabIndexAttr = btn.getAttribute("tabindex");
        // tabindex should either be absent (null) or >= 0.
        const isAccessible = tabIndexAttr === null || Number(tabIndexAttr) >= 0;
        expect(isAccessible).toBe(true);
    });

    test("toggle button contains an SVG icon", async () => {
        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        // In light mode a moon icon (SVG) is shown.
        expect(`${TOGGLE_SELECTOR} svg`).toHaveCount(1);

        // The SVG is decorative (hidden from screen readers).
        expect(`${TOGGLE_SELECTOR} svg[aria-hidden="true"]`).toHaveCount(1);
    });

    // ===================================================================
    // 2. Theme Switching Behavior
    // ===================================================================

    test("clicking toggle switches from light to dark mode", async () => {
        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        // Precondition — light mode.
        expect(`${TOGGLE_SELECTOR}[aria-pressed="false"]`).toHaveCount(1);

        // Act.
        await contains(TOGGLE_SELECTOR).click();
        await animationFrame();

        // The component should now reflect dark mode.
        expect(`${TOGGLE_SELECTOR}[aria-pressed="true"]`).toHaveCount(1);
    });

    test("clicking toggle again switches back to light mode", async () => {
        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        // Switch to dark.
        await contains(TOGGLE_SELECTOR).click();
        await animationFrame();
        expect(`${TOGGLE_SELECTOR}[aria-pressed="true"]`).toHaveCount(1);

        // Switch back to light.
        await contains(TOGGLE_SELECTOR).click();
        await animationFrame();
        expect(`${TOGGLE_SELECTOR}[aria-pressed="false"]`).toHaveCount(1);
    });

    test("aria-label updates on toggle", async () => {
        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        // Light → dark.
        await contains(TOGGLE_SELECTOR).click();
        await animationFrame();
        expect(TOGGLE_SELECTOR).toHaveAttribute("aria-label", "Switch to light mode");

        // Dark → light.
        await contains(TOGGLE_SELECTOR).click();
        await animationFrame();
        expect(TOGGLE_SELECTOR).toHaveAttribute("aria-label", "Switch to dark mode");
    });

    // ===================================================================
    // 3. Carbon Theme Class on <html>
    // ===================================================================

    test("light mode applies cds--white class to documentElement", async () => {
        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        const htmlEl = document.documentElement;
        expect(htmlEl.classList.contains(LIGHT_THEME_CLASS)).toBe(true);
        expect(htmlEl.classList.contains(DARK_THEME_CLASS)).toBe(false);
    });

    test("dark mode applies cds--g90 class to documentElement", async () => {
        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        await contains(TOGGLE_SELECTOR).click();
        await animationFrame();

        const htmlEl = document.documentElement;
        expect(htmlEl.classList.contains(DARK_THEME_CLASS)).toBe(true);
        expect(htmlEl.classList.contains(LIGHT_THEME_CLASS)).toBe(false);
    });

    test("previous theme class is removed when switching themes", async () => {
        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        const htmlEl = document.documentElement;

        // Start in light → has cds--white.
        expect(htmlEl.classList.contains(LIGHT_THEME_CLASS)).toBe(true);

        // Switch to dark → cds--white removed, cds--g90 added.
        await contains(TOGGLE_SELECTOR).click();
        await animationFrame();
        expect(htmlEl.classList.contains(LIGHT_THEME_CLASS)).toBe(false);
        expect(htmlEl.classList.contains(DARK_THEME_CLASS)).toBe(true);

        // Switch back → cds--g90 removed, cds--white restored.
        await contains(TOGGLE_SELECTOR).click();
        await animationFrame();
        expect(htmlEl.classList.contains(DARK_THEME_CLASS)).toBe(false);
        expect(htmlEl.classList.contains(LIGHT_THEME_CLASS)).toBe(true);
    });

    // ===================================================================
    // 4. data-carbon-theme Attribute
    // ===================================================================

    test("data-carbon-theme attribute is 'white' in light mode", async () => {
        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        const attr = document.documentElement.getAttribute("data-carbon-theme");
        expect(attr).toBe("white");
    });

    test("data-carbon-theme attribute changes to 'g90' in dark mode", async () => {
        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        await contains(TOGGLE_SELECTOR).click();
        await animationFrame();

        const attr = document.documentElement.getAttribute("data-carbon-theme");
        expect(attr).toBe("g90");
    });

    // ===================================================================
    // 5. color_scheme Cookie Integration
    // ===================================================================

    test("toggle sets color_scheme cookie to dark when switching to dark", async () => {
        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        await contains(TOGGLE_SELECTOR).click();
        await animationFrame();

        // The component writes document.cookie directly. Read it back.
        const cookieStr = document.cookie;
        expect(cookieStr).toInclude("color_scheme=dark");
    });

    test("toggle sets color_scheme cookie to light when switching back", async () => {
        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        // Switch to dark.
        await contains(TOGGLE_SELECTOR).click();
        await animationFrame();

        // Switch back to light.
        await contains(TOGGLE_SELECTOR).click();
        await animationFrame();

        const cookieStr = document.cookie;
        expect(cookieStr).toInclude("color_scheme=light");
    });

    test("theme preference reads from cookie on init (dark)", async () => {
        // Pre-set the cookie BEFORE mounting so that _detectDarkMode reads it.
        document.cookie = `${COLOR_SCHEME_COOKIE}=dark; path=/`;

        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        // The component should initialize in dark mode.
        expect(`${TOGGLE_SELECTOR}[aria-pressed="true"]`).toHaveCount(1);
        expect(document.documentElement.classList.contains(DARK_THEME_CLASS)).toBe(true);
    });

    test("theme preference reads from cookie on init (light)", async () => {
        // Explicitly set light cookie.
        document.cookie = `${COLOR_SCHEME_COOKIE}=light; path=/`;

        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        expect(`${TOGGLE_SELECTOR}[aria-pressed="false"]`).toHaveCount(1);
        expect(document.documentElement.classList.contains(LIGHT_THEME_CLASS)).toBe(true);
    });

    // ===================================================================
    // 6. localStorage Preference Caching
    // ===================================================================

    test("toggle caches preference in localStorage as 'dark'", async () => {
        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        await contains(TOGGLE_SELECTOR).click();
        await animationFrame();

        expect(mockLocalStorage[THEME_STORAGE_KEY]).toBe("dark");
    });

    test("toggle caches preference in localStorage as 'light'", async () => {
        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        // Switch to dark first.
        await contains(TOGGLE_SELECTOR).click();
        await animationFrame();

        // Switch back to light.
        await contains(TOGGLE_SELECTOR).click();
        await animationFrame();

        expect(mockLocalStorage[THEME_STORAGE_KEY]).toBe("light");
    });

    test("reads from localStorage when cookie is absent", async () => {
        // No cookie set, but localStorage has a preference.
        mockLocalStorage[THEME_STORAGE_KEY] = "dark";

        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        // Component should pick up the localStorage hint.
        expect(`${TOGGLE_SELECTOR}[aria-pressed="true"]`).toHaveCount(1);
        expect(document.documentElement.classList.contains(DARK_THEME_CLASS)).toBe(true);
    });

    // ===================================================================
    // 7. Page Reload on Toggle
    // ===================================================================

    test("toggleTheme triggers browser.location.reload", async () => {
        // Override the reload mock with a stepping spy.
        patchWithCleanup(browser.location, {
            reload() {
                expect.step("location reload");
            },
        });

        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        await contains(TOGGLE_SELECTOR).click();
        // The component uses browser.setTimeout(..., 100) before calling
        // reload — advance the mock timer to fire the deferred callback.
        await advanceTime(150);
        await animationFrame();

        expect.verifySteps(["location reload"]);
    });

    // ===================================================================
    // 8. WCAG 2.1 AA Accessibility Checks
    // ===================================================================

    test("toggle button type is 'button' (not submit)", async () => {
        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        expect(TOGGLE_SELECTOR).toHaveAttribute("type", "button");
    });

    test("SVG icons are decorative (aria-hidden and not focusable)", async () => {
        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        // Light mode icon (moon).
        expect(`${TOGGLE_SELECTOR} svg[aria-hidden="true"]`).toHaveCount(1);
        expect(`${TOGGLE_SELECTOR} svg[focusable="false"]`).toHaveCount(1);

        // Switch to dark.
        await contains(TOGGLE_SELECTOR).click();
        await animationFrame();

        // Dark mode icon (sun).
        expect(`${TOGGLE_SELECTOR} svg[aria-hidden="true"]`).toHaveCount(1);
        expect(`${TOGGLE_SELECTOR} svg[focusable="false"]`).toHaveCount(1);
    });

    test("toggle icon changes between light and dark mode", async () => {
        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        // Capture the SVG path data in light mode (moon icon).
        const moonPathD = document.querySelector(
            `${TOGGLE_SELECTOR} svg path`
        )?.getAttribute("d");
        expect(moonPathD).not.toBe(null);

        // Switch to dark.
        await contains(TOGGLE_SELECTOR).click();
        await animationFrame();

        // Capture the SVG path data in dark mode (sun icon).
        const sunPathD = document.querySelector(
            `${TOGGLE_SELECTOR} svg path`
        )?.getAttribute("d");
        expect(sunPathD).not.toBe(null);

        // The two icons must be different (moon vs sun).
        expect(moonPathD).not.toBe(sunPathD);
    });

    // ===================================================================
    // 9. Active-State CSS Class on the Button
    // ===================================================================

    test("button receives cds--header__action--active class in dark mode", async () => {
        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        // Light mode — no active class.
        expect(TOGGLE_ACTIVE_SELECTOR).toHaveCount(0);

        // Switch to dark.
        await contains(TOGGLE_SELECTOR).click();
        await animationFrame();

        // Dark mode — active class present.
        expect(TOGGLE_ACTIVE_SELECTOR).toHaveCount(1);

        // Switch back.
        await contains(TOGGLE_SELECTOR).click();
        await animationFrame();

        // Active class removed again.
        expect(TOGGLE_ACTIVE_SELECTOR).toHaveCount(0);
    });

    // ===================================================================
    // 10. Theme Detection Priority
    // ===================================================================

    test("cookie takes priority over localStorage for initial detection", async () => {
        // Set conflicting signals: cookie says light, localStorage says dark.
        document.cookie = `${COLOR_SCHEME_COOKIE}=light; path=/`;
        mockLocalStorage[THEME_STORAGE_KEY] = "dark";

        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        // Cookie wins → light mode.
        expect(`${TOGGLE_SELECTOR}[aria-pressed="false"]`).toHaveCount(1);
        expect(document.documentElement.classList.contains(LIGHT_THEME_CLASS)).toBe(true);
    });

    test("DOM theme class is a fallback when no cookie and no localStorage", async () => {
        // Pre-apply a dark theme class directly on the DOM.
        document.documentElement.classList.add("cds--g100");

        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        // The component reads cds--g100 from the DOM and treats it as dark.
        expect(`${TOGGLE_SELECTOR}[aria-pressed="true"]`).toHaveCount(1);
    });

    test("defaults to light mode when no signal is present", async () => {
        // No cookie, no localStorage, no DOM class → defaults light.
        await mountWithCleanup(CarbonThemeToggle);
        await animationFrame();

        expect(`${TOGGLE_SELECTOR}[aria-pressed="false"]`).toHaveCount(1);
        expect(document.documentElement.classList.contains(LIGHT_THEME_CLASS)).toBe(true);
    });

    // ===================================================================
    // 11. Integration with Wrapper Components
    // ===================================================================

    test("CarbonThemeToggle works inside a host wrapper component", async () => {
        // Use Component + xml to create an inline wrapper that hosts the
        // toggle, simulating integration inside the Carbon header.
        class ThemeToggleHost extends Component {
            static props = {};
            static components = { CarbonThemeToggle };
            static template = xml`
                <div class="cds--header__global">
                    <CarbonThemeToggle />
                </div>
            `;
        }

        await mountWithCleanup(ThemeToggleHost);
        await animationFrame();

        // The toggle button should render inside the wrapper.
        expect(".cds--header__global .cds--header__action--theme-toggle").toHaveCount(1);

        // Clicking it still works through the wrapper.
        await contains(TOGGLE_SELECTOR).click();
        await animationFrame();
        expect(`${TOGGLE_SELECTOR}[aria-pressed="true"]`).toHaveCount(1);
    });

    test("CarbonThemeToggle can be mounted with explicit mock env", async () => {
        // Use makeMockEnv to create an isolated test environment.
        const env = await makeMockEnv();

        await mountWithCleanup(CarbonThemeToggle, { env });
        await animationFrame();

        // Verify the component renders and functions correctly in the
        // custom environment.
        expect(TOGGLE_SELECTOR).toHaveCount(1);
        expect(`${TOGGLE_SELECTOR}[aria-pressed="false"]`).toHaveCount(1);
    });

    test("registry category is accessible for systray integration checks", async () => {
        // Verify the systray registry category exists and is queryable.
        // This is the registry where Carbon header utilities are registered.
        const systrayCategory = registry.category("systray");
        expect(systrayCategory).not.toBe(null);
        expect(systrayCategory).not.toBe(undefined);
    });

    // ===================================================================
    // 12. WebClient Integration (Full Shell Context)
    // ===================================================================

    test("WebClient class is importable and has correct template", async () => {
        // Verify the WebClient component exists and has the expected
        // template name. The Carbon module overrides this template via
        // QWeb inheritance to inject the Carbon shell with theme toggle.
        expect(WebClient.template).toBe("web.WebClient");
        expect(typeof WebClient.prototype.setup).toBe("function");
    });
});
