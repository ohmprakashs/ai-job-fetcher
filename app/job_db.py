import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'jobs.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
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
                       ("snippet", "TEXT"), ("applied_at", "TEXT")]:
        try:
            c.execute(f"ALTER TABLE jobs ADD COLUMN {col} {ctype}")
        except sqlite3.OperationalError:
            pass # Column might already exist

    conn.commit()
    conn.close()

def insert_or_update_job(job):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    skills_str = ','.join(job.get('skills', []))
    try:
        c.execute('''
            INSERT INTO jobs (title, company, location, skills, source, fetched_at, url,
                              experience_min, experience_max, posted_days_ago, posted_date,
                              description, snippet)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(title, company, location, source) DO UPDATE SET
                skills=excluded.skills,
                fetched_at=excluded.fetched_at,
                url=excluded.url,
                experience_min=excluded.experience_min,
                experience_max=excluded.experience_max,
                posted_days_ago=excluded.posted_days_ago,
                posted_date=excluded.posted_date,
                description=COALESCE(NULLIF(excluded.description,''), jobs.description),
                snippet=COALESCE(NULLIF(excluded.snippet,''), jobs.snippet)
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
        ))
        conn.commit()
    finally:
        conn.close()


def update_job_description(job_id: int, description: str):
    """Cache fetched JD text so we don't re-scrape every time."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("UPDATE jobs SET description=? WHERE id=?", (description, job_id))
        conn.commit()
    finally:
        conn.close()

def mark_job_applied(title, company, location, source):
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT title, company, location, source, is_applied FROM jobs")
        rows = c.fetchall()
        return {(r[0], r[1], r[2], r[3]): bool(r[4]) for r in rows}
    finally:
        conn.close()


def get_applied_count():
    """Return total number of jobs marked as applied."""
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute("SELECT COUNT(*) FROM jobs WHERE is_applied=1").fetchone()[0]
    finally:
        conn.close()


def get_applied_jobs():
    """Return all jobs marked as applied, newest first."""
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
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

def insert_jobs(jobs):
    for job in jobs:
        insert_or_update_job(job)

def get_jobs_from_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        # Order by fetched_at DESC so newest seen jobs are at the top
        c.execute("SELECT * FROM jobs ORDER BY fetched_at DESC")
        rows = c.fetchall()
        jobs = []
        for r in rows:
            job = dict(r)
            job['skills'] = job['skills'].split(',') if job['skills'] else []
            # Make sure we convert is_applied boolean
            job['is_applied'] = bool(job.get('is_applied', 0))
            jobs.append(job)
        return jobs
    finally:
        conn.close()
