with open('app/templates/index.html', 'r') as f:
    text = f.read()

text = text.replace('required>', '>') # Remove required so user can still do normal searches if they don't want to upload

with open('app/templates/index.html', 'w') as f:
    f.write(text)
