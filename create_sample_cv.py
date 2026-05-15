from fpdf import FPDF
pdf = FPDF()
pdf.add_page()
pdf.set_font("Helvetica", size=12)
pdf.multi_cell(0, 10, "John Doe\nSoftware Engineer\n\nExperience:\n- 3 years in Python development\n- Built APIs using Flask and Docker\n- Familiar with CI/CD\n\nEducation:\nB.S. Computer Science")
pdf.output("sample_cv.pdf")
