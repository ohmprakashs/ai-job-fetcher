import os
import re

with open('app/ui.py', 'r') as f:
    text = f.read()

# Add route
route_code = """
@app.route('/remove-resume', methods=['POST'])
def remove_resume():
    resume_path = os.path.join(_BASE_DIR, "..", "sample_cv.pdf")
    if os.path.exists(resume_path):
        os.remove(resume_path)
    return redirect(url_for('index'))

@app.route('/generate-cv/<int:job_id>', methods=['GET'])
"""
text = text.replace("@app.route('/generate-cv/<int:job_id>', methods=['GET'])", route_code.strip())

# Add has_resume
index_logic = """    resume_path = os.path.join(_BASE_DIR, "..", "sample_cv.pdf")
    has_resume = os.path.exists(resume_path)
    
    return render_template(
        'index.html',
        skills=skills,"""
text = text.replace("    return render_template(\n        'index.html',\n        skills=skills,", index_logic)

# Make sure we pass has_resume
text = text.replace("        did_submit=did_submit,\n    )", "        did_submit=did_submit,\n        has_resume=has_resume,\n    )")

with open('app/ui.py', 'w') as f:
    f.write(text)
