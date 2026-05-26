import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'jobs.db')

def get_conn():
    """
    Return a SQLite connection with:
    - 30s busy timeout so concurrent writers queue instead of crashing
    - WAL journal mode: multiple readers + one writer never block each other
    - check_same_thread=False: safe for Flask multi-thread mode
    """
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.OperationalError:
        pass  # DB may be mid-transition; WAL will activate on next open
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            company TEXT,
            location TEXT,
            skills TEXT,
            source TEXT,
            fetched_at TEXT,
            url TEXT,
            is_applied INTEGER DEFAULT 0,
            experience_min INTEGER,
            experience_max INTEGER,
            posted_days_ago INTEGER,
            posted_date TEXT,
            UNIQUE(title, company, location, source)
        )
    ''')
    
    # Run migrations if table already existed without new columns
    for col, ctype in [("url", "TEXT"), ("is_applied", "INTEGER DEFAULT 0"),
                       ("experience_min", "INTEGER"), ("experience_max", "INTEGER"),
                       ("posted_days_ago", "INTEGER"), ("posted_date", "TEXT"),
                       ("apply_type", "TEXT"), ("description", "TEXT"),
                       ("snippet", "TEXT"), ("applied_at", "TEXT"),
                       # Lifecycle columns
                       ("status", "TEXT DEFAULT 'active'"),
                       ("first_seen_at", "TEXT"),
                       ("last_checked_at", "TEXT"),
                       ("application_status", "TEXT DEFAULT 'not_applied'")]:
        try:
            c.execute(f"ALTER TABLE jobs ADD COLUMN {col} {ctype}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Backfill first_seen_at from fetched_at for older rows
    c.execute("""
        UPDATE jobs SET first_seen_at = fetched_at
        WHERE first_seen_at IS NULL AND fetched_at IS NOT NULL
    """)

    conn.commit()
    conn.close()

def insert_or_update_job(job):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    skills_str = ','.join(job.get('skills', []))
    try:
        c.execute('''
            INSERT INTO jobs (title, company, location, skills, source, fetched_at, url,
                              experience_min, experience_max, posted_days_ago, posted_date,
                              description, snippet, first_seen_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
            ON CONFLICT(title, company, location, source) DO UPDATE SET
                skills=excluded.skills,
                fetched_at=excluded.fetched_at,
                url=excluded.url,
                experience_min=excluded.experience_min,
                experience_max=excluded.experience_max,
                posted_days_ago=excluded.posted_days_ago,
                posted_date=excluded.posted_date,
                description=COALESCE(NULLIF(excluded.description,''), jobs.description),
                snippet=COALESCE(NULLIF(excluded.snippet,''), jobs.snippet),
                status=CASE WHEN jobs.status='expired' THEN 'active' ELSE jobs.status END
        ''', (
            job.get('title', ''),
            job.get('company', ''),
            job.get('location', ''),
            skills_str,
            job.get('source', ''),
            now,
            job.get('url', ''),
            job.get('experience_min'),
            job.get('experience_max'),
            job.get('posted_days_ago'),
            job.get('posted_date'),
            job.get('description', '') or '',
            job.get('snippet', '') or '',
            now,  # first_seen_at — ignored on conflict, keeps original value
        ))
        conn.commit()
    finally:
        conn.close()


# ── Known skills list for extraction ──────────────────────────────────────
KNOWN_SKILLS = [
    "python","java","go","golang","rust","javascript","typescript","c++","c#",
    "ruby","php","swift","kotlin","scala","r",
    "docker","kubernetes","k8s","helm","terraform","ansible","chef","puppet",
    "aws","gcp","azure","openstack","vmware",
    "ci/cd","jenkins","github actions","gitlab ci","circleci","argocd","spinnaker",
    "prometheus","grafana","datadog","new relic","elk","splunk","kibana","logstash",
    "pagerduty","servicenow","opsgenie","victorops",
    "linux","ubuntu","centos","rhel","windows","macos",
    "nginx","apache","haproxy","istio","envoy",
    "postgresql","mysql","mongodb","redis","elasticsearch","cassandra","oracle","mssql",
    "kafka","rabbitmq","celery","sqs","pubsub",
    "react","angular","vue","next.js","django","flask","fastapi",
    "spring boot","node.js","express","laravel",
    "git","github","gitlab","bitbucket","jira","confluence",
    "machine learning","deep learning","tensorflow","pytorch","scikit-learn","mlops",
    "spark","hadoop","airflow","dbt","databricks","snowflake",
    "rest api","graphql","grpc","microservices","serverless",
    "devops","sre","platform engineering","finops","devsecops",
    "bash","shell","powershell","yaml","json","xml",
    "vpc","iam","ec2","s3","lambda","eks","ecs","gke","aks",
    "sonarqube","nexus","artifactory","vault","consul",
    "selenium","pytest","junit","postman","jmeter",
]

def _extract_skills_from_text(text: str) -> list:
    """Extract known skills that appear in the given text."""
    import re
    text_lower = text.lower()
    found = []
    for skill in KNOWN_SKILLS:
        pattern = r'(?<![a-z0-9])' + re.escape(skill) + r'(?![a-z0-9])'
        if re.search(pattern, text_lower):
            found.append(skill)
    return found


def update_job_description(job_id: int, description: str):
    """Cache fetched JD text and extract skills from it."""
    extracted = _extract_skills_from_text(description)
    skills_str = ",".join(extracted) if extracted else ""
    conn = get_conn()
    c = conn.cursor()
    try:
        if skills_str:
            # Merge with any existing skills (avoid overwriting Naukri tags)
            existing = c.execute("SELECT skills FROM jobs WHERE id=?", (job_id,)).fetchone()
            existing_skills = set((existing[0] or "").split(",")) if existing else set()
            existing_skills.discard("")
            merged = ",".join(sorted(existing_skills | set(extracted)))
            c.execute("UPDATE jobs SET description=?, skills=? WHERE id=?", (description, merged, job_id))
        else:
            c.execute("UPDATE jobs SET description=? WHERE id=?", (description, job_id))
        conn.commit()
    finally:
        conn.close()


def backfill_skills_from_descriptions():
    """Backfill skills from description + snippet for ALL jobs lacking rich skills."""
    conn = get_conn()
    c = conn.cursor()
    try:
        # Target every job that has some text (desc or snippet) but fewer than 3 skills
        rows = c.execute("""
            SELECT id, description, snippet, skills FROM jobs
            WHERE (
                (description IS NOT NULL AND description != '')
                OR (snippet IS NOT NULL AND snippet != '')
            )
            AND (
                skills IS NULL OR skills = ''
                OR LENGTH(skills) - LENGTH(REPLACE(skills, ',', '')) < 2
            )
        """).fetchall()
        updated = 0
        for row in rows:
            job_id, desc, snippet, existing_skills = row
            text = (desc or "") + " " + (snippet or "")
            extracted = _extract_skills_from_text(text)
            if extracted:
                existing = set((existing_skills or "").split(","))
                existing.discard("")
                merged = ",".join(sorted(existing | set(extracted)))
                c.execute("UPDATE jobs SET skills=? WHERE id=?", (merged, job_id))
                updated += 1
        conn.commit()
        return updated
    finally:
        conn.close()


def get_jobs_needing_jd_fetch(limit=60):
    """Return jobs that have a URL but no cached description — need JD fetch."""
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT id, url, source FROM jobs
            WHERE (description IS NULL OR description = '')
            AND url IS NOT NULL AND url != '' AND url != '#'
            ORDER BY fetched_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [{"id": r[0], "url": r[1], "source": r[2]} for r in rows]
    finally:
        conn.close()


def batch_update_job_skills(updates: list):
    """Bulk write (job_id, skills_str) pairs to DB."""
    if not updates:
        return
    conn = get_conn()
    try:
        conn.executemany(
            "UPDATE jobs SET description=?, skills=? WHERE id=?",
            updates
        )
        conn.commit()
    finally:
        conn.close()

def mark_job_applied(title, company, location, source):
    conn = get_conn()
    c = conn.cursor()
    try:
        # Store IST timestamp (UTC+5:30) for daily tracking
        now_ist = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        c.execute('''
            UPDATE jobs SET is_applied = 1, applied_at = COALESCE(applied_at, ?)
            WHERE title=? AND company=? AND location=? AND source=?
        ''', (now_ist, title, company, location, source))
        conn.commit()
    finally:
        conn.close()

def get_job_applications_status():
    """Returns a dict mapping (title, company, location, source) -> is_applied"""
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("SELECT title, company, location, source, is_applied FROM jobs")
        rows = c.fetchall()
        return {(r[0], r[1], r[2], r[3]): bool(r[4]) for r in rows}
    finally:
        conn.close()


def get_applied_count():
    """Return total number of jobs marked as applied."""
    conn = get_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM jobs WHERE is_applied=1").fetchone()[0]
    finally:
        conn.close()


def get_applied_jobs():
    """Return all jobs marked as applied, newest first."""
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE is_applied=1 ORDER BY applied_at DESC, fetched_at DESC"
        ).fetchall()
        jobs = []
        for r in rows:
            job = dict(r)
            job['skills'] = job['skills'].split(',') if job['skills'] else []
            job['is_applied'] = True
            jobs.append(job)
        return jobs
    finally:
        conn.close()


def get_daily_applied_stats():
    """Return list of (date, count, sources) grouped by applied_at date, newest first."""
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT
                COALESCE(substr(applied_at,1,10), substr(fetched_at,1,10)) AS day,
                COUNT(*) AS cnt,
                GROUP_CONCAT(DISTINCT source) AS sources
            FROM jobs
            WHERE is_applied=1
            GROUP BY day
            ORDER BY day DESC
        """).fetchall()
        return [{"date": r[0], "count": r[1], "sources": r[2] or ""} for r in rows]
    finally:
        conn.close()

def get_job_by_id(job_id):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = c.fetchone()
        if not row:
            return None
        job = dict(row)
        job['skills'] = job['skills'].split(',') if job['skills'] else []
        return job
    finally:
        conn.close()

# ── Job lifecycle helpers ─────────────────────────────────────────────────────

# Phrases that indicate a job is no longer accepting applications
_EXPIRED_SIGNALS = [
    "no longer accepting applications",
    "position has been filled",
    "this job is no longer available",
    "job has expired",
    "job posting has expired",
    "application deadline has passed",
    "this listing has been removed",
    "this job has been closed",
    "applications are closed",
    "not accepting applications",
]

def mark_job_status(job_id: int, status: str):
    """Update job status: 'active' | 'expired' | 'filled' | 'closed'."""
    conn = get_conn()
    try:
        now = datetime.utcnow().isoformat()
        conn.execute(
            "UPDATE jobs SET status=?, last_checked_at=? WHERE id=?",
            (status, now, job_id)
        )
        conn.commit()
    finally:
        conn.close()


def update_application_status(job_id: int, application_status: str):
    """
    Update how the application turned out.
    Values: 'not_applied' | 'applied' | 'shortlisted' | 'rejected' | 'no_response'
    """
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE jobs SET application_status=? WHERE id=?",
            (application_status, job_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_new_jobs_count() -> int:
    """Count jobs posted today or yesterday (posted_days_ago <= 1)."""
    conn = get_conn()
    try:
        return conn.execute("""
            SELECT COUNT(*) FROM jobs
            WHERE status='active'
            AND (
                posted_days_ago <= 1
                OR (posted_date IS NOT NULL AND posted_date >= date('now', '-1 day'))
            )
        """).fetchone()[0]
    finally:
        conn.close()


def get_stale_jobs_to_check(limit: int = 20) -> list:
    """
    Return jobs that should be re-validated:
    - active, have a URL
    - not checked in last 6h (recently posted) or 24h (older jobs)
    - not applied (no point checking those)
    """
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT id, url, source, title, company FROM jobs
            WHERE status = 'active'
            AND url IS NOT NULL AND url != '' AND url != '#'
            AND is_applied = 0
            AND (
                last_checked_at IS NULL
                OR (
                    -- recently posted jobs (<=3 days): recheck every 6h
                    CAST(COALESCE(posted_days_ago, 999) AS INTEGER) <= 3
                    AND last_checked_at < datetime('now', '-6 hours')
                )
                OR (
                    -- older jobs: recheck every 24h
                    CAST(COALESCE(posted_days_ago, 999) AS INTEGER) > 3
                    AND last_checked_at < datetime('now', '-24 hours')
                )
            )
            ORDER BY
                CAST(COALESCE(posted_days_ago, 999) AS INTEGER) ASC,
                last_checked_at ASC NULLS FIRST
            LIMIT ?
        """, (limit,)).fetchall()
        return [{"id": r[0], "url": r[1], "source": r[2],
                 "title": r[3], "company": r[4]} for r in rows]
    finally:
        conn.close()


def check_and_mark_expired_jobs(limit: int = 20) -> dict:
    """
    Background checker: fetch JD text for stale jobs, detect expired signals,
    mark status accordingly. Returns summary dict.
    """
    import time
    try:
        from jd_scraper import scrape_jd_text
    except ImportError:
        return {"checked": 0, "expired": 0, "still_active": 0}

    jobs = get_stale_jobs_to_check(limit=limit)
    checked = expired = still_active = 0
    now = datetime.utcnow().isoformat()

    conn = get_conn()
    try:
        for job in jobs:
            try:
                time.sleep(1.5)
                jd_text, is_expired = scrape_jd_text(job["url"], job["source"].lower())
                jd_text = jd_text or ""
                jd_lower = jd_text.lower()

                # Determine new status
                if is_expired or not jd_text or len(jd_text) < 30:
                    new_status = "expired"
                elif any(sig in jd_lower for sig in _EXPIRED_SIGNALS):
                    new_status = "expired"
                else:
                    new_status = "active"

                conn.execute(
                    "UPDATE jobs SET status=?, last_checked_at=? WHERE id=?",
                    (new_status, now, job["id"])
                )
                checked += 1
                if new_status == "expired":
                    expired += 1
                    print(f"[lifecycle] Expired: {job['title']} @ {job['company']}")
                else:
                    still_active += 1
            except Exception:
                pass
        conn.commit()
    finally:
        conn.close()

    return {"checked": checked, "expired": expired, "still_active": still_active}


def get_lifecycle_stats() -> dict:
    """Return counts for each job status for the UI."""
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT
                COUNT(*) total,
                SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) active,
                SUM(CASE WHEN status='expired' THEN 1 ELSE 0 END) expired,
                SUM(CASE WHEN status='filled' THEN 1 ELSE 0 END) filled,
                SUM(CASE WHEN application_status='shortlisted' THEN 1 ELSE 0 END) shortlisted,
                SUM(CASE WHEN application_status='rejected' THEN 1 ELSE 0 END) rejected,
                SUM(CASE WHEN application_status='no_response' THEN 1 ELSE 0 END) no_response
            FROM jobs
        """).fetchone()
        return {
            "total": rows[0] or 0, "active": rows[1] or 0, "expired": rows[2] or 0,
            "filled": rows[3] or 0, "shortlisted": rows[4] or 0,
            "rejected": rows[5] or 0, "no_response": rows[6] or 0,
        }
    finally:
        conn.close()

def bulk_mark_expired_from_text() -> int:
    """
    Scan existing DB jobs and mark as 'expired' if their snippet or description
    contains known expired signals (e.g. 'no longer accepting applications').
    Returns count of jobs marked expired.
    """
    conn = get_conn()
    try:
        signals_sql = " OR ".join(
            [f"LOWER(snippet) LIKE '%{s}%' OR LOWER(description) LIKE '%{s}%'" for s in _EXPIRED_SIGNALS]
        )
        result = conn.execute(f"""
            UPDATE jobs SET status='expired'
            WHERE status NOT IN ('expired','filled','closed')
            AND ({signals_sql})
        """)
        conn.commit()
        return result.rowcount
    finally:
        conn.close()


def insert_jobs(jobs):
    for job in jobs:
        insert_or_update_job(job)

def get_jobs_from_db():
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        # Exclude expired/filled/closed jobs from normal listings
        c.execute(
            "SELECT * FROM jobs WHERE status NOT IN ('expired','filled','closed') ORDER BY fetched_at DESC"
        )
        rows = c.fetchall()
        jobs = []
        for r in rows:
            job = dict(r)
            job['skills'] = job['skills'].split(',') if job['skills'] else []
            job['is_applied'] = bool(job.get('is_applied', 0))
            jobs.append(job)
        return jobs
    finally:
        conn.close()
