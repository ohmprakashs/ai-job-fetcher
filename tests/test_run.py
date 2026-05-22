import sys
sys.path.append("app")
from app.cv_generator import build_tailored_pdf
job = {"title": "Full Stack Dev", "company": "Walmart", "skills": "React, Node.js, Python, Flask, AWS", "url": "https://www.linkedin.com/jobs/view/4402184359", "source": "LinkedIn"}
path = build_tailored_pdf(job, "sample_cv.pdf", "test_awesome_format_cv.pdf")
print("Saved to:", path)
