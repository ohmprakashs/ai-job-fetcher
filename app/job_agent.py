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
                
                # Expand search locations with synonyms (e.g. Bangalore <-> Bengaluru)
                expanded_locs = set(search_locs)
                for loc in search_locs:
                    if "bangalore" in loc or "bengaluru" in loc:
                        expanded_locs.update(["bangalore", "bengaluru"])
                        
                # If none of the search locs are in the job location, filter it out
                if expanded_locs and not any(l in job_loc for l in expanded_locs):
                    continue
                
            # Check skills carefully: either the skill is in the job title or explicitly in the tags
            # We want to match at least ONE skill strongly.
            if self.skills:
                job_title_lower = str(job.get("title", "")).lower()
                job_skills_lower = [s.lower().strip() for s in job.get("skills", [])]
                
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
                    
            # Check designation flexibly against Job Title
            if self.designation:
                job_title = str(job.get("title", "")).lower()
                desig_parts = self.designation.replace(',', ' ').split()
                # Ensure all words from designation are found in the title
                if not all(part in job_title for part in desig_parts):
                    continue

            # Calculate match score (Resume vs JD)
            score = 0
            job_title_lower = str(job.get("title", "")).lower()
            job_skills_lower = [str(s).lower().strip() for s in job.get("skills", [])]
            
            if self.skills:
                matches = 0
                # What the job requires (from tags)
                job_required_skills = [s for s in job_skills_lower if len(s) > 1]
                
                # If LinkedIn or job has no skills, we evaluate based on how many user skills match the title
                if not job_required_skills:
                    # just see if at least one user skill is in title.
                    for skill in self.skills:
                        if skill in job_title_lower:
                            matches += 1
                    # Give it a decent baseline if it matches title well
                    score = min(100, int((matches / max(1, len(self.skills))) * 100) + 50) if matches > 0 else 0
                else:
                    # Normal Naukri job with tags
                    # Does the job have the user's skill?
                    for user_skill in self.skills:
                        has_it = False
                        for req_skill in job_required_skills:
                            if user_skill in req_skill or req_skill in user_skill:
                                has_it = True
                                break
                        if not has_it and user_skill in job_title_lower:
                            has_it = True
                        if has_it:
                            matches += 1
                    
                    score = int((matches / len(self.skills)) * 100)
                
            # Bonus score if designation strictly matches 
            if self.designation and all(p in job_title_lower for p in self.designation.replace(",", " ").split()):
                score += min(100 - score, 20)  # Max score is 100
                
            job['match_score'] = score
                    
            if not self.skills:
                job['match_score'] = 100
                filtered_jobs.append(job)
            elif job["match_score"] >= 70:
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
