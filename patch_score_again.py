with open("app/auto_apply_bot.py", "r") as f:
    content = f.read()

content = content.replace('if score > 70:', 'if score >= 70:')

with open("app/auto_apply_bot.py", "w") as f:
    f.write(content)

