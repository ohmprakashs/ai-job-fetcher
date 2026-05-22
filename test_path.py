import sys, os
sys.path.insert(0, os.path.abspath('app'))
from cv_generator import extract_skills_from_cv
print(extract_skills_from_cv('sample_cv.pdf'))
