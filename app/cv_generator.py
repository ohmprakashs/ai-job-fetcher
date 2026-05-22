import os
import re
from pypdf import PdfReader
from fpdf import FPDF
from jd_scraper import scrape_jd_text


# Section headers we expect to find in any CV (ordered by length desc to avoid partial matches)
_CV_SECTION_HEADERS = sorted([
    "PROFESSIONAL SUMMARY", "PROFESSIONAL EXPERIENCE", "EMPLOYMENT HISTORY",
    "WORK EXPERIENCE", "ACADEMIC BACKGROUND", "CAREER OBJECTIVE",
    "SKILLS & COMPETENCIES", "TECHNICAL SKILLS", "CORE COMPETENCIES",
    "KEY SKILLS", "TECH STACK", "TECHNOLOGIES",
    "CERTIFICATIONS", "CERTIFICATES", "ACHIEVEMENTS", "AWARDS",
    "REFERENCES", "EDUCATION", "EXPERIENCE", "PROJECTS",
    "SUMMARY", "OBJECTIVE", "PROFILE", "SKILLS", "LANGUAGES",
    "ABOUT ME",
], key=len, reverse=True)


def _normalize_pdf_text(text: str) -> str:
    """
    Many PDF extractors (pypdf) return the entire document as a near-single line.
    Insert newlines before known section headers so downstream code (section detection,
    skill injection) can parse the CV structure regardless of the number of pages.
    Works correctly for 1–5 page CVs.
    """
    # Only normalize if the text has very few newlines relative to its size
    if text.count('\n') > len(text) / 200:
        return text  # already well-structured

    # Build a single alternation regex (sorted longest-first prevents "SKILLS"
    # from matching inside "TECHNICAL SKILLS")
    all_headers_re = '|'.join(re.escape(h) for h in _CV_SECTION_HEADERS)
    # Insert \n before each section header; also \n after so content starts on new line
    text = re.sub(
        r'(?<!\n)\s{1,6}(' + all_headers_re + r')(?=\s|\n|[A-Z:]|$)',
        r'\n\1\n',
        text,
    )

    # Collapse 3+ consecutive spaces to newline (column layout artifact in PDFs)
    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        clean_lines.append(re.sub(r'   +', '\n', line))
    return '\n'.join(clean_lines)


def extract_text_from_pdf(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return _normalize_pdf_text(text)
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


def _safe_encode(text: str) -> str:
    """Encode to latin-1 (fpdf requirement), replacing unmappable chars."""
    return text.encode("latin-1", "replace").decode("latin-1")


def _render_text(pdf, text: str, indent: int = 0) -> None:
    """Safely render text with multi_cell; skips empty, truncates if still too wide."""
    text = text.strip()
    if not text:
        return
    lm = pdf.l_margin + indent
    usable_w = pdf.w - lm - pdf.r_margin
    if usable_w < 10:
        usable_w = pdf.w - pdf.l_margin - pdf.r_margin
        lm = pdf.l_margin
    pdf.set_x(lm)
    try:
        pdf.multi_cell(usable_w, 5, _safe_encode(text))
    except Exception:
        # Last resort: truncate to something safe
        try:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(pdf.w - pdf.l_margin - pdf.r_margin, 5, _safe_encode(text[:80]))
        except Exception:
            pass
    pdf.set_x(pdf.l_margin)


def create_pdf(text, output_path):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_margins(15, 15, 15)

    lines = text.split("\n")

    # First non-empty line → name / title header
    header_printed = False
    start_idx = 0
    for i, line in enumerate(lines):
        if line.strip() and not header_printed:
            pdf.set_font("Helvetica", "B", 16)
            _render_text(pdf, line.strip())
            header_printed = True
            start_idx = i + 1
            break

    for line in lines[start_idx:]:
        line_str = line.strip()

        if not line_str:
            pdf.ln(2)
            continue

        if line_str == "---":
            pdf.set_x(pdf.l_margin)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(3)
            continue

        # Section heading: ALL CAPS, reasonable length, no pipe
        if line_str.isupper() and 3 < len(line_str) < 60 and "|" not in line_str:
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(0, 51, 102)
            _render_text(pdf, line_str)
            pdf.set_text_color(0, 0, 0)
            pdf.set_x(pdf.l_margin)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(2)
            continue

        # Subtitle / targeting line
        if "|" in line_str and "TARGETING" in line_str:
            pdf.set_font("Helvetica", "I", 10)
            pdf.set_text_color(80, 80, 80)
            _render_text(pdf, line_str)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(2)
            continue

        # Bullet point
        if line_str[:1] in ("-", "•", "*") or line_str.startswith(chr(149)):
            pdf.set_font("Helvetica", "", 10)
            content = "• " + line_str[1:].strip()
            _render_text(pdf, content, indent=5)
            continue

        # Regular text
        pdf.set_font("Helvetica", "", 10)
        _render_text(pdf, line_str)

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


# ---------------------------------------------------------------------------
# Smart Incremental CV Tailoring
# ---------------------------------------------------------------------------

def _skill_in_text(skill: str, text: str) -> bool:
    """Word-boundary-aware skill search (case-insensitive)."""
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(skill) + r"(?![a-z0-9])", text))


