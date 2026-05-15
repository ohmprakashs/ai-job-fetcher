with open('app/auto_apply_bot.py', 'r') as f:
    text = f.read()

import re

old_prompt = """    1. If it's Naukri, thoroughly scan the page for the 'Apply' or 'Apply Now' button. It may be at the top or bottom of the page (sometimes id="apply-button", class containing "apply", or text "Apply"). Click it.
       - IMPORTANT: If a button says "Apply on company site" or redirects externally, DO NOT click it. Stop and return "EXTERNAL_SITE".
       - Once clicked, check if it says "Applied Successfully" or "Already Applied". If either appears, consider it done and return "SUCCESS". 
       - Sometimes Naukri has a chat bot or modal. Handle it if necessary.
       - If you cannot find the Apply button after waiting, scroll down and look again."""


new_prompt = """    1. If it's Naukri, thoroughly scan the page for the 'Apply' or 'Apply Now' button. Look for elements with class "apply-button", id "apply-button", or text "Apply".
       - Naukri uses different layouts. Sometimes the button is inside a strictly fixed header (`div.apply-button-container`), or at the very bottom.
       - If a chat pop-up or modal blocks the screen, close or click past it before clicking apply.
       - IMPORTANT: If a button says "Apply on company site" or redirects externally, DO NOT click it. Stop and return "EXTERNAL_SITE".
       - Once clicked, look for toast notifications or text saying "Applied Successfully" or "Already Applied". If either appears, consider it done and return "SUCCESS"."""

text = text.replace(old_prompt, new_prompt)

with open('app/auto_apply_bot.py', 'w') as f:
    f.write(text)
