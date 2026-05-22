with open("app/cv_generator.py", "r") as f:
    text = f.read()

import re

# Replace the text extractor
new_extractor = """def extract_text_from_pdf(pdf_path):
    try:
        if str(pdf_path).lower().endswith('.docx'):
            print(f"Warning: docx upload not supported for full text extraction: {pdf_path}")
            return ""
            
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\\n"
        return text
    except Exception as e:
        print(f"Error reading PDF {pdf_path}: {e}")
        return ""
"""

text = re.sub(r'def extract_text_from_pdf\(pdf_path\):[\s\S]*?(?=def format_offline_cv)', new_extractor + '\n', text)

# Replace the known skills extractor
new_skills = """def extract_skills_from_cv(pdf_path):
    text = extract_text_from_pdf(pdf_path).lower()
    if not text.strip():
        print("Warning: CV text extraction returned empty string!")
        return ""
        
    KNOWN_SKILLS = [
        "python", "java", "c++", "c#", "c", "javascript", "typescript", "golang", "go", "ruby", "rust", "php", "swift", "kotlin", "perl", "scala", "r", "bash", "shell", "powershell", "dart", "matlab",
        "react", "angular", "vue", "vue.js", "svelte", "node.js", "express", "django", "flask", "fastapi", "spring", "spring boot", "ruby on rails", "laravel", "next.js", "nuxt.js", "bootstrap", "tailwind", "jquery", "asp.net", "hibernate",
        "sql", "mysql", "postgresql", "mongodb", "oracle", "nosql", "firebase", "cassandra", "redis", "sqlite", "mariadb", "dynamodb", "couchbase", "elasticsearch", "neo4j", "supabase", "cockroachdb",
        "aws", "azure", "gcp", "google cloud", "docker", "kubernetes", "terraform", "jenkins", "ansible", "puppet", "chef", "vagrant", "circleci", "travis ci", "gitlab ci", "bitbucket ci", "helm", "cloudformation", "openshift", "serverless", "fargate",
        "linux", "unix", "ubuntu", "centos", "debian", "redhat", "windows", "macos", "git", "github", "gitlab", "bitbucket", "svn", "jira", "confluence", "slack", "trello",
        "ci/cd", "agile", "scrum", "kanban", "devops", "devsecops", "microservices", "rest api", "graphql", "grpc", "soap", "mvc", "tdd", "bdd", "oop",
        "machine learning", "deep learning", "nlp", "pytorch", "tensorflow", "keras", "scikit-learn", "pandas", "numpy", "matplotlib", "seaborn", "jupyter", "opencv", "computer vision", "llm", "generative ai", "openai", "chatgpt", "langchain", "huggingface",
        "hadoop", "spark", "kafka", "snowflake", "airflow", "databricks", "bigquery", "redshift", "hive", "flink", "dbt", "talend", "tableau", "power bi", "looker",
        "prometheus", "grafana", "servicenow", "splunk", "datadog", "new relic", "elk", "logstash", "kibana", "appdynamics", "dynatrace", "zabbix", "nagios", "pagerduty",
        "html", "css", "html5", "css3", "sass", "less", "android", "ios", "react native", "flutter", "xamarin", "ionic",
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

text = re.sub(r'def extract_skills_from_cv\(pdf_path\):[\s\S]*$', new_skills + '\n', text)

with open("app/cv_generator.py", "w") as f:
    f.write(text)
