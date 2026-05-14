from flask import Flask, render_template, request, redirect, url_for, send_file
from job_agent import JobAIAgent
from job_fetcher import find_common_jobs
from job_db import init_db, mark_job_applied, get_job_applications_status, get_job_by_id
import os
import threading
from auto_apply_bot import run_auto_apply
from cv_generator import build_tailored_pdf

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, template_folder=os.path.join(_BASE_DIR, "templates"))
app.secret_key = "secret_jobs_key"  # needed for flash messages if we use them

# Default skills for the UI
DEFAULT_SKILLS = ["python", "docker", "kubernetes", "prometheus", "grafana"]

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
        summary = agent.fetch_and_summarize()
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
    )

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
        thread = threading.Thread(target=run_auto_apply, args=(platform, designation, skills))
        thread.start()
        
        message = "✅ Auto Apply Bot successfully fired up in the background! Please keep your hands off the mouse while it runs."
        
    return render_template('auto_apply.html', message=message)

if __name__ == '__main__':
    app.run(debug=True)
