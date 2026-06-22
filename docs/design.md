# UI/UX Design: trading-tom-v2

**Status:** Draft for MVP build
**Owner:** UI/UX Design (acting against locked PRD at `docs/PRD.md`)
**Last updated:** 2026-06-22

This document specifies the complete user interface and experience for trading-tom-v2: a multi-user paper-trading platform with two roles (Admin, Regular User), a shared automated trading engine, and an admin-only backtest tool. It is designed against `docs/PRD.md` section by section. Where the PRD is silent, a decision is made and flagged inline and consolidated in Section 9 (Assumptions).

---

## Table of Contents

1. [Design Principles & Overall Approach](#1-design-principles--overall-approach)
2. [Design System Foundations](#2-design-system-foundations)
3. [Information Architecture & Navigation](#3-information-architecture--navigation)
4. [Screen-by-Screen Specs with Wireframes](#4-screen-by-screen-specs-with-wireframes)
5. [Key Interaction Patterns](#5-key-interaction-patterns)
6. [Data Display Conventions](#6-data-display-conventions)
7. [Responsive Behavior](#7-responsive-behavior)
8. [Accessibility](#8-accessibility)
9. [Assumptions](#9-assumptions)

---

## 1. Design Principles & Overall Approach

### 1.1 Who this is for

Two distinct audiences, both at a desk most of the time:

- **Regular User**: a curious observer of a strategy they don't control. They check in periodically (daily/weekly), not constantly — there's no reason to refresh every minute since the engine only acts once a day after market close. Their dominant emotional state is "did the engine do anything since I last looked, and how am I doing." They need **legibility and trust**, not trading-floor adrenaline. They never act on this UI beyond reading.
- **Admin**: an operator running the platform for a small group of people. They need **operational confidence** — is the engine healthy, did the last run succeed, can I fix a stuck account, can I fund someone quickly. Their dominant task is administration, not analysis, except when they deliberately switch into the backtest tool to evaluate strategy performance.

Both audiences are sophisticated about money/numbers (this is a finance tool) but not necessarily about trading jargon — hence "exit reason" badges get human-readable labels, not just enum codes (Section 6).

### 1.2 Visual tone

**Clarity and trust over excitement.** This is a paper-trading observability tool, not a trading terminal trying to look thrilling. Reference points: the calm density of a brokerage statement (Schwab/Fidelity dashboards) crossed with the legibility of a modern SaaS analytics product (Linear, Stripe Dashboard) — not a flashy crypto-app aesthetic, not Bloomberg-terminal density.

Concretely:
- **Light theme, professional neutral base** (off-white/near-white background, slate-gray text, single restrained accent color for primary actions) — not a default "finance = dark mode" assumption. Dark mode is explicitly out of scope for MVP (Section 9, assumption) — most users check this during the day at a desk; a dark terminal aesthetic would also wrongly imply real-time/HFT urgency this product deliberately does not have.
- **Numbers are the hero.** Every screen's job is to get the user to a correct number (their balance, a trade's P&L, a backtest's return) as fast as possible, with full precision available on demand (hover/expand) and a clean rounded default (Section 6).
- **Green/red is supportive, not load-bearing.** Gains and losses are always paired with a +/− sign and are never the only signal of direction (Section 8 — accessibility).
- **No artificial urgency.** No countdown timers, no "act now" language — appropriate for a read-only observation product where the user literally cannot place a trade.
- **Admin density is higher than User density.** Admin screens (user lists, run logs, trade logs) favor compact tables with more columns visible at once. Regular User screens favor a bit more breathing room since their tasks are fewer and less frequent.

### 1.3 Platform approach

- **Web responsive only**, per PRD 1.4. Designed mobile-first up to a "data-dense desktop" breakpoint, but desktop is the primary expected context (an admin operating a local Docker Compose deployment is almost certainly at a desktop; a regular user checking their dashboard may be on a phone browser occasionally).
- **No native app chrome assumptions** — standard browser, responsive CSS, no platform-specific gestures.
- Built as a React SPA (per PRD tech stack) with client-side routing; this doc specifies routes, not implementation, but route names are chosen to map cleanly to React Router paths.

### 1.4 The single most important interaction

For a Regular User: **"How am I doing, and why?"** — answered by the dashboard headline number (total value, P&L) plus a same-screen sample of recent activity, with one click to the full trade history for the "why."

For an Admin: **"Is everything running correctly, and can I fix the one thing that's wrong?"** — answered by the engine status view (Section 4.10) being reachable in one click from anywhere in the admin shell, and by every list view (users, trades, backtests) supporting fast filtering down to the one row that matters.

---

## 2. Design System Foundations

### 2.1 Color palette

A small, restrained palette. Named tokens below (use as CSS variables / design tokens in implementation).

**Neutrals (base UI):**

| Token | Hex | Usage |
|---|---|---|
| `neutral-0` | `#FFFFFF` | Card/surface background |
| `neutral-50` | `#F7F8FA` | Page background |
| `neutral-100` | `#EEF0F3` | Subtle section backgrounds, table stripe |
| `neutral-200` | `#E2E5EA` | Borders, dividers |
| `neutral-300` | `#C7CCD4` | Disabled borders, placeholder icons |
| `neutral-500` | `#8A93A1` | Secondary text, placeholder text |
| `neutral-700` | `#4B5563` | Body text on light surfaces |
| `neutral-900` | `#1A1F2B` | Primary text, headings |

**Brand / primary accent:**

| Token | Hex | Usage |
|---|---|---|
| `primary-600` | `#2554C7` | Primary buttons, links, active nav, focus rings |
| `primary-700` | `#1E429E` | Primary button hover/active |
| `primary-50` | `#EAF0FD` | Selected row/tab background, primary-tinted badges |

Rationale: a confident, slightly desaturated blue — reads as "trustworthy finance app" (same family as most brokerage brands) without being a literal copy of any one brand. Avoided green-as-primary specifically so it never competes visually with "green = gain."

**Semantic — gains/losses (the most important colors in the product):**

| Token | Hex | Usage |
|---|---|---|
| `gain-600` | `#15803D` | Positive P&L text, up-arrows, BUY-side accents where relevant |
| `gain-50` | `#EDFAF1` | Positive P&L cell/badge background tint |
| `loss-600` | `#C0273C` | Negative P&L text, down-arrows |
| `loss-50` | `#FDEDEF` | Negative P&L cell/badge background tint |
| `neutral-500` | `#8A93A1` | Exactly-zero P&L (no gain, no loss) |

Both `gain-600` and `loss-600` are tuned to pass WCAG AA contrast (≥4.5:1) against both `neutral-0` white and `neutral-50` backgrounds (Section 8).

**Semantic — status/feedback:**

| Token | Hex | Usage |
|---|---|---|
| `warning-600` | `#B45309` / bg `#FEF3E2` | Warnings (e.g. zero-state nudges, partial-fill notices) |
| `danger-600` | `#C0273C` / bg `#FDEDEF` | Errors, destructive actions (delete user), failed engine runs |
| `info-600` | `#2554C7` / bg `#EAF0FD` | Informational banners, queued/running status |
| `success-600` | `#15803D` / bg `#EDFAF1` | Confirmations, completed runs (shares tokens with gain — both mean "good outcome") |

**Role accent (subtle, for shell-level orientation only):** Admin shell uses a thin `neutral-900` top bar accent vs. User shell's `primary-600` thin accent, so a screenshot alone hints which mode you're in. This is decorative wayfinding, not a heavy theme split — see Section 3.2.

### 2.2 Typography

System-first stack for performance and platform-native feel, finance-tool legible:

```
font-family: "Inter", -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
font-family (numeric/tabular contexts): "Inter", with font-feature-settings: "tnum" 1;  /* tabular figures for column alignment */
```

Tabular numerals are mandatory in every table/column of numbers (price, qty, P&L) so digits align vertically — small detail, large legibility win in a data-dense finance table.

**Type scale:**

| Token | Size / Line-height | Weight | Usage |
|---|---|---|---|
| `display` | 32px / 40px | 700 | Headline number only (e.g. Total Value on dashboard) |
| `h1` | 24px / 32px | 600 | Page titles |
| `h2` | 18px / 26px | 600 | Section/card headers |
| `h3` | 15px / 22px | 600 | Sub-section headers, table group headers |
| `body` | 14px / 20px | 400 | Default body text, table cells |
| `body-strong` | 14px / 20px | 600 | Emphasized cell text (e.g. ticker symbol) |
| `small` | 12px / 16px | 400 | Helper text, timestamps, badge labels |
| `mono-data` (optional) | 13px / 18px | 500 | Reserved for raw IDs (engine_run_id, trade id) if shown |

Base table row height: 40px desktop / 48px on touch-sized viewports (more tap target room).

### 2.3 Spacing & layout grid

8px base unit.

| Token | Value |
|---|---|
| `space-1` | 4px |
| `space-2` | 8px |
| `space-3` | 12px |
| `space-4` | 16px |
| `space-5` | 24px |
| `space-6` | 32px |
| `space-7` | 48px |
| `space-8` | 64px |

- Page content max-width: **1280px**, centered, with 24px side gutters below that width.
- Card padding: 24px (desktop), 16px (mobile).
- Standard corner radius: 8px for cards/inputs/buttons, 999px (full) for badges/pills.
- Standard border: 1px solid `neutral-200`.
- Elevation: cards use a single soft shadow (`0 1px 2px rgba(16,24,40,0.06), 0 1px 3px rgba(16,24,40,0.08)`), modals use a stronger shadow (`0 8px 24px rgba(16,24,40,0.18)`). No more than two elevation levels — avoid a "floating everything" look.

### 2.4 Core reusable components

**Buttons**

| Variant | Use | Style |
|---|---|---|
| Primary | One per view/section — the main action (Create User, Fund Account, Run Backtest, Trigger Run Now) | Solid `primary-600`, white text, `primary-700` on hover, 8px radius, 14px/600 |
| Secondary | Supporting actions (Cancel, Export, Edit) | White bg, `neutral-300` border, `neutral-900` text |
| Destructive | Delete/Deactivate user | White bg, `loss-600` border + text; solid `loss-600` only inside a confirm dialog's final confirm button |
| Ghost/Link | Inline table-row actions ("View", "Fund") | No border/bg, `primary-600` text, underline on hover |
| Disabled | Any variant mid-action or blocked | 40% opacity, `cursor: not-allowed`, no hover state change |

All buttons: 40px height (desktop), 44px (mobile/touch), 16px horizontal padding, visible focus ring (`2px solid primary-600` offset 2px) for keyboard nav (Section 8).

**Tables**

The workhorse component — trade history, user lists, run history, backtest lists all use one shared table pattern:
- Sticky header row, `neutral-50` background, `small`/600 weight, uppercase letter-spacing 0.02em, sortable columns show a subtle caret.
- Zebra-free by default (relies on row borders, not stripes, to stay calmer) — `1px solid neutral-200` row dividers. Optional `neutral-100` stripe only on very dense admin tables (aggregate all-trades view) where row-tracking across many columns benefits from it.
- Row hover: `neutral-50` background, cursor pointer if row is clickable (drills into detail).
- Numeric columns right-aligned with tabular figures; text columns left-aligned; status/badge columns centered.
- Empty state: centered icon + one-line message + (if applicable) a primary action, rendered inside the table's body area, not a separate page.
- Loading state: skeleton rows (gray animated placeholder bars), not a spinner blocking the whole table — keeps header/filters interactive.

**Cards**

White surface, 8px radius, 1px `neutral-200` border, 24px padding, optional header row (`h2` title + optional right-aligned action). Used for dashboard summary blocks, the positions panel, the backtest metrics summary.

**Form inputs**

- Text/number/date inputs: 40px height, 1px `neutral-300` border, 8px radius, `primary-600` border + ring on focus, `loss-600` border + helper text on validation error.
- Label above input (`small`/600, `neutral-700`), helper/error text below input (`small`, `neutral-500` normally / `loss-600` on error).
- Currency inputs show a fixed `$` prefix glyph inside the field, right-pad for decimals; preset-amount buttons (Section 4.7) sit below as quick-fill chips.
- Select/dropdown: same shell as text input, chevron icon right-aligned.
- Date range pickers: two date inputs side by side ("From" / "To") with inline validation (Section 5).

**Badges / pills**

Full-radius (999px) pills, `small` text/600 weight, 4px vertical / 10px horizontal padding. Two families:

1. **Exit/entry reason badges** (Section 6) — neutral-tinted by default, colored only where it reinforces meaning (e.g. profit-target badge gets a faint `gain-50` tint, stop-loss gets `loss-50` tint, max-hold and trend-invalidation stay neutral since they're outcome-agnostic).
2. **Status badges** — account status (Active/Deactivated), engine run status (Queued/Running/Complete/Failed), backtest status — use the status colors from 2.1 (`info-600` running, `success-600` complete, `danger-600` failed, `neutral-500` deactivated/inactive).

**Charts**

One chart type for MVP: the **equity curve line chart** (backtest results, Section 4.13). Single line, `primary-600` stroke 2px, light `primary-50` area fill beneath (subtle, ~15% opacity), gridlines `neutral-200` dashed, axis labels `small`/`neutral-500`. Hover shows a vertical guide line + tooltip card with date + portfolio value. No 3D, no gradients beyond the flat area fill, no animation beyond a one-time draw-in on first render.

**Modals**

Centered overlay, max-width 480px (forms) or 720px (richer content), `neutral-900` at 40% opacity scrim behind, white card with 12px radius (slightly larger than base 8px to read as "floating"), header (`h2` + close `×`), body, footer with right-aligned action buttons (Secondary "Cancel" then Primary/Destructive confirm, in that left-to-right order). Closes on scrim click, `Esc` key, or explicit Cancel — never on accidental outside-click during an async submit (button shows loading state, modal becomes non-dismissible until the request resolves, to prevent double-submits and lost context).

**Toasts**

Bottom-right stack (desktop) / bottom-center single (mobile), auto-dismiss after 5s (success/info) or persist until manually dismissed (errors), max 3 stacked, slide-in/fade-out transition. Icon + message + optional single action link ("View" / "Undo" where applicable) + close `×`. Color-coded left border (4px) using the status colors from 2.1.

**Navigation shell**

Left sidebar (desktop, collapsible to icon-rail at narrow widths) containing role-appropriate nav items (Section 3), top bar containing current page title, the logged-in user's name/role badge, and a logout control. Specified fully in Section 3 and the wireframes in Section 4.

---

## 3. Information Architecture & Navigation

### 3.1 Sitemap / route list

```
/login                              Public. Login form.

──── Regular User (role: user) ────
/dashboard                          User home: balance summary + positions + recent trades
/positions                          Full open positions detail view
/trades                             Full paginated/filterable trade history

──── Admin (role: admin) ────
/admin                              Redirects to /admin/users (admin "home")
/admin/users                        User management list
/admin/users/:userId                Per-user inspector (balances/positions/trades for that user)
/admin/trades-today                 Aggregate all-users trades-today view
/admin/engine                       Engine status / run history + manual trigger
/admin/backtests                    Backtest run list
/admin/backtests/new                Backtest submission form (could be a modal — see 4.12 note)
/admin/backtests/:backtestId        Backtest results page

──── Shared ────
/                                   Redirects to /dashboard (user) or /admin/users (admin) based on role
/logout                             Action, not a page — clears tokens, redirects to /login
* (404)                             Not-found page with link back to home
```

Notes:
- An Admin does **not** get a separate `/dashboard` for "their own" funded account in MVP nav — per PRD 2.1, an admin who also holds a funded account is just another user account; an Admin can view their own account the same way they view anyone else's: via `/admin/users/:userId` using their own user id. **Assumption**: we do not duplicate Regular-User dashboard nav inside the Admin shell (Section 9, item 1). If the business wants admins to casually monitor their own paper account without the inspector chrome, that's a fast v1.1 add (a "view as me" shortcut), not an MVP requirement.
- `/admin/backtests/new` is listed as its own route for deep-linkability, but is presented as a modal triggered from `/admin/backtests` (Section 4.12) — the route exists so the modal state is URL-addressable/bookmarkable and survives a refresh, not because it needs a fully distinct page chrome.

### 3.2 Navigation differences: Admin vs. Regular User

Both roles share the same shell skeleton (left sidebar + top bar) for consistency and lower engineering cost, but with different nav item sets and a subtle accent difference (Section 2.1) so it's never ambiguous which mode you're in — important since the same human could plausibly hold both an admin login and a personal funded account in two different browser sessions.

**Regular User sidebar:**
```
[Logo/Wordmark]
─────────────────
  Dashboard          (/dashboard)
  Positions          (/positions)
  Trade History       (/trades)
─────────────────
  [user avatar/initials]  Jane Doe
  Regular User
  Log out
```

**Admin sidebar:**
```
[Logo/Wordmark]  ADMIN
─────────────────
  Users               (/admin/users)
  Trades Today         (/admin/trades-today)
  Engine               (/admin/engine)
  Backtests            (/admin/backtests)
─────────────────
  [user avatar/initials]  Sam Admin
  Admin
  Log out
```

No role-switcher UI — a user with an admin login simply sees the admin nav; there is no "view as user" toggle in MVP (would need its own design pass; not requested).

### 3.3 Logged-out experience

Hitting any authenticated route while logged out (no valid access/refresh token) redirects to `/login`, preserving the originally-requested path as a `?next=` param so a successful login returns the user to where they were headed (standard pattern). The `/login` route itself is the **only** unauthenticated route besides the 404 — there is no public marketing page, no self-service signup link anywhere (per PRD 2.2, "no self-service signup" is intentional and the login screen must not imply otherwise).

### 3.4 Route guard summary (for engineering handoff)

| Route prefix | Required role | Behavior if unauthorized |
|---|---|---|
| `/login` | none (public) | n/a — if already logged in, redirect to home |
| `/dashboard`, `/positions`, `/trades` | `user` or `admin` (any authenticated) | Redirect to `/login` if no valid session |
| `/admin/*` | `admin` only | A `user`-role token hitting `/admin/*` client-side is redirected to `/dashboard`; this mirrors the server's `403` (PRD FR-12) — the UI must never rely on hiding the nav link alone |

---

## 4. Screen-by-Screen Specs with Wireframes

All wireframes below are **ASCII art**, chosen for consistency and because it renders identically everywhere this doc is read (terminal, GitHub, plain text editor) without needing a browser. Each screen lists: purpose, key states, and the wireframe(s) for its primary state plus called-out alternate states (loading/empty/error/zero-state) per the PRD's explicit requirements.

Layout convention used throughout: outer box = browser viewport at desktop width (~1280px target, drawn at reduced scale); left rail = nav sidebar; top strip = page header/breadcrumb; remaining area = page content.

### 4.1 Login screen

**Purpose:** Sole entry point to the product (PRD 2.2, 3.4). Must clearly distinguish three failure states: invalid credentials, deactivated account, and (implicitly) a healthy success path. No signup link anywhere on this screen.

**States:** default, submitting (button loading), invalid-credentials error, deactivated-account error, (optional) rate-limited/lockout notice per PRD 9.1.

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                    │
│                                                                    │
│                         ┌──────────────────────────┐              │
│                         │      ◆ trading-tom         │              │
│                         │                            │              │
│                         │  Sign in                  │              │
│                         │  Paper-trading platform   │              │
│                         │                            │              │
│                         │  Email                    │              │
│                         │  ┌──────────────────────┐  │              │
│                         │  │ jane@example.com     │  │              │
│                         │  └──────────────────────┘  │              │
│                         │                            │              │
│                         │  Password                 │              │
│                         │  ┌──────────────────────┐  │              │
│                         │  │ ••••••••••           │  │              │
│                         │  └──────────────────────┘  │              │
│                         │                            │              │
│                         │  ┌──────────────────────┐  │              │
│                         │  │      Sign in          │  │              │
│                         │  └──────────────────────┘  │              │
│                         │                            │              │
│                         │  Forgot your password?     │              │
│                         │  Contact your admin.       │              │
│                         │                            │              │
│                         └──────────────────────────┘              │
│                                                                    │
└──────────────────────────────────────────────────────────────────┘
```

Card is centered, 400px wide, on `neutral-50` page background — no marketing copy, no imagery, deliberately spare. "Forgot your password? Contact your admin." is static help text, not a link (PRD 2.2 — no email-based reset flow exists, so the UI must not imply one).

**Error state — invalid credentials** (PRD FR-8 AC2 — generic message, does not reveal whether the email exists):

```
                         ┌──────────────────────────┐
                         │      ◆ trading-tom         │
                         │                            │
                         │  Sign in                  │
                         │                            │
                         │  ┌────────────────────────┐│
                         │  │⚠ Invalid email or      ││   ← danger-600 text,
                         │  │  password.              ││     danger-50 bg banner,
                         │  └────────────────────────┘│     inside the card, above
                         │                            │     the fields
                         │  Email                    │
                         │  ┌──────────────────────┐  │
                         │  │ jane@example.com     │  │   ← red border on both
                         │  └──────────────────────┘  │     fields (no field-level
                         │  Password                 │     distinction — don't
                         │  ┌──────────────────────┐  │     hint which one is wrong)
                         │  │                       │  │
                         │  └──────────────────────┘  │
                         │  ┌──────────────────────┐  │
                         │  │      Sign in          │  │
                         │  └──────────────────────┘  │
                         └──────────────────────────┘
```

**Error state — deactivated account** (PRD FR-8 AC3 — distinct message from invalid credentials, per explicit AC):

```
                         ┌──────────────────────────┐
                         │      ◆ trading-tom         │
                         │                            │
                         │  Sign in                  │
                         │                            │
                         │  ┌────────────────────────┐│
                         │  │⊘ This account has been ││   ← warning/neutral tone,
                         │  │  disabled. Contact your ││     not "danger red" —
                         │  │  admin for access.      ││     this isn't the user's
                         │  └────────────────────────┘│     fault, no need to alarm
                         │                            │
                         │  Email                    │
                         │  ┌──────────────────────┐  │
                         │  │ jane@example.com     │  │
                         │  └──────────────────────┘  │
                         │  ...                       │
                         └──────────────────────────┘
```

Password field is cleared on any failed attempt (standard security hygiene); email field is preserved. Submit button shows an inline spinner + "Signing in…" label while the request is in flight, and is disabled to prevent double submission.

---

### 4.2 Regular User dashboard

**Purpose:** PRD FR-9, FR-10 — primary landing page. Headline balance numbers, P&L, a compact positions panel, and a recent-trades preview, with clear navigation to the full Positions and Trade History pages. Must handle the **$0 zero-state** explicitly (FR-9 AC2).

**States:** funded-and-active (default), zero-balance (not yet funded), loading (skeleton), data-fetch error (e.g. price feed down — show last-known values with a staleness notice, never a blank page).

```
┌──────────────────────────────────────────────────────────────────────┐
│ ◆ trading-tom          Dashboard                    Jane Doe ▾  ⏻   │
├───────────┬────────────────────────────────────────────────────────┤
│ Dashboard │  Dashboard                                              │
│ Positions │  As of last engine run: Jun 22, 2026 · 5:02 PM ET       │
│ Trades    │                                                          │
│           │  ┌────────────────┐ ┌────────────────┐ ┌──────────────┐│
│           │  │ TOTAL VALUE     │ │ CASH BALANCE    │ │ EQUITY VALUE  ││
│           │  │ $108,420.55     │ │ $42,110.20      │ │ $66,310.35    ││
│           │  └────────────────┘ └────────────────┘ └──────────────┘│
│           │                                                          │
│           │  ┌────────────────────────┐ ┌────────────────────────┐ │
│           │  │ REALIZED P&L (lifetime) │ │ UNREALIZED P&L (open)   │ │
│           │  │ ▲ +$6,420.55 (+6.3%)    │ │ ▲ +$1,910.10 (+2.97%)   │ │
│           │  │     (gain-600 text)     │ │     (gain-600 text)     │ │
│           │  └────────────────────────┘ └────────────────────────┘ │
│           │                                                          │
│           │  ┌──────────────────────────────────────────────────┐  │
│           │  │ Open Positions (4)                  View all →   │  │
│           │  ├──────────────────────────────────────────────────┤  │
│           │  │ TICKER  QTY  ENTRY    CURRENT  DAYS  UNREAL. P&L  │  │
│           │  │ AAPL    40   $189.20  $196.50  5d    ▲ +$292 +3.9%│  │
│           │  │ MSFT    18   $412.10  $405.00  2d    ▼ −$128 −1.7%│  │
│           │  │ SPY     25   $521.40  $529.80  8d    ▲ +$210 +1.6%│  │
│           │  │ NVDA    12   $118.05  $123.90  1d    ▲ +$70  +5.0%│  │
│           │  └──────────────────────────────────────────────────┘  │
│           │                                                          │
│           │  ┌──────────────────────────────────────────────────┐  │
│           │  │ Recent Trades                       View all →   │  │
│           │  ├──────────────────────────────────────────────────┤  │
│           │  │ DATE    SIDE  TICKER  QTY  PRICE   REASON   P&L  │  │
│           │  │ Jun 22  SELL  TSLA    15   $241.30 [Profit  ▲+$ │  │
│           │  │                                      Target]  312│  │
│           │  │ Jun 22  BUY   NVDA    12   $118.05 [Trend     —  │  │
│           │  │                                      Entry]      │  │
│           │  │ Jun 20  SELL  AMD     30   $98.10  [Stop     ▼-$ │  │
│           │  │                                      Loss]    84 │  │
│           │  └──────────────────────────────────────────────────┘  │
└───────────┴────────────────────────────────────────────────────────┘
```

Layout notes:
- The "As of last engine run" timestamp is always visible near the page title — it sets correct expectations that this is not real-time data (reinforces PRD 9.3's intentional non-real-time design).
- Three top stat cards (Total Value, Cash, Equity) are neutral-toned (this is "where you stand," not "how you did") — the two P&L cards below are the only ones that take on gain/loss coloring, since P&L is the "how did I do" framing.
- Open Positions panel shows at most 5 rows (matches the PRD 4.4 max-concurrent-positions cap, so it never needs internal scrolling) with a "View all →" link to `/positions`. Recent Trades panel shows the last 5 trades with a "View all →" link to `/trades`.
- Exit-reason and entry-reason values render as colored badges per Section 6.3, not raw enum strings.

**Zero-state (not yet funded)** — PRD FR-9 AC2, explicit requirement:

```
┌──────────────────────────────────────────────────────────────────────┐
│ ◆ trading-tom          Dashboard                    Jane Doe ▾  ⏻   │
├───────────┬────────────────────────────────────────────────────────┤
│ Dashboard │  Dashboard                                              │
│ Positions │                                                          │
│ Trades    │                                                          │
│           │            ┌──────────────────────────────┐             │
│           │            │            🪙                  │             │
│           │            │                                │             │
│           │            │   You're not funded yet        │             │
│           │            │                                │             │
│           │            │   Your account balance is      │             │
│           │            │   $0.00. The trading engine    │             │
│           │            │   only trades on funded        │             │
│           │            │   accounts. Ask your admin to  │             │
│           │            │   load virtual cash into your  │             │
│           │            │   account to get started.      │             │
│           │            │                                │             │
│           │            │   Cash: $0.00  Equity: $0.00   │             │
│           │            │   Total: $0.00                 │             │
│           │            └──────────────────────────────┘             │
│           │                                                          │
│           │  (No Open Positions or Recent Trades panels shown —      │
│           │   nothing has ever happened on this account.)            │
└───────────┴────────────────────────────────────────────────────────┘
```

This is a dedicated empty-state card, not the normal three-stat-card layout with zeros silently displayed — per PRD's explicit instruction that a $0 user must see "a clear 'not yet funded' zero-state," not a page that merely looks broken. Positions and Recent Trades panels are omitted entirely in this state (there's nothing to show and an empty table would read as a bug); they reappear automatically the moment the account is funded and has any activity.

**Loading state:** the three top stat cards and both panels render as skeleton placeholders (gray pulsing bars matching each element's final shape) for up to ~1s (PRD 9.3 target); no full-page spinner.

**Stale-data notice (data-fetch error / price feed degraded):** if the backend signals that the latest mark-to-market price fetch failed (PRD 7.3 — fetch failures are logged but must not crash), the dashboard still renders using the last successfully cached values and shows a small inline warning banner under the page title: `⚠ Prices last updated Jun 21, 2026 — today's price refresh failed. Showing last known values.` Cash/realized figures (which don't depend on live price fetch) are never affected by this — only equity_value/unrealized P&L are flagged as potentially stale.

---

### 4.3 Regular User trade history

**Purpose:** PRD FR-11, 5.3 — full paginated, filterable, newest-first trade log for the logged-in user only.

**States:** populated (default), filtered, empty (no trades ever — distinct from zero-balance zero-state on the dashboard, since a user could be funded with no signals fired yet), loading.

```
┌──────────────────────────────────────────────────────────────────────┐
│ ◆ trading-tom          Trade History                Jane Doe ▾  ⏻   │
├───────────┬────────────────────────────────────────────────────────┤
│ Dashboard │  Trade History                                          │
│ Positions │                                                          │
│ Trades    │  Ticker          Date range                             │
│           │  ┌──────────┐    ┌──────────┐ to ┌──────────┐  [Apply]  │
│           │  │ All ▾    │    │ 2026-01-01│   │ 2026-06-22│  [Clear] │
│           │  └──────────┘    └──────────┘    └──────────┘           │
│           │                                                          │
│           │  ┌──────────────────────────────────────────────────┐  │
│           │  │DATE    SIDE TICKER QTY PRICE  VALUE   REASON   P&L│  │
│           │  ├──────────────────────────────────────────────────┤  │
│           │  │Jun 22  SELL TSLA   15  $241.30 $3,619.50          │  │
│           │  │                            [Profit Target] ▲+$312│  │
│           │  │Jun 22  BUY  NVDA   12  $118.05 $1,416.60          │  │
│           │  │                            [Trend Entry]      —  │  │
│           │  │Jun 20  SELL AMD    30  $98.10  $2,943.00          │  │
│           │  │                            [Stop Loss]    ▼ -$84  │  │
│           │  │Jun 18  SELL AAPL   20  $182.40 $3,648.00          │  │
│           │  │                            [Max Hold Reached] ▲+$61│ │
│           │  │Jun 15  BUY  AAPL   20  $178.95 $3,579.00          │  │
│           │  │                            [Trend Entry]      —  │  │
│           │  │Jun 12  SELL QQQ    10  $445.10 $4,451.00          │  │
│           │  │                       [Trend Reversed] ▲ +$112    │  │
│           │  │  ... 142 more trades                              │  │
│           │  └──────────────────────────────────────────────────┘  │
│           │                                                          │
│           │           ◂ Prev   Page 1 of 8   Next ▸     [25 ▾ /pg] │
└───────────┴────────────────────────────────────────────────────────┘
```

Column set matches PRD 5.2 fields relevant to a user-facing view: Date (`executed_at`, bar date), Side, Ticker, Qty, Price, Value (`trade_value`), Reason (`signal_reason`, rendered as a badge per Section 6.3), realized P&L (only populated on SELL rows, per PRD 5.2 — BUY rows show an em-dash `—` in that column, not `$0.00`, to avoid implying a BUY had zero P&L rather than "not applicable").

Filters: ticker (dropdown, populated from tickers the user has actually traded — not the full universe, since most users only ever touch a handful), and a date range (From/To). "Apply" runs the filter (server-side query, not client-side, since history can run to thousands of rows per PRD 9.3); "Clear" resets to the unfiltered newest-first view. Filter state is reflected in the URL query string (`/trades?ticker=AAPL&from=2026-01-01&to=2026-06-22`) so a filtered view is shareable/bookmarkable and survives refresh.

Pagination: 25 rows/page default (selectable 25/50/100), standard Prev/Next + "Page X of Y," page number resets to 1 whenever a filter changes.

**Empty state (filtered to no results):**

```
│           │  ┌──────────────────────────────────────────────────┐  │
│           │  │                                                    │  │
│           │  │              No trades match these filters.       │  │
│           │  │                    [Clear filters]                 │  │
│           │  │                                                    │  │
│           │  └──────────────────────────────────────────────────┘  │
```

**Empty state (no trades ever, account funded but engine hasn't acted yet):**

```
│           │  ┌──────────────────────────────────────────────────┐  │
│           │  │                                                    │  │
│           │  │   No trades yet. The engine evaluates your        │  │
│           │  │   account on the next scheduled run — check        │  │
│           │  │   back after market close.                        │  │
│           │  │                                                    │  │
│           │  └──────────────────────────────────────────────────┘  │
```

---

### 4.4 Regular User open positions detail

**Purpose:** PRD FR-10 — full detail view of currently open holdings, one row per position, beyond the 5-row preview on the dashboard (though since max concurrent positions is 5 per PRD 4.4, this page in practice never has more than 5 rows for a single user either — it exists primarily for a stable, linkable, fuller-detail view rather than to handle overflow).

**States:** populated, empty (no open positions — either never traded, or fully exited at the moment), loading.

```
┌──────────────────────────────────────────────────────────────────────┐
│ ◆ trading-tom          Open Positions                Jane Doe ▾  ⏻  │
├───────────┬────────────────────────────────────────────────────────┤
│ Dashboard │  Open Positions (4 of 5 max)                            │
│ Positions │  Prices as of last engine run: Jun 22, 2026 · 5:02 PM   │
│ Trades    │                                                          │
│           │  ┌──────────────────────────────────────────────────┐  │
│           │  │TICKER  QTY  ENTRY PRICE  ENTRY DATE  DAYS HELD     │  │
│           │  │        CURRENT PRICE              UNREAL. P&L      │  │
│           │  ├──────────────────────────────────────────────────┤  │
│           │  │AAPL    40   $189.20       Jun 17, 2026   5d        │  │
│           │  │        Now: $196.50               ▲ +$292.00 +3.9%│  │
│           │  ├──────────────────────────────────────────────────┤  │
│           │  │MSFT    18   $412.10       Jun 20, 2026   2d        │  │
│           │  │        Now: $405.00               ▼ −$127.80 −1.7%│  │
│           │  ├──────────────────────────────────────────────────┤  │
│           │  │SPY     25   $521.40       Jun 14, 2026   8d        │  │
│           │  │        Now: $529.80               ▲ +$210.00 +1.6%│  │
│           │  ├──────────────────────────────────────────────────┤  │
│           │  │NVDA    12   $118.05       Jun 21, 2026   1d        │  │
│           │  │        Now: $123.90               ▲ +$70.20  +5.0%│  │
│           │  └──────────────────────────────────────────────────┘  │
│           │                                                          │
│           │  ℹ Positions exit automatically at +8% target, −4%       │
│           │    stop, after 10 trading days, or if the trend          │
│           │    reverses — whichever happens first.                  │
└───────────┴────────────────────────────────────────────────────────┘
```

Each row is two visual lines (entry-side stats on line 1, current-price + unrealized P&L on line 2) — chosen over a flatter 8-column single-line table because "entry vs. now" is the core comparison the user is making, and stacking the "now" line directly under "entry" makes the before/after relationship easier to scan than a wide single row would on most viewports. A static info note at the bottom restates the exit rules in plain language (no jargon, ties back to PRD 4.5) since this is the one screen a curious user is most likely to ask "wait, when does this close?"

"4 of 5 max" in the header subtly teaches the position-cap rule without needing a tooltip.

**Empty state:**

```
│           │  Open Positions (0 of 5 max)                            │
│           │                                                          │
│           │  ┌──────────────────────────────────────────────────┐  │
│           │  │         You have no open positions right now.     │  │
│           │  │     Check your Trade History to see past trades.  │  │
│           │  │                  [Go to Trade History]             │  │
│           │  └──────────────────────────────────────────────────┘  │
```

---

## 4. Screen-by-Screen Specs (continued): Admin Screens

### 4.5 Admin: user management list

**Purpose:** PRD FR-2, FR-3, FR-4, Section 3 — the Admin "home" screen. List all users, distinguish active vs. deactivated, and launch create/delete/fund actions.

**States:** populated (default, Active tab), Deactivated tab, empty (brand-new deployment, only the bootstrap admin exists), loading.

```
+------------------------------------------------------------------------+
| trading-tom  ADMIN    Users                          Sam Admin v  [X] |
+-----------+------------------------------------------------------------+
| Users     |  Users                              [+ Create User]       |
| Trades    |                                                            |
|  Today    |  [ Active (11) ]  [ Deactivated (2) ]                      |
| Engine    |                                                            |
| Backtests |  [search] Search by name or email...                      |
|           |                                                            |
|           |  +--------------------------------------------------------+|
|           |  |NAME         EMAIL              ROLE   TOTAL VALUE      ||
|           |  |                                        STATUS      ... ||
|           |  +--------------------------------------------------------+|
|           |  |Jane Doe     jane@example.com    User  $108,420.55      ||
|           |  |                                  [Active]          ... ||
|           |  +--------------------------------------------------------+|
|           |  |Tom Reyes    tom@example.com      User  $0.00           ||
|           |  |                              [Active - Unfunded]       ||
|           |  |                                                    ... ||
|           |  +--------------------------------------------------------+|
|           |  |Sam Admin    sam@example.com     Admin  $50,200.10      ||
|           |  |                                  [Active]          ... ||
|           |  +--------------------------------------------------------+|
|           |  |Priya Singh  priya@example.com    User  $94,118.40      ||
|           |  |                                  [Active]          ... ||
|           |  +--------------------------------------------------------+|
|           |           < Prev   Page 1 of 1   Next >                   |
+-----------+------------------------------------------------------------+
```

Row "..." (an overflow `...` button) opens an action menu: **View** (-> `/admin/users/:userId`), **Fund Account** (-> modal, Section 4.7), **Deactivate** (-> confirm dialog). On the Deactivated tab, the menu instead shows **View** only (read access is preserved per PRD FR-5 AC2; there is no "delete forever" — soft delete is final for MVP, no reactivate flow specified by PRD so none is offered here — see Section 9).

Status badge logic: `[Active]` (neutral/success-tinted) for any funded-or-not active user; `[Active - Unfunded]` adds a small secondary qualifier (not a separate color, just appended text in the same neutral badge) when `cash_balance + equity_value == 0`, so an admin scanning the list can immediately spot who still needs funding without opening each row. Deactivated tab rows show `[Deactivated]` in a `neutral-500`-toned badge.

Clicking anywhere on a row (other than the "..." menu) navigates to that user's inspector page (Section 4.8) — the row itself is the primary "View" affordance; the menu exists for the secondary actions.

**Create User button** opens the modal in Section 4.6.

**Deactivate confirm dialog** (destructive action, per Section 2.4 modal conventions):

```
                    +------------------------------------+
                    |  Deactivate Tom Reyes?           X  |
                    +------------------------------------+
                    |  Tom Reyes will no longer be able   |
                    |  to log in. Their trade history     |
                    |  remains visible to admins, and     |
                    |  any open positions will stop       |
                    |  updating but will not be sold.     |
                    |                                      |
                    |             [Cancel] [Deactivate]    |
                    +------------------------------------+
```

"Deactivate" button is the `loss-600`-styled destructive button (Section 2.4). Body copy explicitly restates the PRD 3.2 behavior (positions are not auto-liquidated) so the admin isn't surprised later — this is a deliberate trust-building disclosure, not boilerplate.

**Empty state** (fresh deployment, only the seeded admin exists — PRD 2.3):

```
|           |  Users                              [+ Create User]       |
|           |                                                            |
|           |  [ Active (1) ]  [ Deactivated (0) ]                       |
|           |                                                            |
|           |  +--------------------------------------------------------+|
|           |  |   Only your admin account exists so far.                ||
|           |  |   Create a user to get started.                         ||
|           |  |              [+ Create User]                            ||
|           |  +--------------------------------------------------------+|
```

---

### 4.6 Admin: create user modal/form

**Purpose:** PRD FR-2 / 3.1. Admin sets email, display name, role, and an initial password directly (no invite-email flow).

**States:** default, validating, duplicate-email error, success (toast + modal closes + new row appears in list).

```
                    +------------------------------------+
                    |  Create User                     X  |
                    +------------------------------------+
                    |  Display name                       |
                    |  +--------------------------------+  |
                    |  | Tom Reyes                       |  |
                    |  +--------------------------------+  |
                    |                                      |
                    |  Email                               |
                    |  +--------------------------------+  |
                    |  | tom@example.com                 |  |
                    |  +--------------------------------+  |
                    |                                      |
                    |  Initial password                    |
                    |  +--------------------------------+  |
                    |  | **********                      |  |
                    |  +--------------------------------+  |
                    |  Share this with the user            |
                    |  out-of-band — there is no invite     |
                    |  email sent automatically.            |
                    |                                      |
                    |  Role                                |
                    |  ( ) Admin   (*) Regular User         |
                    |                                      |
                    |             [Cancel] [Create User]   |
                    +------------------------------------+
```

The "share this with the user out-of-band" helper text directly reflects PRD 2.2/3.1 (admin sets password directly, no invite-email infra) — important so an admin doesn't go looking for a "resend invite" feature that doesn't exist.

**Duplicate email error** (PRD FR-2 AC2 — clear error, no user created):

```
                    +------------------------------------+
                    |  Create User                     X  |
                    +------------------------------------+
                    |  +----------------------------------+|
                    |  |! A user with this email already   ||  <- danger banner above
                    |  |  exists.                          ||     the fields, plus the
                    |  +----------------------------------+|     Email field itself gets
                    |  Display name                        |     a red border
                    |  +--------------------------------+  |
                    |  | Tom Reyes                       |  |
                    |  +--------------------------------+  |
                    |  Email                                |
                    |  +--------------------------------+  |
                    |  | tom@example.com  <- red border  |  |
                    |  +--------------------------------+  |
                    |  ...                                  |
                    |             [Cancel] [Create User]   |
                    +------------------------------------+
```

Client-side validation (before submit, instant): display name non-empty, email well-formed, password meets a minimum length (assumption: 8 characters minimum, no other complexity rule imposed — see Section 9). Server-side duplicate-email check only surfaces after submit (can't be known client-side); the banner + field-level red border pattern matches the general form-error convention in Section 5.3. On success: modal closes, a success toast reads `Tom Reyes created.`, and the new row appears at the top of the (now re-sorted or simply re-fetched) Active users list.

---

### 4.7 Admin: fund account modal

**Purpose:** PRD FR-4 / 3.3. Positive-amount-only top-up, with preset quick-fill buttons.

**States:** default, validating, zero/negative-amount error, success.

```
                    +------------------------------------+
                    |  Fund Account: Tom Reyes          X |
                    +------------------------------------+
                    |  Current balance: $0.00              |
                    |                                      |
                    |  Amount to add                       |
                    |  +--------------------------------+  |
                    |  | $  10,000.00                    |  |
                    |  +--------------------------------+  |
                    |                                      |
                    |  [ $1,000 ]  [ $10,000 ]  [ $100,000 ]|
                    |     (quick-fill chips)                |
                    |                                      |
                    |  New balance will be: $10,000.00     |
                    |                                      |
                    |  This is an additive top-up only —   |
                    |  there is no withdraw/set-balance     |
                    |  action in this version.              |
                    |                                      |
                    |             [Cancel] [Fund Account]  |
                    +------------------------------------+
```

The three preset buttons ($1,000 / $10,000 / $100,000) are exactly the PRD-suggested amounts (Section 3.3) — clicking one fills the amount field with that value (and it remains editable afterward, so an admin can use a preset as a starting point and adjust). "New balance will be: $X" is a live-computed preview (`current_balance + amount`) that updates as the admin types, giving immediate confirmation before submitting — important since this is a real (if virtual) financial action and PRD 3.3 frames funding as also being the activation trigger (Section 9 calls out that we make this activation consequence explicit in the UI, see below).

**Zero/negative amount error** (PRD FR-4 AC2):

```
                    |  Amount to add                       |
                    |  +--------------------------------+  |
                    |  | $  0.00            <- red border|  |
                    |  +--------------------------------+  |
                    |  ! Amount must be greater than $0.   |  <- loss-600 helper text
                    |                                      |
                    |             [Cancel] [Fund Account]  |  <- disabled until valid
```

**Activation callout (first-time funding only):** if `current_balance == 0` (i.e., this funding action will flip the user from dormant to active per PRD 3.3's activation rule), the modal shows one extra informational line beneath the preview:

```
                    |  New balance will be: $10,000.00     |
                    |  (i) This will activate Tom Reyes for |
                    |    trading starting with the next     |
                    |    scheduled engine run.               |
```

This line is suppressed on subsequent fundings of an already-funded account (where it would be noise) — shown only on the $0 -> >$0 transition, since that's the moment with real consequence the admin should consciously register (PRD 3.3's "funding is activation" rule, surfaced as a UI moment rather than a buried fact).

On success: modal closes, toast reads `$10,000.00 added to Tom Reyes. New balance: $10,000.00.`, and the user's row in the list (and their inspector page, if open) reflects the new total value.

---

### 4.8 Admin: per-user inspector

**Purpose:** PRD FR-5 — same balance/positions/trade-history views as the Regular User screens, but admin-facing with a user picker, and working identically for active and deactivated users (read access isn't blocked by deactivation).

**States:** active user, deactivated user (banner notice, all data still visible), loading.

```
+------------------------------------------------------------------------+
| trading-tom  ADMIN    Users / Jane Doe                Sam Admin v  [X] |
+-----------+------------------------------------------------------------+
| Users     |  [search] Switch user: [ Jane Doe          v ]             |
| Trades    |                                                            |
|  Today    |  Jane Doe . jane@example.com . [Active]    [Fund Account]  |
| Engine    |                                                            |
| Backtests |  +----------------+ +----------------+ +------------------+|
|           |  | TOTAL VALUE     | | CASH BALANCE    | | EQUITY VALUE     ||
|           |  | $108,420.55     | | $42,110.20      | | $66,310.35       ||
|           |  +----------------+ +----------------+ +------------------+|
|           |  +------------------------+ +------------------------+    |
|           |  | REALIZED P&L (lifetime) | | UNREALIZED P&L (open)   |    |
|           |  | UP +$6,420.55 (+6.3%)   | | UP +$1,910.10 (+2.97%)  |    |
|           |  +------------------------+ +------------------------+    |
|           |                                                            |
|           |  [ Positions (4) ]  [ Trade History (147) ]   <- tabs     |
|           |                                                            |
|           |  (selected tab renders the same table component as        |
|           |   Section 4.3 / 4.4, scoped to Jane Doe, including the    |
|           |   same ticker/date filters and pagination)                |
+-----------+------------------------------------------------------------+
```

The "Switch user" combobox (type-ahead search by name/email) lets an admin jump directly to another user's inspector without returning to the list — supports the common workflow of checking several accounts in a row. The stat cards and Positions/Trade-History tabs are the **same components** used on the Regular-User dashboard/positions/trades pages (Section 4.2–4.4), just re-skinned with the admin shell and a "Fund Account" shortcut button in the header — this reuse is intentional (Section 1.2: consistency) and keeps the two roles' data presentation perfectly aligned, so an admin never has to mentally translate between "what I see" and "what the user sees."

**Deactivated-user banner** (replaces the active-status badge area, data below remains fully visible per PRD FR-5 AC2):

```
|           |  Jane Doe . jane@example.com . [Deactivated]              |
|           |  +--------------------------------------------------+    |
|           |  | (X) This account is deactivated and cannot log in.|    |
|           |  |     Historical data below is preserved and viewable.|  |
|           |  +--------------------------------------------------+    |
|           |  (stat cards / tabs continue to render normally below)    |
```

Note: "Fund Account" action is hidden/disabled for a deactivated user (funding an account that can't log in and won't be traded — since the engine also skips inactive users per PRD 3.2 — would be a confusing dead-end action), with a tooltip explaining why if hovered.

---

### 4.9 Admin: aggregate all-trades-today view

**Purpose:** PRD 5.3 — "useful for spot-checking the engine's per-run behavior" across every user at once, scoped to the current trading day.

**States:** populated, empty (no trades today — e.g. engine hasn't run yet, or no signals fired), loading.

```
+------------------------------------------------------------------------+
| trading-tom  ADMIN    Trades Today                    Sam Admin v  [X] |
+-----------+------------------------------------------------------------+
| Users     |  Trades Today — Jun 22, 2026             [Export CSV]      |
| Trades    |  From engine run #4821 . completed 5:02 PM ET              |
|  Today    |                                                            |
| Engine    |  Ticker: [ All v ]   Side: [ All v ]   User: [ All v ]    |
| Backtests |                                                            |
|           |  +--------------------------------------------------------+|
|           |  |USER       TICKER SIDE QTY PRICE   REASON     P&L       ||
|           |  +--------------------------------------------------------+|
|           |  |Jane Doe   TSLA   SELL 15  $241.30 [Profit   UP+$312    ||
|           |  |                                     Target]            ||
|           |  |Jane Doe   NVDA   BUY  12  $118.05 [Trend        —      ||
|           |  |                                     Entry]             ||
|           |  |Priya Singh AAPL  BUY  22  $196.50 [Trend        —      ||
|           |  |                                     Entry]             ||
|           |  |Priya Singh AMD   SELL 18  $98.10  [Stop    DOWN -$54   ||
|           |  |                                     Loss]              ||
|           |  +--------------------------------------------------------+|
|           |                                                            |
|           |  21 trades . 14 users evaluated . 2 signals skipped       |
|           |  (max positions reached) . 0 errors          [Details ->] |
+-----------+------------------------------------------------------------+
```

This view is intentionally a flat cross-user feed (User column added vs. the per-user trade table), sorted newest-first within the day, filterable by ticker/side/user — same filter pattern as Section 4.3 for consistency. The summary strip at the bottom (`21 trades . 14 users evaluated . 2 signals skipped . 0 errors`) is a condensed version of the engine run summary (Section 4.10) repeated here for convenience, with a "Details ->" link that jumps to the full run record on `/admin/engine`. "Export CSV" supports the admin's "spot-checking" use case (PRD 5.3) — easy to pull into a spreadsheet for manual verification.

Users with no activity that day (e.g. an unfunded account) simply do not appear in this table at all — it is a trade feed, not a user roster, so there is no placeholder row for inactivity.

**Empty state:**

```
|           |  Trades Today — Jun 22, 2026                              |
|           |  +--------------------------------------------------------+|
|           |  |     No trades have been executed today yet.             ||
|           |  |     Last completed run: Jun 21, 2026 . 5:01 PM ET       ||
|           |  |              [View Engine Status ->]                    ||
|           |  +--------------------------------------------------------+|
```

---

### 4.10 Admin: engine status / run history view

**Purpose:** PRD FR-6, 4.6, 9.4 — the primary operational debugging surface. Shows run summaries (tickers evaluated, signals fired, trades executed, errors) and exposes the manual "trigger run now" control, including the "run already in progress" blocked state (FR-6 AC2).

**States:** idle (no run in progress, default), run-in-progress (trigger button disabled with explanation), run-failed (error surfaced prominently), history list with expandable detail.

```
+------------------------------------------------------------------------+
| trading-tom  ADMIN    Engine                          Sam Admin v  [X] |
+-----------+------------------------------------------------------------+
| Users     |  Engine Status                                            |
| Trades    |                                                            |
|  Today    |  +--------------------------------------------------------+|
| Engine    |  |  Status: o Idle — last run completed                   ||
| Backtests |  |  Jun 22, 2026 . 5:02 PM ET                              ||
|           |  |                                                          ||
|           |  |  Next scheduled run: Jun 23, 2026 . 5:00 PM ET          ||
|           |  |                                                          ||
|           |  |              [ Trigger Run Now ]                        ||
|           |  +--------------------------------------------------------+|
|           |                                                            |
|           |  Run History                                              |
|           |  +--------------------------------------------------------+|
|           |  |RUN #  STARTED          DURATION STATUS    TICKERS       ||
|           |  |                                            SIGNALS       ||
|           |  |                                            TRADES        ||
|           |  |                                            ERRORS        ||
|           |  +--------------------------------------------------------+|
|           |  |4821   Jun 22 5:00 PM   1m 48s  [Complete]  28 tkrs       ||
|           |  |                                  6 signals               ||
|           |  |                                  21 trades  0 err        ||
|           |  |                                              v           ||
|           |  +--------------------------------------------------------+|
|           |  |4820   Jun 21 5:00 PM   1m 52s  [Complete]  28 tkrs       ||
|           |  |                                  3 signals               ||
|           |  |                                  9 trades   0 err        ||
|           |  +--------------------------------------------------------+|
|           |  |4819   Jun 20 5:00 PM   2m 10s  [Complete]  28 tkrs       ||
|           |  |                                  4 signals               ||
|           |  |                                  11 trades  1 err        ||
|           |  |                                              !           ||
|           |  +--------------------------------------------------------+|
+-----------+------------------------------------------------------------+
```

Each run row is expandable (caret) to reveal the full per-ticker breakdown and an error log if any errors occurred — expansion happens inline (accordion), not a navigation, since runs are usually reviewed in the context of "what happened around this time," not as standalone deep pages.

**Expanded run detail (with an error)**, run #4819:

```
|           |  +--------------------------------------------------------+|
|           |  |4819   Jun 20 5:00 PM   2m 10s  [Complete]  28 tkrs       ||
|           |  |                                  4 signals               ||
|           |  |                                  11 trades  1 err        ||
|           |  |                                              ^           ||
|           |  |  +----------------------------------------------------+ ||
|           |  |  | ! 1 error during this run                            | ||
|           |  |  |  - GME: fetch failed (provider timeout) —            | ||
|           |  |  |    ticker skipped for this run.                      | ||
|           |  |  |                                                       | ||
|           |  |  | Tickers evaluated: 28   Signals fired: 4              | ||
|           |  |  | Entries: 6   Exits: 5   Trades total: 11              | ||
|           |  |  | Users affected: 9                                     | ||
|           |  |  +----------------------------------------------------+ ||
```

This directly satisfies PRD 4.6's run summary contract (tickers evaluated, signals fired, trades executed, errors) and 7.3's requirement that a per-ticker fetch failure be logged and surfaced in this view without crashing the run (note the run still shows `[Complete]`, not `[Failed]` — a partial per-ticker error does not fail the whole run, consistent with PRD 7.3's "skip that ticker, don't crash the whole run" behavior). A run only shows status `[Failed]` if the run itself aborted (e.g. DB unavailable) rather than a single ticker's fetch failing.

**Run-in-progress state** (PRD FR-6 AC2 — manual trigger blocked with a clear message, no overlapping runs):

```
|           |  +--------------------------------------------------------+|
|           |  |  Status: o Running — started 5:00:03 PM ET               ||
|           |  |  Evaluating ticker 14 of 28...                           ||
|           |  |                                                          ||
|           |  |              [ Run In Progress... ]  (disabled)         ||
|           |  |  A run is already in progress. Please wait for it       ||
|           |  |  to complete before triggering another.                  ||
|           |  +--------------------------------------------------------+|
```

Status dot uses `info-600` (blue, "in progress," not yet a final outcome) while running, `success-600` green for idle/last-run-complete, `danger-600` red if the engine's last attempt aborted outright. The page polls for status updates while a run is in progress (short interval, e.g. every 3–5s) so the admin sees live progress without manual refresh — this is the one screen in the product where near-real-time polling is appropriate, since it reflects an in-flight backend job, not market data.

**Trigger-now confirmation** (lightweight, not a heavy modal, since this is a routine operational action, not destructive):

```
                    +------------------------------------+
                    |  Trigger engine run now?          X |
                    +------------------------------------+
                    |  This runs the exact same logic as  |
                    |  the scheduled daily run, evaluating |
                    |  all active accounts immediately.    |
                    |                                      |
                    |           [Cancel] [Trigger Run]     |
                    +------------------------------------+
```

---

### 4.11 Admin: backtest submission form

**Purpose:** PRD FR-7, 6.2 — date range, ticker subset, starting capital. Validates before any compute starts (FR-7 AC2).

**States:** default (full universe selected), narrowed ticker subset, validation error (end before start / out-of-range dates), submitting.

Presented as a modal launched from the Backtest run list (Section 4.12), per the IA note in Section 3.1 (route `/admin/backtests/new` backs this modal for deep-linkability).

```
                    +----------------------------------------+
                    |  New Backtest                        X |
                    +----------------------------------------+
                    |  Date range                              |
                    |  +--------------+    +--------------+   |
                    |  | 2024-01-01   | to | 2025-12-31    |   |
                    |  +--------------+    +--------------+   |
                    |  Available data: 2018-01-01 to today      |
                    |                                            |
                    |  Tickers                                  |
                    |  (*) Full universe (28 tickers)            |
                    |  ( ) Choose a subset                       |
                    |      +----------------------------------+ |
                    |      | [ ] AAPL [ ] MSFT [ ] SPY [ ] QQQ| |
                    |      | [ ] NVDA [ ] AMD  [ ] TSLA [ ]...| |
                    |      +----------------------------------+ |
                    |                                            |
                    |  Starting capital                          |
                    |  +----------------------------------------+|
                    |  | $ 100,000.00                            ||
                    |  +----------------------------------------+|
                    |                                            |
                    |              [Cancel] [Run Backtest]      |
                    +----------------------------------------+
```

"Available data: [range] to today" is shown statically beneath the date inputs as a constant hint of the data provider's bounds (PRD 6.2 — "must fall within the historical range available"); exact submission-time validation still happens against the live provider range, this is just an honest hint, not a hard client-side cap, since the available range could change. Ticker subset defaults to "Full universe" (matches PRD 6.2's "defaults to the full live-engine universe"); choosing "Choose a subset" reveals a checkbox grid of the universe tickers. Starting capital defaults to **$100,000** (PRD 6.2's stated default).

**Validation error — end date before start date** (FR-7 AC2):

```
                    |  Date range                              |
                    |  +--------------+    +--------------+   |
                    |  | 2025-12-31 <-|  to | 2024-01-01 <-|   |   <- both red-bordered
                    |  +--------------+    +--------------+   |
                    |  ! End date must be after the start      |
                    |    date.                                  |
                    |              [Cancel] [Run Backtest]     |  <- disabled until fixed
```

**Validation error — date range outside available historical data** (FR-7 AC2):

```
                    |  +--------------+    +--------------+   |
                    |  | 2010-01-01 <-|  to | 2025-12-31    |  |
                    |  +--------------+    +--------------+   |
                    |  ! Start date is before the earliest      |
                    |    available data (2018-01-01) for        |
                    |    one or more selected tickers.            |
```

Both validations run client-side instantly on blur/change (no need to round-trip for the "end before start" case) and are also re-checked server-side before any compute starts, per FR-7 AC2's "rejected... before any compute starts" — the UI must never show a "running" state for a request the server will reject.

On valid submit: modal closes, a toast reads `Backtest queued.`, and the admin lands on `/admin/backtests` where the new run appears at the top of the list in a `[Queued]` or `[Running]` state (Section 5.1 covers the full async status pattern).

---

### 4.12 Admin: backtest run list

**Purpose:** PRD 6.5 — "past backtest runs are listed... so Admin can compare runs after a strategy code change over time."

**States:** populated with mixed statuses (complete/running/queued/failed), empty (first-ever backtest not yet run).

```
+------------------------------------------------------------------------+
| trading-tom  ADMIN    Backtests                        Sam Admin v [X] |
+-----------+------------------------------------------------------------+
| Users     |  Backtests                          [+ New Backtest]      |
| Trades    |                                                            |
|  Today    |  +--------------------------------------------------------+|
| Engine    |  |RUN ID  SUBMITTED       RANGE          TICKERS           ||
| Backtests |  |                                        STATUS            ||
|           |  |                                        RETURN            ||
|           |  |                                        WIN RATE          ||
|           |  +--------------------------------------------------------+|
|           |  |BT-104  Jun 22 9:14 AM  2024-01—2025-12  28 tkrs          ||
|           |  |                          [Running 62%]                  ||
|           |  |                                          —    —          ||
|           |  +--------------------------------------------------------+|
|           |  |BT-103  Jun 21 4:02 PM  2020-01—2025-12  28 tkrs          ||
|           |  |                          [Complete]                     ||
|           |  |                          UP +41.2% ($141,200)           ||
|           |  |                          58% win rate                   ||
|           |  +--------------------------------------------------------+|
|           |  |BT-102  Jun 20 11:30 AM 2024-06—2024-12  6 tkrs           ||
|           |  |                          [Failed]                       ||
|           |  |                          Provider rate-limit error      ||
|           |  +--------------------------------------------------------+|
|           |  |BT-101  Jun 18 2:15 PM  2018-01—2023-12  28 tkrs          ||
|           |  |                          [Complete]                     ||
|           |  |                          DOWN -3.8% (-$3,800)           ||
|           |  |                          44% win rate                   ||
|           |  +--------------------------------------------------------+|
+-----------+------------------------------------------------------------+
```

Each row's headline numbers (total return, win rate) are exactly the "compare runs" summary PRD 6.5 calls for — visible without opening the run. A `[Running 62%]` badge shows live progress (percent of trading days processed) for in-flight runs; a `[Failed]` row shows the failure reason inline instead of metrics (a backtest can fail outright, e.g. a hard rate-limit error mid-fetch — distinct from the live engine's per-ticker-skip tolerance, since a backtest over a fixed historical range either completes or doesn't, there's no "next day" to recover on). Clicking any row (regardless of status) navigates to `/admin/backtests/:backtestId` — a `[Running]`/`[Queued]` row's detail page shows the in-progress view from Section 5.1, a `[Failed]` row's detail page shows the error detail, and `[Complete]` shows full results (Section 4.13).

**Empty state:**

```
|           |  Backtests                          [+ New Backtest]      |
|           |  +--------------------------------------------------------+|
|           |  |   No backtests have been run yet.                       ||
|           |  |   Evaluate the strategy against historical data.        ||
|           |  |              [+ New Backtest]                            ||
|           |  +--------------------------------------------------------+|
```

---

### 4.13 Admin: backtest results page

**Purpose:** PRD 6.4, 6.5 — equity curve chart, summary metrics table, expandable per-trade log.

**States:** complete (full results, default below), running/queued (status view, Section 5.1), failed (error detail).

```
+------------------------------------------------------------------------+
| trading-tom  ADMIN  Backtests / BT-103                 Sam Admin v [X] |
+-----------+------------------------------------------------------------+
| Users     |  BT-103 . 2020-01-01 to 2025-12-31 . 28 tickers           |
| Trades    |  Starting capital: $100,000.00 . Completed Jun 21, 2026   |
|  Today    |                                                            |
| Engine    |  +--------------------------------------------------------+|
| Backtests |  | Equity Curve                                            ||
|           |  | $145k|                                    .--.          ||
|           |  |      |                              .-----'   '-       ||
|           |  | $130k|                        .------'                  ||
|           |  |      |                  .------'                        ||
|           |  | $115k|            .------'                              ||
|           |  |      |      .-----'                                     ||
|           |  | $100k+------'                                           ||
|           |  |      +-----+-------+-------+-------+-------+-----       ||
|           |  |          2020    2021    2022    2023    2024  2025     ||
|           |  +--------------------------------------------------------+|
|           |                                                            |
|           |  +------------+ +------------+ +------------+ +-----------+|
|           |  |TOTAL RETURN| | WIN RATE    | | TOTAL TRADES| |MAX DRAWDN||
|           |  |UP +41.2%   | | 58%         | | 212         | | -11.4%   ||
|           |  |+$41,200.00 | | 123 of 212  | | 106 round-  | | -$13,650 ||
|           |  |            | | profitable  | | trips       | |          ||
|           |  +------------+ +------------+ +------------+ +-----------+|
|           |  +----------------------------+                            |
|           |  | AVG HOLDING PERIOD          |                           |
|           |  | 6.4 trading days            |                           |
|           |  +----------------------------+                            |
|           |                                                            |
|           |  Trade Log (212)                          [Export CSV]    |
|           |  +--------------------------------------------------------+|
|           |  |DATE       SIDE TICKER QTY  PRICE   REASON     P&L      ||
|           |  +--------------------------------------------------------+|
|           |  |2020-01-14 BUY  AAPL   52   $77.50  [Trend        —     ||
|           |  |                                      Entry]            ||
|           |  |2020-01-24 SELL AAPL   52   $83.70  [Profit   UP+$322   ||
|           |  |                                      Target]           ||
|           |  |  ... 210 more rows (paginated, same pattern              ||
|           |  |      as Section 4.3)                                     ||
|           |  +--------------------------------------------------------+|
+-----------+------------------------------------------------------------+
```

Chart is the single equity-curve line chart specified in Section 2.4, hover-interactive (tooltip shows exact date + portfolio value at any point along the line). The four/five metric cards directly map to PRD 6.4's required outputs: Total Return ($ and %), Win Rate (% and the underlying fraction), Total Trades (with round-trip count called out, since "212 trades" alone conflates entries+exits — showing both the raw trade-row count and the round-trip count avoids confusion), Max Drawdown (% and $), Average Holding Period (days) — laid out as a 4-card row plus one wrapping card rather than 5 even cards, since 5 doesn't divide cleanly into a clean desktop grid at this card width; this is a layout-only decision (Section 9).

Trade Log reuses the same table component/pattern as the Regular User trade history (Section 4.3) — pagination, no ticker/date filters needed here by default since the range is already fixed by the backtest itself, though a ticker filter could be trivially added (noted as a nice-to-have, not required by PRD 6.4 which only specifies "expandable per-trade log").

**Per-ticker breakdown** (PRD 6.4 — explicitly called a non-blocking nice-to-have): if implemented, renders as an additional collapsed section below the Trade Log titled "Per-Ticker Breakdown," a simple sortable table of ticker -> trades -> net P&L. Since PRD marks this optional/non-blocking, it is designed here but explicitly **not** required for MVP ship (Section 9 reiterates this).

---
## 5. Key Interaction Patterns

### 5.1 Async backtest status: queued -> running -> complete

Per PRD 6.5, a backtest may run synchronously (short ranges) or asynchronously (long ranges, fetch-bound). The UI treats every backtest as potentially async to avoid two different code paths for "fast" vs. "slow" runs:

1. **Submit** (Section 4.11) -> immediate toast `Backtest queued.` and navigation to the run list, new row shown as `[Queued]`.
2. **Queued -> Running** transition happens automatically (polling, ~3-5s interval, same pattern as engine status Section 4.10) — row updates in place to `[Running NN%]` with a progress percentage if the backend can report one (e.g. trading-days-processed / total-trading-days), or an indeterminate `[Running...]` state with a subtle animated progress bar if no percentage is available.
3. **Complete** -> row updates to `[Complete]` with headline return/win-rate populated; a toast fires `Backtest BT-104 complete: +18.2% return.` if the admin is still on the list page when it finishes; if the admin has navigated to the run's detail page while it was running, that page itself transitions live from a "running" placeholder (spinner + "Backtest in progress — this page will update automatically") to the full results layout (Section 4.13) without requiring a manual refresh.
4. **Failed** -> row updates to `[Failed]` with the error reason inline; detail page shows a dedicated error state (icon + message + "what to try next," e.g. "Reduce the date range or ticker subset and try again" for a rate-limit failure).

This status pattern (queued -> running -> complete/failed, polled, live-updating in place) is identical in shape to the engine-run status pattern in Section 4.10 — both are "watch a backend job progress" interactions and intentionally share one visual vocabulary (status dot + colored badge + polling) so a user who's learned one understands the other immediately.

### 5.2 Table pagination & filtering

One shared convention across every paginated table in the product (trade history, user list, trades-today, run history, backtest list, backtest trade log):

- **Default sort:** newest-first (by date/timestamp) unless otherwise noted; admin lists (users) default to alphabetical-by-name instead, since "newest" is less meaningful for a roster.
- **Filters are server-side**, not client-side, for any table that can exceed a few hundred rows (trade history, trades-today) — per PRD 9.3's "hundreds to low-thousands of trade rows" expectation, client-side filtering of the full dataset would not scale and would also leak data the server should be scoping (e.g. a user's own trade table should never fetch *all* trades and filter client-side, both for performance and for not trusting the client with data it shouldn't have).
- **Filter state lives in the URL query string** so filtered/paginated views are bookmarkable and survive a refresh (e.g. `/trades?ticker=AAPL&from=2026-01-01&to=2026-06-22&page=2`).
- **Changing any filter resets pagination to page 1** (changing a filter while sitting on page 4 of the old result set would likely land on an out-of-range page).
- **"Clear filters" affordance** appears whenever at least one filter is active, returning to the unfiltered default view in one click.
- **Page size selector** (25/50/100 rows) persists per-table as a lightweight client preference (not synced server-side) — defaults to 25.
- **Loading during filter/page change:** the table body shows skeleton rows in place (Section 2.4) while headers/filters remain interactive — never a full-page spinner/blank, since the user's mental context (what filter am I on) must stay visible.

### 5.3 Form validation error display

Consistent pattern across every form/modal in the product (Create User, Fund Account, Backtest submission, future forms):

- **Inline, field-level errors** are the primary mechanism: red border on the offending input(s) + a `small`, `loss-600`-colored helper line directly beneath that field, replacing the field's normal helper text (if any) while the error is active.
- **Validate on blur** for single-field rules (e.g. email format, password length) — don't show an error while the user is still mid-typing their first pass through a field.
- **Validate on change** for cross-field rules once both fields have been touched at least once (e.g. end-date-before-start-date) — these errors should disappear immediately once corrected, not require a re-submit to clear.
- **A top-of-form banner** is reserved for errors that are not attributable to a single field, or that come back from the server only after submit (e.g. "duplicate email," "provider rate-limit error") — danger-tinted banner (Section 2.1) directly under the modal/form header, above the fields.
- **Submit button is disabled** whenever a known client-side validation error is present, and re-enabled the instant it's resolved — this avoids a round-trip just to learn something client-side validation already knew.
- **Server-side errors on submit** (e.g. duplicate email arriving after a submit click) re-render as the top-of-form banner described above; the submit button returns to its enabled, non-loading state so the admin can correct and retry without reopening the modal.
- **Never silently fail.** Every rejected submission produces a visible message; there is no submit action in this product that can fail with no UI feedback.

### 5.4 Toast / notification conventions

(Full visual spec in Section 2.4.) Usage rules:
- **Success toasts** for completed write actions the user initiated (user created, account funded, run triggered, backtest queued) — confirms the action landed, since several of these (funding, triggering a run) have real downstream consequences the admin should see acknowledged.
- **Info toasts** for asynchronous events the user is watching but didn't just click (e.g. "Backtest BT-104 complete" firing while the admin is on another page) — softer color, slightly longer dwell time since the user wasn't already looking at the screen when it appeared.
- **Error toasts** for failures that aren't better expressed as inline form errors (e.g. a network failure mid-request, a session that expired mid-action) — these persist until dismissed (don't auto-dismiss) since an error the user didn't cause by typing deserves a deliberate acknowledgment.
- **Never use a toast as the only record of something important** — anything a toast announces (a user was created, an account was funded) is also reflected durably in the relevant list/table, so missing or dismissing a toast never costs the admin information.

### 5.5 Loading / empty / error states, generally

Three states every data view in this product must explicitly design for (most screens in Section 4 show at least one; this is the general rule they all follow):

- **Loading:** skeleton placeholders matching the final layout's shape (cards, table rows) — never a generic full-page spinner for anything that has a known target layout. A full-page spinner is acceptable only for the very first app load before any shell has rendered.
- **Empty (zero data, not an error):** a centered message inside the component's normal content area (not a separate page) explaining *why* it's empty in plain language and, where applicable, a primary action to resolve it (e.g. "+ Create User," "Go to Trade History"). Empty states are never literally blank — Section 4.2's zero-balance state and Section 4.5's fresh-deployment state are the canonical examples.
- **Error (request failed):** distinguished from "empty" — shows a warning icon, a one-line explanation in plain language (not a raw error code/stack trace), and a retry action where retrying is sensible (most GET requests); falls back to last-known-good cached data plus a staleness notice where that's safer than showing nothing (Section 4.2's stale-price-data pattern is the canonical example of this fallback).

---

## 6. Data Display Conventions

### 6.1 USD formatting

- All monetary values display as `$X,XXX.XX` — thousands separator, always exactly 2 decimal places, regardless of the underlying `DECIMAL(14,4)` storage precision (PRD 5.3 — "display only rounds at render time," internal precision is preserved server-side to avoid rounding drift across many trades).
- Negative monetary values display as `-$X,XXX.XX` (leading minus before the dollar sign), never trailing-minus or parentheses-style accounting notation — parentheses are a common alternative but are avoided here since this product already uses a colored +/- convention for P&L specifically (6.2 below) and mixing two negative-number conventions in one product would be inconsistent.
- Full, unrounded precision is available on hover (title-attribute tooltip showing e.g. `$3,648.0000`) on any monetary figure for an admin auditing exact values — a deliberate "precision on demand" affordance per Section 1.2's "numbers are the hero" principle, never needed by default.
- Percentages display to 1 decimal place (e.g. `+3.9%`, `-11.4%`) except win rate, which displays as a whole percent (e.g. `58%`) since fractional win-rate precision isn't meaningful at typical MVP trade-count volumes.

### 6.2 Green/red P&L coloring (with non-color reinforcement)

Every P&L value (realized or unrealized, in any table, card, or chart) follows the same three-part convention so color is never the only signal (Section 8 — accessibility, WCAG 1.4.1):

1. **A leading sign glyph**: an up-triangle/chevron (▲) for positive, down-triangle/chevron (▼) for negative, and a plain en-dash (–) or "—" for exactly zero or not-applicable (e.g. a BUY row's P&L column). This is shown in every wireframe in Section 4 as `▲ +$...` / `▼ -$...`.
2. **An explicit +/- sign** on the number itself (`+$292.00`, not just `$292.00` in green) — redundant with the glyph by design, since redundancy is exactly the point for accessibility and for any context where the glyph might not render (e.g. a plain-text CSV export per Section 4.9/4.13's "Export CSV" actions retains the +/- sign even though it obviously can't retain color).
3. **Color** (`gain-600` green text / `loss-600` red text) as the third, fastest-to-scan but non-exclusive signal.

Zero/flat values use `neutral-500` gray text with no glyph and no sign (`$0.00`, not `+$0.00`) — flat is its own state, not a degenerate case of "gain."

### 6.3 Exit/entry reason badges

Raw `signal_reason` enum values (PRD 5.2: `ENTRY_TREND_MOMENTUM`, `EXIT_PROFIT_TARGET`, `EXIT_STOP_LOSS`, `EXIT_MAX_HOLD`, `EXIT_TREND_INVALIDATION`) are never shown verbatim in the UI — they always render through a lookup table to a short, human-readable badge label, since neither audience (Section 1.1) is assumed to know the underlying strategy's internal rule names:

| Enum value | Badge label | Badge tint |
|---|---|---|
| `ENTRY_TREND_MOMENTUM` | **Trend Entry** | Neutral (`neutral-100` bg / `neutral-700` text) |
| `EXIT_PROFIT_TARGET` | **Profit Target** | Gain-tinted (`gain-50` bg / `gain-600` text) |
| `EXIT_STOP_LOSS` | **Stop Loss** | Loss-tinted (`loss-50` bg / `loss-600` text) |
| `EXIT_MAX_HOLD` | **Max Hold Reached** | Neutral (outcome-agnostic — could be a gain or a loss at max-hold, the badge itself shouldn't imply either; the adjacent P&L column already shows the actual outcome) |
| `EXIT_TREND_INVALIDATION` | **Trend Reversed** | Neutral (same reasoning as Max Hold — an early exit on thesis invalidation can land either side of breakeven) |

Rationale for only tinting the two target/stop badges: those two reasons are the only ones whose *label itself* deterministically implies an outcome (profit target always means a winning exit; stop loss always means a losing exit), so tinting them reinforces a true fact. Max-hold and trend-invalidation exits are outcome-independent by definition, so coloring those badges would risk implying a P&L direction that isn't necessarily there — the badge communicates *why*, the separate P&L column (Section 6.2) communicates *how it went*, and the two are kept visually distinct on purpose.

Every badge is also exposed with a hover tooltip giving one plain-language sentence of the underlying rule (e.g. Stop Loss -> "Price fell 4% or more below the entry price.") — supports the "explainability" goal called out explicitly in PRD 4.1 ("its behavior is auditable").

### 6.4 Tables generally

- Tabular (monospaced-width) numerals in every numeric column (Section 2.2) so quantities/prices/P&L align vertically for fast scanning down a column — this is a small typographic detail with an outsized legibility payoff in a finance table.
- Tickers render in `body-strong` weight (Section 2.2) to act as a visual anchor per row, since "which stock" is usually the first thing scanned for in any trade-related table.
- Dates render as `Jun 22, 2026` (or `Jun 22` when the year is unambiguous within a clearly-dated context, e.g. the trades-today view) rather than numeric `MM/DD/YYYY` — avoids US/international date-order ambiguity entirely, appropriate since this product has no stated locale/internationalization requirement (Section 9, assumption) but should still never be ambiguous to read.

---

## 7. Responsive Behavior

### 7.1 Breakpoints

| Name | Width | Primary context |
|---|---|---|
| `mobile` | < 640px | Phone browser, portrait |
| `tablet` | 640–1023px | Tablet, small laptop window |
| `desktop` | 1024–1279px | Standard laptop |
| `wide` | >= 1280px | External monitor — content remains capped at 1280px max-width (Section 2.3), extra space is just margin |

### 7.2 Navigation shell

- **Desktop/wide/tablet:** persistent left sidebar (Section 3.2), full text labels.
- **Mobile:** sidebar collapses entirely behind a hamburger menu in the top bar; tapping it opens a full-height slide-in drawer with the same nav items. The top bar itself stays fixed (page title + hamburger + user avatar) so orientation ("where am I, who am I logged in as") never scrolls away.

### 7.3 Dashboard / stat cards

- **Desktop/wide:** stat cards lay out in a row (3 across for the top balance row, 2 across for the P&L row, per the Section 4.2 wireframe).
- **Tablet:** rows wrap to 2-up grids.
- **Mobile:** every stat card stacks to full-width, single column, in the same top-to-bottom priority order as desktop (Total Value first — it's the single most important number on the page, then Cash/Equity, then the two P&L cards). No information is dropped on mobile, only re-flowed.

### 7.4 Dense tables (trade history, run history, trades-today, backtest results)

This is the hardest responsive problem in the product — these tables have 6-9 columns at desktop width, which cannot all fit legibly on a 375px phone viewport. Strategy, applied consistently across every dense table:

1. **Prioritize columns.** Every table has a defined column priority order (e.g. trade history: Date > Ticker > Side > P&L > Reason > Qty > Price > Value). The top 3-4 priority columns remain visible at all times; lower-priority columns progressively drop as width shrinks.
2. **Below `tablet` width, switch from a multi-column table to a stacked card-per-row layout** rather than truncating/hiding columns in a cramped grid. Each "row" becomes a compact card: a header line with the two or three highest-priority fields (e.g. `AAPL  BUY  Jun 22`), then the remaining fields as label/value pairs beneath, with P&L and the reason badge always retained since those are the fields users most want even on mobile (per Section 1.1/1.4 — "how am I doing, and why" is the core question, and that's exactly Reason + P&L).
3. **Filters collapse into a single "Filters" button** that opens a small sheet/modal containing the same ticker/date controls, rather than the inline filter row from desktop — preserves full functionality without permanently consuming vertical space on a small screen.
4. **Pagination controls simplify** to just Prev/Next plus "Page X of Y" text (drop the page-size selector to a secondary "..." overflow) to fit a narrow bottom bar.

Example: the Section 4.3 trade history row `Jun 22 | SELL | TSLA | 15 | $241.30 | $3,619.50 | [Profit Target] | +$312` becomes, on mobile:

```
+--------------------------------+
| TSLA   SELL          Jun 22    |
| [Profit Target]                |
| Qty 15   @ $241.30             |
| UP +$312.00                    |
+--------------------------------+
```

### 7.5 Charts (equity curve)

- **Desktop/wide/tablet:** full-width line chart as drawn in Section 4.13, with all gridlines/axis labels.
- **Mobile:** chart remains full-width but x-axis labels thin out (show every Nth tick, e.g. only year boundaries instead of every quarter) to avoid label collision; the hover-tooltip interaction becomes tap-to-show-tooltip (no native "hover" on touch) and dismisses on tap-away.

### 7.6 Modals/forms

- **Desktop/tablet:** centered modal at its specified max-width (Section 2.4).
- **Mobile:** modals expand to a near-full-screen sheet (full width, ~90% height, slides up from the bottom) rather than a small centered box — a 480px-wide modal centered on a 375px viewport would have negative effective width, so this is a required adaptation, not a stylistic choice. Footer action buttons remain pinned to the bottom of the sheet so they're reachable without scrolling past long form content (relevant for the backtest submission form's ticker checklist, Section 4.11).

---

## 8. Accessibility

### 8.1 Color contrast

- All text/background color pairs in Section 2.1 are chosen to meet **WCAG 2.1 AA** (≥4.5:1 for normal text, ≥3:1 for large/bold text ≥18px) — explicitly verified for `gain-600`/`loss-600` against both `neutral-0` and `neutral-50` backgrounds, since those are the highest-stakes text colors in the product (Section 6.2).
- Badge tints (Section 2.4, 6.3) use a colored *border or text*, not color-fill-only, against a light tint background — text-on-tint pairs are also contrast-checked, not just assumed safe because they "look like" a standard palette.
- Focus rings (`2px solid primary-600`, 2px offset) are checked for contrast against both light card backgrounds and the page background, since a focus ring that disappears against its surface defeats its purpose.

### 8.2 Not relying on color alone

Directly addressed by the three-part P&L convention in Section 6.2 (glyph + explicit sign + color) and the badge-tooltip convention in Section 6.3 (text label, not a bare color swatch) — this satisfies WCAG 1.4.1 (Use of Color) throughout the product, not just as a one-off pattern on the dashboard. Status badges (Active/Deactivated, Running/Complete/Failed) likewise always carry a text label, never a bare colored dot with no label as the only state indicator (the engine status dot in Section 4.10 is always paired with an adjacent text status, e.g. "Idle," "Running," never the dot alone).

### 8.3 Keyboard & focus

- **Full keyboard operability**: every interactive element (nav links, table-row links, buttons, form inputs, modal close/cancel/confirm, filter controls, pagination) is reachable via `Tab` and operable via `Enter`/`Space`, with a visible focus indicator at every step (Section 2.4's focus-ring spec).
- **Logical tab order** follows visual reading order (top-to-bottom, left-to-right) within the nav, then the page content, then any open modal — when a modal opens, focus moves to the modal's first focusable element (typically the first input or the close button) and is trapped within the modal until it closes (focus does not leak back to the underlying page while the modal scrim is up).
- **`Esc` closes the active modal** and returns focus to the element that triggered it (e.g. the "Fund Account" button that opened the modal), a standard and expected pattern.
- **Skip-to-content link** (visually hidden until focused) at the top of every authenticated page, letting a keyboard/screen-reader user bypass the sidebar nav and jump straight to the page's main content — relevant since the sidebar nav repeats on every page and would otherwise have to be tabbed through every single time.
- **Table sort/filter controls** are real `<button>`/`<select>`/`<input>` elements (not div-based fake controls), so they inherit native keyboard behavior and screen-reader semantics for free rather than requiring custom ARIA reimplementation.
- **Live-updating regions** (engine status polling Section 4.10, backtest status polling Section 5.1) use `aria-live="polite"` on the status text so a screen-reader user is told when a run transitions from Running to Complete without needing to manually re-check the page.

---

## 9. Assumptions

Decisions made in this design that go beyond what's explicitly specified in the PRD. Each is a reasonable default chosen to keep the design buildable and internally consistent, not a question left open for the stakeholder — flagged here, as instructed, for visibility and easy revisit later.

1. **No "view as me" admin shortcut.** An Admin who also holds a personal funded account views it through the same per-user inspector (`/admin/users/:userId`) as any other user's account, with full admin chrome — there is no separate lightweight "my own dashboard" view inside the admin shell. (Section 3.1)
2. **No reactivate-user flow.** Soft-deleted (deactivated) users can be viewed but the design does not include a "reactivate" action, since the PRD specifies delete/deactivate but never mentions undoing it. If this is needed, it's a small additive change (an extra action in the same "⋯" menu and Deactivated-tab table) rather than a redesign.
3. **No "last admin" UI guard depicted explicitly.** PRD 10.8 leaves "can the last admin delete themselves/the only other admin" unresolved at the requirements level and says implementation should block it. This design assumes that block is enforced server-side (PRD's own framing) and, if a deactivate action is rejected for that reason, it surfaces through the same generic top-of-form/banner error pattern (Section 5.3) with a specific message (e.g. "You can't deactivate the last active admin.") — no separate UI treatment was designed since this is an edge case, not a primary flow.
4. **Dark mode is out of scope for MVP.** Light theme only (Section 1.2). Revisit if user feedback requests it; the token-based color system (Section 2.1) is structured so a dark variant could be layered in later without a full redesign.
5. **No internationalization/locale support.** All dates, currency, and copy are US English / USD only, consistent with the PRD's explicit "US equities" / USD-only scope — no locale switcher, no alternate date formats designed.
6. **Password minimum length of 8 characters assumed** for the Create User form's client-side validation (Section 4.6) — the PRD specifies hashing/storage requirements (bcrypt/argon2) but not a complexity policy; 8 characters is a reasonable, unobtrusive minimum for an admin-set password in a closed system, not a strict policy with character-class requirements.
7. **No CSV export requirement in the PRD** — "Export CSV" buttons on the trades-today view (Section 4.9) and backtest trade log (Section 4.13) are a design addition supporting the PRD's own stated use case ("useful for spot-checking the engine's per-run behavior," 5.3) rather than a literal requirement. If out of scope for MVP engineering effort, these buttons can be cut without affecting any other part of the design — they're additive, not load-bearing.
8. **Per-ticker breakdown (backtest)** is designed (Section 4.13) but, per PRD 6.4's own framing ("optional nice-to-have, not blocking MVP"), is explicitly not required for initial ship.
9. **Five-card metrics layout (4 + 1 wrap)** for backtest summary metrics (Section 4.13) is a pure layout choice (5 doesn't divide evenly into a clean grid at the chosen card width) — any equivalent grid arrangement (e.g. a 3+2 split, or all 5 in one scrollable row) would satisfy the same requirement equally well.
10. **Engine run polling interval (~3-5s)** and **backtest status polling interval (~3-5s)** are reasonable defaults for "feels responsive without hammering the backend" — not specified by the PRD, easily tuned at implementation time.
11. **Ticker filter dropdown on Regular User trade history is scoped to tickers the user has actually traded**, not the full ~20-30 ticker universe — a minor UX improvement (a shorter, more relevant list) not specified either way in the PRD.
12. **"Trigger Run Now" gets a lightweight confirm dialog, not a heavy double-confirmation pattern** — treated as a routine operational action (reversible in spirit, since it just runs the same logic early) rather than a destructive one; deactivating/deleting a user gets the heavier destructive-button treatment (Section 2.4) since that has a real access-control consequence.
13. **No notion of "draft" backtest configurations** (saving a backtest form's inputs without submitting) — every backtest submission either runs or is discarded; not specified by the PRD and not assumed needed for MVP.
14. **Status-dot + badge visual system (Section 2.1, 4.10) is shared between engine runs and backtest runs** — both are "is a background job healthy" surfaces and intentionally reuse one visual language rather than inventing two, even though the PRD describes them as separate features.
