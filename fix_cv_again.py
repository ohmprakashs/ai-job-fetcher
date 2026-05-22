with open("app/cv_generator.py", "r") as f:
    text = f.read()

import re
old_ext = """def extract_text_from_pdf(pdf_path):
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\\n"
    return text"""

new_ext = """def extract_text_from_pdf(pdf_path):
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted: text += extracted + "\\n"
        return text
    except Exception as e:
        print("PDF Error:", e)
        return "" """

text = text.replace(old_ext, new_ext)

with open("app/cv_generator.py", "w") as f:
    f.write(text)
