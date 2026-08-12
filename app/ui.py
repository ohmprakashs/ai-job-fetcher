from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify, session
from functools import wraps
from job_agent import JobAIAgent
from job_fetcher import find_common_jobs
from job_db import (init_db, mark_job_applied, get_job_applications_status, get_job_by_id,
                    get_applied_count, get_applied_jobs, get_daily_applied_stats,
                    backfill_skills_from_descriptions, get_jobs_needing_jd_fetch,
                    batch_update_job_skills, _extract_skills_from_text, update_job_description,
                    check_and_mark_expired_jobs, get_new_jobs_count, update_application_status,
                    mark_job_status, get_lifecycle_stats)
import os
import threading
import time
from datetime import datetime, timedelta
from auto_apply_bot import run_auto_apply
from cv_generator import build_tailored_pdf, extract_skills_from_cv, extract_text_from_pdf, tailor_cv_smart
from ai_matcher import generate_ai_match_report, generate_ats_scorecard
from jd_scraper import scrape_jd_text
import sqlite3

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, template_folder=os.path.join(_BASE_DIR, "templates"))
app.secret_key = os.environ.get("APP_SECRET_KEY", "secret_jobs_key_change_me")

# ── Credentials (override via env vars in production) ──────────────
APP_USERNAME = os.environ.get("APP_USERNAME", "admin")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "admin123")

# ── Billing / rate limits (override via env vars) ───────────────────
FREE_DAILY_SEARCH_LIMIT = int(os.environ.get("FREE_DAILY_SEARCH_LIMIT", "5"))
PAID_DAILY_SEARCH_LIMIT = int(os.environ.get("PAID_DAILY_SEARCH_LIMIT", "200"))
PAYMENT_LINK_URL = os.environ.get("PAYMENT_LINK_URL", "")
DEFAULT_SUBSCRIPTION_DAYS = int(os.environ.get("DEFAULT_SUBSCRIPTION_DAYS", "30"))
PAYMENT_SUCCESS_TOKEN = os.environ.get("PAYMENT_SUCCESS_TOKEN", "")


def _billing_db_path():
    return os.path.join(_BASE_DIR, "..", "jobs.db")


def _init_billing_tables():
    conn = sqlite3.connect(_billing_db_path())
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS user_subscriptions (
            username TEXT PRIMARY KEY,
            plan TEXT NOT NULL DEFAULT 'free',
            paid_until TEXT,
            updated_at TEXT
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS user_daily_usage (
            username TEXT NOT NULL,
            usage_date TEXT NOT NULL,
            action TEXT NOT NULL,
            usage_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT,
            PRIMARY KEY (username, usage_date, action)
        )
        """
    )
    conn.commit()
    conn.close()


def _get_user_subscription(username):
    conn = sqlite3.connect(_billing_db_path())
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT username, plan, paid_until FROM user_subscriptions WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()

    if not row:
        return {"plan": "free", "paid_until": None, "is_paid": False}

    paid_until = row["paid_until"]
    is_paid = False
    if paid_until:
        try:
            is_paid = datetime.utcnow().date() <= datetime.strptime(paid_until, "%Y-%m-%d").date()
        except Exception:
            is_paid = False
    return {"plan": row["plan"] or "free", "paid_until": paid_until, "is_paid": is_paid}


def _get_daily_usage(username, action="job_search"):
    today = datetime.utcnow().date().isoformat()
    conn = sqlite3.connect(_billing_db_path())
    c = conn.cursor()
    c.execute(
        "SELECT usage_count FROM user_daily_usage WHERE username=? AND usage_date=? AND action=?",
        (username, today, action),
    )
    row = c.fetchone()
    conn.close()
    return int(row[0]) if row else 0


def _increment_daily_usage(username, action="job_search"):
    today = datetime.utcnow().date().isoformat()
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(_billing_db_path())
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO user_daily_usage (username, usage_date, action, usage_count, updated_at)
        VALUES (?, ?, ?, 1, ?)
        ON CONFLICT(username, usage_date, action)
        DO UPDATE SET usage_count = usage_count + 1, updated_at = excluded.updated_at
        """,
        (username, today, action, now),
    )
    conn.commit()
    conn.close()


def _get_user_limit_state(username, action="job_search"):
    sub = _get_user_subscription(username)
    usage = _get_daily_usage(username, action=action)
    limit = PAID_DAILY_SEARCH_LIMIT if sub["is_paid"] else FREE_DAILY_SEARCH_LIMIT
    remaining = max(0, limit - usage)
    blocked = usage >= limit
    return {
        "is_paid": sub["is_paid"],
        "plan": "paid" if sub["is_paid"] else "free",
        "paid_until": sub.get("paid_until"),
        "daily_limit": limit,
        "daily_usage": usage,
        "remaining": remaining,
        "blocked": blocked,
    }


