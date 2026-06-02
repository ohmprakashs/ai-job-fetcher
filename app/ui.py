from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify, session
from job_agent import JobAIAgent
from job_fetcher import find_common_jobs
from job_db import (init_db, mark_job_applied, get_job_applications_status, get_job_by_id,
                    get_applied_count, get_applied_jobs, get_daily_applied_stats,
                    backfill_skills_from_descriptions, get_jobs_needing_jd_fetch,
                    batch_update_job_skills, _extract_skills_from_text, update_job_description,
                    check_and_mark_expired_jobs, get_new_jobs_count, update_application_status,
                    mark_job_status, get_lifecycle_stats, bulk_mark_expired_from_text,
                    verify_new_jobs_for_expiry, upsert_google_user, get_user_by_id,
                    register_user, get_user_by_email, update_last_login, update_user_profile,
                    _decode_cred)
import os
import threading
import time
from datetime import datetime
from auto_apply_bot import run_auto_apply
from cv_generator import build_tailored_pdf, extract_skills_from_cv, extract_text_from_pdf, tailor_cv_smart
from ai_matcher import generate_ai_match_report, generate_ats_scorecard
from jd_scraper import scrape_jd_text
from dotenv import load_dotenv

load_dotenv()

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, template_folder=os.path.join(_BASE_DIR, "templates"))
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-in-production")

# ── Google OAuth (Flask-Dance) ───────────────────────────────────────────────
_GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID", "")
_GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
_SSO_ENABLED = bool(_GOOGLE_CLIENT_ID and _GOOGLE_CLIENT_SECRET)

if _SSO_ENABLED:
    from flask_dance.contrib.google import make_google_blueprint, google
    from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

    google_bp = make_google_blueprint(
        client_id=_GOOGLE_CLIENT_ID,
        client_secret=_GOOGLE_CLIENT_SECRET,
        scope=["openid", "https://www.googleapis.com/auth/userinfo.email",
               "https://www.googleapis.com/auth/userinfo.profile"],
        redirect_to="google_authorized",
    )
    app.register_blueprint(google_bp, url_prefix="/login")

    login_manager = LoginManager()
    login_manager.login_view = "login_page"
    login_manager.init_app(app)

    class User(UserMixin):
        def __init__(self, user_row):
            self.id = str(user_row["id"])
            self.email = user_row["email"]
            self.name = user_row.get("name") or user_row["email"].split("@")[0]
            self.picture = user_row.get("picture") or ""

    _UserObj = User  # alias used in shared routes below

    @login_manager.user_loader
    def load_user(user_id):
        row = get_user_by_id(int(user_id))
        return User(row) if row else None

    @app.route("/google-authorized")
    def google_authorized():
        if not google.authorized:
            return redirect(url_for("google.login"))
        try:
            resp = google.get("/oauth2/v2/userinfo")
            if not resp.ok:
                return redirect(url_for("login_page", error="Google login failed. Try again."))
            info = resp.json()
            user_row = upsert_google_user(
                google_id=info["id"],
                email=info.get("email", ""),
                name=info.get("name", ""),
                picture=info.get("picture", ""),
            )
            if user_row:
                login_user(User(user_row), remember=True)
        except Exception as e:
            return redirect(url_for("login_page", error=f"Login error: {e}"))
        return redirect(url_for("index"))

else:
    # SSO not configured — login_required is a no-op (dev mode), no google.login
    def login_required(f):
        from functools import wraps
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get("user_id"):
                return redirect(url_for("login_page"))
            return f(*args, **kwargs)
        return decorated
    # Stub current_user so shared routes can reference it safely
    class _FakeCU:
        is_authenticated = False
        name = ""
        email = ""
        picture = ""
    current_user = _FakeCU()
    class _UserObj:
        pass

