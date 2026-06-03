---
name: mixpanel-session-agent
description: >-
  Pulls a specific user's Mixpanel session replays and produces a session-by-session narrative analysis — what the user did, which actions they took, which UI states they hit, which bugs they encountered. Use whenever someone says "analyze sessions for {user}", "do a session replay analysis", "pull replays for {email/distinct_id}", "session breakdown of {user}", or any variant involving Mixpanel + a specific user + a date range. The skill enforces the 1-day chunking rule, property-name verification against your product's event schema, bug-detection patterns, and an analysis log that prevents redundant re-analysis of past sessions.
---

# Mixpanel Session Agent

## What this is for

Pulls Mixpanel session replays for a single user across a date range, narrates each session in plain English, detects known UI bugs from event patterns, and produces both a markdown narrative and a structured event log.

This skill exists because direct Mixpanel calls hit several traps that took multiple iterations to figure out:

1. The `Get-User-Replays-Data` MCP tool **silently drops sessions** when called with multi-day windows. Always pull in 1-day chunks.
2. Event property names are not always what you'd guess (e.g. `agent` not `agent_name`, `toast_title` not `snackbar_message`). Always verify against your product's schema before pulling.
3. Many product events fire with sparse properties unless you explicitly request them. The full property list must be requested.
4. Some event names are misleading (a "Context Menu" event might actually be a specific feature menu, not a generic right-click). The event dictionary in `references/events.json` should be the source of truth for **your** product.
5. Bugs manifest as event patterns (e.g., N rapid-fire `Filter Applied` events = a multi-select cascade bug). The skill detects these automatically using patterns you define.
6. Re-analyzing sessions that have already been looked at wastes time. The skill consults `references/analysis_log.json` and only fetches sessions newer than the latest one already analyzed for that user — unless explicitly told to redo the full range.

## Before you use this skill

This is a **template skill**. You must populate three reference files with **your product's** specifics before it produces useful output:

1. `references/events.json` — your product's event dictionary (what each Mixpanel event means, which properties it carries, how to narrate it, which bug patterns to detect)
2. `references/product_modules.md` — context on your product surfaces (page URLs, key UI elements, naming) so narratives use accurate product language
3. `references/analysis_log.json` — starts empty; populated automatically as the skill runs

Each file ships as a template with the schema documented and 1–2 illustrative placeholder entries. Replace the placeholders with your real events / modules before running.

## When to trigger

Trigger on phrases like:
- "Analyze sessions for {user}"
- "Pull Mixpanel replays for {email or distinct_id}"
- "What did {user} do in {product} between {date} and {date}"
- "Session-by-session breakdown of {user}"
- "Debug {user}'s flow / why did {user} get stuck"
- "Run the session analysis on {user}"

If the user mentions Mixpanel + a specific end user + asks anything about their behavior, this skill applies. Do not bypass it and call Mixpanel tools directly.

## Workflow

Follow these phases in order. Do not skip steps — each one prevents a real failure mode that has happened before.

### Phase 1 — Resolve the user and the project

1. **Identify the user.** You may be given an email, a distinct_id, or just a name.
   - If given an email: query Insights with `filters: [{propertyName: "<your_email_property>", value: "<email>"}]` breakdown by `$distinct_id` to resolve the distinct_id. Use a wide date range (60 days back).
   - If given a distinct_id: use it directly.
   - If given just a name: ask for the email or distinct_id. Don't guess.
2. **Identify the project.** Default to the production project documented in `references/events.json` → `project_name`. If multiple environments exist, ask which one.
3. **Verify the user exists** by running a quick `$any_event` total count for the requested window. If 0 events, the user is wrong or the date range is wrong — stop and say so.

### Phase 2 — Check the analysis log

Read `references/analysis_log.json`. Look up the user by `distinct_id`.

- **If the user is not in the log:** proceed to Phase 3 with the full requested date range.
- **If the user is in the log and has a `latest_analyzed_session_date`:** compare it to the requested range.
  - If the requested range is entirely before `latest_analyzed_session_date`: ask "I've already analyzed all sessions in this range. Want me to re-pull anyway, or skip?"
  - If the requested range overlaps: ask "I've already analyzed sessions through {latest_date}. I can either (a) only pull sessions after that date, or (b) re-pull the full range. Which?"
  - If the requested range is entirely after `latest_analyzed_session_date`: just proceed silently — no question needed.

This prevents wasted work when the same user is analyzed again later.

### Phase 3 — Verify event property names BEFORE pulling

This is the step that has burned past runs. Do not skip it.

1. Call `Mixpanel:Get-Property-Names` for each event you intend to extract properties from.
2. Cross-reference with the property names listed in `references/events.json` for that event. If they match, proceed. If they don't, **the event schema has changed since this skill was last updated** — flag it and update `events.json`.
3. Build the `event_properties` parameter list. The MCP tool accepts up to 5 properties per call. Prioritize the properties marked `narrative_impact: HIGH` in `events.json`.

### Phase 4 — Pull data in 1-day chunks

For each day in the requested range (or the post-`latest_analyzed_session_date` subrange):

```
Mixpanel:Get-User-Replays-Data(
  distinct_id=<distinct_id>,
  project_id=<project_id>,
  from_date=<YYYY-MM-DD>,
  to_date=<YYYY-MM-DD>,    # same as from_date for 1-day window
  event_properties=[<up to 5 HIGH-impact properties from Phase 3>]
)
```