def login_required(f):
    """Decorator: redirect to /login if user is not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated

def _startup_background_work():
    """On startup: backfill skills, fetch missing JDs, then run stale-job checker."""
    try:
        init_db()
        _init_billing_tables()
        # Step 1: extract skills from all cached descriptions + snippets
        n = backfill_skills_from_descriptions()
        if n:
            print(f"[startup] Backfilled skills for {n} jobs.")

        # Step 2: fetch JDs for jobs that have a URL but no description yet
        jobs_to_fetch = get_jobs_needing_jd_fetch(limit=60)
        if jobs_to_fetch:
            print(f"[startup] Fetching JDs for {len(jobs_to_fetch)} jobs in background...")
        fetched = 0
        for job in jobs_to_fetch:
            try:
                time.sleep(1.2)
                jd_text = scrape_jd_text(job["url"], job["source"].lower()) or ""
                if jd_text and len(jd_text) > 100:
                    extracted = _extract_skills_from_text(jd_text)
                    skills_str = ",".join(sorted(set(extracted))) if extracted else ""
                    batch_update_job_skills([(jd_text, skills_str, job["id"])])
                    fetched += 1
            except Exception:
                pass
        if fetched:
            print(f"[startup] Fetched and indexed JDs for {fetched} jobs.")
            n2 = backfill_skills_from_descriptions()
            if n2:
                print(f"[startup] Post-fetch backfill updated {n2} more jobs.")

        # Step 3: check for expired/filled jobs (throttled, 20 per startup)
        result = check_and_mark_expired_jobs(limit=20)
        if result["checked"]:
            print(f"[lifecycle] Checked {result['checked']} jobs: "
                  f"{result['expired']} expired, {result['still_active']} still active.")
    except Exception as e:
        print(f"[startup] Background work error: {e}")

threading.Thread(target=_startup_background_work, daemon=True).start()

# Default skills for the UI (empty — skills are extracted from uploaded resume)
DEFAULT_SKILLS = []

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if username == APP_USERNAME and password == APP_PASSWORD:
            session['logged_in'] = True
            session['username'] = username
            next_url = request.form.get('next') or url_for('index')
            return redirect(next_url)
        error = 'Invalid username or password.'
    return render_template('login.html', error=error, next=request.args.get('next', ''))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/upload-resume', methods=['POST'])
@login_required
def upload_resume():
    """AJAX endpoint: saves the uploaded PDF resume and returns extracted skills as JSON."""
    resume_file = request.files.get('resume')
    if not resume_file or not resume_file.filename:
        return jsonify({"status": "error", "message": "No file provided."}), 400

    resume_path = os.path.join(_BASE_DIR, "..", "sample_cv.pdf")
    resume_file.save(resume_path)

    extracted_skills_str = extract_skills_from_cv(resume_path)
    skills = [s.strip() for s in extracted_skills_str.split(',') if s.strip()] if extracted_skills_str else []

    from cv_generator import extract_role_from_cv
    extracted_role = extract_role_from_cv(resume_path)

    return jsonify({"status": "success", "skills": skills, "skills_str": ", ".join(skills), "role": extracted_role})


@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    init_db()
    _init_billing_tables()
    skills = DEFAULT_SKILLS
    jobs = []
    common_jobs = []
    summary = {}
    location_filter = ''
    designation_filter = ''
    experience_years = None
    posted_within_days = None
    did_submit = False
    rate_limit_message = ""
    username = session.get("username", "guest")
    limit_state = _get_user_limit_state(username, action="job_search")
    if request.method == 'POST':
        did_submit = True

        # Enforce per-user daily quota before running expensive fetch calls.
        if limit_state["blocked"]:
            rate_limit_message = (
                f"Daily limit reached ({limit_state['daily_usage']}/{limit_state['daily_limit']}). "
                "Upgrade to continue searching today."
            )
        else:
            _increment_daily_usage(username, action="job_search")
            limit_state = _get_user_limit_state(username, action="job_search")

            # Skills come from the form field (already pre-filled by AJAX /upload-resume)
            skills = [s.strip().lower() for s in request.form.get('skills', '').split(',') if s.strip()]


            location_filter = request.form.get('location', '').strip().lower()
            designation_filter = request.form.get('designation', '').strip().lower()
            years_raw = (request.form.get('years') or '').strip()
            if years_raw:
                try:
                    experience_years = int(years_raw)
                except ValueError:
                    experience_years = None

            posted_raw = (request.form.get('posted_within_days') or '').strip()
            if posted_raw:
                try:
                    posted_within_days = int(posted_raw)
                except ValueError:
                    posted_within_days = None

            agent = JobAIAgent(
                skills,
                location=location_filter,
                designation=designation_filter,
                experience_years=experience_years,
                posted_within_days=posted_within_days,
            )
            agent.fetch_and_summarize()
            jobs = agent.get_jobs()

            # Removed the strict local text fallback filter.
            # Platforms like Naukri return City/State names (e.g. "Bangalore"),
            # preventing a strict "india" substring match from working correctly.
            common_jobs = find_common_jobs(jobs)
        
    # Enrich jobs with applied status from DB
    applied_status_map = get_job_applications_status()
    for job in jobs:
        key = (job.get('title', ''), job.get('company', ''), job.get('location', ''), job.get('source', ''))
        job['is_applied'] = applied_status_map.get(key, False)
        
    resume_path = os.path.join(_BASE_DIR, "..", "sample_cv.pdf")
    has_resume = os.path.exists(resume_path)
    applied_count = get_applied_count()
    new_jobs_count = get_new_jobs_count(hours=24)
    from datetime import timedelta
    now_date = (datetime.utcnow() - timedelta(hours=24)).strftime('%Y-%m-%d')

    return render_template(
        'index.html',
        skills=skills,
        jobs=jobs,
        summary=summary,
        common_jobs=common_jobs,
        location_filter=location_filter,
        designation_filter=designation_filter,
        experience_years=experience_years,
        posted_within_days=posted_within_days,
        did_submit=did_submit,
        has_resume=has_resume,
        applied_count=applied_count,
        new_jobs_count=new_jobs_count,
        now_date=now_date,
        usage_daily_limit=limit_state["daily_limit"],
        usage_daily_count=limit_state["daily_usage"],
        usage_remaining=limit_state["remaining"],
        usage_plan=limit_state["plan"],
        usage_blocked=limit_state["blocked"],
        rate_limit_message=rate_limit_message,
        payment_link_url=PAYMENT_LINK_URL,
    )


@app.route('/apply-async', methods=['POST'])
@login_required
def apply_job_async():
    data = request.get_json()
    if data:
        title = data.get('title', '')
        company = data.get('company', '')
        location = data.get('location', '')
        source = data.get('source', '')

        init_db()
        mark_job_applied(title, company, location, source)
        applied_count = get_applied_count()
        return {"status": "success", "applied_count": applied_count}
    return {"status": "error"}, 400


@app.route('/api/update-application-status', methods=['POST'])
@login_required
def api_update_application_status():
    """Update application outcome for a job (shortlisted / rejected / no_response)."""
    data = request.get_json() or {}
    job_id = data.get('job_id')
    status = data.get('status', '')
    allowed = {'not_applied', 'applied', 'shortlisted', 'rejected', 'no_response'}
    if not job_id or status not in allowed:
        return jsonify({"status": "error", "message": "Invalid job_id or status"}), 400
    init_db()
    update_application_status(int(job_id), status)
    return jsonify({"status": "success"})


@app.route('/api/mark-job-status', methods=['POST'])
@login_required
def api_mark_job_status():
    """Manually mark a job as expired / filled / active."""
    data = request.get_json() or {}
    job_id = data.get('job_id')
    status = data.get('status', '')
    allowed = {'active', 'expired', 'filled', 'closed'}
    if not job_id or status not in allowed:
        return jsonify({"status": "error", "message": "Invalid job_id or status"}), 400
    init_db()
    mark_job_status(int(job_id), status)
    return jsonify({"status": "success"})


@app.route('/api/lifecycle-stats')
@login_required
def api_lifecycle_stats():
    """Return job lifecycle + application outcome stats as JSON."""
    init_db()
    stats = get_lifecycle_stats()
    stats['new_24h'] = get_new_jobs_count(hours=24)
    return jsonify(stats)


@app.route('/api/check-expired-jobs', methods=['POST'])
@login_required
def api_check_expired_jobs():
    """Admin endpoint to manually trigger a stale-job validation batch."""
    limit = int(request.get_json(silent=True, force=True).get('limit', 20) if request.data else 20)
    def _run():
        result = check_and_mark_expired_jobs(limit=limit)
        print(f"[lifecycle] Manual check: {result}")
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started", "limit": limit})


@app.route('/applied-jobs')
@login_required
def applied_jobs():
    """Page showing all jobs marked as applied with daily breakdown."""
    init_db()
    jobs = get_applied_jobs()
    daily_stats = get_daily_applied_stats()
    count = len(jobs)

    # Group by source
    by_source = {}
    for job in jobs:
        src = job.get('source', 'Unknown')
        by_source.setdefault(src, []).append(job)

    # ── Daily log table rows ──
    daily_rows = ""
    for i, d in enumerate(daily_stats, 1):
        bar_pct = min(100, int(d["count"] / max(1, max(x["count"] for x in daily_stats)) * 100))
        src_badges = ""
        for s in (d["sources"] or "").split(","):
            s = s.strip()
            if s:
                bg = "#e0f2fe" if s == "LinkedIn" else "#fef3c7"
                cl = "#0369a1" if s == "LinkedIn" else "#92400e"
                src_badges += f'<span style="background:{bg};color:{cl};padding:1px 8px;border-radius:20px;font-size:.75rem;font-weight:600;margin-right:4px;">{s}</span>'
        daily_rows += f"""
        <tr>
            <td style="color:#6b7280;font-size:.82rem;">{i}</td>
            <td style="font-weight:700;">{d["date"]}</td>
            <td>
                <div style="display:flex;align-items:center;gap:10px;">
                    <div style="flex:1;background:#e5e7eb;border-radius:20px;height:8px;max-width:160px;">
                        <div style="background:#0a66c2;width:{bar_pct}%;height:8px;border-radius:20px;"></div>
                    </div>
                    <span style="font-weight:800;color:#0a66c2;font-size:1.05rem;">{d["count"]}</span>
                    <span style="color:#6b7280;font-size:.82rem;">job{'s' if d['count']!=1 else ''}</span>
                </div>
            </td>
            <td>{src_badges}</td>
        </tr>"""

    # ── Full jobs table rows ──
    job_rows = ""
    app_status_options = {
        'not_applied': ('—', '#6b7280', '#f3f4f6'),
        'applied':     ('📤 Applied', '#0a66c2', '#e0f2fe'),
        'shortlisted': ('🌟 Shortlisted', '#059669', '#d1fae5'),
        'rejected':    ('❌ Rejected', '#dc2626', '#fee2e2'),
        'no_response': ('😶 No Response', '#92400e', '#fef3c7'),
    }
    for i, job in enumerate(jobs, 1):
        score = job.get("match_score") or 0
        score_color = "#16a34a" if score >= 75 else "#ea580c" if score >= 50 else "#6b7280"
        url = job.get("url") or "#"
        applied_date = (job.get("applied_at") or job.get("fetched_at") or "")[:10]
        src = job.get('source', '')
        src_bg = "#e0f2fe" if src == "LinkedIn" else "#fef3c7"
        src_cl = "#0369a1" if src == "LinkedIn" else "#92400e"
        job_id = job.get("id", "")

        # Application status selector
        cur_app_status = job.get("application_status") or "applied"
        if cur_app_status not in app_status_options:
            cur_app_status = "applied"
        cur_label, cur_color, cur_bg = app_status_options[cur_app_status]
        status_opts = ""
        for val, (lbl, col, bg) in app_status_options.items():
            sel = "selected" if val == cur_app_status else ""
            status_opts += f'<option value="{val}" {sel}>{lbl}</option>'

        job_rows += f"""
        <tr id="job-row-{job_id}">
            <td style="color:#6b7280;font-size:.82rem;">{i}</td>
            <td><a href="{url}" target="_blank" style="color:#0a66c2;font-weight:600;">{job.get("title","")}</a></td>
            <td>{job.get("company","")}</td>
            <td>{job.get("location","")}</td>
            <td><span style="background:{src_bg};color:{src_cl};padding:2px 10px;border-radius:20px;font-size:.78rem;font-weight:600;">{src}</span></td>
            <td style="color:{score_color};font-weight:700;">{score}{'%' if score else '—'}</td>
            <td style="color:#6b7280;font-size:.83rem;">{applied_date}</td>
            <td>
              <select onchange="updateAppStatus({job_id}, this.value, this)"
                style="border:1px solid #e5e7eb;border-radius:8px;padding:3px 8px;font-size:.78rem;
                       background:{cur_bg};color:{cur_color};font-weight:600;cursor:pointer;">
                {status_opts}
              </select>
            </td>
        </tr>"""

    linkedin_count = len(by_source.get("LinkedIn", []))
    naukri_count   = len(by_source.get("Naukri", []))
    days_active    = len(daily_stats)

    lc = get_lifecycle_stats()
    shortlisted_count = lc.get("shortlisted", 0)
    rejected_count    = lc.get("rejected", 0)
    no_response_count = lc.get("no_response", 0)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Applied Jobs — AI Job Matcher</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f4f6f8;color:#1a1a1a;}}
    .topbar{{background:#fff;border-bottom:1px solid #e0e0e0;padding:0 28px;height:56px;display:flex;align-items:center;gap:20px;}}
    .brand{{font-weight:800;font-size:1.1rem;color:#0a66c2;text-decoration:none;}}
    .topbar .back-link{{color:#0a66c2;font-size:.88rem;font-weight:600;text-decoration:none;}}
  .page{{max-width:1140px;margin:28px auto;padding:0 20px;}}
  .page-header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;flex-wrap:wrap;gap:12px;}}
  .page-title{{font-size:1.45rem;font-weight:800;}}
  .badge{{background:#16a34a;color:#fff;border-radius:20px;padding:4px 16px;font-size:.9rem;font-weight:700;}}
  .stats-row{{display:flex;gap:14px;margin-bottom:28px;flex-wrap:wrap;}}
  .stat{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:14px 20px;min-width:120px;}}
  .stat .n{{font-size:1.6rem;font-weight:800;color:#0a66c2;}}
  .stat .l{{font-size:.72rem;color:#777;margin-top:2px;text-transform:uppercase;letter-spacing:.04em;}}
  .stat.green .n{{color:#16a34a;}}
  .stat.orange .n{{color:#ea580c;}}
  .stat.purple .n{{color:#7c3aed;}}
  .stat.red .n{{color:#dc2626;}}
  .stat.amber .n{{color:#d97706;}}
  .section-title{{font-size:1rem;font-weight:800;color:#111;margin-bottom:12px;display:flex;align-items:center;gap:8px;}}
  .card{{background:#fff;border-radius:12px;box-shadow:0 1px 6px rgba(0,0,0,.07);margin-bottom:28px;overflow:hidden;}}
  table{{width:100%;border-collapse:collapse;}}
  thead tr{{background:#f8fafc;}}
  th{{padding:10px 14px;font-size:.75rem;font-weight:700;color:#555;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid #e5e7eb;text-align:left;}}
  td{{padding:11px 14px;font-size:.87rem;border-bottom:1px solid #f0f0f0;vertical-align:middle;}}
  tr:last-child td{{border-bottom:none;}}
  tr:hover td{{background:#f8fafc;}}
  .empty{{text-align:center;padding:50px 20px;color:#888;}}
  .empty .icon{{font-size:2.5rem;margin-bottom:10px;}}
  .toast{{position:fixed;bottom:24px;right:24px;background:#111;color:#fff;padding:10px 20px;border-radius:10px;
          font-size:.85rem;font-weight:600;display:none;z-index:9999;box-shadow:0 4px 16px rgba(0,0,0,.18);}}
</style>
</head>
<body>
<div class="topbar">
    <a class="brand" href="/" title="Go to Home">🤖 AI Job Matcher</a>
    <a class="back-link" href="/">← Back to Job Search</a>
</div>
<div class="page">
  <div class="page-header">
    <div class="page-title">✅ Applied Jobs Log</div>
    <span class="badge">{count} Total Applied</span>
  </div>

  <!-- Summary stats -->
  <div class="stats-row">
    <div class="stat"><div class="n">{count}</div><div class="l">Total Applied</div></div>
    <div class="stat green"><div class="n">{linkedin_count}</div><div class="l">LinkedIn</div></div>
    <div class="stat orange"><div class="n">{naukri_count}</div><div class="l">Naukri</div></div>
    <div class="stat purple"><div class="n">{days_active}</div><div class="l">Active Days</div></div>
    <div class="stat green"><div class="n">{shortlisted_count}</div><div class="l">🌟 Shortlisted</div></div>
    <div class="stat red"><div class="n">{rejected_count}</div><div class="l">❌ Rejected</div></div>
    <div class="stat amber"><div class="n">{no_response_count}</div><div class="l">😶 No Response</div></div>
  </div>

  <!-- Daily breakdown -->
  <div class="section-title">📅 Daily Application Log</div>
  <div class="card">
    {"<table><thead><tr><th>#</th><th>Date</th><th>Applications</th><th>Platform</th></tr></thead><tbody>" + daily_rows + "</tbody></table>"
     if daily_stats else
     "<div class='empty'><div class='icon'>📅</div><p>No daily data yet.</p></div>"}
  </div>

  <!-- Full job list -->
  <div class="section-title">📋 All Applied Jobs</div>
  <div class="card">
    {"<table><thead><tr><th>#</th><th>Job Title</th><th>Company</th><th>Location</th><th>Platform</th><th>ATS Score</th><th>Applied On</th><th>Outcome</th></tr></thead><tbody>" + job_rows + "</tbody></table>"
     if jobs else
     "<div class='empty'><div class='icon'>📋</div><p>No jobs marked as applied yet.</p><p style='margin-top:8px'><a href='/' style='color:#0a66c2'>Search jobs</a> and click <strong>Mark Applied</strong> on any job.</p></div>"}
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const appStatusColors = {{
  not_applied:  {{ bg:'#f3f4f6', color:'#6b7280' }},
  applied:      {{ bg:'#e0f2fe', color:'#0a66c2' }},
  shortlisted:  {{ bg:'#d1fae5', color:'#059669' }},
  rejected:     {{ bg:'#fee2e2', color:'#dc2626' }},
  no_response:  {{ bg:'#fef3c7', color:'#92400e' }},
}};

function updateAppStatus(jobId, status, selectEl) {{
  fetch('/api/update-application-status', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ job_id: jobId, status: status }})
  }}).then(r => r.json()).then(d => {{
    if (d.status === 'success') {{
      const c = appStatusColors[status] || appStatusColors.applied;
      selectEl.style.background = c.bg;
      selectEl.style.color = c.color;
      showToast('✅ Outcome updated');
    }} else {{
      showToast('❌ Failed to update');
    }}
  }}).catch(() => showToast('❌ Network error'));
}}

function showToast(msg) {{
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.display = 'block';
  setTimeout(() => t.style.display = 'none', 2500);
}}
</script>
</body>
</html>"""
    return html

