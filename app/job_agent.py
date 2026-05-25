from job_fetcher import fetch_jobs, _job_matches_experience, _job_matches_posted_within, _matches_requested_skills
from collections import defaultdict
from job_db import init_db, insert_jobs, get_jobs_from_db, update_job_description

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

                # ── Fetch real JD text for LinkedIn jobs ──────────────────
                # LinkedIn card pages don't include skill tags. When a job
                # has no cached description, fetch it now (fast HTTP GET) and
                # cache it so we only do this once per job.
                # Guard: use `or ""` to safely convert DB NULLs (Python None) to ""
                job_description = str(job.get("description") or "").strip()
                job_snippet     = str(job.get("snippet")     or "").strip()
                job_source      = str(job.get("source",   "") or "").lower()

                # Only lazily fetch JDs for jobs whose title fully matches the
                # designation — avoids fetching hundreds of JDs on every scoring run.
                # "any()" would be too broad (hundreds of "Engineer" titles).
                # "all()" limits fetches to jobs where every designation word appears.
                title_has_designation = bool(self.designation) and all(
                    p in str(job.get("title", "")).lower()
                    for p in self.designation.replace(",", " ").split()
                    if len(p) > 2
                )
                if (not job_description and job_source == "linkedin"
                        and job.get("url") and title_has_designation):
                    try:
                        from jd_scraper import scrape_jd_text
                        fetched = scrape_jd_text(job["url"], "linkedin") or ""
                        if fetched:
                            job_description = fetched
                            if job.get("id"):
                                update_job_description(job["id"], fetched)
                    except Exception:
                        pass

                # ── Detect "mirror skills": LinkedIn stores our own search
                # keywords that happened to appear in the card title.
                # These are NOT real JD skill requirements.
                # NOTE: only apply to LinkedIn — Naukri provides real skill tags.
                skills_are_mirrors = (
                    job_source == "linkedin"
                    and 0 < len(job_required_skills) <= 2   # small set = likely just title keywords
                    and all(s in self.skills for s in job_required_skills)
                    and not job_description
                )

                # Build the broadest possible search text
                # Use `or ""` on every field to guard against DB NULLs
                search_text = " ".join(filter(None, [
                    job_title_lower,
                    "" if skills_are_mirrors else " ".join(job_required_skills),
                    job_description.lower(),
                    job_snippet.lower(),
                    str(job.get("company") or "").lower(),
                ]))

                def _skill_in_text(skill, text):
                    return bool(_re.search(
                        r'(?<![a-z0-9])' + _re.escape(skill) + r'(?![a-z0-9])', text
                    ))

                for user_skill in self.skills:
                    tag_match = (
                        not skills_are_mirrors and
                        any(user_skill == req or (len(user_skill) > 2 and user_skill in req)
                            for req in job_required_skills)
                    )
                    if tag_match or _skill_in_text(user_skill, search_text):
                        matched_skills.append(user_skill)
                    else:
                        missing_skills.append(user_skill)

                # ── Fallback: job returned by platform but has no real skill data ──
                # When we have no JD text AND title matches designation,
                # assume all user skills are potentially relevant (the platform
                # itself returned this job for our query). Show it; user can verify.
                no_real_data = (
                    (len(job_required_skills) == 0 or skills_are_mirrors)
                    and not job_description
                    and not job_snippet           # already str(…or""), safe to bool
                )
                title_matches_desig = bool(self.designation) and any(
                    p in job_title_lower
                    for p in self.designation.replace(",", " ").split()
                    if len(p) > 2
                )
                if no_real_data and title_matches_desig:
                    matched_skills = list(self.skills)
                    missing_skills = []

                # Score: proportional to % of skills matched, scaled to 75 pts
                match_ratio = len(matched_skills) / len(self.skills) if self.skills else 0
                score = int(match_ratio * 75)

            desig_score = 0
            if self.designation:
                desig_parts = self.designation.replace(",", " ").split()
                if all(p in job_title_lower for p in desig_parts):
                    desig_score = 25
                elif len(desig_parts) > 1 and sum(1 for p in desig_parts if p in job_title_lower) >= len(desig_parts) / 2:
                    desig_score = 10

            score += desig_score

            job['match_score'] = min(score, 100)
            job['matched_skills'] = matched_skills
            job['missing_skills'] = missing_skills

            if not self.skills and not self.designation:
                job['match_score'] = 100
                filtered_jobs.append(job)
            elif job["match_score"] >= 35:
                # Show jobs with >= 35 match — surfaces adjacent roles (e.g. SRE vs DevOps)
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