# ── Login / Register / Logout routes (shared for SSO + email+pw) ────────────
from werkzeug.security import generate_password_hash, check_password_hash

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if _SSO_ENABLED and current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user_row = get_user_by_email(email)
        if not user_row:
            return render_template("login.html", error="No account found with this email. Please register.",
                                   prefill_email=email, sso_enabled=_SSO_ENABLED)
        if user_row.get("auth_type") == "google":
            return render_template("login.html", error="This email is linked to Google Sign-In. Use the Google button below.",
                                   prefill_email=email, sso_enabled=_SSO_ENABLED)
        if not check_password_hash(user_row.get("password_hash", ""), password):
            return render_template("login.html", error="Incorrect password. Please try again.",
                                   prefill_email=email, sso_enabled=_SSO_ENABLED)
        update_last_login(user_row["id"])
        if _SSO_ENABLED:
            from flask_login import login_user as _login_user
            _login_user(_UserObj(user_row), remember=True)
        else:
            session["user_id"] = user_row["id"]
        return redirect(url_for("index"))
    error = request.args.get("error", "")
    success = request.args.get("success", "")
    return render_template("login.html", error=error, success=success, sso_enabled=_SSO_ENABLED)


@app.route("/register", methods=["GET", "POST"])
def register_page():
    if _SSO_ENABLED and current_user.is_authenticated:
        return redirect(url_for("index"))
    prefill = {}
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        phone = request.form.get("phone", "").strip() or None
        prefill = {"name": name, "email": email, "phone": phone or ""}
        if not name or not email or not password:
            return render_template("register.html", error="Please fill in all required fields.",
                                   prefill=prefill, sso_enabled=_SSO_ENABLED)
        if len(password) < 8:
            return render_template("register.html", error="Password must be at least 8 characters.",
                                   prefill=prefill, sso_enabled=_SSO_ENABLED)
        if password != confirm:
            return render_template("register.html", error="Passwords do not match.",
                                   prefill=prefill, sso_enabled=_SSO_ENABLED)
        pw_hash = generate_password_hash(password)
        user_row, err = register_user(name, email, pw_hash, phone)
        if err:
            return render_template("register.html", error=err,
                                   prefill=prefill, sso_enabled=_SSO_ENABLED)
        if _SSO_ENABLED:
            from flask_login import login_user as _login_user
            _login_user(_UserObj(user_row), remember=True)
            return redirect(url_for("index"))
        else:
            session["user_id"] = user_row["id"]
            return redirect(url_for("index"))
    return render_template("register.html", error="", prefill=prefill, sso_enabled=_SSO_ENABLED)


@app.route("/logout")
def logout():
    if _SSO_ENABLED:
        from flask_login import logout_user as _logout_user
        _logout_user()
        if "google_oauth_token" in session:
            del session["google_oauth_token"]
    else:
        session.pop("user_id", None)
    return redirect(url_for("login_page"))


@app.route("/account-settings", methods=["GET", "POST"])
@login_required
def account_settings():
    cu = _get_current_user()
    uid = session.get("user_id") if not _SSO_ENABLED else (cu.id if hasattr(cu, "id") else None)
    user_row = get_user_by_id(int(uid)) if uid else None
    if not user_row:
        return redirect(url_for("login_page"))

    error, success = "", ""
    if request.method == "POST":
        action = request.form.get("action", "profile")
        if action == "profile":
            name         = request.form.get("name", "").strip()
            email        = request.form.get("email", "").strip().lower()
            phone        = request.form.get("phone", "").strip()
            linkedin_url = request.form.get("linkedin_url", "").strip()
            naukri_url   = request.form.get("naukri_url", "").strip()
            if not name:
                error = "Name cannot be empty."
            elif not email or "@" not in email:
                error = "Please enter a valid email address."
            else:
                user_row, err = update_user_profile(
                    uid, name=name, email=email,
                    phone=phone or None, linkedin_url=linkedin_url, naukri_url=naukri_url)
                if err:
                    error = err
                else:
                    success = "Profile updated successfully."
                    if _SSO_ENABLED:
                        from flask_login import login_user as _login_user
                        _login_user(_UserObj(user_row), remember=True)

        elif action == "social":
            li_email  = request.form.get("linkedin_email", "").strip()
            li_pass   = request.form.get("linkedin_password", "")
            nk_email  = request.form.get("naukri_email", "").strip()
            nk_pass   = request.form.get("naukri_password", "")
            user_row, err = update_user_profile(
                uid,
                linkedin_email=li_email or None,
                linkedin_password=li_pass if li_pass else None,
                naukri_email=nk_email or None,
                naukri_password=nk_pass if nk_pass else None,
            )
            error = err or ""
            if not err:
                success = "Social account credentials saved."

        elif action == "password":
            if user_row.get("auth_type") == "google":
                error = "Password cannot be changed for Google Sign-In accounts."
            else:
                current_pw  = request.form.get("current_password", "")
                new_pw      = request.form.get("new_password", "")
                confirm_pw  = request.form.get("confirm_password", "")
                if not check_password_hash(user_row.get("password_hash", ""), current_pw):
                    error = "Current password is incorrect."
                elif len(new_pw) < 8:
                    error = "New password must be at least 8 characters."
                elif new_pw != confirm_pw:
                    error = "New passwords do not match."
                else:
                    user_row, err = update_user_profile(uid, new_password_hash=generate_password_hash(new_pw))
                    error = err or ""
                    if not err:
                        success = "Password changed successfully."

    return render_template("account_settings.html", user=user_row, error=error,
                           success=success, sso_enabled=_SSO_ENABLED,
                           current_user=_get_current_user())


