---
name: mixpanel-session-agent
description: >-
  Pulls a specific user's Mixpanel session replays and produces a session-by-session narrative analysis: what the user did, which actions they took, which UI states they hit, which bugs they encountered. Use whenever someone says "analyze sessions for {user}", "do a session replay analysis", "pull replays for {email/distinct_id}", "session breakdown of {user}", or any variant involving Mixpanel + a specific user + a date range. The skill enforces a one-day-per-call pull, property-name verification against your product's event schema, bug-detection patterns, and an analysis log that prevents redundant re-analysis of past sessions.
---

# Mixpanel Session Agent

## What this is for

Pulls Mixpanel session replays for a single user across a date range, narrates each session in plain English, detects known UI bugs from event patterns, and produces both a markdown narrative and a structured event log.

This skill exists because direct Mixpanel calls hit several traps that took multiple iterations to figure out:

1. The `Get-User-Replays-Data` MCP tool **silently drops sessions** on multi-day windows and caps properties at 5 per call. This skill pulls from the **Raw Export API** instead (`scripts/pull_events.py`), which is deterministic, returns every event property, and costs one HTTP call per day. We still pull one day per call for clean session boundaries, but completeness no longer depends on it.
2. Event property names are not always what you'd guess (for example `agent` not `agent_name`, `toast_title` not `snackbar_message`). Always verify against your product's schema before narrating.
3. Identity filtering is a trap. Mixpanel's export `where` engine silently returns 0 when filtering on `properties["distinct_id"]` under ID-merge, and a server-side `where` on `user_email` is lossy (it misses `$mp_session_record` and pre-login events). The script filters client-side on `$user_id` / `$distinct_id` / `distinct_id`, which is the only complete path. Do not "optimize" this back into a server-side distinct_id filter.
4. Some event names are misleading (a "Context Menu" event might actually be a specific feature menu, not a generic right-click). The event dictionary in `references/events.json` is the source of truth for **your** product.
5. Bugs manifest as event patterns (for example N rapid-fire `Filter Applied` events = a multi-select cascade bug). The skill detects these automatically using patterns you define.
6. Re-analyzing sessions that have already been looked at wastes time. The skill consults `references/analysis_log.json` and only fetches sessions newer than the latest one already analyzed for that user, unless explicitly told to redo the full range.

## Before you use this skill

This is a **template skill**. You must do two things before it produces useful output:

1. **Configure credentials.** Copy `.env.example` to `.env` and fill in `MIXPANEL_API_SECRET` and `MIXPANEL_PROJECT_ID`. The `.env` is gitignored. The script reads it (or your shell environment) automatically.
2. **Populate the reference files** with your product's specifics:
   - `references/events.json`: your product's event dictionary (what each event means, which properties it carries, how to narrate it, which bug patterns to detect)
   - `references/product_modules.md`: context on your product surfaces (page URLs, key UI elements, naming) so narratives use accurate product language
   - `references/analysis_log.json`: starts empty, populated automatically as the skill runs

Each reference file ships as a template with the schema documented and one or two illustrative placeholder entries. Replace the placeholders with your real events and modules before running.

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

Follow these phases in order. Do not skip steps, each one prevents a real failure mode that has happened before.

### Phase 0: Confirm credentials are configured

`scripts/pull_events.py` reads `MIXPANEL_API_SECRET` and `MIXPANEL_PROJECT_ID` from a `.env` at the repo root (or the process environment). If they are missing or still placeholders, the script exits with a clear error. Fill `.env` (template at `.env.example`) before proceeding.

### Phase 1: Resolve the user and the project

1. **Identify the user.** You may be given an email, a distinct_id, or just a name.
   - If given an email: run `pull_events.py --email <email>`. The script pulls each day unfiltered, derives the user's identity id(s) from email-bearing events, then keeps every event (including email-less replay/pre-login events) for that identity. It prints the resolved distinct_id to stderr, record it in the analysis log so future runs can use `--distinct-id`.
   - If given a distinct_id (for example from `analysis_log.json`): use `--distinct-id <id>` directly. This is the canonical, complete path.
   - If given just a name: ask for the email or distinct_id. Don't guess.
2. **Identify the project.** Use the project id in your `.env` (`MIXPANEL_PROJECT_ID`), or pass `--project-id`. If you run multiple environments, confirm which one.
3. **Verify the user exists** by checking the per-day counts the script prints. If every day is 0, the user id is wrong or the date range is wrong, stop and say so.

### Phase 2: Check the analysis log

Read `references/analysis_log.json`. Look up the user by `distinct_id`.

- **If the user is not in the log:** proceed to Phase 3 with the full requested date range.
- **If the user is in the log and has a `latest_analyzed_session_date`:** compare it to the requested range.
  - If the requested range is entirely before `latest_analyzed_session_date`: ask "I've already analyzed all sessions in this range. Want me to re-pull anyway, or skip?"
  - If the requested range overlaps: ask "I've already analyzed sessions through {latest_date}. I can either (a) only pull sessions after that date, or (b) re-pull the full range. Which?"
  - If the requested range is entirely after `latest_analyzed_session_date`: just proceed silently, no question needed.

This prevents wasted work when the same user is analyzed again later.

### Phase 3: Pull the events

Run the export script for the requested range (or the post-`latest_analyzed_session_date` subrange):

```bash
python3 scripts/pull_events.py --distinct-id <id> --from 2026-05-12 --to 2026-06-15 --out user.ndjson
# or, when you only have an email:
python3 scripts/pull_events.py --email user@org.com --from 2026-06-10 --to 2026-06-10 --out user.ndjson
```

