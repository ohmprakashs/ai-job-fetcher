with open('app/auto_apply_bot.py', 'r') as f:
    text = f.read()

import re

# We need to give the AI agent more steps since Naukri UI is complex and sometimes requires scrolling, closing modals, then clicking apply.
text = text.replace('history = await agent.run(max_steps=3)', 'history = await agent.run(max_steps=5)')

with open('app/auto_apply_bot.py', 'w') as f:
    f.write(text)
