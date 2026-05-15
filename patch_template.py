with open('app/templates/index.html', 'r') as f:
    text = f.read()

import re

old_block = """                                    {% if job.is_applied %}
                                        <span class="apply-btn" style="background: #28a745; cursor: default; border: 1px solid #218838;">Applied</span>
                                    {% else %}
                                        <form action="{{ url_for('apply_job') }}" method="post" target="_blank" style="display:inline; margin-right: 5px;">
                                            <input type="hidden" name="title" value="{{ job.title }}">
                                            <input type="hidden" name="company" value="{{ job.company }}">
                                            <input type="hidden" name="location" value="{{ job.location if job.location else '' }}">
                                            <input type="hidden" name="source" value="{{ job.source }}">
                                            <input type="hidden" name="url" value="{{ job.url if job.url else '#' }}">
                                            <button
                                                type="submit"
                                                class="apply-btn{% if not job.url %} disabled{% endif %}"
                                                {% if not job.url %}disabled{% endif %}
                                                onclick="setTimeout(() => window.location.reload(), 1000)"
                                            >Apply</button>
                                        </form>
                                        {% if job.id %}
                                        <a href="{{ url_for('generate_cv', job_id=job.id) }}" class="apply-btn" style="background: #17a2b8; margin-top: 5px; font-size: 0.9em;" target="_blank">Generate CV</a>
                                        {% endif %}
                                    {% endif %}"""

new_block = """                                        <form action="{{ url_for('apply_job') }}" method="post" target="_blank" style="display:inline; margin-right: 5px;">
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
                                        </form>
                                        {% if job.id %}
                                        <a href="{{ url_for('generate_cv', job_id=job.id) }}" class="apply-btn" style="background: #17a2b8; margin-top: 5px; font-size: 0.9em;" target="_blank">Generate CV</a>
                                        {% endif %}"""

text = text.replace(old_block, new_block)

with open('app/templates/index.html', 'w') as f:
    f.write(text)