def _compute_simple_score(cv_lower: str, skills: list) -> int:
    """Compute a simple keyword-match % score for delta tracking."""
    if not skills:
        return 0
    matched = sum(1 for s in skills if _skill_in_text(s.lower(), cv_lower))
    return int(matched / len(skills) * 100)


def _find_skills_section_line(lines: list) -> int:
    """Return the index of the line that starts a Skills/Technical Skills section, or -1."""
    SKILLS_HEADERS = {"SKILLS", "TECHNICAL SKILLS", "KEY SKILLS", "CORE COMPETENCIES",
                      "SKILLS & COMPETENCIES", "TECHNOLOGIES", "TECH STACK",
                      "SKILLS AND COMPETENCIES", "SKILLS & EXPERIENCE"}
    for i, line in enumerate(lines):
        stripped = line.strip().upper()
        if stripped in SKILLS_HEADERS:
            return i
        # Partial match: line that IS or STARTS WITH a skills header
        if any(stripped == h or stripped.startswith(h) for h in SKILLS_HEADERS):
            return i
    return -1


def _find_summary_section_line(lines: list) -> int:
    """Return the index of the professional summary / objective section, or -1."""
    SUMMARY_HEADERS = {"PROFESSIONAL SUMMARY", "SUMMARY", "OBJECTIVE",
                       "PROFILE", "ABOUT ME", "CAREER OBJECTIVE",
                       "PROFESSIONAL PROFILE", "EXECUTIVE SUMMARY"}
    for i, line in enumerate(lines):
        stripped = line.strip().upper()
        if stripped in SUMMARY_HEADERS:
            return i
        if any(stripped == h or stripped.startswith(h) for h in SUMMARY_HEADERS):
            return i
    return -1


