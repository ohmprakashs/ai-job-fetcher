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
    """Fetches jobs periodically using generic inputs to keep DB fresh"""
    try:
        from job_agent import JobAIAgent
        from job_db import init_db
        print("Starting background job fetch...")
        init_db()
        # You can adjust these default background search parameters
        skills = ["python", "docker", "kubernetes", "prometheus", "grafana"]
        agent = JobAIAgent(skills=skills)
        agent.fetch_and_summarize()
        print("Background job fetch complete.")
    except Exception as e:
        print(f"Error in background fetch: {e}")

def main() -> None:
    # Initialize Background Scheduler
    scheduler = BackgroundScheduler()
    # Run fetch every 6 hours
    scheduler.add_job(func=background_fetch_all, trigger="interval", hours=6)
    scheduler.start()

    import ui  # type: ignore

    try:
        ui.app.run(host="0.0.0.0", port=5001, debug=True, use_reloader=False) # use_reloader=False prevents scheduler running twice
    finally:
        scheduler.shutdown()

if __name__ == "__main__":
    main()
