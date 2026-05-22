import sqlite3
import os
import ast
import time
from playwright.sync_api import sync_playwright

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "jobs.db")
USER_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "playwright_profile")
CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_unapplied_jobs(platform="all", designation="", skills=None):
    if skills is None:
        skills = []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    query = "SELECT * FROM jobs WHERE is_applied = 0 AND url IS NOT NULL AND url != ''"
    if platform.lower() == "naukri":
        query += " AND source='Naukri'"
    elif platform.lower() == "linkedin":
        query += " AND source='LinkedIn'"

    c.execute(query)
    all_jobs = [dict(r) for r in c.fetchall()]
    conn.close()

    lower_skills = [s.lower() for s in skills]
    designation_lower = designation.lower()
    filtered_jobs = []

    for job in all_jobs:
        score = 0
        job_title_lower = str(job.get("title", "")).lower()

        job_skills_lower = []
        try:
            val = job.get("skills", "[]") or "[]"
            if val.startswith("["):
                job_skills_lower = [str(x).lower() for x in ast.literal_eval(val)]
            else:
                job_skills_lower = [val.lower()]
        except Exception:
            pass

        if lower_skills:
            matches = 0
            job_req = [s.strip() for s in job_skills_lower if len(s.strip()) > 1]
            if not job_req:
                for skill in lower_skills:
                    if skill in job_title_lower:
                        matches += 1
                score = min(100, int((matches / max(1, len(lower_skills))) * 100) + 50) if matches > 0 else 0
            else:
                for user_skill in lower_skills:
                    if any(user_skill in r or r in user_skill for r in job_req) or user_skill in job_title_lower:
                        matches += 1
                score = int((matches / max(1, len(lower_skills))) * 100)

        if designation_lower and designation_lower in job_title_lower:
            score += min(100 - score, 20)

        if score >= 70:
            job["match_score"] = score
            filtered_jobs.append(job)

    filtered_jobs.sort(key=lambda x: x["match_score"], reverse=True)
    return filtered_jobs[:5]  # cap at 5 to avoid long runs


def mark_applied(job_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE jobs SET is_applied = 1 WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()


# ── Playwright button clicker ─────────────────────────────────────────────────

def _try_click(page, selectors, timeout=4000):
    """Try a list of CSS/text selectors and click the first one found. Returns True on success."""
    for sel in selectors:
        try:
            btn = page.wait_for_selector(sel, timeout=timeout, state="visible")
            if btn and btn.is_visible():
                btn.scroll_into_view_if_needed()
                btn.click()
                return True
        except Exception:
            continue
    return False


def apply_to_job(page, job, emit_log):
    url = job["url"]
    source = job.get("source", "").lower()
    title = job.get("title", "N/A")
    company = job.get("company", "N/A")

    log = lambda msg: (print(msg), emit_log(msg) if emit_log else None)

    log(f"→ Navigating: {title} @ {company}")
    try:
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        time.sleep(2)
    except Exception as e:
        log(f"  ✗ Could not load page: {e}")
        return False

    # ── Naukri ────────────────────────────────────────────────────────────────
    if "naukri" in source:
        # Dismiss chat pop-ups if present
        _try_click(page, ["button[aria-label='Close']", ".chatbot_close", "[id*='close']"], timeout=2000)
        time.sleep(1)

        apply_selectors = [
            "button:has-text('Apply')",
            "button:has-text('Apply Now')",
            "[class*='apply-button']",
            "#apply-button",
            "a:has-text('Apply Now')",
        ]
        clicked = _try_click(page, apply_selectors)
        if not clicked:
            log(f"  ✗ No Apply button found on Naukri page.")
            return False

        time.sleep(3)
        content = page.content().lower()
        if "applied successfully" in content or "already applied" in content or "application submitted" in content:
            log(f"  ✓ Applied successfully!")
            return True
        else:
            log(f"  ✓ Clicked Apply (verify manually if confirmation appeared).")
            return True

    # ── LinkedIn ──────────────────────────────────────────────────────────────
    elif "linkedin" in source:
        easy_apply_selectors = [
            "button:has-text('Easy Apply')",
            ".jobs-apply-button",
            "[aria-label*='Easy Apply']",
        ]
        clicked = _try_click(page, easy_apply_selectors)
        if not clicked:
            log(f"  ✗ No Easy Apply button found (may require login or be external).")
            return False

        time.sleep(2)

        # Step through multi-page form: click Next until Submit appears
        for _ in range(6):
            if _try_click(page, ["button:has-text('Submit application')", "button:has-text('Submit')"], timeout=2000):
                time.sleep(2)
                log(f"  ✓ Application submitted!")
                return True
            if not _try_click(page, ["button:has-text('Next')", "button:has-text('Review')"], timeout=2000):
                break
            time.sleep(1)

        log(f"  ✗ Could not complete LinkedIn Easy Apply form (requires manual fields).")
        return False

    else:
        log(f"  ✗ Unknown source '{source}' — skipping.")
        return False


# ── Main entry point ──────────────────────────────────────────────────────────

def run_auto_apply(platform="all", designation="", skills=None, emit_log=None, cv_text=""):
    log = lambda msg: (print(msg), emit_log(msg) if emit_log else None)

    log("Fetching unapplied jobs from DB...")
    jobs = get_unapplied_jobs(platform, designation, skills)

    if not jobs:
        log("No eligible unapplied jobs found. Wait for the background fetch to refresh.")
        return

    log(f"Found {len(jobs)} eligible jobs. Launching browser with saved profile...")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            executable_path=CHROME_PATH,
            headless=False,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--window-size=1280,900"],
        )
        page = context.new_page()

        for job in jobs:
            success = apply_to_job(page, job, emit_log)
            if success:
                mark_applied(job["id"])
            time.sleep(3)

        context.close()

    log("Auto-Apply Bot finished.")


if __name__ == "__main__":
    run_auto_apply()
