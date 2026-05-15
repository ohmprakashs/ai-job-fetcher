import re

with open('app/templates/index.html', 'r') as f:
    text = f.read()

# Replace the overly complex apply button
pattern = r'<button\s+type="button"\s+class="apply-btn[^>]+>.*?<\/button>'
replacement = """<button
                                            type="button"
                                            class="apply-btn{% if not job.url %} disabled{% endif %}"
                                            style="margin-right: 5px;"
                                            {% if not job.url %}disabled{% endif %}
                                            onclick="window.open('{{ job.url }}', '_blank', 'noopener,noreferrer');"
                                        >View Job</button>
                                        <button
                                            type="button"
                                            class="apply-btn"
                                            style="margin-top: 5px; {% if job.is_applied %}background: #28a745; border: 1px solid #218838;{% else %}background: #ffc107; color: #000; border: 1px solid #d39e00;{% endif %}"
                                            onclick="fetch('{{ url_for('apply_job_async') }}', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({title: '{{ job.title }}', company: '{{ job.company }}', location: '{{ job.location if job.location else '' }}', source: '{{ job.source }}'})}).then(() => window.location.reload());"
                                        >{% if job.is_applied %}✅ Applied{% else %}Mark as Applied{% endif %}</button>"""

text = re.sub(pattern, replacement, text, count=1, flags=re.DOTALL)

with open('app/templates/index.html', 'w') as f:
    f.write(text)
