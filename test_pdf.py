import sys, os
sys.path.append(os.path.join(os.getcwd(), 'app'))
from app.cv_generator import extract_text_from_pdf
text = extract_text_from_pdf('sample_cv.pdf')
print("PDF TEXT:", repr(text))
