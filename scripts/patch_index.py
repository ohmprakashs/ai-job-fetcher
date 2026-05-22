with open("app/templates/index.html", "r") as f:
    text = f.read()

text = text.replace("<th>Source</th><th>Apply</th>", "<th>Source</th><th>Apply Type</th><th>Apply</th>")

old_str = "<td>{{ job.source }}</td>"
new_str = "<td>{{ job.source }}</td><td>{{ job.apply_type if job.apply_type else 'N/A' }}</td>"
text = text.replace(old_str, new_str)

with open("app/templates/index.html", "w") as f:
    f.write(text)
print("Updated index.html")
