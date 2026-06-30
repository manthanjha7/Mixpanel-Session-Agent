# Mixpanel Session Agent

An AI-agent skill that pulls a specific user's Mixpanel session replays and produces a session-by-session narrative analysis: what the user did, which actions they took, which UI states they hit, which bugs they encountered.

Built originally for an internal PM workflow (analyzing how individual customers actually use a product), then generalized into a reusable template. The skill exists because direct Mixpanel calls hit several non-obvious failure modes (silent session drops on multi-day windows, a 5-property cap, lossy identity filtering, surprising property names, misleading event names). Centralizing the workarounds into a skill is the only way to get repeatable, trustworthy output.

---

## What it does

Given a single user (email or `distinct_id`) and a date range, the skill:

1. Resolves the user against your Mixpanel project.
2. Checks an on-disk analysis log so it doesn't re-pull sessions already analyzed.
3. Pulls every event for that user from the **Mixpanel Raw Export API** (`scripts/pull_events.py`), one HTTP call per day, with the full property bag and complete, deterministic identity matching.
4. Verifies event property names against your product's event dictionary before narrating.
5. Cross-checks against an Insights-derived ground-truth count, or against a screenshot if you provide one.
6. Narrates each session in plain English, using your product's vocabulary.
7. Runs deterministic bug-pattern detectors (filter cascades, repeated error toasts, rapid-fire clicks).
8. Outputs a markdown narrative, a structured event log, and raw JSON.
9. Updates the analysis log so the next run is incremental.

The narrative reads like a PM walked through the replay, not like a dump of event names.

---

## Requirements

- Python 3.10+ and `requests` (`pip install -r requirements.txt`).
- A Mixpanel **project API secret** and **project id** (set in `.env`, see below).
- A populated `references/events.json` describing **your** product's Mixpanel events. The repo ships a template with the full schema and placeholder entries, you fill it in once for your product.
- An AI agent runtime that can read `SKILL.md` and run the scripts. The Mixpanel MCP server is optional and only used for the Phase 5 Insights cross-check, the replay pull does not need it.

The skill does **not** ship with any API keys, tokens, or customer data. Your `.env` is gitignored.

---

## Install

Drop the repo into your agent's skills directory:

```bash
git clone https://github.com/manthanjha7/Mixpanel-Session-Agent.git ~/.agent/skills/mixpanel-session-agent
cd ~/.agent/skills/mixpanel-session-agent
pip install -r requirements.txt
```

Or, if you keep skills in a project repo:

```bash
git clone https://github.com/manthanjha7/Mixpanel-Session-Agent.git .agent/skills/mixpanel-session-agent
```

The exact path depends on your agent runtime. Point your agent at the `SKILL.md` file and it will load the workflow.

---

## Configure for your product (one-time setup)

### 0. Credentials (`.env`)

Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
# MIXPANEL_API_SECRET=...   (Project Settings, Access Keys)
# MIXPANEL_PROJECT_ID=...   (Project Settings, Overview)
```

`.env` is gitignored. `scripts/pull_events.py` reads it (or your shell environment) automatically and exits with a clear error if the values are still placeholders.

### 1. `references/events.json`

Your product's event dictionary. For every event you want narrated, add an entry with:

- `module`: which product surface the event belongs to (for example `home`, `search`, `checkout`)
- `meaning`: one-line description of what triggers it
- `narrative_template`: how to render it in plain English (use `{property}` placeholders)
- `key_properties`: the top properties worth surfacing
- `property_semantics`: per-property notes flagging `HIGH | MEDIUM | LOW` `narrative_impact` so the agent knows which ones must be read vs which are just for the structured log

Also define `bug_patterns` (deterministic detectors) and `noise_rules` (events to collapse or skip). The template ships with three common bug patterns (filter cascade, repeated error toasts, rapid-fire same event), keep, modify, or remove them.

### 2. `references/product_modules.md`

Free-form context about your product's surfaces: page URLs, key UI elements, modes, common entity names. This is what the agent reads to narrate sessions in your product's voice (for example "Then the user opened the Reports page" instead of "Then a page-view fired").

### 3. `references/analysis_log.json`

Starts empty. The skill populates this automatically as you run analyses. Don't edit by hand, use `scripts/update_log.py`.

---

## Usage

Pull events for a user directly:

```bash
python3 scripts/pull_events.py --distinct-id <id> --from 2026-05-20 --to 2026-06-01 --out user.ndjson
# or, when you only have an email:
python3 scripts/pull_events.py --email jane@example.com --from 2026-05-20 --to 2026-06-01 --out user.ndjson
```

Or, in an agent session, just ask in plain English:

```
Analyze sessions for jane@example.com from 2026-05-20 to 2026-06-01
```

Other triggers the skill responds to:

- "Pull Mixpanel replays for `<distinct_id>`"
- "What did `<user>` do in `<product>` last week"
- "Session-by-session breakdown of `<user>`"
- "Debug `<user>`'s flow / why did `<user>` get stuck"

The skill produces three artifacts per run:

- `{user_name}_session_analysis.md`: the narrated markdown (the main output)
- `{user_name}_session_analysis.xlsx`: `Sessions` sheet + `Event Sequence` sheet
- `{user_name}_raw.json`: raw event data for archival and re-analysis

See `examples/example_session_narrative.md` for what the markdown output looks like.

---

## Why this exists (the war stories)

Each phase of the workflow encodes a real failure mode:

| Failure | Fix |
| --- | --- |
| `Get-User-Replays-Data` returns fewer sessions on multi-day calls than on one-day calls covering the same window, and caps properties at 5 per call | Pull from the Raw Export API (`pull_events.py`): complete, deterministic, full property bag, one call per day |
| Filtering on `distinct_id` server-side silently returns 0 under ID-merge, and a `user_email` `where` misses pre-login and session-record events | Match identity client-side on `$user_id` / `$distinct_id` / `distinct_id` (handled in the script) |
| Property names don't match what you'd guess from the event name | Verify against `events.json` before narrating; flag schema drift |
| Event names are misleading (a "Context Menu" event was actually one specific feature menu) | Encode the meaning in `events.json` rather than guessing from the name |
| Same user analyzed repeatedly wastes time | Persistent `analysis_log.json` skips already-analyzed sessions |
| Narratives that just list events read like garbage to a PM | `narrative_template` + `property_semantics` per event |

If you're running ad-hoc Mixpanel session analyses today, you've probably hit at least three of these. This skill is the codified version of the fix.

---

## Repo structure

```
.
├── SKILL.md                       # Skill definition the agent reads
├── README.md                      # You are here
├── LICENSE                        # MIT
├── requirements.txt               # Python deps (requests)
├── .env.example                   # Copy to .env, fill in your Mixpanel secret + project id
├── references/
│   ├── events.json                # YOUR product's event dictionary (template)
│   ├── product_modules.md         # YOUR product's surfaces (template)
│   └── analysis_log.json          # auto-populated; starts empty
├── scripts/
│   ├── pull_events.py             # Raw Export API pull (the data source)
│   └── update_log.py              # Maintains analysis_log.json
└── examples/
    ├── example_analysis_entry.json    # Shape of an entry passed to update_log.py
    └── example_session_narrative.md   # Example of the markdown output
```

---

## License

MIT, see [LICENSE](LICENSE).

---

## Authors

Built by **Pihoo** and **Manthan**. Originally developed for an internal product-analytics workflow, generalized for public reuse.
