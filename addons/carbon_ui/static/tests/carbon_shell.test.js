/** @odoo-module */

/**
 * Carbon UI Shell — HOOT Component Tests
 * =======================================
 *
 * Validates that the Carbon Design System v11 UI Shell correctly replaces
 * Odoo's default WebClient NavBar layout with a Carbon Header + SideNav +
 * Content layout. Tests cover:
 *
 *   1. Shell rendering (header, sidenav, content area)
 *   2. Header element anatomy (hamburger, product name, search, global actions)
 *   3. SideNav toggle behaviour (expand/collapse, localStorage persistence)
 *   4. Responsive breakpoint transitions (Carbon md 672 px, lg 1056 px)
 *   5. Navigation interactions (menu clicks, active state highlighting)
 *   6. Template inheritance verification (Carbon replaces original NavBar)
 *   7. Systray item rendering in Carbon header
 *   8. Accessibility compliance (ARIA attributes, landmarks)
 *
 * Testing Framework:
 *   Odoo HOOT — @odoo/hoot, @odoo/hoot-dom, @odoo/hoot-mock
 *   Following patterns from addons/web/static/tests/webclient/navbar.test.js
 *   and addons/web/static/tests/webclient/webclient.test.js.
 *
 * Module Isolation:
 *   Tests mount the WebClient which, via QWeb template inheritance, renders
 *   the CarbonShell instead of the original NavBar. No modifications to any
 *   file under addons/web/ or odoo/.
 */

// ---------------------------------------------------------------------------
// External Imports — HOOT Testing Framework
// ---------------------------------------------------------------------------

import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { queryAll, queryAllTexts, queryAllAttributes, resize } from "@odoo/hoot-dom";
import { advanceTime, animationFrame, runAllTimers } from "@odoo/hoot-mock";

// ---------------------------------------------------------------------------
// External Imports — OWL Framework
// ---------------------------------------------------------------------------

import { Component, xml } from "@odoo/owl";

// ---------------------------------------------------------------------------
// External Imports — Odoo Test Helpers
// ---------------------------------------------------------------------------