**Never pull a multi-day window.** A multi-day call drops sessions silently — verified empirically across multiple users. The cost of N single-day calls is not high; the cost of missing a session is.

For each day:
- If the API returns "No replays available", that day has no sessions — note it and continue.
- If the API returns replays with `replay_events: []`, those are idle/scroll-only sessions — keep them in the raw data but mark them empty.
- If the API returns replays with events, save them to the working JSON.

### Phase 5 — Cross-check against ground truth (when possible)

If a screenshot of the Mixpanel UI showing the session list is provided, cross-check the count of sessions and event counts against the screenshot. If anything is missing, retry that specific day with a different chunk boundary or escalate.

If no screenshot is available, run an Insights query for a high-signal event (e.g. your product's primary action) count for the user across the window. If the replay-tied count is significantly lower than the Insights count, sessions are missing — flag it rather than producing a quietly incomplete analysis.

### Phase 6 — Narrate

For each replay (or merged behavioral session), walk the events in chronological order and produce a numbered narrative.

For each event, look it up in `references/events.json`:
- If the event has a `narrative_template`, use it (substituting properties as needed)
- If `skip_in_narrative` is true, omit it
- If the event isn't in the dictionary, **stop and ask what it means** — then add it to `events.json` for future runs
- **Read `property_semantics` before narrating any event.** Each event entry carries a `property_semantics` block that rates each property as HIGH, MEDIUM, or LOW `narrative_impact`. Rules:
  - **HIGH** — you MUST read the property value and use it to shape the bullet. Skipping a HIGH property = confabulating the meaning.
  - **MEDIUM** — mention when it adds clarity, but don't manufacture verbosity.
  - **LOW** — keep in the structured event log for debugging; do not include in the markdown narrative.
- Apply the noise rules defined in `events.json` (skip duplicate `Page Viewed` events when a more specific page-view fires within 1 second, collapse consecutive repetitive clicks into a count, etc.).

### Phase 7 — Detect bug patterns

Run all detectors defined in `references/events.json` → `bug_patterns`. New patterns get added there as they're discovered.

Common patterns the template ships with:
- **Filter cascade**: ≥3 `Filter Applied` events within 2 seconds with monotonically shrinking `filter_values` arrays → multi-select cascade bug
- **Returning-user onboarding**: first-run popup fires for a user whose first session was more than 7 days ago
- **Repeated error toasts**: multiple error-variant toast/snackbar events for the same user in a session → product is failing them repeatedly
- **Rapid-fire same event**: ≥4 of the same event in <5 seconds → possible UI feedback loop or accidental clicks

### Phase 8 — Output

Produce three files:

1. **`{user_name}_session_analysis.md`** — the narrated markdown
2. **`{user_name}_session_analysis.xlsx`** — two sheets: `Sessions` (one row per session) and `Event Sequence` (one row per event with all properties)
3. **`{user_name}_raw.json`** — the raw event data for archival

### Phase 9 — Update the analysis log

Run `scripts/update_log.py` with the new analysis entry. The script:
- Appends a new entry to the user's `analyses` array (or creates a new user entry)
- Recomputes `latest_analyzed_session_date` as the MAX across all sessions in all analyses for that user
- Saves the file

This is what makes the next run efficient.

## Output style

Narratives should be interpretive, not mechanical. Use product names from `references/product_modules.md`, not generic terms.

For known bugs, surface them inline at the moment they happened, not just in a footer. Example:
> ⚠️ **BUG DETECTED:** The user clicked a single filter, but the system selected all 7 sub-items at once. They then had to uncheck them one-by-one over 11 seconds.

End each session narrative with "Then the session ended."

## When to ask vs proceed silently

**Ask before proceeding** when:
- An event name is not in the dictionary
- Property names returned by the schema don't match the dictionary (schema drift)
- Replay-tied event count is significantly lower than Insights count for the same window
- A new bug pattern emerges that isn't in the detectors yet

**Proceed silently** when:
- The skill is doing its normal job and everything matches expectations
- Pulling data day-by-day (don't narrate each pull)
- Routing through the analysis log

## Reference files

- `references/events.json` — Event dictionary. The source of truth for what every product event means, which properties it carries, how to narrate it, and which bug patterns to detect.
- `references/product_modules.md` — Context about your product's surfaces so the narratives use the right product language.
- `references/analysis_log.json` — Memory of past analyses. Tracks which sessions have already been analyzed so the skill doesn't redo work.

## Common mistakes to avoid

1. **Don't call `Get-User-Replays-Data` with a multi-day window.** It drops sessions. 1 day per call. Always.
2. **Don't guess property names.** Verify against the schema each run.
3. **Don't trust the event name to mean what it sounds like.** Read the dictionary.
4. **Don't narrate pure telemetry events** (chart-loaded, page-render-timing, etc.). Mark them `skip_in_narrative: true` in `events.json`.
5. **Don't claim instrumentation is broken without checking another user first.** If an event is missing for one user, check if it exists for another before filing it as a bug.
6. **Don't re-analyze sessions already in the log unless asked.** Check `analysis_log.json` first.
7. **Don't skip the verification step.** If a Mixpanel UI screenshot is provided, cross-check session counts before producing the narrative. If you can't verify, run an Insights count as a sanity check.
