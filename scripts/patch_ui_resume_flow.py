import re

with open('app/ui.py', 'r') as f:
    text = f.read()

old_logic = """                
            # If the user just uploaded a resume, we return immediately to show them the extracted skills in the UI
            # without triggering the full long 30-second job scrape automatically!
            has_resume = True
            return render_template(
                'index.html',
                skills=skills,
                jobs=[],
                summary={},
                common_jobs=[],
                location_filter=request.form.get('location', '').strip().lower(),
                designation_filter=request.form.get('designation', '').strip().lower(),
                experience_years=None,
                posted_within_days=None,
                did_submit=False,
                has_resume=has_resume,
            )"""

new_logic = """"""

text = text.replace(old_logic, new_logic)

with open('app/ui.py', 'w') as f:
    f.write(text)

print("Removed short-circuit render for resume upload.")