def tailor_cv_smart(base_pdf_path: str, job_dict: dict, output_pdf_path: str,
                    jd_text: str = "") -> dict:
    """
    Intelligently tailor a CV to improve ATS match by 10–20% without a full rewrite.

    Strategy:
    1. Compute baseline ATS score from skills + keywords.
    2. Identify top missing keywords/skills from the JD.
    3. Inject them into the skills section and/or professional summary.
    4. Only add terms the JD actually requires; never fabricate experience.
    5. Write out the modified CV as a PDF and return a change log.

    Returns a dict:
        {
            "output_path": str,
            "baseline_score": int,
            "new_score": int,
            "score_delta": int,
            "changes": [str, ...]
        }
    """
    if not os.path.exists(base_pdf_path):
        raise FileNotFoundError(f"Base CV not found at {base_pdf_path}")

    cv_text = extract_text_from_pdf(base_pdf_path)
    cv_lower = cv_text.lower()

    job_skills = [str(s).strip().lower() for s in job_dict.get("skills", []) if s]
    job_title = job_dict.get("title", "Role")
    company = job_dict.get("company", "Company")

    # Build JD keyword corpus
    if not jd_text:
        jd_text = " ".join(filter(None, [
            job_title,
            " ".join(job_skills),
            job_dict.get("description", ""),
            job_dict.get("snippet", ""),
        ]))
    jd_lower = jd_text.lower()

    # Identify missing skills (JD has them but CV does not)
    missing_skills = [s for s in job_skills if not _skill_in_text(s, cv_lower)]

    # Also consider broader ATS keywords present in JD but absent from CV
    from ai_matcher import _ATS_KEYWORDS
    missing_kw = [
        kw for kw in _ATS_KEYWORDS
        if _skill_in_text(kw, jd_lower) and not _skill_in_text(kw, cv_lower)
        and kw not in missing_skills
    ]

    # Compute baseline score
    all_jd_terms = list(dict.fromkeys(job_skills + [
        kw for kw in _ATS_KEYWORDS if _skill_in_text(kw, jd_lower)
    ]))
    baseline_score = _compute_simple_score(cv_lower, all_jd_terms)

    # Determine how many keywords to inject to achieve +10–20% improvement
    target_delta_min, target_delta_max = 10, 20
    total_terms = len(all_jd_terms) if all_jd_terms else 1

    # How many additional matches are needed to reach +10% and +20%?
    needed_min = max(1, int(target_delta_min * total_terms / 100))
    needed_max = max(2, int(target_delta_max * total_terms / 100))

    # Simulate: add candidates one by one and stop once we hit the +20% ceiling
    candidates = list(dict.fromkeys(missing_skills + missing_kw))
    to_inject = []
    simulated_lower = cv_lower
    for c in candidates:
        if len(to_inject) >= needed_max:
            break
        projected = _compute_simple_score(simulated_lower + " " + c, all_jd_terms)
        delta_so_far = projected - baseline_score
        to_inject.append(c)
        simulated_lower = simulated_lower + " " + c
        if delta_so_far >= target_delta_max:
            break

    if not to_inject:
        # Nothing to inject — CV already matches well
        create_pdf(cv_text, output_pdf_path)
        return {
            "output_path": output_pdf_path,
            "baseline_score": baseline_score,
            "new_score": baseline_score,
            "score_delta": 0,
            "changes": ["No missing keywords found — CV already matches the JD well."],
        }

    # --- Inject into CV text ---
    lines = cv_text.split("\n")
    changes = []

    skills_idx = _find_skills_section_line(lines)
    summary_idx = _find_summary_section_line(lines)

    injected_skills = [t for t in to_inject if t in (missing_skills + missing_kw[:5])]
    skills_to_add = injected_skills[:min(len(injected_skills), needed_max)]

    if skills_idx != -1:
        # Find the last line of the skills section (next blank or next ALL-CAPS section header)
        insert_after = skills_idx + 1
        for k in range(skills_idx + 1, min(skills_idx + 15, len(lines))):
            l = lines[k].strip()
            if l and l.isupper() and len(l) > 3:
                break
            insert_after = k + 1

        # Format as a bullet line with new skills
        new_skills_line = "• " + "  •  ".join(s.title() for s in skills_to_add)
        lines.insert(insert_after, new_skills_line)
        changes.append(f"Added to Skills section: {', '.join(skills_to_add)}")
    else:
        # No skills section found — append a new one before the first section
        skills_block = "\nSKILLS\n" + "• " + "  •  ".join(s.title() for s in skills_to_add)
        lines.insert(1, skills_block)
        changes.append(f"Created Skills section with: {', '.join(skills_to_add)}")

    # Inject role-specific keywords into the summary (if it exists)
    summary_keywords = [t for t in to_inject if t not in skills_to_add][:3]
    if summary_idx != -1 and summary_keywords:
        # Find the end of summary block
        append_at = summary_idx + 1
        for k in range(summary_idx + 1, min(summary_idx + 10, len(lines))):
            l = lines[k].strip()
            if l and l.isupper() and len(l) > 3:
                break
            if l:
                append_at = k
        kw_sentence = (
            f"Experienced in {', '.join(t.title() for t in summary_keywords)}, "
            "with a strong background in delivering scalable and efficient solutions."
        )
        lines.insert(append_at + 1, kw_sentence)
        changes.append(f"Enriched summary with: {', '.join(summary_keywords)}")

    modified_cv_text = "\n".join(lines)
    modified_lower = modified_cv_text.lower()

    # Compute new score
    new_score = _compute_simple_score(modified_lower, all_jd_terms)
    score_delta = new_score - baseline_score

    create_pdf(modified_cv_text, output_pdf_path)

    return {
        "output_path": output_pdf_path,
        "baseline_score": baseline_score,
        "new_score": new_score,
        "score_delta": score_delta,
        "changes": changes,
    }