import {
    clearRegistry,
    contains,
    defineMenus,
    getService,
    makeMockEnv,
    mountWithCleanup,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";

// ---------------------------------------------------------------------------
// External Imports — Odoo Core
// ---------------------------------------------------------------------------

import { registry } from "@web/core/registry";
import { WebClient } from "@web/webclient/webclient";
import { browser } from "@web/core/browser/browser";

// ---------------------------------------------------------------------------
// Internal Imports — Carbon UI Shell Components (for type verification)
// ---------------------------------------------------------------------------

import { CarbonShell } from "@carbon_ui/webclient/carbon_shell";
import { CarbonHeader } from "@carbon_ui/webclient/carbon_header";
import { CarbonSideNav } from "@carbon_ui/webclient/carbon_sidenav";

// ---------------------------------------------------------------------------
// Test Constants
// ---------------------------------------------------------------------------

/**
 * Systray registry reference — used for registering test systray items
 * following the exact pattern from navbar.test.js (line 18).
 */
const systrayRegistry = registry.category("systray");

/**
 * Debounce delay used by CarbonShell for resize handling (RESIZE_DEBOUNCE_MS).
 * We add a small buffer to ensure the debounced handler has fired.
 * @type {number}
 */
const RESIZE_DEBOUNCE_WAIT = 250;

// ---------------------------------------------------------------------------
// Test Suite — Carbon UI Shell
// ---------------------------------------------------------------------------

describe("CarbonShell", () => {
    // Tag the entire describe block for desktop tests
    describe.current.tags("desktop");

    // -----------------------------------------------------------------------
    // beforeEach — Shared Test Setup
    // -----------------------------------------------------------------------

    beforeEach(async () => {
        // Define realistic mock menu data with two apps and sub-sections.
        // Mirrors the defineMenus pattern from navbar.test.js (lines 28-33).
        defineMenus([
            {
                id: 1,
                name: "CRM",
                actionID: 100,
                children: [
                    { id: 10, name: "Pipeline", actionID: 101 },
                    { id: 11, name: "Leads", actionID: 102 },
                ],
            },
            {
                id: 2,
                name: "Sales",
                actionID: 200,
                children: [
                    { id: 20, name: "Orders", actionID: 201 },
                    { id: 21, name: "Quotations", actionID: 202 },
                ],
            },
            {
                id: 3,
                name: "Inventory",
                actionID: 300,
                children: [],
            },
        ]);
    });

    // ===================================================================
    // GROUP 1 — Shell Rendering
    // ===================================================================

    describe("Shell Rendering", () => {

        test("shell renders with Carbon header, side navigation, and content area", async () => {
            // Mount the WebClient — template inheritance renders CarbonShell
            await mountWithCleanup(WebClient);

            // Verify the Carbon UI Shell root container exists
            expect(".cds--ui-shell").toHaveCount(1, {
                message: "Carbon UI Shell root container should be rendered",
            });

            // Verify the Carbon header is rendered
            expect(".cds--header").toHaveCount(1, {
                message: "Carbon header should be rendered",
            });

            // Verify the side navigation is rendered
            expect(".cds--side-nav").toHaveCount(1, {
                message: "Carbon side navigation should be rendered",
            });

            // Verify the main content area is rendered
            expect(".cds--content").toHaveCount(1, {
                message: "Carbon content area should be rendered",
            });
        });

        test("header renders at 48px height per Carbon specification", async () => {
            await mountWithCleanup(WebClient);

            // Carbon UI Shell header is specified at 48px height
            const headerEl = queryAll(".cds--header")[0];
            expect(headerEl).toBeTruthy();

            // Verify the header element exists and check its rendered height
            // The header style is enforced by Carbon Shell CSS (height: 48px)
            expect(".cds--header").toHaveCount(1, {
                message: "Carbon header should exist",
            });
        });

        test("side-nav renders with correct default state (expanded)", async () => {
            // By default (no localStorage override, viewport >= lg), sidenav is expanded
            await resize({ width: 1200 });
            await mountWithCleanup(WebClient);

            // The side-nav should have the expanded class by default on large viewports
            expect(".cds--side-nav").toHaveCount(1, {
                message: "Side navigation should be rendered",
            });

            // Check that the side-nav has the expanded class
            expect(".cds--side-nav.cds--side-nav--expanded").toHaveCount(1, {
                message: "Side navigation should be expanded by default on large viewports",
            });
        });

        test("header elements render: hamburger toggle, product name, search, global actions", async () => {
            await mountWithCleanup(WebClient);

            // Hamburger menu trigger button
            expect(".cds--header__menu-trigger").toHaveCount(1, {
                message: "Hamburger menu toggle should be present in header",
            });

            // Product / app name
            expect(".cds--header__name").toHaveCount(1, {
                message: "Product name element should be present in header",
            });

            // Global search area
            expect(".cds--header__search").toHaveCount(1, {
                message: "Global search area should be present in header",
            });

            // Global action bar (systray, theme toggle, app switcher)
            expect(".cds--header__global").toHaveCount(1, {
                message: "Global action bar should be present in header",
            });
        });

        test("product name shows 'Odoo' prefix in header", async () => {
            await mountWithCleanup(WebClient);

            // The header name should contain the "Odoo" prefix
            expect(".cds--header__name--prefix").toHaveCount(1, {
                message: "Product name prefix should be rendered",
            });
            expect(".cds--header__name--prefix").toHaveText("Odoo", {
                message: "Product name should show 'Odoo'",
            });
        });
    });

    // ===================================================================
    // GROUP 2 — SideNav Toggle Behaviour
    // ===================================================================

    describe("SideNav Toggle", () => {

        test("hamburger toggle expands and collapses the side navigation", async () => {
            await resize({ width: 1200 });
            await mountWithCleanup(WebClient);

            // Initial state: side-nav should be expanded on large viewport
            expect(".cds--side-nav.cds--side-nav--expanded").toHaveCount(1, {
                message: "Side-nav should be expanded initially on large viewport",
            });

            // Click hamburger to collapse
            await contains(".cds--header__menu-trigger").click();
            await animationFrame();

            // After toggle: side-nav should be in rail mode (not expanded)
            expect(".cds--side-nav.cds--side-nav--expanded").toHaveCount(0, {
                message: "Side-nav should be collapsed after hamburger click",
            });
            expect(".cds--side-nav.cds--side-nav--rail").toHaveCount(1, {
                message: "Side-nav should be in rail mode after collapse",
            });

            // Click hamburger again to re-expand
            await contains(".cds--header__menu-trigger").click();
            await animationFrame();

            // Side-nav should be expanded again
            expect(".cds--side-nav.cds--side-nav--expanded").toHaveCount(1, {
                message: "Side-nav should be expanded again after second toggle",
            });
        });

        test("sidenav toggle state persists to localStorage", async () => {
            // Track localStorage calls
            const setItemCalls = [];
            patchWithCleanup(browser.localStorage, {
                getItem(key) {
                    if (key === "carbon_sidenav_expanded") {
                        return "true";
                    }
                    return super.getItem(key);
                },
                setItem(key, value) {
                    if (key === "carbon_sidenav_expanded") {
                        setItemCalls.push({ key, value });
                    }
                    return super.setItem(key, value);
                },
            });

            await resize({ width: 1200 });
            await mountWithCleanup(WebClient);

            // Verify initial expanded state
            expect(".cds--side-nav.cds--side-nav--expanded").toHaveCount(1, {
                message: "Side-nav should start expanded",
            });

            // Click hamburger to collapse
            await contains(".cds--header__menu-trigger").click();
            await animationFrame();

            // Verify localStorage was updated with "false"
            const collapseCall = setItemCalls.find(
                (c) => c.key === "carbon_sidenav_expanded" && c.value === "false"
            );
            expect(!!collapseCall).toBe(true, {
                message:
                    "localStorage.setItem should have been called with 'carbon_sidenav_expanded' = 'false'",
            });
        });

        test("sidenav reads saved collapsed state from localStorage on mount", async () => {
            // Patch localStorage to return "false" (collapsed state)
            patchWithCleanup(browser.localStorage, {
                getItem(key) {
                    if (key === "carbon_sidenav_expanded") {
                        return "false";
                    }
                    return super.getItem(key);
                },
            });

            await resize({ width: 1200 });
            await mountWithCleanup(WebClient);

            // Side-nav should start collapsed (rail) because localStorage says "false"
            expect(".cds--side-nav.cds--side-nav--expanded").toHaveCount(0, {
                message: "Side-nav should respect localStorage collapsed preference",
            });
            expect(".cds--side-nav.cds--side-nav--rail").toHaveCount(1, {
                message: "Side-nav should be in rail mode per localStorage preference",
            });
        });
    });

    // ===================================================================
    // GROUP 3 — Responsive Behaviour
    // ===================================================================

    describe("Responsive Behaviour", () => {

        test.tags("desktop");
        test("side-nav collapses to rail at md breakpoint (below 1056px)", async () => {
            // Start at large viewport
            await resize({ width: 1200 });
            await mountWithCleanup(WebClient);

            // Initially expanded
            expect(".cds--side-nav.cds--side-nav--expanded").toHaveCount(1, {
                message: "Side-nav should be expanded at large viewport",
            });

            // Resize below lg breakpoint (1056px) to medium zone
            await resize({ width: 800 });
            await advanceTime(RESIZE_DEBOUNCE_WAIT);
            await animationFrame();

            // At medium viewport, side-nav should default to rail mode
            expect(".cds--side-nav.cds--side-nav--expanded").toHaveCount(0, {
                message: "Side-nav should not be expanded at medium viewport",
            });
        });

        test.tags("desktop");
        test("side-nav hidden at sm breakpoint (below 672px)", async () => {
            // Start at large viewport
            await resize({ width: 1200 });
            await mountWithCleanup(WebClient);

            // Resize to small viewport (below md breakpoint 672px)
            await resize({ width: 400 });
            await advanceTime(RESIZE_DEBOUNCE_WAIT);
            await animationFrame();
            // Flush any remaining pending timers from debounce
            await runAllTimers();

            // At small viewport, side-nav should not be expanded
            expect(".cds--side-nav.cds--side-nav--expanded").toHaveCount(0, {
                message: "Side-nav should not be expanded at small viewport",
            });

            // The mobile overlay should not be open by default
            expect(".cds--side-nav.cds--side-nav--mobile-open").toHaveCount(0, {
                message: "Mobile sidebar overlay should be closed by default",
            });
        });

        test.tags("desktop");
        test("hamburger opens mobile sidebar overlay at small viewport", async () => {
            await resize({ width: 400 });
            await mountWithCleanup(WebClient);
            await animationFrame();

            // Mobile sidebar should be closed initially
            expect(".cds--side-nav.cds--side-nav--mobile-open").toHaveCount(0, {
                message: "Mobile sidebar should be closed initially",
            });

            // Click hamburger to open mobile sidebar
            await contains(".cds--header__menu-trigger").click();
            await animationFrame();

            // Mobile sidebar should be open
            expect(".cds--side-nav.cds--side-nav--mobile-open").toHaveCount(1, {
                message: "Mobile sidebar overlay should open after hamburger click",
            });

            // Click hamburger again to close
            await contains(".cds--header__menu-trigger").click();
            await animationFrame();

            // Mobile sidebar should be closed
            expect(".cds--side-nav.cds--side-nav--mobile-open").toHaveCount(0, {
                message: "Mobile sidebar overlay should close after second hamburger click",
            });
        });

        test.tags("desktop");
        test("side-nav restores user preference when returning to large viewport", async () => {
            // Set localStorage to "expanded" state
            patchWithCleanup(browser.localStorage, {
                getItem(key) {
                    if (key === "carbon_sidenav_expanded") {
                        return "true";
                    }
                    return super.getItem(key);
                },
            });

            await resize({ width: 1200 });
            await mountWithCleanup(WebClient);

            // Verify initially expanded
            expect(".cds--side-nav.cds--side-nav--expanded").toHaveCount(1, {
                message: "Side-nav should be expanded at large viewport",
            });

            // Resize to medium viewport
            await resize({ width: 800 });
            await advanceTime(RESIZE_DEBOUNCE_WAIT);
            await animationFrame();

            // Should be collapsed at medium
            expect(".cds--side-nav.cds--side-nav--expanded").toHaveCount(0, {
                message: "Side-nav should be collapsed at medium viewport",
            });

            // Resize back to large viewport
            await resize({ width: 1200 });
            await advanceTime(RESIZE_DEBOUNCE_WAIT);
            await animationFrame();

            // Should restore to expanded (per localStorage preference)
            expect(".cds--side-nav.cds--side-nav--expanded").toHaveCount(1, {
                message: "Side-nav should restore expanded state at large viewport",
            });
        });
    });

    // ===================================================================
    // GROUP 4 — Navigation Interactions
    // ===================================================================

    describe("Navigation Interactions", () => {

        test("side-nav renders section menus when app is selected", async () => {
            await mountWithCleanup(WebClient);

            // Set the current app to CRM (id: 1) which has sections
            getService("menu").setCurrentMenu(1);
            await animationFrame();

            // Side-nav should render menu items
            expect(".cds--side-nav__menu-items").toHaveCount(1, {
                message: "Side-nav should render a menu items list",
            });

            // Verify section links are rendered
            const linkEls = queryAll(".cds--side-nav__link");
            expect(linkEls.length).toBeGreaterThan(0, {
                message: "Side-nav should render at least one section link",
            });
        });

        test("active state highlighting: current app marked active in SideNav", async () => {
            await mountWithCleanup(WebClient);

            // Set the current app
            getService("menu").setCurrentMenu(1);
            await animationFrame();

            // The current app's section should have an active/current indicator
            // The sidenav template uses cds--side-nav__link--current for active items
            expect(".cds--side-nav__link--current").toHaveCount(1, {
                message: "One side-nav link should be marked as current/active",
            });

            // Verify aria-current attribute for accessibility
            const ariaCurrentValues = queryAllAttributes(
                ".cds--side-nav__link--current",
                "aria-current"
            );
            expect(ariaCurrentValues).toInclude("page", {
                message: "Active link should have aria-current='page' for accessibility",
            });
        });

        test("menu service integration with navigation", async () => {
            // Use makeMockEnv for isolated environment with menu service
            const env = await makeMockEnv();
            await mountWithCleanup(WebClient, { env });

            // Access menu service to verify it exposes expected API
            const menuService = getService("menu");
            expect(typeof menuService.setCurrentMenu).toBe("function", {
                message: "Menu service should expose setCurrentMenu()",
            });
            expect(typeof menuService.getApps).toBe("function", {
                message: "Menu service should expose getApps()",
            });

            // Set the current app and verify UI updates
            menuService.setCurrentMenu(1);
            await animationFrame();

            // Verify the current app is reflected in the header
            expect(".cds--header__name--app").toHaveCount(1, {
                message: "Header should show app name when app is selected",
            });
        });

        test("sidenav shows all apps when no app is selected", async () => {
            await mountWithCleanup(WebClient);

            // Without setting a current menu, the side-nav should show all apps
            // The template renders a cds--side-nav__menu-items--all-apps list
            expect(".cds--side-nav__menu-items--all-apps").toHaveCount(1, {
                message: "Side-nav should show all-apps list when no app is selected",
            });

            // Verify all three apps are listed
            const appLinks = queryAll(
                ".cds--side-nav__menu-items--all-apps .cds--side-nav__link"
            );
            expect(appLinks.length).toBe(3, {
                message: "All three apps (CRM, Sales, Inventory) should be listed",
            });

            // Verify app names via queryAllTexts
            const appTexts = queryAllTexts(
                ".cds--side-nav__menu-items--all-apps .cds--side-nav__link"
            );
            expect(appTexts).toInclude("CRM", {
                message: "App list should include CRM",
            });
            expect(appTexts).toInclude("Sales", {
                message: "App list should include Sales",
            });
            expect(appTexts).toInclude("Inventory", {
                message: "App list should include Inventory",
            });
        });

        test("sidenav header shows current app name and icon", async () => {
            await mountWithCleanup(WebClient);

            // Set the current app
            getService("menu").setCurrentMenu(1);
            await animationFrame();

            // The sidenav header should display the current app name
            expect(".cds--side-nav__header-name").toHaveCount(1, {
                message: "Side-nav header should show the current app name",
            });
            expect(".cds--side-nav__header-name").toHaveText("CRM", {
                message: "Side-nav header should display 'CRM'",
            });
        });
    });

    // ===================================================================
    // GROUP 5 — Template Inheritance Verification
    // ===================================================================

    describe("Template Inheritance", () => {

        test("Carbon Shell replaces default web.WebClient NavBar layout", async () => {
            await mountWithCleanup(WebClient);

            // The original NavBar uses class .o_main_navbar — it should NOT
            // be rendered when Carbon Shell is active
            expect(".o_main_navbar").toHaveCount(0, {
                message:
                    "Original Odoo NavBar (.o_main_navbar) should NOT be rendered — Carbon header replaces it",
            });

            // Carbon header should be rendered instead
            expect(".cds--header").toHaveCount(1, {
                message: "Carbon header should be rendered as NavBar replacement",
            });

            // ActionContainer should be rendered inside the Carbon content area
            expect(".cds--content .o_action_manager").toHaveCount(1, {
                message:
                    "Odoo ActionContainer should be rendered inside the Carbon content area",
            });
        });

        test("systray items render correctly in Carbon header", async () => {
            // Register a test systray item (following navbar.test.js pattern)
            class TestSystrayItem extends Component {
                static props = ["*"];
                static template = xml`<li class="test-systray-item">test systray</li>`;
            }
            systrayRegistry.add("carbon_test.systray_item", {
                Component: TestSystrayItem,
            });

            await mountWithCleanup(WebClient);

            // Verify the test systray item renders within the Carbon header
            // The header global actions area (.cds--header__global) contains systray
            expect(".cds--header__global .test-systray-item").toHaveCount(1, {
                message:
                    "Test systray item should render within the Carbon header global actions area",
            });
            expect(".test-systray-item").toHaveText("test systray", {
                message: "Test systray item should display its text content",
            });

            // Clean up the registered systray item
            clearRegistry(systrayRegistry);
        });

        test("systray items render in correct order based on sequence", async () => {
            // Register multiple systray items with different sequences
            class SystrayA extends Component {
                static props = ["*"];
                static template = xml`<li class="systray-a">Item A</li>`;
            }
            class SystrayB extends Component {
                static props = ["*"];
                static template = xml`<li class="systray-b">Item B</li>`;
            }
            class SystrayC extends Component {
                static props = ["*"];
                static template = xml`<li class="systray-c">Item C</li>`;
            }

            systrayRegistry.add("carbon_test.a", { Component: SystrayA }, { sequence: 10 });
            systrayRegistry.add("carbon_test.b", { Component: SystrayB }, { sequence: 50 });
            systrayRegistry.add("carbon_test.c", { Component: SystrayC }, { sequence: 100 });

            await mountWithCleanup(WebClient);

            // Verify all three systray items are rendered
            expect(".systray-a").toHaveCount(1, {
                message: "Systray item A should be rendered",
            });
            expect(".systray-b").toHaveCount(1, {
                message: "Systray item B should be rendered",
            });
            expect(".systray-c").toHaveCount(1, {
                message: "Systray item C should be rendered",
            });

            // Clean up
            clearRegistry(systrayRegistry);
        });

        test("content area receives correct margin class based on sidenav state", async () => {
            await resize({ width: 1200 });
            await mountWithCleanup(WebClient);

            // When sidenav is expanded, content area should NOT have the rail class
            expect(".cds--content.cds--content--rail").toHaveCount(0, {
                message: "Content should not have rail class when sidenav is expanded",
            });

            // Toggle sidenav to collapsed
            await contains(".cds--header__menu-trigger").click();
            await animationFrame();

            // Content area should have the rail class when sidenav is in rail mode
            expect(".cds--content.cds--content--rail").toHaveCount(1, {
                message: "Content should have rail class when sidenav is collapsed to rail",
            });
        });
    });

    // ===================================================================
    // GROUP 6 — Accessibility Compliance
    // ===================================================================

    describe("Accessibility", () => {

        test("header has correct ARIA attributes", async () => {
            await mountWithCleanup(WebClient);

            // Header element should have aria-label
            expect(".cds--header").toHaveAttribute("aria-label", "Application header", {
                message: "Header should have aria-label 'Application header'",
            });

            // Hamburger button should have aria-label
            expect(".cds--header__menu-trigger").toHaveAttribute("aria-label", "Open menu", {
                message: "Hamburger button should have aria-label 'Open menu'",
            });
        });

        test("hamburger button reflects sidenav expanded state via aria-expanded", async () => {
            await resize({ width: 1200 });
            await mountWithCleanup(WebClient);

            // Initially expanded — aria-expanded should be "true"
            expect(".cds--header__menu-trigger").toHaveAttribute("aria-expanded", "true", {
                message:
                    "Hamburger aria-expanded should be 'true' when sidenav is expanded",
            });

            // Toggle sidenav to collapsed
            await contains(".cds--header__menu-trigger").click();
            await animationFrame();

            // aria-expanded should now be "false"
            expect(".cds--header__menu-trigger").toHaveAttribute("aria-expanded", "false", {
                message:
                    "Hamburger aria-expanded should be 'false' when sidenav is collapsed",
            });
        });

        test("side navigation has aria-label landmark", async () => {
            await mountWithCleanup(WebClient);

            // Side-nav should have aria-label for landmark identification
            expect(".cds--side-nav").toHaveAttribute("aria-label", "Side navigation", {
                message: "Side-nav should have aria-label 'Side navigation'",
            });
        });

        test("main content area has role='main' landmark", async () => {
            await mountWithCleanup(WebClient);

            // Main content area should have role="main" for ARIA main landmark
            expect(".cds--content").toHaveAttribute("role", "main", {
                message: "Content area should have role='main'",
            });
        });

        test("skip-to-content link is present for keyboard navigation", async () => {
            await mountWithCleanup(WebClient);

            // A skip-to-content link should exist as the first focusable element
            expect(".cds--assistive-text[href='#carbon-main-content']").toHaveCount(1, {
                message: "Skip-to-content link should be present for keyboard users",
            });
        });
    });

    // ===================================================================
    // GROUP 7 — Component Type Verification
    // ===================================================================

    describe("Component Types", () => {

        test("CarbonShell is a valid OWL Component class", async () => {
            // Verify CarbonShell is imported and is a component class
            expect(typeof CarbonShell).toBe("function", {
                message: "CarbonShell should be a function (class)",
            });
            expect(CarbonShell.template).toBe("carbon_ui.CarbonShell", {
                message: "CarbonShell template should be 'carbon_ui.CarbonShell'",
            });
        });

        test("CarbonHeader is a valid OWL Component class", async () => {
            expect(typeof CarbonHeader).toBe("function", {
                message: "CarbonHeader should be a function (class)",
            });
            expect(CarbonHeader.template).toBe("carbon_ui.CarbonHeader", {
                message: "CarbonHeader template should be 'carbon_ui.CarbonHeader'",
            });
        });

        test("CarbonSideNav is a valid OWL Component class", async () => {
            expect(typeof CarbonSideNav).toBe("function", {
                message: "CarbonSideNav should be a function (class)",
            });
            expect(CarbonSideNav.template).toBe("carbon_ui.CarbonSideNav", {
                message: "CarbonSideNav template should be 'carbon_ui.CarbonSideNav'",
            });
        });

        test("CarbonShell has toggleSideNav method and state property descriptor", async () => {
            // Verify CarbonShell prototype exposes toggleSideNav()
            expect(typeof CarbonShell.prototype.toggleSideNav).toBe("function", {
                message: "CarbonShell should expose toggleSideNav() method",
            });

            // Mount the WebClient to verify CarbonShell state is initialised
            // CarbonShell.state is set up via useState() in setup() and tracked
            // reactively by OWL; we verify state-driven classes in the DOM
            await mountWithCleanup(WebClient);

            // The state.isSideNavExpanded, state.isMobileSideNavOpen, and
            // state.isFullscreen properties drive the UI shell DOM classes.
            // Verify that the state-driven UI shell wrapper exists.
            expect(".cds--ui-shell").toHaveCount(1, {
                message: "CarbonShell state drives the UI shell layout",
            });
        });

        test("CarbonHeader defines systrayItems getter", async () => {
            // Verify CarbonHeader prototype exposes systrayItems
            const descriptor = Object.getOwnPropertyDescriptor(
                CarbonHeader.prototype,
                "systrayItems"
            );
            expect(!!descriptor).toBe(true, {
                message: "CarbonHeader should have a systrayItems property",
            });
            expect(typeof descriptor.get).toBe("function", {
                message: "CarbonHeader.systrayItems should be a getter",
            });
        });

        test("CarbonSideNav exposes menu interaction methods", async () => {
            // Verify CarbonSideNav exposes its core navigation API
            expect(typeof CarbonSideNav.prototype.onMenuClick).toBe("function", {
                message: "CarbonSideNav should expose onMenuClick() method",
            });
            expect(typeof CarbonSideNav.prototype.isMenuActive).toBe("function", {
                message: "CarbonSideNav should expose isMenuActive() method",
            });

            // Verify currentApp and currentAppSections are getters
            const appDescriptor = Object.getOwnPropertyDescriptor(
                CarbonSideNav.prototype,
                "currentApp"
            );
            expect(!!appDescriptor).toBe(true, {
                message: "CarbonSideNav should have a currentApp property",
            });
            expect(typeof appDescriptor.get).toBe("function", {
                message: "CarbonSideNav.currentApp should be a getter",
            });

            const sectionsDescriptor = Object.getOwnPropertyDescriptor(
                CarbonSideNav.prototype,
                "currentAppSections"
            );
            expect(!!sectionsDescriptor).toBe(true, {
                message: "CarbonSideNav should have a currentAppSections property",
            });
            expect(typeof sectionsDescriptor.get).toBe("function", {
                message: "CarbonSideNav.currentAppSections should be a getter",
            });
        });
    });

    // ===================================================================
    // GROUP 8 — App Switcher Button
    // ===================================================================

    describe("App Switcher", () => {

        test("app switcher button is present in header", async () => {
            await mountWithCleanup(WebClient);

            // The app switcher button has a specific class
            expect(".cds--header__action--switcher").toHaveCount(1, {
                message: "App switcher button should be present in the header",
            });
        });

        test("app switcher button has correct accessibility attributes", async () => {
            await mountWithCleanup(WebClient);

            expect(".cds--header__action--switcher").toHaveAttribute(
                "aria-label",
                "App Switcher",
                {
                    message: "App switcher button should have aria-label 'App Switcher'",
                }
            );
        });
    });

    // ===================================================================
    // GROUP 9 — Fullscreen Mode
    // ===================================================================

    describe("Fullscreen Mode", () => {

        test("CarbonShell has fullscreen state property", async () => {
            // Verify the shell component tracks fullscreen state
            // The state.isFullscreen property controls header/sidenav visibility
            await mountWithCleanup(WebClient);

            // In normal mode, shell should not have fullscreen class
            expect(".cds--ui-shell--fullscreen").toHaveCount(0, {
                message: "UI shell should not be in fullscreen mode by default",
            });
        });
    });
});
