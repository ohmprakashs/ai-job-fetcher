with open("app/cv_generator.py", "r") as f:
    text = f.read()

new_func = """
def extract_skills_from_cv(pdf_path):
    text = extract_text_from_pdf(pdf_path).lower()
    if not text.strip():
        print("Warning: CV text extraction returned empty string!")
        return ""
        
    # An exhaustive offline keyword array fallback (Expanded AI Mock)
    KNOWN_SKILLS = [
        # Programming & Scripting
        "python", "java", "c++", "c#", "c", "javascript", "typescript", "golang", "go", "ruby", "rust", "php", "swift", "kotlin", "perl", "scala", "r", "bash", "shell", "powershell", "dart", "matlab",
        # Frameworks & Libraries
        "react", "angular", "vue", "vue.js", "svelte", "node.js", "express", "django", "flask", "fastapi", "spring", "spring boot", "ruby on rails", "laravel", "next.js", "nuxt.js", "bootstrap", "tailwind", "jquery", "asp.net", "hibernate",
        # Databases
        "sql", "mysql", "postgresql", "mongodb", "oracle", "nosql", "firebase", "cassandra", "redis", "sqlite", "mariadb", "dynamodb", "couchbase", "elasticsearch", "neo4j", "supabase", "cockroachdb",
        # Cloud & DevOps
        "aws", "azure", "gcp", "google cloud", "docker", "kubernetes", "terraform", "jenkins", "ansible", "puppet", "chef", "vagrant", "circleci", "travis ci", "gitlab ci", "bitbucket ci", "helm", "cloudformation", "openshift", "serverless", "fargate",
        # OS, Version Control & Collaboration
        "linux", "unix", "ubuntu", "centos", "debian", "redhat", "windows", "macos", "git", "github", "gitlab", "bitbucket", "svn", "jira", "confluence", "slack", "trello",
        # Methodologies & Architecture
        "ci/cd", "agile", "scrum", "kanban", "devops", "devsecops", "microservices", "rest api", "graphql", "grpc", "soap", "mvc", "tdd", "bdd", "oop",
        # AI, ML, Data
        "machine learning", "deep learning", "nlp", "pytorch", "tensorflow", "keras", "scikit-learn", "pandas", "numpy", "matplotlib", "seaborn", "jupyter", "opencv", "computer vision", "llm", "generative ai", "openai", "chatgpt", "langchain", "huggingface",
        # Big Data & Data Engineering
        "hadoop", "spark", "kafka", "snowflake", "airflow", "databricks", "bigquery", "redshift", "hive", "flink", "dbt", "talend", "tableau", "power bi", "looker",
        # Monitoring & ITSM
        "prometheus", "grafana", "servicenow", "splunk", "datadog", "new relic", "elk", "logstash", "kibana", "appdynamics", "dynatrace", "zabbix", "nagios", "pagerduty",
        # Web & Mobile
        "html", "css", "html5", "css3", "sass", "less", "android", "ios", "react native", "flutter", "xamarin", "ionic",
        # Others
        "nginx", "apache", "rabbitmq", "activemq", "maven", "gradle", "npm", "yarn", "webpack", "babel", "oauth", "jwt", "saml", "sso", "selenium", "cypress", "jest", "puppeteer", "mocha", "jasmine", "pytest", "junit"
    ]
    
    found_skills = set()
    for skill in sorted(KNOWN_SKILLS, key=len, reverse=True):
        import re
        escaped_skill = re.escape(skill)
        match = re.search(r'(?<![a-z0-9])' + escaped_skill + r'(?![a-z0-9])', text)
        if match:
            found_skills.add(skill)
            
    print("Local Extracted Skills from CV:", list(found_skills))
    return ", ".join(list(found_skills))
"""

import re
text = re.sub(r'def extract_skills_from_cv\(pdf_path\):[\s\S]+$', new_func.strip(), text)

with open("app/cv_generator.py", "w") as f:
    f.write(text)

print("Patched cv_generator.py with exhaustive skills list!")