@app.route('/apply', methods=['POST'])
@login_required
def apply_job():
    """Endpoint that records a job application and redirects to the external URL."""
    title = request.form.get('title', '')
    company = request.form.get('company', '')
    location = request.form.get('location', '')
    source = request.form.get('source', '')
    job_url = request.form.get('url', '')
    
    # Mark in DB
    init_db()
    mark_job_applied(title, company, location, source)
    
    # Send user to the actual application page
    if job_url and job_url != '#':
        return redirect(job_url)
    
    return redirect(url_for('index'))

@app.route('/remove-resume', methods=['POST'])
@login_required
def remove_resume():
    resume_path = os.path.join(_BASE_DIR, "..", "sample_cv.pdf")
    if os.path.exists(resume_path):
        os.remove(resume_path)
    return redirect(url_for('index'))

@app.route('/ai-match/<int:job_id>', methods=['GET'])
@login_required
def ai_match(job_id):
    job = get_job_by_id(job_id)
    if not job or not job.get("url"):
        return jsonify({"status": "error", "message": "Job or URL not found."}), 404
        
    resume_path = os.path.join(_BASE_DIR, "..", "sample_cv.pdf")
    jd_text = scrape_jd_text(job.get("url", ""), job.get("source", ""))
    report = generate_ai_match_report(resume_path, job, jd_text)
    return jsonify({"status": "success", "report": report})


