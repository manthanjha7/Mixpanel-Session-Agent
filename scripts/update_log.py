#!/usr/bin/env python3
"""
update_log.py — Append a new analysis entry to references/analysis_log.json
and recompute latest_analyzed_session_date for the user.

Usage:
    python update_log.py <distinct_id> <user_json_file>
    python update_log.py --get-latest <distinct_id>

Where <user_json_file> is a JSON file with this shape:
{
  "user_name": "Jane Doe",
  "email": "jane@example.com",
  "organization": "Example Co",
  "date_range_requested": "YYYY-MM-DD to YYYY-MM-DD",
  "method": "1-day chunks",
  "sessions_analyzed": [
    {
      "date": "YYYY-MM-DD",
      "replay_id": "...",
      "event_count": 22,
      "summary": "...",
      "agents_used": [...],
      "snackbars": [...]
    },
    ...
  ]
}

This script:
1. Loads references/analysis_log.json (or creates it if missing)
2. Looks up the user by distinct_id
3. Appends the new analysis entry to the user's analyses array
4. Recomputes latest_analyzed_session_date as the MAX session date across ALL analyses
5. Writes the file back
"""

import json
import sys
from pathlib import Path
from datetime import date


def update_log(log_path: Path, distinct_id: str, new_analysis: dict) -> None:
    if log_path.exists():
        with open(log_path) as f:
            log = json.load(f)
    else:
        log = {
            "schema_version": "1.0",
            "description": "Memory of past Mixpanel session analyses run by this skill.",
            "users": {},
        }

    users = log.setdefault("users", {})

    if distinct_id not in users:
        users[distinct_id] = {
            "user_name": new_analysis.get("user_name", "Unknown"),
            "email": new_analysis.get("email", ""),
            "organization": new_analysis.get("organization", ""),
            "analyses": [],
            "latest_analyzed_session_date": None,
        }

    user = users[distinct_id]

    for field in ("user_name", "email", "organization", "role"):
        if field in new_analysis and new_analysis[field]:
            user[field] = new_analysis[field]

    analysis_entry = {
        "analysis_date": new_analysis.get("analysis_date", date.today().isoformat()),
        "date_range_requested": new_analysis.get("date_range_requested", ""),
        "method": new_analysis.get("method", "1-day chunks"),
        "sessions_analyzed": new_analysis.get("sessions_analyzed", []),
    }

    user["analyses"].append(analysis_entry)

    all_session_dates = []
    for analysis in user["analyses"]:
        for sess in analysis.get("sessions_analyzed", []):
            d = sess.get("date")
            if d:
                all_session_dates.append(d)

    if all_session_dates:
        user["latest_analyzed_session_date"] = max(all_session_dates)

    with open(log_path, "w") as f:
        json.dump(log, f, indent=2)

    print(f"✓ Updated log for {user.get('user_name', distinct_id)}")
    print(f"  Total analyses: {len(user['analyses'])}")
    print(f"  Sessions in this analysis: {len(analysis_entry['sessions_analyzed'])}")
    print(f"  Latest analyzed session date: {user['latest_analyzed_session_date']}")


def get_latest_for_user(log_path: Path, distinct_id: str) -> str | None:
    """Helper: read just the latest_analyzed_session_date for a user. Returns None if user not in log."""
    if not log_path.exists():
        return None
    with open(log_path) as f:
        log = json.load(f)
    user = log.get("users", {}).get(distinct_id)
    if not user:
        return None
    return user.get("latest_analyzed_session_date")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python update_log.py <distinct_id> <user_json_file>")
        print("  or:  python update_log.py --get-latest <distinct_id>")
        sys.exit(1)

    log_path = Path(__file__).parent.parent / "references" / "analysis_log.json"

    if sys.argv[1] == "--get-latest":
        distinct_id = sys.argv[2]
        latest = get_latest_for_user(log_path, distinct_id)
        if latest:
            print(latest)
        else:
            print("(no prior analyses for this user)")
        sys.exit(0)

    distinct_id = sys.argv[1]
    user_json_file = Path(sys.argv[2])

    with open(user_json_file) as f:
        new_analysis = json.load(f)

    update_log(log_path, distinct_id, new_analysis)
