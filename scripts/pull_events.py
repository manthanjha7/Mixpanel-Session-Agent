#!/usr/bin/env python3
"""
pull_events.py: pull one user's raw events from the Mixpanel Raw Export API.

This REPLACES the `Get-User-Replays-Data` MCP tool. The MCP tool silently drops
sessions on multi-day windows and caps properties at 5 per call. The Raw Export API
(https://data.mixpanel.com/api/2.0/export) is deterministic and complete, returns ALL
event properties (no 5-property cap), and costs one HTTP call per day.

Auth and project are read from a `.env` at the repo root (gitignored) or from the
process environment:
  MIXPANEL_API_SECRET     required. Mixpanel project API secret (basic-auth username).
  MIXPANEL_PROJECT_ID     required. The numeric project id to export from.
  MIXPANEL_PROJECT_TOKEN  optional. Client project token; only used to build
                          "Watch replay" deep links. Omitted links degrade gracefully.

Output: NDJSON (one event per line), sorted by event time, filtered to the target user.
Per-day event counts are printed to stderr so the caller can sanity-check completeness.

Usage:
  python3 pull_events.py --distinct-id <id> --from 2026-05-12 --to 2026-06-15
  python3 pull_events.py --email user@org.com --from 2026-06-10 --to 2026-06-10
  python3 pull_events.py --distinct-id <id> --from 2026-06-01 --to 2026-06-15 --out user.ndjson
"""
import argparse
import json
import os
import sys
from datetime import date, timedelta

import requests

EXPORT_URL = "https://data.mixpanel.com/api/2.0/export"


def find_repo_root(start):
    """Walk up from `start` until a directory containing .git is found."""
    d = os.path.abspath(start)
    while d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, ".git")):
            return d
        d = os.path.dirname(d)
    return None


