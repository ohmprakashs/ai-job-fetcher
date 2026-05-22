from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify
from job_agent import JobAIAgent
from job_fetcher import find_common_jobs
from job_db import init_db, mark_job_applied, get_job_applications_status, get_job_by_id
import os
import threading
from auto_apply_bot import run_auto_apply
from cv_generator import build_tailored_pdf, extract_skills_from_cv, extract_text_from_pdf, tailor_cv_smart
from ai_matcher import generate_ai_match_report, generate_ats_scorecard
from jd_scraper import scrape_jd_text

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, template_folder=os.path.join(_BASE_DIR, "templates"))
app.secret_key = "secret_jobs_key"  # needed for flash messages if we use them

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
        return {"status": "success"}
    return {"status": "error"}, 400

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
