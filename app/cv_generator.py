import os
import re
from pypdf import PdfReader
from fpdf import FPDF
from jd_scraper import scrape_jd_text


def extract_text_from_pdf(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return text
    except Exception as e:
        print("PDF Error:", e)
        return ""


def format_offline_cv(base_cv_text, job_title, company, required_skills, real_jd_text):
    skills_list = required_skills if isinstance(required_skills, list) else []
    if isinstance(required_skills, str) and required_skills:
        skills_list = [s.strip() for s in required_skills.split(",")]

    if real_jd_text and not skills_list:
        common_skills = [
            "python", "java", "c++", "c#", "aws", "docker", "kubernetes",
            "react", "angular", "node.js", "sql", "nosql", "agile", "flask",
            "django", "machine learning", "javascript", "typescript", "git",
            "ci/cd", "azure", "gcp",
        ]
        jd_lower = real_jd_text.lower()
        skills_list = [s for s in common_skills if s in jd_lower]

    skills_str = ", ".join(list(dict.fromkeys(skills_list))).title()

    lines = [line.strip() for line in base_cv_text.split("\n") if line.strip()]
    name = lines[0] if lines else "Candidate Profile"

    cv_text = f"{name}\n"
    cv_text += f"{job_title.upper()} | TARGETING: {company.upper()}\n"
    cv_text += "---\n"
    cv_text += "PROFESSIONAL SUMMARY\n"
    cv_text += (
        f"Results-driven professional with experience aligned to the {job_title} role at {company}. "
    )
    if skills_str:
        cv_text += f"Possess strong foundational expertise in core requirements including {skills_str}. "
    cv_text += (
        "Proven ability to leverage analytical and technical competencies to tackle complex "
        "problems and deliver high-quality solutions efficiently.\n\n"
    )

    if skills_str:
        cv_text += "TARGET SKILLS & COMPETENCIES\n"
        skill_tokens = [s.strip() for s in skills_str.split(",")]
        chunked = [", ".join(skill_tokens[i : i + 4]) for i in range(0, len(skill_tokens), 4)]
        for c in chunked:
            cv_text += f"- {c}\n"
        cv_text += "\n"

    cv_text += "EXPERIENCE & EDUCATION\n"
    for line in lines[1:]:
        if line.lower() in ["experience:", "education:"] or "=====" in line:
            cv_text += f"\n{line.upper()}\n"
        elif bool(re.match(r"^[-•*]", line)):
            cv_text += f"- {line[1:].strip()}\n"
        else:
            cv_text += f"{line}\n"

    return cv_text


def create_pdf(text, output_path):
    text = text.encode("latin-1", "replace").decode("latin-1")
    pdf = FPDF()
    pdf.add_page()
    pdf.set_margins(15, 15, 15)

    lines = text.split("\n")

    if lines:
        pdf.set_font("Helvetica", "B", 20)
        pdf.cell(0, 10, lines[0].strip(), ln=True, align="C")
        lines = lines[1:]

    for line in lines:
        line_str = line.strip()
        if not line_str:
            pdf.ln(3)
            continue

        if line_str == "---":
            pdf.line(15, pdf.get_y(), 195, pdf.get_y())
            pdf.ln(3)
            continue

        if line_str.isupper() and len(line_str) > 4 and "|" not in line_str:
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(0, 51, 102)
            pdf.cell(0, 6, line_str, ln=True)
            pdf.set_text_color(0, 0, 0)
            pdf.line(15, pdf.get_y(), 195, pdf.get_y())
            pdf.ln(2)
        elif "|" in line_str and "TARGETING" in line_str:
            pdf.set_font("Helvetica", "I", 11)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(0, 6, line_str, ln=True, align="C")
            pdf.set_text_color(0, 0, 0)
            pdf.ln(2)
        elif line_str.startswith("-") or line_str.startswith("•") or line_str.startswith("*"):
            pdf.set_font("Helvetica", "", 11)
            pdf.set_x(20)
            pdf.multi_cell(0, 5, chr(149) + " " + line_str[1:].strip())
            pdf.set_x(15)
        else:
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(0, 5, line_str)

    pdf.output(output_path)


def build_tailored_pdf(job_dict, base_pdf_path, output_pdf_path):
    if not os.path.exists(base_pdf_path):
        raise FileNotFoundError(f"Base CV not found at {base_pdf_path}")

    base_text = extract_text_from_pdf(base_pdf_path)

    title = job_dict.get("title", "Software Engineer")
    company = job_dict.get("company", "Unknown")
    url = job_dict.get("url", "")
    source = job_dict.get("source", "")
    skills = job_dict.get("skills", "")

    # Try to scrape real JD text to improve skill matching in the template
    real_jd = scrape_jd_text(url, source)

    tailored_text = format_offline_cv(base_text, title, company, skills, real_jd)
    create_pdf(tailored_text, output_pdf_path)
    return output_pdf_path


def extract_skills_from_cv(pdf_path):
    text = extract_text_from_pdf(pdf_path).lower()
    if not text.strip():
        print("Warning: CV text extraction returned empty string!")
        return ""

    KNOWN_SKILLS = [
        "python", "java", "c++", "c#", "javascript", "typescript", "golang", "ruby",
        "rust", "php", "swift", "kotlin", "perl", "scala", "bash", "shell",
        "powershell", "dart", "matlab",
        "react", "angular", "vue", "vue.js", "svelte", "node.js", "express",
        "django", "flask", "fastapi", "spring", "spring boot", "ruby on rails",
        "laravel", "next.js", "nuxt.js", "bootstrap", "tailwind", "jquery",
        "asp.net", "hibernate",
        "sql", "mysql", "postgresql", "mongodb", "oracle", "nosql", "firebase",
        "cassandra", "redis", "sqlite", "mariadb", "dynamodb", "couchbase",
        "elasticsearch", "neo4j", "supabase", "cockroachdb",
        "aws", "azure", "gcp", "google cloud", "docker", "kubernetes", "terraform",
        "jenkins", "ansible", "puppet", "chef", "vagrant", "circleci", "travis ci",
        "gitlab ci", "bitbucket ci", "helm", "cloudformation", "openshift",
        "serverless", "fargate",
        "linux", "windows", "macos", "git", "github", "gitlab", "bitbucket",
        "svn", "jira", "confluence",
        "ci/cd", "devops", "devsecops", "microservices", "rest api", "graphql",
        "grpc", "soap", "mvc", "tdd", "bdd", "oop",
        "machine learning", "deep learning", "nlp", "pytorch", "tensorflow", "keras",
        "scikit-learn", "pandas", "numpy", "matplotlib", "seaborn", "jupyter",
        "opencv", "computer vision", "llm", "generative ai", "openai", "chatgpt",
        "langchain", "huggingface",
        "hadoop", "spark", "kafka", "snowflake", "airflow", "databricks",
        "bigquery", "redshift", "hive", "flink", "dbt", "talend", "tableau",
        "power bi", "looker",
        "prometheus", "grafana", "servicenow", "splunk", "datadog", "new relic",
        "elk", "logstash", "kibana", "appdynamics", "dynatrace", "zabbix",
        "nagios", "pagerduty",
        "html", "css", "html5", "css3", "sass", "android", "ios", "react native",
        "flutter", "xamarin", "ionic",
        "nginx", "apache", "rabbitmq", "activemq", "maven", "gradle", "npm",
        "yarn", "webpack", "babel", "oauth", "jwt", "saml", "sso", "selenium",
        "cypress", "jest", "puppeteer", "mocha", "jasmine", "pytest", "junit",
    ]

    found_skills = []
    for skill in sorted(KNOWN_SKILLS, key=len, reverse=True):
        escaped = re.escape(skill)
        if re.search(r"(?<![a-z0-9])" + escaped + r"(?![a-z0-9])", text):
            if skill not in found_skills:
                found_skills.append(skill)

    print("Extracted Skills from CV:", found_skills)
    return ", ".join(found_skills)

def extract_role_from_cv(pdf_path):
    import re
    text = extract_text_from_pdf(pdf_path)
    if not text.strip():
        return ""
    
    # Common roles to look for
    KNOWN_ROLES = [
        "Software Engineer", "Backend Developer", "Frontend Developer", "Full Stack Developer",
        "Data Scientist", "Data Engineer", "Machine Learning Engineer", "DevOps Engineer",
        "Cloud Engineer", "System Administrator", "Database Administrator", "Site Reliability Engineer",
        "Python Developer", "Java Developer", "Web Developer", "UI/UX Developer",
        "Product Manager", "Project Manager", "Scrum Master", "Business Analyst"
    ]
    
    # Search the first early part of the resume heavily for roles
    cv_head = text[:600].lower()
    
    # Simple offline matching logic
    for role in KNOWN_ROLES:
        escaped_role = re.escape(role.lower())
        if re.search(r'(?<![a-z0-9])' + escaped_role + r'(?![a-z0-9])', cv_head):
            print(f"✅ Offline AI matched role: {role}")
            return role
            
    return ""
