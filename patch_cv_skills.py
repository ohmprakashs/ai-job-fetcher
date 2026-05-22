with open("app/cv_generator.py", "r") as f:
    text = f.read()

import re
old_skills = """    KNOWN_SKILLS = [
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
    ]"""

new_skills = """    KNOWN_SKILLS = [
        "python", "java", "c++", "c#", "javascript", "typescript", "golang", "ruby", "rust", "php", "swift", "kotlin", "perl", "scala", "bash", "shell", "powershell", "dart", "matlab",
        "react", "angular", "vue", "vue.js", "svelte", "node.js", "express", "django", "flask", "fastapi", "spring", "spring boot", "ruby on rails", "laravel", "next.js", "nuxt.js", "bootstrap", "tailwind", "jquery", "asp.net", "hibernate",
        "sql", "mysql", "postgresql", "mongodb", "oracle", "nosql", "firebase", "cassandra", "redis", "sqlite", "mariadb", "dynamodb", "couchbase", "elasticsearch", "neo4j", "supabase", "cockroachdb",
        "aws", "azure", "gcp", "google cloud", "docker", "kubernetes", "terraform", "jenkins", "ansible", "puppet", "chef", "vagrant", "circleci", "travis ci", "gitlab ci", "bitbucket ci", "helm", "cloudformation", "openshift", "serverless", "fargate",
        "linux", "windows", "macos", "git", "github", "gitlab", "bitbucket", "svn", "jira", "confluence",
        "ci/cd", "devops", "devsecops", "microservices", "rest api", "graphql", "grpc", "soap", "mvc", "tdd", "bdd", "oop",
        "machine learning", "deep learning", "nlp", "pytorch", "tensorflow", "keras", "scikit-learn", "pandas", "numpy", "matplotlib", "seaborn", "jupyter", "opencv", "computer vision", "llm", "generative ai", "openai", "chatgpt", "langchain", "huggingface",
        "hadoop", "spark", "kafka", "snowflake", "airflow", "databricks", "bigquery", "redshift", "hive", "flink", "dbt", "talend", "tableau", "power bi", "looker",
        "prometheus", "grafana", "servicenow", "splunk", "datadog", "new relic", "elk", "logstash", "kibana", "appdynamics", "dynatrace", "zabbix", "nagios", "pagerduty",
        "html", "css", "html5", "css3", "sass", "android", "ios", "react native", "flutter", "xamarin", "ionic",
        "nginx", "apache", "rabbitmq", "activemq", "maven", "gradle", "npm", "yarn", "webpack", "babel", "oauth", "jwt", "saml", "sso", "selenium", "cypress", "jest", "puppeteer", "mocha", "jasmine", "pytest", "junit"
    ]"""

if old_skills in text:
    text = text.replace(old_skills, new_skills)
    with open("app/cv_generator.py", "w") as f:
        f.write(text)
    print("Patched KNOWN_SKILLS.")
else:
    print("Could not find old_skills!")