# Helper: get current user for non-SSO mode
def _get_current_user():
    if _SSO_ENABLED:
        return current_user
    uid = session.get("user_id")
    if uid:
        row = get_user_by_id(uid)
        if row:
            return type("U", (), {"is_authenticated": True, "name": row.get("name",""),
                                   "email": row.get("email",""), "picture": row.get("picture","")})()
    return type("U", (), {"is_authenticated": False, "name": "", "email": "", "picture": ""})()

app.secret_key = "secret_jobs_key"

def _startup_background_work():
    """On startup: backfill skills, fetch missing JDs, then run stale-job checker."""
    try:
        init_db()
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
                jd_text, _expired = scrape_jd_text(job["url"], job["source"].lower())
                if _expired:
                    from job_db import mark_job_status
                    mark_job_status(job["id"], "expired")
                    continue
                jd_text = jd_text or ""
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

        # Step 3: bulk mark existing DB jobs expired based on text signals (fast, no HTTP)
        cleaned = bulk_mark_expired_from_text()
        if cleaned:
            print(f"[lifecycle] Bulk-marked {cleaned} existing jobs as expired (text signals).")

        # Step 4: verify brand-new LinkedIn jobs (never checked) for expiry
        new_expired = verify_new_jobs_for_expiry(limit=30)
        if new_expired:
            print(f"[lifecycle] Removed {new_expired} newly-fetched jobs already closed on LinkedIn.")

        # Step 5: check for expired/filled jobs via HTTP (throttled, 20 per startup)
        # Step 3: check for expired/filled jobs (throttled, 20 per startup)
        result = check_and_mark_expired_jobs(limit=20)
        if result["checked"]:
            print(f"[lifecycle] Checked {result['checked']} jobs: "
                  f"{result['expired']} expired, {result['still_active']} still active.")
    except Exception as e:
        print(f"[startup] Background work error: {e}")

threading.Thread(target=_startup_background_work, daemon=True).start()


def _continuous_expired_checker():
    """Background thread: every 5 minutes check 50 jobs for expiry."""
    time.sleep(60)  # wait 1 min after startup before first run
    while True:
        try:
            result = check_and_mark_expired_jobs(limit=50)
            if result.get("expired"):
                print(f"[lifecycle] Continuous checker: {result['expired']} jobs marked expired.")
        except Exception as e:
            print(f"[lifecycle] Continuous checker error: {e}")
        time.sleep(300)  # run every 5 minutes

threading.Thread(target=_continuous_expired_checker, daemon=True).start()

# Default skills for the UI (empty — skills are extracted from uploaded resume)
DEFAULT_SKILLS = []

@app.route('/upload-resume', methods=['POST'])
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
    skills = DEFAULT_SKILLS
    jobs = []
    common_jobs = []
    summary = {}
    location_filter = ''
    designation_filter = ''
    experience_years = None
    posted_within_days = None
    did_submit = False
    if request.method == 'POST':
        did_submit = True

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
        # Pass stored social credentials so fetcher auto-logs in
        _cu_row = get_user_by_id(session.get("user_id") or 0) or {}
        agent.fetch_and_summarize(credentials={
            "linkedin_email":    _cu_row.get("linkedin_email") or "",
            "linkedin_password": _decode_cred(_cu_row.get("linkedin_password") or ""),
            "naukri_email":      _cu_row.get("naukri_email") or "",
            "naukri_password":   _decode_cred(_cu_row.get("naukri_password") or ""),
        })
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
    new_jobs_count = get_new_jobs_count()
    now_date = datetime.utcnow().strftime('%Y-%m-%d')
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
        current_user=_get_current_user(),
    )


