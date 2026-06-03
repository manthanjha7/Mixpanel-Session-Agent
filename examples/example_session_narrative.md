# Jane Doe — Session Analysis

**Email:** jane@example.com
**Organization:** Example Co
**Date range:** 2026-05-20 to 2026-06-01
**Sessions analyzed:** 2

---

## Session 1 — 2026-05-20 (18 events)

1. The user signed in via SSO.
2. The user landed on the Home page.
3. The user submitted a query: _"How do I configure project alerts?"_
4. The user selected the **Default Assistant**.
5. The response loaded. The user clicked 3 source citations in succession.
6. The user submitted a follow-up query: _"Can I scope this to a single project?"_
7. The user clicked **Export**.
8. ✅ **"Download started"** appeared.
9. Then the session ended.

---

## Session 2 — 2026-05-28 (42 events)

1. The user signed in via SSO.
2. The user landed on the Search page.
3. The user typed a query: _"open issues assigned to me"_ and submitted.
4. The user clicked a single category filter (`category_A`).
5. ⚠️ **BUG DETECTED:** The system selected all 7 sub-items in the category at once. The user then unchecked them one-by-one over 11 seconds to isolate just `category_A`. (Matches `bug_patterns.filter_cascade`.)
6. The user opened 5 result cards in succession.
7. ❌ **"Connection Error"** appeared.
8. The user retried the query.
9. The response loaded successfully.
10. Then the session ended.

---

## Patterns detected this window

- **Filter cascade** (Session 2) — single click on a parent filter selected all sub-items. See `bug_patterns.filter_cascade` in `events.json`.
- **Connection error** (Session 2) — 1 occurrence. Not yet a pattern, but track if recurring.