def load_env():
    """Load a `.env` at the repo root into os.environ (without overriding existing vars)."""
    root = find_repo_root(__file__) or find_repo_root(os.getcwd())
    if not root:
        return
    env_path = os.path.join(root, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def daterange(from_date, to_date):
    start = date.fromisoformat(from_date)
    end = date.fromisoformat(to_date)
    cur = start
    while cur <= end:
        yield cur.isoformat()
        cur += timedelta(days=1)


def export_day(day, where, project_id, secret):
    """Fetch one day of raw events. `where` is an optional server-side filter expression.

    NOTE on identity filtering: Mixpanel's export `where` engine does NOT match on the
    displayed `properties["distinct_id"]` once ID-merge is on (it silently returns 0), and
    OR-ing the identity keys in `where` over-matches. So we only use server-side `where`
    for a clean property like `user_email`; distinct_id filtering is done client-side
    (see `matches_distinct_id`), which is deterministic.
    """
    params = {"from_date": day, "to_date": day}
    if where:
        params["where"] = where
    resp = requests.get(
        EXPORT_URL,
        params=params,
        auth=(secret, ""),
        headers={"X-Mixpanel-Project-Id": project_id},
        timeout=120,
    )
    resp.raise_for_status()
    events = []
    for line in resp.text.splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


def matches_distinct_id(event, target):
    """True if the event belongs to `target` under any identity key.

    The export `where` engine can't reliably filter on distinct_id under ID-merge, so we
    match client-side against $user_id / $distinct_id / distinct_id. This also catches
    pre-login events that carry no user_email.
    """
    p = event.get("properties", {})
    return target in (p.get("$user_id"), p.get("$distinct_id"), p.get("distinct_id"))


def main():
    p = argparse.ArgumentParser(description="Pull one user's raw Mixpanel events via the Export API.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--distinct-id", help="Mixpanel distinct_id to filter on")
    g.add_argument("--email", help="user_email to filter on (no distinct_id resolution needed)")
    p.add_argument("--from", dest="from_date", required=True, help="YYYY-MM-DD (inclusive)")
    p.add_argument("--to", dest="to_date", required=True, help="YYYY-MM-DD (inclusive)")
    p.add_argument("--project-id", help="Mixpanel project id (overrides MIXPANEL_PROJECT_ID)")
    p.add_argument("--out", help="write NDJSON here (default: stdout)")
    args = p.parse_args()

    load_env()
    secret = os.environ.get("MIXPANEL_API_SECRET", "")
    if not secret or secret.startswith("PASTE_") or secret.startswith("your-"):
        sys.exit("ERROR: MIXPANEL_API_SECRET not configured. Set it in a .env at the repo root "
                 "(see .env.example) or export it in your shell.")
    project_id = args.project_id or os.environ.get("MIXPANEL_PROJECT_ID", "")
    if not project_id or project_id in ("0", "your-project-id"):
        sys.exit("ERROR: project id not configured. Pass --project-id or set MIXPANEL_PROJECT_ID "
                 "in a .env at the repo root (see .env.example).")

    # We always pull the full day unfiltered and filter client-side. Server-side `where` on
    # user_email is lossy: user_email is absent on $mp_session_record and pre-login events
    # (it returned only 4 of 33 events for a user who actually had 33). Client-side identity
    # matching is the only complete, deterministic path.
    who = args.distinct_id or args.email
    resolved_ids = set()  # identity ids we've tied to the target (for email mode)

    all_events = []
    per_day = {}
    skipped = []
    for day in daterange(args.from_date, args.to_date):
        try:
            events = export_day(day, None, project_id, secret)
        except requests.HTTPError as e:
            resp = getattr(e, "response", None)
            status = getattr(resp, "status_code", None)
            body = (getattr(resp, "text", "") or "").strip()
            # Mixpanel's "today" (project timezone) can lag the local date, so a requested
            # day at/after that boundary 400s with "cannot be later than today". Don't let
            # one such day abort a multi-day pull, warn and skip it.
            if status == 400 and "later than today" in body:
                print(f"  {day}: SKIPPED, not available yet ({body})", file=sys.stderr)
                per_day[day] = 0
                skipped.append(day)
                continue
            if status in (401, 403):
                sys.exit(f"ERROR: auth rejected ({status}). Check MIXPANEL_API_SECRET. "
                         f"Detail: {body[:200]}")
            sys.exit(f"ERROR pulling {day}: {e}, {body[:300]}")

        if args.distinct_id:
            kept = [e for e in events if matches_distinct_id(e, args.distinct_id)]
            resolved_ids.add(args.distinct_id)
        else:
            # Resolve this day's identity ids from email-bearing events, then keep every event
            # (including email-less replay/pre-login events) carrying any of those ids.
            for e in events:
                if e.get("properties", {}).get("user_email") == args.email:
                    p = e["properties"]
                    resolved_ids.update(
                        v for v in (p.get("$user_id"), p.get("$distinct_id"), p.get("distinct_id")) if v
                    )
            kept = [e for e in events if any(matches_distinct_id(e, i) for i in resolved_ids)]

        per_day[day] = len(kept)
        all_events.extend(kept)
        print(f"  {day}: {len(kept)} events", file=sys.stderr)

    # Sort chronologically by Mixpanel event time (properties.time, unix seconds)
    all_events.sort(key=lambda e: e.get("properties", {}).get("time", 0))

    out = open(args.out, "w") if args.out else sys.stdout
    try:
        for e in all_events:
            out.write(json.dumps(e, ensure_ascii=False) + "\n")
    finally:
        if args.out:
            out.close()

    active_days = sum(1 for n in per_day.values() if n)
    print(f"\nTOTAL: {len(all_events)} events for {who} across "
          f"{active_days}/{len(per_day)} active days "
          f"({args.from_date} to {args.to_date})", file=sys.stderr)
    if skipped:
        print(f"NOTE: {len(skipped)} day(s) skipped (not yet available in Mixpanel): "
              f"{', '.join(skipped)}", file=sys.stderr)
    if args.email and resolved_ids:
        print(f"Resolved identity id(s) for {args.email}: {', '.join(sorted(resolved_ids))}",
              file=sys.stderr)
    if args.out:
        print(f"Wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
