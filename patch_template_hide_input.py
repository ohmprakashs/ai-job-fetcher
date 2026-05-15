with open('app/templates/index.html', 'r') as f:
    text = f.read()

old_section = """        <div class="section">
            <label for="resume" style="font-weight: bold; margin-right: 10px;">Upload Base Resume (PDF):</label>
            <input type="file" id="resume" name="resume" accept="application/pdf">
            {% if has_resume %}
            <span style="color: #28a745; font-weight: bold; margin-left: 10px;">✅ Resume is loaded!</span>
            <button type="submit" formaction="{{ url_for('remove_resume') }}" formnovalidate style="margin-left: 10px; padding: 5px 10px; background: #dc3545; color: #fff; border: none; border-radius: 4px; cursor: pointer;">Remove Resume</button>
            {% endif %}
        </div>"""

new_section = """        <div class="section">
            {% if has_resume %}
                <span style="color: #28a745; font-weight: bold;">✅ Your Resume is securely uploaded and active!</span>
                <span style="color: #555; font-family: monospace; margin-left: 10px;">(sample_cv.pdf)</span>
                <button type="submit" formaction="{{ url_for('remove_resume') }}" formnovalidate style="margin-left: 10px; padding: 5px 10px; background: #dc3545; color: #fff; border: none; border-radius: 4px; cursor: pointer;">Remove Resume</button>
            {% else %}
                <label for="resume" style="font-weight: bold; margin-right: 10px;">Upload Base Resume (PDF):</label>
                <input type="file" id="resume" name="resume" accept="application/pdf" required>
            {% endif %}
        </div>"""

# Need to accommodate any minor indent variations
import re
text = text.replace(old_section, new_section)
# If direct replace blocked by spaces
text = re.sub(
    r'<div class="section">\s*<label for="resume".*?Upload Base Resume.*?accept="application/pdf">\s*{% if has_resume %}.*?Remove Resume</button>\s*{% endif %}\s*</div>', 
    new_section, 
    text, 
    flags=re.DOTALL
)

with open('app/templates/index.html', 'w') as f:
    f.write(text)