@app.route('/ats-scorecard/<int:job_id>', methods=['GET'])
@login_required
def ats_scorecard(job_id):
    """Return a full structured ATS scorecard as JSON."""
    job = get_job_by_id(job_id)
    if not job:
        return jsonify({"status": "error", "message": "Job not found."}), 404

    resume_path = os.path.join(_BASE_DIR, "..", "sample_cv.pdf")
    jd_text = scrape_jd_text(job.get("url", ""), job.get("source", ""))
    scorecard = generate_ats_scorecard(resume_path, job, jd_text)
    if "error" in scorecard:
        return jsonify({"status": "error", "message": scorecard["error"]}), 400
    return jsonify({"status": "success", "scorecard": scorecard})


@app.route('/smart-tailor-cv/<int:job_id>', methods=['GET'])
@login_required
def smart_tailor_cv(job_id):
    """
    Take the uploaded resume, inject the missing JD skills (+10-20% ATS boost),
    and return a preview page with a download button + change log.
    """
    job = get_job_by_id(job_id)
    if not job:
        return "Job not found.", 404

    base_pdf_path = os.path.join(_BASE_DIR, "..", "sample_cv.pdf")
    if not os.path.exists(base_pdf_path):
        return "No resume uploaded. Please upload your CV first.", 400

    output_pdf_path = os.path.join(_BASE_DIR, "..", f"smart_cv_{job_id}.pdf")
    jd_text = scrape_jd_text(job.get("url", ""), job.get("source", ""))

    try:
        result = tailor_cv_smart(base_pdf_path, job, output_pdf_path, jd_text)
    except Exception as e:
        return f"Failed to generate smart CV: {str(e)}", 500

    # If browser requests a download directly, serve the file
    if request.args.get("download") == "1":
        delta = result.get("score_delta", 0)
        return send_file(
            output_pdf_path,
            as_attachment=True,
            download_name=f"SmartCV_{job.get('company','tailored')}_+{delta}pct.pdf",
        )

    # Otherwise show a summary page
    baseline = result.get("baseline_score", 0)
    new_score = result.get("new_score", 0)
    delta     = result.get("score_delta", 0)
    changes   = result.get("changes", [])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Smart CV — {job.get('title','')} @ {job.get('company','')}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  body{{font-family:'Inter',sans-serif;background:#f3f2ee;color:#1a1a1a;margin:0;padding:32px 24px;}}
  .card{{background:#fff;border:1px solid #e0e0e0;border-radius:10px;max-width:620px;margin:0 auto;padding:32px 36px;}}
  h1{{font-size:1.25rem;font-weight:700;margin-bottom:4px;}}
  .sub{{color:#666;font-size:.9rem;margin-bottom:24px;}}
  .score-row{{display:flex;gap:24px;margin-bottom:24px;}}
  .score-box{{flex:1;border:1px solid #e0e0e0;border-radius:8px;padding:14px;text-align:center;}}
  .score-box .val{{font-size:1.8rem;font-weight:800;}}
  .score-box .lbl{{font-size:.72rem;color:#777;text-transform:uppercase;letter-spacing:.05em;margin-top:2px;}}
  .before .val{{color:#dc2626;}} .after .val{{color:#16a34a;}} .delta .val{{color:#0a66c2;}}
  .changes{{background:#f8faff;border:1px solid #c9dff5;border-radius:8px;padding:16px 18px;margin-bottom:24px;}}
  .changes h3{{font-size:.85rem;font-weight:700;color:#444;text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px;}}
  .change-item{{font-size:.88rem;color:#374151;padding:5px 0;border-bottom:1px solid #e5e7eb;display:flex;gap:8px;align-items:flex-start;}}
  .change-item:last-child{{border-bottom:none;}}
  .change-item::before{{content:'✅';flex-shrink:0;}}
  .note{{font-size:.8rem;color:#777;margin-bottom:20px;line-height:1.6;}}
  .dl-btn{{display:inline-flex;align-items:center;gap:8px;padding:12px 28px;background:#0a66c2;color:#fff;border:none;border-radius:20px;font-family:inherit;font-size:.95rem;font-weight:700;text-decoration:none;cursor:pointer;transition:background .2s;}}
  .dl-btn:hover{{background:#085396;}}
  .back{{display:inline-block;margin-top:14px;font-size:.85rem;color:#0a66c2;cursor:pointer;}}
</style>
</head>
<body>
<div class="card">
  <h1>🎯 Smart CV Ready</h1>
  <div class="sub">Tailored for: <strong>{job.get('title','')}</strong> at <strong>{job.get('company','')}</strong></div>

  <div class="score-row">
    <div class="score-box before"><div class="val">{baseline}%</div><div class="lbl">Before (ATS)</div></div>
    <div class="score-box after"> <div class="val">{new_score}%</div><div class="lbl">After (ATS)</div></div>
    <div class="score-box delta"> <div class="val">+{delta}%</div><div class="lbl">Improvement</div></div>
  </div>

  <div class="changes">
    <h3>What was added to your CV</h3>
    {''.join(f'<div class="change-item">{c}</div>' for c in changes) if changes else '<div class="change-item">No changes needed — CV already matches well.</div>'}
  </div>

  <p class="note">
    Only the <strong>missing keywords required by this JD</strong> were added to your Skills section
    and Professional Summary. No experience or qualifications were fabricated.
  </p>

  <a href="/smart-tailor-cv/{job_id}?download=1" class="dl-btn">⬇ Download Smart CV (PDF)</a>
  <br>
  <a class="back" onclick="history.back()">← Back to jobs</a>
</div>
</body>
</html>"""
    return html

@app.route('/generate-cv/<int:job_id>', methods=['GET'])
@login_required
def generate_cv(job_id):
    job = get_job_by_id(job_id)
    if not job:
        return "Job not found.", 404
        
    base_pdf_path = os.path.join(_BASE_DIR, "..", "sample_cv.pdf")
    output_pdf_path = os.path.join(_BASE_DIR, "..", f"tailored_cv_{job_id}.pdf")
    
    try:
        build_tailored_pdf(job, base_pdf_path, output_pdf_path)
        return send_file(output_pdf_path, as_attachment=True, download_name=f"Tailored_CV_{job['company']}.pdf")
    except Exception as e:
        return f"Failed to generate CV: {str(e)}", 500


@app.route('/api/autocomplete', methods=['GET'])
@login_required
def autocomplete():
    """Return autocomplete suggestions for designation, skills, and location."""
    import sqlite3
    from job_db import DB_PATH

    # ── Static curated lists ─────────────────────────────────────────────────
    DESIGNATIONS = sorted([
        "DevOps Engineer", "Senior DevOps Engineer", "Lead DevOps Engineer",
        "Site Reliability Engineer", "SRE", "Cloud Engineer", "Cloud Architect",
        "Platform Engineer", "Infrastructure Engineer", "Software Engineer",
        "Senior Software Engineer", "Full Stack Developer", "Backend Developer",
        "Frontend Developer", "Data Engineer", "Data Scientist", "ML Engineer",
        "MLOps Engineer", "Python Developer", "Java Developer", "Node.js Developer",
        "React Developer", "Angular Developer", "iOS Developer", "Android Developer",
        "Mobile Developer", "Kubernetes Engineer", "Solutions Architect",
        "Security Engineer", "Network Engineer", "Systems Administrator",
        "Database Administrator", "QA Engineer", "Test Automation Engineer",
        "Scrum Master", "Product Manager", "Technical Program Manager",
        "Engineering Manager", "CTO", "VP Engineering",
        # Linux / Sysadmin roles
        "Linux Administrator", "Linux Admin", "Senior Linux Administrator",
        "Linux System Administrator", "Linux Systems Admin",
        "RHEL Administrator", "RedHat Linux Administrator",
        "Unix Administrator", "Unix Linux Administrator",
        "AWS Linux Administrator", "Azure Linux Admin",
        "Linux Support Engineer", "Linux Server Administrator",
        "System Administrator", "Senior System Administrator",
        "IT Administrator", "Infrastructure Administrator",
    ])

    SKILLS = sorted([
        "Python", "Java", "Go", "Rust", "JavaScript", "TypeScript", "C++", "C#",
        "Ruby", "PHP", "Swift", "Kotlin", "Scala", "R",
        "Docker", "Kubernetes", "Helm", "Terraform", "Ansible", "Chef", "Puppet",
        "AWS", "GCP", "Azure", "OpenStack", "VMware",
        "CI/CD", "Jenkins", "GitHub Actions", "GitLab CI", "CircleCI", "ArgoCD",
        "Prometheus", "Grafana", "Datadog", "New Relic", "ELK Stack", "Splunk",
        "PagerDuty", "ServiceNow", "OpsGenie",
        "Linux", "Ubuntu", "CentOS", "Windows Server", "macOS",
        "Nginx", "Apache", "HAProxy", "Istio", "Envoy",
        "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "Cassandra",
        "Kafka", "RabbitMQ", "Celery",
        "React", "Angular", "Vue.js", "Next.js", "Django", "Flask", "FastAPI",
        "Spring Boot", "Node.js", "Express",
        "Git", "GitHub", "GitLab", "Bitbucket", "Jira", "Confluence",
        "Machine Learning", "Deep Learning", "TensorFlow", "PyTorch", "Scikit-learn",
        "Spark", "Hadoop", "Airflow", "dbt",
        "REST API", "GraphQL", "gRPC", "Microservices", "Serverless",
        "DevOps", "SRE", "Platform Engineering", "FinOps",
    ])

    LOCATIONS = sorted([
        "Bangalore", "Bengaluru", "Mumbai", "Pune", "Hyderabad", "Chennai",
        "Delhi", "Noida", "Gurgaon", "Kolkata", "Ahmedabad", "Jaipur",
        "Chandigarh", "Kochi", "Coimbatore", "Indore", "Bhubaneswar",
        "Remote", "Hybrid", "Pan India",
        # Global
        "New York", "San Francisco", "Seattle", "Austin", "London",
        "Singapore", "Dubai", "Toronto", "Berlin",
    ])

    # ── Augment with DB data ─────────────────────────────────────────────────
    try:
        conn = sqlite3.connect(DB_PATH)
        # Pull unique locations from DB jobs
        db_locs = [r[0].strip() for r in conn.execute(
            "SELECT DISTINCT location FROM jobs WHERE location IS NOT NULL AND location != '' AND location != 'N/A' ORDER BY location"
        ).fetchall() if r[0] and len(r[0]) < 60]
        # Pull unique skills from DB job tags (comma-separated)
        db_skills_raw = conn.execute(
            "SELECT skills FROM jobs WHERE skills IS NOT NULL AND skills != ''"
        ).fetchall()
        db_skills = set()
        for (s,) in db_skills_raw:
            for sk in s.split(","):
                sk = sk.strip()
                if 1 < len(sk) < 40:
                    db_skills.add(sk.title())
        # Pull unique job titles from DB to auto-extend designation suggestions
        db_titles = [r[0].strip().title() for r in conn.execute(
            "SELECT DISTINCT title FROM jobs WHERE title IS NOT NULL AND title != '' AND title != 'N/A' ORDER BY title"
        ).fetchall() if r[0] and 3 < len(r[0]) < 80 and '\n' not in r[0] and not any(ch.isdigit() for ch in r[0])]
        conn.close()
    except Exception:
        db_locs, db_skills, db_titles = [], set(), []

    # Merge and deduplicate (case-insensitive)
    locs_seen = {l.lower() for l in LOCATIONS}
    merged_locs = list(LOCATIONS)
    for l in db_locs:
        if l.lower() not in locs_seen:
            merged_locs.append(l)
            locs_seen.add(l.lower())

    skills_seen = {s.lower() for s in SKILLS}
    merged_skills = list(SKILLS)
    for sk in sorted(db_skills):
        if sk.lower() not in skills_seen:
            merged_skills.append(sk)
            skills_seen.add(sk.lower())

    desig_seen = {d.lower() for d in DESIGNATIONS}
    merged_designations = list(DESIGNATIONS)
    for t in db_titles:
        if t.lower() not in desig_seen:
            merged_designations.append(t)
            desig_seen.add(t.lower())

    return jsonify({
        "designations": sorted(merged_designations),
        "skills": merged_skills,
        "locations": merged_locs,
    })


@app.route('/auto-apply', methods=['GET', 'POST'])
def auto_apply_ui():
    message = ""
    if request.method == 'POST':
        platform = request.form.get('platform', 'all')
        designation = request.form.get('designation', '')
        skills_raw = request.form.get('skills', '')
        skills = [s.strip() for s in skills_raw.split(',') if s.strip()]
        
        # Start the lengthy browser automation in a background thread
        # This allows the Flask UI to return the success message immediately!
        resume_path = os.path.join(_BASE_DIR, "..", "sample_cv.pdf")
        cv_text = ""
        if os.path.exists(resume_path):
            cv_text = extract_text_from_pdf(resume_path)
            
        def print_log(msg):
            print(f"[BOT] {msg}")
            
        thread = threading.Thread(target=run_auto_apply, args=(platform, designation, skills, print_log, cv_text))
        thread.start()
        
        message = "✅ Auto Apply Bot successfully fired up in the background! Please keep your hands off the mouse while it runs."
        
    return render_template('auto_apply.html', message=message)


@app.route('/account-settings', methods=['GET', 'POST'])
@login_required
def account_settings():
    """Account settings page — API keys, credentials, automation preferences, notifications."""
    if request.method == 'POST':
        # Handle different settings updates based on the form action
        action = request.form.get('action', '')
        
        if action == 'save_api_key':
            # Save API key (in production, use secure backend storage, not localStorage)
            return jsonify({"status": "success", "message": "API key saved"})
        
        elif action == 'save_preferences':
            experience = request.form.get('experience', '')
            location = request.form.get('location', '')
            exclude_keywords = request.form.get('exclude_keywords', '')
            min_salary = request.form.get('min_salary', '')
            max_salary = request.form.get('max_salary', '')
            # Store in session or database
            return jsonify({"status": "success", "message": "Preferences saved"})
        
        elif action == 'save_automation':
            max_applications = request.form.get('max_applications', '15')
            delay_between = request.form.get('delay_between', '8')
            application_strategy = request.form.get('application_strategy', 'best-match')
            use_tailored_cv = request.form.get('use_tailored_cv', 'off') == 'on'
            return jsonify({"status": "success", "message": "Automation settings saved"})
        
        elif action == 'save_notifications':
            email = request.form.get('email', '')
            notify_new_jobs = request.form.get('notify_new_jobs', 'off') == 'on'
            notify_applied = request.form.get('notify_applied', 'off') == 'on'
            digest_frequency = request.form.get('digest_frequency', 'daily')
            return jsonify({"status": "success", "message": "Notification settings saved"})
        
        elif action == 'clear_cache':
            # Clear browser cache
            import shutil
            profile_path = os.path.join(_BASE_DIR, "..", "playwright_profile")
            try:
                shutil.rmtree(os.path.join(profile_path, "Default", "Cache"), ignore_errors=True)
                return jsonify({"status": "success", "message": "Cache cleared successfully"})
            except Exception as e:
                return jsonify({"status": "error", "message": f"Failed to clear cache: {e}"}), 400
    
    # GET: Render the settings page
    return render_template('account_settings.html')


@app.route('/billing', methods=['GET'])
@login_required
def billing_page():
    """Simple billing/usage page for current user."""
    _init_billing_tables()
    username = session.get("username", "guest")
    state = _get_user_limit_state(username, action="job_search")
    return render_template(
        'billing.html',
        username=username,
        usage_plan=state["plan"],
        usage_daily_limit=state["daily_limit"],
        usage_daily_count=state["daily_usage"],
        usage_remaining=state["remaining"],
        usage_blocked=state["blocked"],
        paid_until=state["paid_until"],
        payment_link_url=PAYMENT_LINK_URL,
        payment_success_token=PAYMENT_SUCCESS_TOKEN,
    )


@app.route('/api/usage-status', methods=['GET'])
@login_required
def api_usage_status():
    """Return current user's daily usage stats (for UI polling if needed)."""
    _init_billing_tables()
    username = session.get("username", "guest")
    state = _get_user_limit_state(username, action="job_search")
    return jsonify(state)


@app.route('/payment/success', methods=['GET'])
def payment_success():
    """
    Minimal callback endpoint to activate paid plan after successful payment.
    For production, verify provider webhook signature before activating.
    """
    if PAYMENT_SUCCESS_TOKEN:
        token = request.args.get('token', '').strip()
        if token != PAYMENT_SUCCESS_TOKEN:
            return jsonify({"status": "error", "message": "Invalid payment callback token"}), 403

    username = request.args.get('user', '').strip() or session.get('username', '').strip()
    if not username:
        return redirect(url_for('login'))

    _init_billing_tables()
    paid_until = (datetime.utcnow().date() + timedelta(days=DEFAULT_SUBSCRIPTION_DAYS)).isoformat()
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(_billing_db_path())
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO user_subscriptions (username, plan, paid_until, updated_at)
        VALUES (?, 'paid', ?, ?)
        ON CONFLICT(username)
        DO UPDATE SET plan='paid', paid_until=excluded.paid_until, updated_at=excluded.updated_at
        """,
        (username, paid_until, now),
    )
    conn.commit()
    conn.close()
    return redirect(url_for('billing_page'))


# ── Naukri account status & setup ─────────────────────────────────────────────

def _check_naukri_cookie_login():
    """
    Read the Chromium persistent-profile Cookies SQLite DB and look for a
    Naukri session cookie.  Returns True if a valid session is found.
    """
    import sqlite3 as _sql
    cookie_db = os.path.join(_BASE_DIR, "..", "playwright_profile", "Default", "Cookies")
    if not os.path.exists(cookie_db):
        return False
    try:
        # Chromium locks the DB while browser is open; copy first to avoid SQLITE_BUSY
        import shutil, tempfile
        tmp = tempfile.mktemp(suffix=".db")
        shutil.copy2(cookie_db, tmp)
        conn = _sql.connect(tmp)
        cur = conn.cursor()
        # Naukri sets a cookie called 'nauk_ses' or 'PHPSESSID' on naukri.com
        cur.execute(
            "SELECT name FROM cookies "
            "WHERE host_key LIKE '%naukri.com%' "
            "  AND name NOT IN ('_ga','_gid','_gat','OptanonConsent') "
            "LIMIT 1"
        )
        row = cur.fetchone()
        conn.close()
        os.unlink(tmp)
        return row is not None
    except Exception as e:
        print(f"[naukri-status] Cookie check error: {e}")
        return False


@app.route('/api/naukri-status', methods=['GET'])
@login_required
def api_naukri_status():
    """Return whether the Naukri session cookie exists in the playwright profile."""
    connected = _check_naukri_cookie_login()
    return jsonify({"connected": connected})


@app.route('/api/naukri-open-login', methods=['POST'])
@login_required
def api_naukri_open_login():
    """
    Reuse the already open Google Chrome tab (active tab in front window) and
    navigate it to Naukri login. This avoids opening any new window/tab.
    """
    try:
        import subprocess
        script = (
            'tell application "Google Chrome"\n'
            '  if (count of windows) = 0 then\n'
            '    make new window\n'
            '  end if\n'
            '  set URL of active tab of front window to "https://www.naukri.com/nlogin/login"\n'
            '  activate\n'
            'end tell'
        )
        subprocess.run(["osascript", "-e", script], check=True)
        return jsonify(
            {
                "status": "launched",
                "message": "Naukri login opened in the active Chrome tab.",
            }
        )
    except Exception as e:
        print(f"[naukri-setup] Browser error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)

