from job_fetcher import fetch_jobs, _job_matches_experience, _job_matches_posted_within, _matches_requested_skills
from collections import defaultdict
from job_db import init_db, insert_jobs, get_jobs_from_db

class JobAIAgent:
    def __init__(self, skills, location="", experience_years=None, posted_within_days=None, designation=""):
        self.skills = [s.lower() for s in skills if s.strip()]
        self.location = location.lower()
        self.designation = designation.lower()
        self.experience_years = experience_years
        self.posted_within_days = posted_within_days
        self.jobs = []
        self.summary = {}

    def fetch_and_summarize(self):
        # 1. Fetch live jobs from the network
        fetched_live_jobs = fetch_jobs(
            self.skills,
            designation=self.designation,
            location=self.location,
            experience_years=self.experience_years,
            posted_within_days=self.posted_within_days,
        )
        
        # 2. Store/update these live jobs in the DB to refresh fetched_at timestamp
        insert_jobs(fetched_live_jobs)
        
        # 3. Pull ALL known jobs from the DB so we have a full "cached" list
        all_cached_jobs = get_jobs_from_db()
        
        # 4. Filter the cached jobs according to the current UI filters
        filtered_jobs = []
        for job in all_cached_jobs:
            # Check location
            if self.location:
                job_loc = str(job.get("location", "")).lower()
                search_locs = [l.strip() for l in self.location.split(",") if l.strip()]
                # If none of the search locs are in the job location, filter it out
                if search_locs and not any(l in job_loc for l in search_locs):
                    continue
                
            # Check skills carefully: either the skill is in the job title or explicitly in the tags
            # We want to match at least ONE skill strongly.
            if self.skills:
                job_title_lower = str(job.get("title", "")).lower()
                job_skills_lower = [s.lower() for s in job.get("skills", [])]
                
                matched = False
                for req_skill in self.skills:
                    if req_skill in job_title_lower or req_skill in job_skills_lower:
                        matched = True
                        break
                if not matched:
                    # Try soft matching inside the title if it wasn't an exact match
                    if not any(req_skill in job_title_lower for req_skill in self.skills):
                        continue
                 
            # Check experience
            if self.experience_years is not None:
                if not _job_matches_experience(job, self.experience_years):
                    continue
                    
            # Check posted within days
            if self.posted_within_days is not None:
                if not _job_matches_posted_within(job, self.posted_within_days):
                    continue
                    
            # Check designation strictly against Job Title
            if self.designation:
                job_title = str(job.get("title", "")).lower()
                if self.designation not in job_title:
                    continue

            # Calculate match score (Resume vs JD)
            score = 0
            job_title_lower = str(job.get("title", "")).lower()
            job_skills_lower = [str(s).lower() for s in job.get("skills", [])]
            
            if self.skills:
                matches = 0
                for skill in self.skills:
                    if skill in job_skills_lower or skill in job_title_lower:
                        matches += 1
                score = int((matches / len(self.skills)) * 100)
                
            # Bonus score if designation strictly matches 
            if self.designation and self.designation in job_title_lower:
                score += min(100 - score, 20)  # Max score is 100
                
            job['match_score'] = score
                    
            filtered_jobs.append(job)
            
        # Sort jobs by match_score descending
        filtered_jobs.sort(key=lambda j: (j.get('posted_days_ago') if j.get('posted_days_ago') is not None else 9999, -j.get('match_score', 0)))
            
        self.jobs = filtered_jobs
        self.summary = self._summarize_jobs()
        return self.summary

    def _summarize_jobs(self):
        company_skill_count = defaultdict(lambda: defaultdict(int))
        for job in self.jobs:
            company = job.get('company', 'Unknown')
            for skill in job.get('skills', []):
                company_skill_count[company][skill] += 1
        return {company: dict(skills) for company, skills in company_skill_count.items()}

    def get_jobs(self):
        return self.jobs

    def get_summary(self):
        return self.summary