@app.route('/apply-async', methods=['POST'])
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
def api_lifecycle_stats():
    """Return job lifecycle + application outcome stats as JSON."""
    init_db()
    stats = get_lifecycle_stats()
    stats['new_24h'] = get_new_jobs_count()
    stats['new_24h'] = get_new_jobs_count(hours=24)
    return jsonify(stats)


@app.route('/api/check-expired-jobs', methods=['POST'])
def api_check_expired_jobs():
    """Admin endpoint to manually trigger a stale-job validation batch."""
    limit = int(request.get_json(silent=True, force=True).get('limit', 20) if request.data else 20)
    def _run():
        result = check_and_mark_expired_jobs(limit=limit)
        print(f"[lifecycle] Manual check: {result}")
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started", "limit": limit})


@app.route('/api/validate-job/<int:job_id>', methods=['GET'])
def api_validate_job(job_id):
    """
    Instantly check whether a specific job is still accepting applications.
    Returns {"active": true/false}. Marks the job expired in DB if closed.
    """
    from jd_scraper import scrape_jd_text
    job = get_job_by_id(job_id)
    if not job or not job.get("url"):
        return jsonify({"active": False, "reason": "not_found"})
    try:
        jd_text, is_expired = scrape_jd_text(job["url"], job.get("source", ""))
        if is_expired or (not jd_text and job.get("source", "").lower() == "linkedin"):
            mark_job_status(job_id, "expired")
            return jsonify({"active": False, "reason": "no_longer_accepting"})
        return jsonify({"active": True})
    except Exception as e:
        return jsonify({"active": True, "reason": str(e)})  # fail open — don't block user