The script pulls one day per HTTP call, filters to the target identity client-side, sorts events chronologically, and writes NDJSON (one event per line). It prints per-day counts and the resolved identity id(s) to stderr. The full property bag is returned for every event, so there is no up-front property list to build and nothing has to be re-pulled to get a missing property.

### Phase 4: Know the property names you'll narrate

This is the step that has burned past runs. Do not skip it.

1. For each event you will narrate, cross-reference its property names against `references/events.json`. The HIGH-impact properties you must surface are the ones marked `narrative_impact: HIGH` in the dictionary.
2. After the first day's pull, eyeball the actual property keys present on a few events. If they don't match `events.json`, **the event schema has changed**, flag it and update `events.json`.

### Phase 5: Cross-check against ground truth (when possible)

If a screenshot of the Mixpanel UI showing the session list is provided, cross-check the session and event counts against it. If anything is missing, re-pull that specific day or escalate.

If no screenshot is available, run an Insights query (the MCP tools are fine for this) for a high-signal event (for example your product's primary action) across the window. If the export-tied count is significantly lower than the Insights count, sessions are missing, flag it rather than producing a quietly incomplete analysis.

### Phase 6: Narrate

For each replay (or merged behavioral session), walk the events in chronological order and produce a numbered narrative.

For each event, look it up in `references/events.json`:
- If the event has a `narrative_template`, use it (substituting properties as needed)
- If `skip_in_narrative` is true, omit it
- If the event isn't in the dictionary, **stop and ask what it means**, then add it to `events.json` for future runs
- **Read `property_semantics` before narrating any event.** Each event entry rates each property as HIGH, MEDIUM, or LOW `narrative_impact`. Rules:
  - **HIGH:** you MUST read the property value and use it to shape the bullet. Skipping a HIGH property = confabulating the meaning.
  - **MEDIUM:** mention when it adds clarity, but don't manufacture verbosity.
  - **LOW:** keep in the structured event log for debugging, do not include in the markdown narrative.
- Apply the noise rules defined in `events.json` (skip duplicate `Page Viewed` events when a more specific page-view fires within 1 second, collapse consecutive repetitive clicks into a count, and so on).

### Phase 7: Detect bug patterns

Run all detectors defined in `references/events.json` under `bug_patterns`. New patterns get added there as they're discovered.

Common patterns the template ships with:
- **Filter cascade:** 3 or more `Filter Applied` events within 2 seconds with monotonically shrinking `filter_values` arrays = multi-select cascade bug
- **Repeated error toasts:** multiple error-variant toast/snackbar events for the same user in a session = product is failing them repeatedly
- **Rapid-fire same event:** 4 or more of the same event in under 5 seconds = possible UI feedback loop or accidental clicks

### Phase 8: Output

Produce three files:

1. **`{user_name}_session_analysis.md`**: the narrated markdown
2. **`{user_name}_session_analysis.xlsx`**: two sheets, `Sessions` (one row per session) and `Event Sequence` (one row per event with all properties)
3. **`{user_name}_raw.json`**: the raw event data for archival

### Phase 9: Update the analysis log

Run `scripts/update_log.py` with the new analysis entry. The script:
- Appends a new entry to the user's `analyses` array (or creates a new user entry)
- Recomputes `latest_analyzed_session_date` as the MAX across all sessions in all analyses for that user
- Saves the file

This is what makes the next run efficient.

## Output style

Narratives should be interpretive, not mechanical. Use product names from `references/product_modules.md`, not generic terms. Keep data-pipeline mechanics (export API, Insights cross-check) out of the output, the reader sees only what the user did and what happened.

For known bugs, surface them inline at the moment they happened, not just in a footer. Example:
> ⚠️ **BUG DETECTED:** The user clicked a single filter, but the system selected all 7 sub-items at once. They then had to uncheck them one-by-one over 11 seconds.

End each session narrative with "Then the session ended."

## When to ask vs proceed silently

**Ask before proceeding** when:
- An event name is not in the dictionary
- Property names in the data don't match the dictionary (schema drift)
- The export-tied event count is significantly lower than the Insights count for the same window
- A new bug pattern emerges that isn't in the detectors yet

**Proceed silently** when:
- The skill is doing its normal job and everything matches expectations
- Pulling data day-by-day (don't narrate each pull)
- Routing through the analysis log

## Reference files

- `references/events.json`: event dictionary. The source of truth for what every product event means, which properties it carries, how to narrate it, and which bug patterns to detect.
- `references/product_modules.md`: context about your product's surfaces so narratives use the right product language.
- `references/analysis_log.json`: memory of past analyses. Tracks which sessions have already been analyzed so the skill doesn't redo work.

## Common mistakes to avoid

1. **Don't pull replays through the `Get-User-Replays-Data` MCP tool.** It drops sessions and caps properties. Use `scripts/pull_events.py` (Raw Export API).
2. **Don't move identity filtering server-side.** The client-side `$user_id` / `$distinct_id` / `distinct_id` match in the script is the only complete path under ID-merge.
3. **Don't guess property names.** Verify against the schema each run.
4. **Don't trust the event name to mean what it sounds like.** Read the dictionary.
5. **Don't narrate pure telemetry events** (chart-loaded, page-render-timing, and the like). Mark them `skip_in_narrative: true` in `events.json`.
6. **Don't claim instrumentation is broken without checking another user first.** If an event is missing for one user, check whether it exists for another before filing it as a bug.
7. **Don't re-analyze sessions already in the log unless asked.** Check `analysis_log.json` first.
8. **Don't skip the cross-check.** If a Mixpanel UI screenshot is provided, verify session counts before narrating. If you can't, run an Insights count as a sanity check.
