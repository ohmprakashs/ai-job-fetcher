# AI Job Hunter & Auto-Apply Pipeline

An intelligent, automated pipeline that scrapes job postings from LinkedIn and Naukri, caches them, scores them against your resume/skills, and automatically applies to them using a headless browser.

## 🚀 Features Implemented So Far

### 1. Automated Job Fetching
* **Dual Platform Support**: Scrapes Naukri and LinkedIn job boards.
* **Pagination & Multi-location**: Automatically pages through results and supports comma-separated location arrays.
* **Smart Filtering**: Filters jobs based on designation, required skills, location, experience years, and posting date.

### 2. SQLite Database Logging
* **Persistent Caching**: Stores scraped jobs into a local `jobs.db` database.
* **Application Tracking**: Tracks `is_applied` boolean to ensure you never auto-apply to the same job twice.

### 3. Match Scoring (JD vs Resume)
* **AI Match %**: Compares user-defined skills and designation against the fetched Job Description.
* **Intelligent Sorting**: Automatically prioritizes the highest-matching jobs (up to 100%) to the top of the UI.

### 4. Background Job Scheduler
* **APScheduler Integration**: Runs a background daemon every 6 hours inside the Flask app to softly update the database with fresh jobs without requiring manual intervention.

### 5. Playwright Auto-Apply Bot
* **Persistent Sessions**: Reuses a local Chrome directory (`playwright_profile`) so you remain logged into LinkedIn/Naukri, bypassing captchas and OTPs.
* **1-Click Apply**: Locates and clicks "Apply" on Naukri and "Easy Apply" on LinkedIn automatically.
* **Background Execution**: The bot runs asynchronously via Python `threading` from the web UI so it doesn't freeze the server.

### 6. Interactive Web Dashboard
* **Flask UI**: A clean dashboard running at `http://127.0.0.1:5001/`.
* **Real-time Controls**: View match scores, edit skill/date filters, and fire off the Auto-Apply bot directly from the browser.

---

## 📂 Project Structure

```text
├── app/
│   ├── auto_apply_bot.py   # Headless Playwright bot for auto-applying
│   ├── job_agent.py        # Logic for Match Scoring and DB/Scraper merging
│   ├── job_db.py           # SQLite initialization and CRUD operations
│   ├── job_fetcher.py      # LinkedIn/Naukri web scrapers
│   ├── ui.py               # Flask Web Routes & Threading
│   └── templates/
│       ├── index.html      # Main dashboard table and filters
│       └── auto_apply.html # Auto-Apply trigger page
├── jobs.db                 # Auto-generated SQLite Database
├── run.py                  # Entry point with APScheduler background worker
└── requirements.txt        # Project dependencies
```

---

## 🛠 Usage

1. **Install Dependencies:**
   ```bash
   pip3 install -r requirements.txt
   pip3 install playwright playwright-stealth apscheduler
   playwright install chromium
   ```

2. **Run the Application & Scheduler:**
   ```bash
   python3 run.py
   ```

3. **Access the Dashboard:**
   Open `http://127.0.0.1:5001/` in your browser.

---

## 🔜 Next Steps / Current Sandbox focus
* **LLM-Powered Form Filling:** Upgrading the `auto_apply_bot.py` to use a Vision/Text LLM to dynamically read company-specific ATS forms (Workday, Lever, Greenhouse) and fill them out intelligently, eliminating the blind-spots of static "Apply" buttons.
