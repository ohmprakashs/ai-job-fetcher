import os
import sys
# Set dummy path just in case
sys.path.append(os.path.join(os.getcwd(), 'app'))
from cv_generator import extract_skills_from_cv

print("TESTING EXTRACTION...")
skills = extract_skills_from_cv('sample_cv.pdf')
print("RESULT:", skills)
