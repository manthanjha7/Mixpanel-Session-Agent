# Product Modules — Context for Session Analysis

> **TEMPLATE FILE.** Replace the placeholder content below with your product's real surfaces. The point of this file is to give the agent enough vocabulary to narrate sessions in your product's voice — page names, button names, mode names, known UI quirks. Each section below shows the shape; fill it in for your product.

This file documents your product's surfaces so session narratives use accurate, on-brand product language. Read this whenever you encounter an event you're not sure how to describe — the module names here should match the `module` field in `events.json`.

---

## <module_id_1> — <Human Readable Name>

**URL pattern:** `/your-route` (and `/your-route/{detail_id}` for detail pages)

**What it is:** One-paragraph description of this surface. What's the user trying to accomplish here?

**Key UI surfaces:**

- **<Element name>** — what it looks like, where it lives, which event fires when the user interacts with it.
- **<Another element>** — same shape.

**Modes / variants** (if any): describe the tabs, modes, or states this surface can be in, and any constraints (e.g., "Task mode requires selecting an agent first, otherwise the user gets an error toast").

**Common entities seen in production** (agent names, document types, etc.):
- `Example`
- `Example`

---

## <module_id_2> — <Another Surface>

Same shape as above.

---

## navigation — Persistent navigation

**What it is:** The persistent nav (top bar, side bar, etc.) shared across pages.

**Key UI surfaces:**

- **Nav buttons** — fires `<your_nav_event>`. To know **which** destination, look at the next page-view event in sequence:
  - Next event `<Module 1 Page Viewed>` → Module 1 button
  - Next event `<Module 2 Page Viewed>` → Module 2 button

---

## auth — Authentication

**What it is:** Sign-in flow (SSO / OAuth / password / etc.).

**Key event:** `<your_auth_event>` — fires at the start of a session right after sign-in. Translates to "user signed in" in narrative.

---

## shared — Cross-cutting concerns

Events that don't belong to a single module but appear across many:

- **<Toast/Snackbar event>** — properties: `toast_title`, `variant`. `variant` decides ✅ vs ❌ in narrative.
- **<Filter event>** — used by multiple modules. Carries `filter_key` and `filter_values`.
- **Page Viewed** — generic, often noise.

---

## Quick reference: which module does what event belong to?

```
module_1:    Event A, Event B, Event C
module_2:    Event D, Event E
navigation:  Nav Button Clicked, Back Clicked
auth:        login_event
shared:      Toast Shown, Filter Applied, Page Viewed
```

---

## Narrative voice guidelines

- **Use product names, not generic terms.** "<Your Product Page>" not "the page". Specific feature names not "the feature".
- **Surface bugs at the moment they happened**, not just in a footer. Use ⚠️ inline.
- **Bold key entity selections**: "Then the user selected the **Default Assistant**".
- **For toasts, use emoji + bold**: ✅ for success, ❌ for error, **bold the toast title**.
- **End each session** with "Then the session ended."
- **Skip pure render telemetry** and collapse noisy repeated events per the rules in `events.json` → `noise_rules`.
