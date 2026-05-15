import re

with open('app/ui.py', 'r') as f:
    text = f.read()

# Add a JSON endpoint for marking jobs as applied without a flask redirect
new_endpoint = """
@app.route('/apply-async', methods=['POST'])
def apply_job_async():
    data = request.get_json()
    if data:
        title = data.get('title', '')
        company = data.get('company', '')
        location = data.get('location', '')
        source = data.get('source', '')
        
        init_db()
        mark_job_applied(title, company, location, source)
        return {"status": "success"}
    return {"status": "error"}, 400
"""

text = text.replace("@app.route('/apply', methods=['POST'])", new_endpoint + "\n@app.route('/apply', methods=['POST'])")

with open('app/ui.py', 'w') as f:
    f.write(text)

