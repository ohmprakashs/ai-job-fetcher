from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify
from job_agent import JobAIAgent
from job_fetcher import find_common_jobs
from job_db import init_db, mark_job_applied, get_job_applications_status, get_job_by_id, get_applied_count, get_applied_jobs, get_daily_applied_stats, backfill_skills_from_descriptions
import os
import threading
from auto_apply_bot import run_auto_apply
from cv_generator import build_tailored_pdf, extract_skills_from_cv, extract_text_from_pdf, tailor_cv_smart
from ai_matcher import generate_ai_match_report, generate_ats_scorecard
from jd_scraper import scrape_jd_text

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, template_folder=os.path.join(_BASE_DIR, "templates"))
app.secret_key = "secret_jobs_key"

# Run skill backfill once on startup (background thread, non-blocking)
def _startup_backfill():
    try:
        init_db()
        n = backfill_skills_from_descriptions()
        if n:
            print(f"[startup] Backfilled skills for {n} jobs from cached descriptions.")
    except Exception as e:
        print(f"[startup] Backfill error: {e}")

threading.Thread(target=_startup_backfill, daemon=True).start()

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
def index():
    init_db()
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
    for i, job in enumerate(jobs, 1):
        score = job.get("match_score") or 0
        score_color = "#16a34a" if score >= 75 else "#ea580c" if score >= 50 else "#6b7280"
        url = job.get("url") or "#"
        applied_date = (job.get("applied_at") or job.get("fetched_at") or "")[:10]
        src = job.get('source', '')
        src_bg = "#e0f2fe" if src == "LinkedIn" else "#fef3c7"
        src_cl = "#0369a1" if src == "LinkedIn" else "#92400e"
        job_rows += f"""
        <tr>
            <td style="color:#6b7280;font-size:.82rem;">{i}</td>
            <td><a href="{url}" target="_blank" style="color:#0a66c2;font-weight:600;">{job.get("title","")}</a></td>
            <td>{job.get("company","")}</td>
            <td>{job.get("location","")}</td>
            <td><span style="background:{src_bg};color:{src_cl};padding:2px 10px;border-radius:20px;font-size:.78rem;font-weight:600;">{src}</span></td>
            <td style="color:{score_color};font-weight:700;">{score}{'%' if score else '—'}</td>
            <td style="color:#6b7280;font-size:.83rem;">{applied_date}</td>
        </tr>"""

    linkedin_count = len(by_source.get("LinkedIn", []))
    naukri_count   = len(by_source.get("Naukri", []))
    days_active    = len(daily_stats)

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
    {"<table><thead><tr><th>#</th><th>Job Title</th><th>Company</th><th>Location</th><th>Platform</th><th>ATS Score</th><th>Applied On</th></tr></thead><tbody>" + job_rows + "</tbody></table>"
     if jobs else
     "<div class='empty'><div class='icon'>📋</div><p>No jobs marked as applied yet.</p><p style='margin-top:8px'><a href='/' style='color:#0a66c2'>Search jobs</a> and click <strong>Mark Applied</strong> on any job.</p></div>"}
  </div>
</div>
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
        conn.close()
    except Exception:
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
