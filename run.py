#!/usr/bin/env python3
import os
import sys
import threading
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

load_dotenv()

repo_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.join(repo_dir, "app")
sys.path.insert(0, app_dir)


def background_fetch_all():
    """
    Runs every 6 hours:
    1. Re-fetch jobs for every saved search in the DB.
    2. Insert any new jobs found.
    3. Remove jobs older than 72 hours that are not applied/bookmarked.
    """
    try:
        from job_agent import JobAIAgent
        from job_db import init_db, get_saved_searches, insert_jobs, remove_stale_jobs
        from job_fetcher import fetch_jobs

        init_db()
        searches = get_saved_searches()

        if not searches:
            # Default seed search when no user searches have been saved yet
            searches = [
                {"designation": "devops engineer",   "skills": ["docker", "kubernetes"], "location": ""},
                {"designation": "software engineer",  "skills": ["python"],              "location": ""},
                {"designation": "data engineer",      "skills": ["python", "sql"],       "location": ""},
            ]

        total_new = 0
        for s in searches:
            try:
                print(f"[scheduler] Fetching: '{s['designation']}' skills={s['skills']} loc='{s['location']}'")
                live = fetch_jobs(
                    s["skills"],
                    designation=s["designation"],
                    location=s["location"],
                    credentials={},
                )
                if live:
                    insert_jobs(live)
                    count = len([j for j in live if not j.get("error")])
                    total_new += count
                    print(f"[scheduler]   → inserted {count} jobs")
            except Exception as e:
                print(f"[scheduler] Error fetching {s['designation']}: {e}")

        # Remove jobs not refreshed in the last 72 hours (not applied, not bookmarked)
        remove_stale_jobs(max_age_hours=72)

        print(f"[scheduler] Cycle complete. Total fetched: {total_new}")
    except Exception as e:
        print(f"[scheduler] Fatal error: {e}")


def main() -> None:
    from job_db import init_db
    init_db()

    scheduler = BackgroundScheduler()
    # Run every 6 hours; also fire immediately on startup (next_run_time=None uses default)
    scheduler.add_job(func=background_fetch_all, trigger="interval", hours=6,
                      id="job_refresh", replace_existing=True)
    scheduler.start()
    print("[scheduler] Started — refresh every 6 hours")

    from app import ui

    try:
        ui.app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    main()
