with open("run.py", "r") as f:
    text = f.read()

old_str = "import sys\nimport threading\nfrom apscheduler.schedulers.background import BackgroundScheduler\n\nrepo_dir = os.path.dirname(os.path.abspath(__file__))"
new_str = "import sys\nimport threading\nfrom apscheduler.schedulers.background import BackgroundScheduler\nfrom dotenv import load_dotenv\n\nload_dotenv()\n\nrepo_dir = os.path.dirname(os.path.abspath(__file__))"

text = text.replace(old_str, new_str)
with open("run.py", "w") as f:
    f.write(text)
print("Added load_dotenv to run.py")
