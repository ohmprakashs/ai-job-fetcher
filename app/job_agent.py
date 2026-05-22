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
                
            # Let the advanced scoring logic handle skill matching later.
            # We no longer hard-filter jobs based on strict skill title matches here.
                 
            # Check experience
            if self.experience_years is not None:
                if not _job_matches_experience(job, self.experience_years):
                    continue
                    
            # Check posted within days
            if self.posted_within_days is not None:
                if not _job_matches_posted_within(job, self.posted_within_days):
                    continue
                    
            # Check designation flexibly against Job Title (now just a soft filter for scoring)
            if self.designation:
                job_title = str(job.get("title", "")).lower()
                desig_parts = self.designation.replace(',', ' ').split()
                # We won't block the job here anymore. We will let the score decide.

            # Calculate Advanced ATS match score (Resume vs JD)
            import re as _re
            score = 0
            job_title_lower = str(job.get("title", "")).lower()
            job_skills_lower = [str(s).lower().strip() for s in job.get("skills", [])]

            matched_skills = []
            missing_skills = []

            if self.skills:
                # Naukri provides explicit skill tags; LinkedIn does not.
                job_required_skills = [s for s in job_skills_lower if len(s) > 1]

                # Build the broadest possible search text from all available fields:
                #   title  +  skill tags  +  description / snippet  +  company name
                # This helps LinkedIn jobs (which lack tags) still get a fair score.
                search_text = " ".join(filter(None, [
                    job_title_lower,
                    " ".join(job_required_skills),
                    str(job.get("description", "")).lower(),
                    str(job.get("snippet", "")).lower(),
                    str(job.get("company", "")).lower(),
                ]))

                def _skill_in_text(skill, text):
                    return bool(_re.search(
                        r'(?<![a-z0-9])' + _re.escape(skill) + r'(?![a-z0-9])', text
                    ))

                for user_skill in self.skills:
                    # Check explicit tag list first (exact / substring match)
                    tag_match = any(
                        user_skill == req or (len(user_skill) > 2 and user_skill in req)
                        for req in job_required_skills
                    )
                    # Fall back to searching all available text
                    if tag_match or _skill_in_text(user_skill, search_text):
                        matched_skills.append(user_skill)
                    else:
                        missing_skills.append(user_skill)

                if self.skills:
                    # Score: 25 pts per matched skill, capped at 75
                    score = min(len(matched_skills) * 25, 75)
                else:
                    score = 0
                
            desig_score = 0
            if self.designation:
                desig_parts = self.designation.replace(",", " ").split()
                # Strict exact full match
                if all(p in job_title_lower for p in desig_parts):
                    desig_score = 25
                # Meaningless partial matches should not grant points to unrelated JDs
                elif len(desig_parts) > 1 and sum(1 for p in desig_parts if p in job_title_lower) >= len(desig_parts) / 2:
                    desig_score = 10
                
            score += desig_score
            
            job['match_score'] = min(score, 100)
            job['matched_skills'] = matched_skills
            job['missing_skills'] = missing_skills
                    
            if not self.skills and not self.designation:
                # No filters provided, show everything with 100% score
                job['match_score'] = 100
                filtered_jobs.append(job)
            elif job["match_score"] >= 50: 
                # Either skills or designation provided, show jobs with >= 50 match
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
