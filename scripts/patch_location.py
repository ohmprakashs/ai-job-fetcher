with open('app/job_agent.py', 'r') as f:
    text = f.read()

old_loc = """            # Check location
            if self.location:
                job_loc = str(job.get("location", "")).lower()
                search_locs = [l.strip() for l in self.location.split(",") if l.strip()]
                # If none of the search locs are in the job location, filter it out
                if search_locs and not any(l in job_loc for l in search_locs):
                    continue"""

new_loc = """            # Check location
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
                    continue"""

text = text.replace(old_loc, new_loc)

with open('app/job_agent.py', 'w') as f:
    f.write(text)
