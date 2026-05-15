with open('app/templates/index.html', 'r') as f:
    text = f.read()

new_input = """        <div class="section">
            <label for="resume" style="font-weight: bold; margin-right: 10px;">Upload Base Resume (PDF):</label>
            <input type="file" id="resume" name="resume" accept="application/pdf">
        </div>
        <button type="submit" style="padding: 10px 20px; background: #007bff; color: #fff; border: none; cursor: pointer; border-radius: 5px;">Fetch Jobs</button>"""

import re
text = re.sub(r'<button type="submit".*?>.*?Fetch Jobs.*?</button>', new_input, text, flags=re.IGNORECASE)

with open('app/templates/index.html', 'w') as f:
    f.write(text)
