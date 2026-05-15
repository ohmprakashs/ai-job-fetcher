import re

with open('app/templates/index.html', 'r') as f:
    text = f.read()

old_button = """                                        <form action="{{ url_for('apply_job') }}" method="post" target="_blank" style="display:inline; margin-right: 5px;">
                                            <input type="hidden" name="title" value="{{ job.title }}">
                                            <input type="hidden" name="company" value="{{ job.company }}">
                                            <input type="hidden" name="location" value="{{ job.location if job.location else '' }}">
                                            <input type="hidden" name="source" value="{{ job.source }}">
                                            <input type="hidden" name="url" value="{{ job.url if job.url else '#' }}">
                                            <button
                                                type="submit"
                                                class="apply-btn{% if not job.url %} disabled{% endif %}"
                                                {% if job.is_applied %}style="background: #28a745; border: 1px solid #218838;"{% endif %}
                                                {% if not job.url %}disabled{% endif %}
                                                onclick="setTimeout(() => window.location.reload(), 1000)"
                                            >{% if job.is_applied %}Applied (Re-Apply){% else %}Apply{% endif %}</button>
                                        </form>"""

new_button = """                                        <button
                                            type="button"
                                            class="apply-btn{% if not job.url %} disabled{% endif %}"
                                            style="margin-right: 5px; {% if job.is_applied %}background: #28a745; border: 1px solid #218838;{% endif %}"
                                            {% if not job.url %}disabled{% endif %}
                                            onclick="fetch('{{ url_for('apply_job_async') }}', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({title: '{{ job.title }}', company: '{{ job.company }}', location: '{{ job.location if job.location else '' }}', source: '{{ job.source }}'})}); window.open('{{ job.url }}', '_blank', 'noopener,noreferrer'); setTimeout(() => window.location.reload(), 1500);"
                                        >{% if job.is_applied %}Applied (Re-Apply){% else %}Apply{% endif %}</button>"""

text = text.replace(old_button, new_button)

with open('app/templates/index.html', 'w') as f:
    f.write(text)
