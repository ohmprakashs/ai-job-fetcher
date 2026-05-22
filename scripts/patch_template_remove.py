with open('app/templates/index.html', 'r') as f:
    text = f.read()

import re

old_section = """        <div class="section">
            <label for="resume" style="font-weight: bold; margin-right: 10px;">Upload Base Resume (PDF):</label>
            <input type="file" id="resume" name="resume" accept="application/pdf">
        </div>
        <button type="submit" style="padding: 10px 20px; background: #007bff; color: #fff; border: none; cursor: pointer; border-radius: 5px;">Fetch Jobs</button>"""

new_section = """        <div class="section">
            <label for="resume" style="font-weight: bold; margin-right: 10px;">Upload Base Resume (PDF):</label>
            <input type="file" id="resume" name="resume" accept="application/pdf">
            {% if has_resume %}
            <span style="color: #28a745; font-weight: bold; margin-left: 10px;">✅ Resume is loaded!</span>
            <button type="submit" formaction="{{ url_for('remove_resume') }}" formnovalidate style="margin-left: 10px; padding: 5px 10px; background: #dc3545; color: #fff; border: none; border-radius: 4px; cursor: pointer;">Remove Resume</button>
            {% endif %}
        </div>
        <button type="submit" style="padding: 10px 20px; background: #007bff; color: #fff; border: none; cursor: pointer; border-radius: 5px;">Fetch Jobs</button>"""

text = text.replace(old_section, new_section)

with open('app/templates/index.html', 'w') as f:
    f.write(text)
