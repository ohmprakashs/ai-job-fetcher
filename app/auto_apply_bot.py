import sqlite3
import os
import time
import asyncio
from langchain_anthropic import ChatAnthropic
from browser_use import Agent, Browser, BrowserProfile

class CustomChatAnthropic(ChatAnthropic):
    model_config = {"extra": "allow"}

    @property
    def provider(self):
        return "anthropic"
        
    @property
    def model_name(self):
        return self.model

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "jobs.db")
USER_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "playwright_profile")

def get_unapplied_jobs(platform='all', designation='', skills=None):
    if skills is None:
        skills = []
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    query = "SELECT * FROM jobs WHERE is_applied = 0 AND url IS NOT NULL AND url != ''"
    if platform.lower() == 'naukri':
        query += " AND source='Naukri'"
    elif platform.lower() == 'linkedin':
        query += " AND source='LinkedIn'"
        
    c.execute(query)
    all_jobs = [dict(r) for r in c.fetchall()]
    conn.close()
    
    # Filter by > 70% match score if skills are provided
    filtered_jobs = []
    lower_skills = [s.lower() for s in skills]
    designation_lower = designation.lower()
    
    for job in all_jobs:
        score = 0
        job_title_lower = str(job.get("title", "")).lower()
        
        # Parse skills column
        import ast
        job_skills_lower = []
        try:
            val = job.get("skills", "[]")
            if val.startswith('['):
                parsed = ast.literal_eval(val)
                job_skills_lower = [str(x).lower() for x in parsed]
            else:
                job_skills_lower = [val.lower()]
        except:
            pass
        if lower_skills:
            matches = 0
            # Clean spaces from job tags
            job_required_skills = [s.strip() for s in job_skills_lower if len(s.strip()) > 1]
            
            if not job_required_skills:
                # Fallback to title matching
                for skill in lower_skills:
                    if skill in job_title_lower:
                        matches += 1
                score = min(100, int((matches / max(1, len(lower_skills))) * 100) + 50) if matches > 0 else 0
            else:
                for user_skill in lower_skills:
                    has_it = False
                    for req_skill in job_required_skills:
                        if user_skill in req_skill or req_skill in user_skill:
                            has_it = True
                            break
                    if not has_it and user_skill in job_title_lower:
                        has_it = True
                    if has_it:
                        matches += 1
                score = int((matches / max(1, len(lower_skills))) * 100)

            
        if designation_lower and designation_lower in job_title_lower:
            score += min(100 - score, 20)
            
        # Only apply if match score is > 70%
        if score > 70:
            job['match_score'] = score
            filtered_jobs.append(job)
            
    filtered_jobs.sort(key=lambda x: x['match_score'], reverse=True)
    return filtered_jobs[:5] # Limit to top 5 to avoid long blockages


def mark_applied(job_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE jobs SET is_applied = 1 WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()

async def process_job(job, browser, llm_model):
    url = job['url']
    print(f"\n[LLM Agent] Evaluating: {job['title']} at {job['company']}")
    print(f"URL: {url}")
    
    # Provide the AI with strict instructions on how to handle the forms
    task_instructions = f"""
    Navigate to this job application URL: {url}
    
    Task: Apply for this job successfully.
    
    1. If it's Naukri, thoroughly scan the page for the 'Apply' or 'Apply Now' button. Look for elements with class "apply-button", id "apply-button", or text "Apply".
       - Naukri uses different layouts. Sometimes the button is inside a strictly fixed header (`div.apply-button-container`), or at the very bottom.
       - If a chat pop-up or modal blocks the screen, close or click past it before clicking apply.
       - IMPORTANT: If a button says "Apply on company site" or redirects externally, DO NOT click it. Stop and return "EXTERNAL_SITE".
       - Once clicked, look for toast notifications or text saying "Applied Successfully" or "Already Applied". If either appears, consider it done and return "SUCCESS".
    2. If it's LinkedIn, look for 'Easy Apply' and click it. Go through the "Next" buttons and click "Submit".
    3. If you encounter any standard applicant tracking system (ATS) form, attempt to fill in basic fields (first name, last name, phone) if explicitly required.
    
    Return "SUCCESS" if you are confident the application was submitted.
    Return "FAILED" if you hit a hard blocker or an external site.
    """

    agent = Agent(
        task=task_instructions,
        llm=llm_model,
        browser=browser
    )
    
    try:
        # Give the agent a maximum of 3 steps to figure it out, then stop.
        history = await agent.run(max_steps=5)
        result_text = str(history).lower()
        
        # Super basic validation based on LLM's final state response
        if "success" in result_text and "external_site" not in result_text:
            print("--> Agent successfully applied! Marking in DB.")
            mark_applied(job['id'])
        else:
            print("--> Agent stopped or failed to apply.")
            
    except Exception as e:
        print(f"Error applying to {url} using LLM: {e}")

async def async_run_auto_apply(platform='all', designation='', skills=None):
    jobs = get_unapplied_jobs(platform, designation, skills)
    if not jobs:
        print("No new jobs pending application.")
        return

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY environment variable is not set!")
        return

    print(f"Found {len(jobs)} unapplied jobs. Starting LLM Auto-Apply Agent...")

    # Initialize Claude 3.5 Sonnet (Best model for UI parsing)
    llm = CustomChatAnthropic(model_name="claude-3-5-sonnet-20241022", temperature=0.0)

    # Launch its own Chrome window using the saved playwright profile so you are still logged in
    browser = Browser(browser_profile=BrowserProfile(
        headless=False,
        executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        user_data_dir=USER_DATA_DIR,
    ))

    for job in jobs:
        await process_job(job, browser, llm)
        await asyncio.sleep(5)
        
    print("Agent execution finished.")

def run_auto_apply(platform='all', designation='', skills=None):
    # Flask triggers this in a background thread
    # We must use asyncio.run to kickstart the async LLM agent loop
    asyncio.run(async_run_auto_apply(platform, designation, skills))

if __name__ == "__main__":
    run_auto_apply()
