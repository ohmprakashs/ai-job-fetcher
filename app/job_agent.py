from job_fetcher import fetch_jobs, _job_matches_experience, _job_matches_posted_within, _matches_requested_skills
from collections import defaultdict
from job_db import init_db, insert_jobs, get_jobs_from_db, update_job_description, verify_new_jobs_for_expiry
import threading
import time
import re as _re

# ── Global search state tracker ──────────────────────────
# Maps search_id → {'status': 'running'|'done', 'count': N, 'started': timestamp}
_search_state = {}
_search_lock  = threading.Lock()


def get_search_status(search_id):
    with _search_lock:
        return dict(_search_state.get(search_id, {}))


_GENERIC_WORDS = {
    'engineer','senior','junior','lead','manager','developer','analyst',
    'specialist','associate','executive','officer','head','principal',
    'staff','architect','consultant','intern','trainee','fresher',
    'support',  # too generic alone; "desktop support" uses "desktop" as key word
}


class JobAIAgent:
    def __init__(self, skills, location="", experience_years=None, posted_within_days=None, designation=""):
        self.skills = [s.lower() for s in skills if s.strip()]
        self.location = location.lower()
        self.designation = designation.lower()
        self.experience_years = experience_years
        self.posted_within_days = posted_within_days
        self.jobs = []
        self.summary = {}

    def fetch_and_summarize(self, credentials=None, search_id=None):
        """
        Fire a background fetch (non-blocking) so the page loads instantly.
        Clients poll /api/search-status/<id> to know when results are ready.
        Throttle: skips if same desig+location fetched within 10 minutes.
        """
        _skills = list(self.skills)
        _desig  = self.designation
        _loc    = self.location
        _exp    = self.experience_years
        _days   = self.posted_within_days
        _creds  = credentials or {}
        _now    = time.time()

        _cache_key   = f"{_desig}|{_loc}"
        _THROTTLE    = 600  # 10 min — skip repeat fetches after auto-reload

        _skip_fetch = False
        with _search_lock:
            last = _search_state.get('__last__' + _cache_key, {})
            if last.get('status') == 'done' and (_now - last.get('started', 0)) < _THROTTLE:
                _skip_fetch = True
                if search_id:
                    _search_state[search_id] = {'status': 'done', 'count': last.get('count', 0), 'started': _now}

        if _skip_fetch:
            return self._filter_and_score(get_jobs_from_db())

        if search_id:
            with _search_lock:
                _search_state[search_id] = {'status': 'running', 'count': 0, 'started': _now}

        def _bg_fetch():
            try:
                live = fetch_jobs(_skills, designation=_desig, location=_loc,
                                  experience_years=_exp, posted_within_days=_days,
                                  credentials=_creds)
                if live:
                    insert_jobs(live)
                count = len([j for j in live if not j.get('error')]) if live else 0
            except Exception as exc:
                print(f"[agent] fetch error: {exc}")
                count = 0
            with _search_lock:
                done_state = {'status': 'done', 'count': count, 'started': _now}
                if search_id:
                    _search_state[search_id] = done_state
                _search_state['__last__' + _cache_key] = done_state

        threading.Thread(target=_bg_fetch, daemon=True).start()

        # Return cached DB results immediately (before bg fetch completes)
        return self._filter_and_score(get_jobs_from_db())

    def _filter_and_score(self, all_cached_jobs):
        """Filter and ATS-score DB jobs. NEVER makes HTTP requests."""

        # ── Pre-compute location expansion once ──────────────
        # self.location may have multiple chips separated by "||"
        # e.g. "Bangalore / Bengaluru||Karnataka"
        # OR a single "City, State" like "Chennai, Tamil Nadu"
        expanded_locs = set()
        if self.location:
            # Split multiple location chips first
            raw_chips = [c.strip() for c in self.location.split("||") if c.strip()]
            for chip in raw_chips:
                chip_lower = chip.lower()
                # If "City, State" format — extract just the city part
                if "," in chip_lower:
                    city_part = chip_lower.rsplit(",", 1)[0].strip()
                    state_part = chip_lower.rsplit(",", 1)[1].strip()
                    expanded_locs.add(chip_lower)  # full "city, state"
                    expanded_locs.add(city_part)
                    expanded_locs.add(state_part)
                else:
                    city_part = chip_lower
                    expanded_locs.add(chip_lower)
                # Split by "/" for compound city names like "Bangalore / Bengaluru"
                for part in chip_lower.split("/"):
                    p = part.strip()
                    if p:
                        expanded_locs.add(p)
                # Always treat bangalore/bengaluru as equivalent
                if "bangalore" in chip_lower or "bengaluru" in chip_lower:
                    expanded_locs.update(["bangalore", "bengaluru"])

        # ── Pre-compute designation words once ───────────────
        desig_list = [d.strip() for d in self.designation.split(",") if d.strip()]

        filtered_jobs = []

        for job in all_cached_jobs:
            # Skip expired/filled/closed
            if job.get("status") in ("expired", "filled", "closed"):
                continue

            # ── Location filter ───────────────────────────────
            if expanded_locs:
                job_loc = str(job.get("location", "")).lower()
                if not any(loc and loc in job_loc for loc in expanded_locs):
                    continue

            # ── Experience filter ─────────────────────────────
            if self.experience_years is not None:
                if not _job_matches_experience(job, self.experience_years):
                    continue

            # ── Posted-within filter ──────────────────────────
            if self.posted_within_days is not None:
                if not _job_matches_posted_within(job, self.posted_within_days):
                    continue

            # ── ATS Scoring ───────────────────────────────────
            score            = 0
            matched_skills   = []
            missing_skills   = []
            job_title_lower  = str(job.get("title", "")).lower()

            if self.skills:
                job_skills_lower   = [str(s).lower().strip() for s in job.get("skills", [])]
                job_required       = [s for s in job_skills_lower if len(s) > 1]
                job_description    = str(job.get("description") or "").strip()
                job_snippet        = str(job.get("snippet")     or "").strip()
                job_source         = str(job.get("source", "")  or "").lower()

                # Detect "mirror skills": LinkedIn sometimes echoes our search keywords
                # as skill tags when there's no real JD data.
                skills_are_mirrors = (
                    job_source == "linkedin"
                    and 0 < len(job_required) <= 2
                    and all(s in self.skills for s in job_required)
                    and not job_description
                )

                search_text = " ".join(filter(None, [
                    job_title_lower,
                    "" if skills_are_mirrors else " ".join(job_required),
                    job_description.lower(),
                    job_snippet.lower(),
                ]))

                def _skill_match(skill, text):
                    return bool(_re.search(
                        r'(?<![a-z0-9])' + _re.escape(skill) + r'(?![a-z0-9])', text
                    ))

                for user_skill in self.skills:
                    tag_hit = (not skills_are_mirrors and
                               any(user_skill == r or (len(user_skill) > 2 and user_skill in r)
                                   for r in job_required))
                    if tag_hit or _skill_match(user_skill, search_text):
                        matched_skills.append(user_skill)
                    else:
                        missing_skills.append(user_skill)

                # Fallback: no real JD data but title clearly matches designation
                # → the platform returned this job for our query, so assume relevant.
                # NOTE: LinkedIn snippets are metadata (title+company+date), NOT real content.
                # So don't count snippet as "real data" for Naukri-only check.
                no_real_data = (
                    (len(job_required) == 0 or skills_are_mirrors)
                    and not job_description
                )
                # Require ALL non-generic words of the designation to be in the title.
                # "any" was too loose: "support" alone matched "Customer Support" for
                # "desktop support engineer" searches.
                def _desig_non_generic(d):
                    return [p for p in d.split() if len(p) > 3 and p not in _GENERIC_WORDS]

                title_matches_desig = bool(desig_list) and any(
                    (ng := _desig_non_generic(d)) and all(p in job_title_lower for p in ng)
                    for d in desig_list
                )
                if no_real_data and title_matches_desig:
                    matched_skills = list(self.skills)
                    missing_skills = []

                match_ratio = len(matched_skills) / len(self.skills) if self.skills else 0
                score = int(match_ratio * 75)

            # Designation score (0–25 pts)
            desig_score = 0
            if desig_list:
                for d in desig_list:
                    d_parts = d.split()
                    if all(p in job_title_lower for p in d_parts):
                        desig_score = 25
                        break
                    specific = [p for p in d_parts if p not in _GENERIC_WORDS and len(p) > 3]
                    if (len(d_parts) > 1
                            and sum(1 for p in d_parts if p in job_title_lower) >= len(d_parts) / 2
                            and (not specific or any(p in job_title_lower for p in specific))):
                        desig_score = max(desig_score, 10)

            score = min(score + desig_score, 100)
            job['match_score']    = score
            job['matched_skills'] = matched_skills
            job['missing_skills'] = missing_skills

            # Inclusion rules
            if not self.skills and not self.designation:
                job['match_score'] = 100
                filtered_jobs.append(job)
            elif not self.skills:
                filtered_jobs.append(job)
            elif score >= 35:
                filtered_jobs.append(job)

        # Sort: newer first, then by score
        filtered_jobs.sort(key=lambda j: (
            j.get('posted_days_ago') if j.get('posted_days_ago') is not None else 9999,
            -j.get('match_score', 0)
        ))

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