@app.route('/applied-jobs')
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
  .brand{{font-weight:800;font-size:1.1rem;color:#0a66c2;}}
  .topbar a{{color:#0a66c2;font-size:.88rem;font-weight:600;text-decoration:none;}}
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
  <div class="brand">🤖 AI Job Matcher</div>
  <a href="/">← Back to Job Search</a>
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
def remove_resume():
    resume_path = os.path.join(_BASE_DIR, "..", "sample_cv.pdf")
    if os.path.exists(resume_path):
        os.remove(resume_path)
    return redirect(url_for('index'))

@app.route('/ai-match/<int:job_id>', methods=['GET'])
def ai_match(job_id):
    job = get_job_by_id(job_id)
    if not job or not job.get("url"):
        return jsonify({"status": "error", "message": "Job or URL not found."}), 404
        
    resume_path = os.path.join(_BASE_DIR, "..", "sample_cv.pdf")
    # Use cached description first; only scrape if missing; ignore is_expired entirely
    jd_text = (job.get("description") or "").strip()
    if not jd_text:
        try:
            scraped, _ = scrape_jd_text(job.get("url", ""), job.get("source", ""))
            jd_text = (scraped or "").strip()
        except Exception:
            pass
    if not jd_text:
        jd_text = (job.get("snippet") or "").strip()
    jd_text = scrape_jd_text(job.get("url", ""), job.get("source", ""))
    report = generate_ai_match_report(resume_path, job, jd_text)
    return jsonify({"status": "success", "report": report})


@app.route('/ats-scorecard/<int:job_id>', methods=['GET'])
def ats_scorecard(job_id):
    """Return a full structured ATS scorecard as JSON."""
    job = get_job_by_id(job_id)
    if not job:
        return jsonify({"status": "error", "message": "Job not found."}), 404

    resume_path = os.path.join(_BASE_DIR, "..", "sample_cv.pdf")

    # ATS = skill matching only. NEVER block on expiry.
    # Use cached description first; scrape only if missing; ignore is_expired.
    jd_text = (job.get("description") or "").strip()
    if not jd_text:
        try:
            scraped, _ = scrape_jd_text(job.get("url", ""), job.get("source", ""))
            jd_text = (scraped or "").strip()
        except Exception:
            pass
    if not jd_text:
        jd_text = (job.get("snippet") or "").strip()

    jd_text = scrape_jd_text(job.get("url", ""), job.get("source", ""))
    scorecard = generate_ats_scorecard(resume_path, job, jd_text)
    if "error" in scorecard:
        return jsonify({"status": "error", "message": scorecard["error"]}), 400
    return jsonify({"status": "success", "scorecard": scorecard})


@app.route('/smart-tailor-cv/<int:job_id>', methods=['GET'])
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

    # Use cached description first; scrape only if missing; ignore is_expired.
    jd_text = (job.get("description") or "").strip()
    if not jd_text:
        try:
            scraped, _ = scrape_jd_text(job.get("url", ""), job.get("source", ""))
            jd_text = (scraped or "").strip()
        except Exception:
            pass
    if not jd_text:
        jd_text = (job.get("snippet") or "").strip()
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
        # IT Support / Helpdesk
        "Desktop Support Engineer", "Desktop Support Technician",
        "System Support Engineer", "IT Support Engineer", "IT Support Analyst",
        "Helpdesk Engineer", "Helpdesk Analyst", "L1 Support Engineer",
        "L2 Support Engineer", "L3 Support Engineer", "Technical Support Engineer",
        "IT Administrator", "IT Analyst", "End User Computing Engineer",
        "Field Support Engineer", "Service Desk Analyst", "NOC Engineer",
        "Network Support Engineer", "Windows Administrator", "Linux Administrator",
        "Active Directory Administrator", "Sysadmin", "Systems Engineer",
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
        # Networking / IT Infrastructure
        "Active Directory", "DNS", "DHCP", "LDAP", "Group Policy", "GPO",
        "TCP/IP", "VPN", "Firewall", "Routing", "Switching", "VLAN",
        "Office 365", "Microsoft 365", "Exchange Server", "SharePoint",
        "Azure AD", "Azure Active Directory", "Intune", "SCCM",
        "Windows 10", "Windows 11", "Windows Server 2019", "Windows Server 2022",
        "PowerShell", "Bash", "Shell Scripting", "Batch Scripting",
        "ITIL", "ITSM", "Incident Management", "Change Management",
        "Virtualization", "Hyper-V", "VMware ESXi", "vSphere",
        "Networking", "LAN", "WAN", "Wi-Fi", "VoIP",
        "Ticketing System", "Remedy", "Zendesk", "Freshdesk",
        "Backup & Recovery", "Veeam", "Symantec Backup Exec",
        "Antivirus", "Endpoint Security", "CrowdStrike", "Sophos",
        "Hardware Troubleshooting", "Desktop Support", "Remote Support",
        "Printer Support", "Asset Management",
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
        # Pull locations from active jobs ordered by frequency (most jobs = most relevant)
        db_loc_rows = conn.execute(
            """SELECT location, COUNT(*) as cnt
               FROM jobs
               WHERE status NOT IN ('expired','filled','closed')
                 AND location IS NOT NULL AND location != '' AND location != 'N/A'
               GROUP BY location
               ORDER BY cnt DESC"""
        ).fetchall()

        # Expand multi-city strings (e.g. "Pune, Bengaluru, Delhi / NCR") into individual cities
        db_loc_freq = {}   # city -> total job count
        for raw_loc, cnt in db_loc_rows:
            raw_loc = raw_loc.strip()
            # Split on comma, clean "Hybrid - " prefix, strip whitespace
            parts = [p.replace("Hybrid - ", "").replace("Hybrid-", "").strip() for p in raw_loc.split(",")]
            for part in parts:
                part = part.strip()
                if part and len(part) < 60 and len(part) > 2:
                    db_loc_freq[part] = db_loc_freq.get(part, 0) + cnt

        # Sort by frequency descending
        db_locs_sorted = [loc for loc, _ in sorted(db_loc_freq.items(), key=lambda x: -x[1])]

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
        conn.close()
    except Exception:
        db_locs_sorted, db_skills = [], set()

    # Merge: DB frequency-sorted locations FIRST, then static fallbacks
    locs_seen = set()
    merged_locs = []
    for l in db_locs_sorted:
        if l.lower() not in locs_seen:
            merged_locs.append(l)
            locs_seen.add(l.lower())
    for l in LOCATIONS:
        db_locs, db_skills = [], set()

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

    return jsonify({
        "designations": DESIGNATIONS,
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

if __name__ == '__main__':
    app.run(debug=True)
