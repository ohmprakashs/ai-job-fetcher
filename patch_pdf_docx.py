with open("app/cv_generator.py", "r") as f:
    text = f.read()

import re
text = text.replace('text += extracted + "', 'text += extracted + "\\n"\n            # "')

with open("app/cv_generator.py", "w") as f:
    f.write(text)

