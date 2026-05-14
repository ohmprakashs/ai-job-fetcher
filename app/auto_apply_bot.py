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

def get_unapplied_jobs():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # ONLY pull Naukri positions for the LLM! LinkedIn has heavy anti-bot blocking
    c.execute("SELECT * FROM jobs WHERE is_applied = 0 AND source='Naukri' AND url IS NOT NULL AND url != '' LIMIT 3")
    jobs = [dict(r) for r in c.fetchall()]
    conn.close()
    return jobs

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
    
    1. If it's Naukri, look for the 'Apply' button and click it. 
       - IF the button says "Apply on company site", DO NOT click it. Stop and return "EXTERNAL_SITE".
       - Wait to see if it says "Applied Successfully".
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
        history = await agent.run(max_steps=3)
        result_text = str(history).lower()
        
        # Super basic validation based on LLM's final state response
        if "success" in result_text and "external_site" not in result_text:
            print("--> Agent successfully applied! Marking in DB.")
            mark_applied(job['id'])
        else:
            print("--> Agent stopped or failed to apply.")
            
    except Exception as e:
        print(f"Error applying to {url} using LLM: {e}")

async def async_run_auto_apply():
    jobs = get_unapplied_jobs()
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

def run_auto_apply():
    # Flask triggers this in a background thread
    # We must use asyncio.run to kickstart the async LLM agent loop
    asyncio.run(async_run_auto_apply())

if __name__ == "__main__":
    run_auto_apply()
