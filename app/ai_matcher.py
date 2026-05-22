import os
import re
from cv_generator import extract_text_from_pdf

# Broad ATS keyword library used for keyword-density scoring
_ATS_KEYWORDS = [
    "python", "java", "c++", "c#", "javascript", "typescript", "golang", "ruby",
    "rust", "php", "swift", "kotlin", "scala", "bash", "shell", "dart", "matlab",
    "react", "angular", "vue", "node.js", "express", "django", "flask", "fastapi",
    "spring", "spring boot", "next.js", "bootstrap", "tailwind", "jquery", "asp.net",
    "sql", "mysql", "postgresql", "mongodb", "oracle", "nosql", "firebase", "cassandra",
    "redis", "sqlite", "dynamodb", "elasticsearch", "supabase",
    "aws", "azure", "gcp", "google cloud", "docker", "kubernetes", "terraform",
    "jenkins", "ansible", "helm", "openshift", "serverless", "fargate", "circleci",
    "linux", "git", "github", "gitlab", "jira", "confluence",
    "ci/cd", "devops", "microservices", "rest api", "graphql", "grpc", "soap",
    "mvc", "tdd", "bdd", "oop", "agile", "scrum", "kanban",
    "machine learning", "deep learning", "nlp", "pytorch", "tensorflow", "keras",
    "scikit-learn", "pandas", "numpy", "opencv", "llm", "generative ai", "openai",
    "langchain", "huggingface", "computer vision",
    "hadoop", "spark", "kafka", "snowflake", "airflow", "databricks", "bigquery",
    "tableau", "power bi", "looker", "dbt",
    "prometheus", "grafana", "splunk", "datadog", "elk",
    "html", "css", "html5", "css3", "sass", "android", "ios", "react native",
    "flutter", "selenium", "cypress", "jest", "pytest", "junit",
    "oauth", "jwt", "saml", "sso", "nginx", "apache", "rabbitmq", "kafka",
    "leadership", "communication", "problem solving", "teamwork", "project management",
]

# Stopwords to skip when pulling keywords from the job title
_TITLE_STOPWORDS = {
    "and", "or", "the", "with", "for", "of", "in", "at", "to", "a",
    "an", "is", "be", "on", "as", "its", "we", "are", "by", "from",
}


def _skill_in_text(skill: str, text: str) -> bool:
    """Word-boundary-aware skill search (case-insensitive)."""
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(skill) + r"(?![a-z0-9])", text))


def _score_skills(cv_lower: str, job_skills: list) -> dict:
    """Score how many of the job's explicit skill tags appear in the CV."""
    matched, missing = [], []
    for skill in set(job_skills):
        s = str(skill).strip().lower()
        if not s:
            continue
        if _skill_in_text(s, cv_lower):
            matched.append(s)
        else:
            missing.append(s)
    total = len(matched) + len(missing)
    score = int(len(matched) / total * 100) if total else 0
    return {"score": score, "matched": sorted(matched), "missing": sorted(missing)}


def _score_keywords(cv_lower: str, jd_text: str) -> dict:
    """Score how many ATS-relevant keywords from the JD appear in the CV."""
    jd_lower = jd_text.lower()
    jd_keywords = [kw for kw in _ATS_KEYWORDS if _skill_in_text(kw, jd_lower)]
    if not jd_keywords:
        # fall back: score CV coverage of the entire keyword library
        jd_keywords = _ATS_KEYWORDS

    matched, missing = [], []
    for kw in jd_keywords:
        if _skill_in_text(kw, cv_lower):
            matched.append(kw)
        else:
            missing.append(kw)

    total = len(matched) + len(missing)
    score = int(len(matched) / total * 100) if total else 0
    return {"score": score, "matched": sorted(matched), "missing": sorted(missing[:10])}


def _score_title(cv_lower: str, job_title: str) -> dict:
    """Score title / role alignment between CV headline and job title."""
    words = [
        w for w in re.findall(r"\b[a-z]+\b", job_title.lower())
        if w not in _TITLE_STOPWORDS and len(w) > 2
    ]
    if not words:
        return {"score": 50, "details": "No title words to compare."}

    found = [w for w in words if w in cv_lower]
    score = int(len(found) / len(words) * 100)
    return {
        "score": score,
        "details": f"{len(found)}/{len(words)} title keywords found in CV",
        "found": found,
        "missing": [w for w in words if w not in found],
    }


def _score_experience(cv_lower: str, job_dict: dict) -> dict:
    """Score how well the CV's experience years match the JD requirement."""
    exp_min = job_dict.get("experience_min")
    exp_max = job_dict.get("experience_max")

    # Try to pull years-of-experience from CV text
    cv_years_match = re.search(
        r"\b(\d{1,2})\s*\+?\s*(?:years?|yrs?)\s*(?:of\s*)?(?:experience|exp)\b",
        cv_lower,
        re.IGNORECASE,
    )
    cv_years = int(cv_years_match.group(1)) if cv_years_match else None

    if exp_min is None and exp_max is None:
        return {"score": 70, "details": "JD does not specify experience requirement."}

    required = f"{exp_min}–{exp_max} yrs" if exp_min != exp_max else f"{exp_min} yrs"

    if cv_years is None:
        return {
            "score": 50,
            "details": f"JD requires {required}; CV does not explicitly state experience years.",
        }

    lo = exp_min if exp_min is not None else exp_max
    hi = exp_max if exp_max is not None else exp_min
    if lo <= cv_years <= hi:
        score = 100
    elif cv_years > hi:
        # Over-experienced — still a reasonable match
        score = 80
    else:
        # Under-experienced
        gap = lo - cv_years
        score = max(0, 60 - gap * 15)

    return {
        "score": score,
        "details": f"JD requires {required}; CV indicates ~{cv_years} yrs experience.",
        "cv_years": cv_years,
    }


def generate_ats_scorecard(cv_path: str, job_dict: dict, jd_text: str = "") -> dict:
    """
    Return a structured ATS scorecard dict with per-category scores,
    an overall weighted score, and actionable recommendations.
    """
    if not os.path.exists(cv_path):
        return {"error": "No CV found. Please upload a resume first."}

    cv_text = extract_text_from_pdf(cv_path)
    if not cv_text.strip():
        return {"error": "CV appears to be empty or unreadable."}

    cv_lower = cv_text.lower()

    job_skills = job_dict.get("skills", [])
    job_title = job_dict.get("title", "Unknown Title")

    # Use job title words as fallback skills when no explicit tags exist
    if not job_skills:
        words = re.findall(r"\b\w+\b", job_title.lower())
        job_skills = [w for w in words if len(w) > 3 and w not in _TITLE_STOPWORDS]

    # Build a JD corpus: use provided jd_text, else combine available fields
    if not jd_text:
        jd_text = " ".join(filter(None, [
            job_title,
            " ".join(job_skills),
            job_dict.get("description", ""),
            job_dict.get("snippet", ""),
        ]))

    skills_result = _score_skills(cv_lower, job_skills)
    keywords_result = _score_keywords(cv_lower, jd_text)
    title_result = _score_title(cv_lower, job_title)
    experience_result = _score_experience(cv_lower, job_dict)

    # Weighted overall score: skills 35%, keywords 30%, title 20%, experience 15%
    overall = int(
        skills_result["score"] * 0.35
        + keywords_result["score"] * 0.30
        + title_result["score"] * 0.20
        + experience_result["score"] * 0.15
    )

    # Recommendations: suggest adding the top missing items
    recommendations = []
    for sk in skills_result["missing"][:4]:
        recommendations.append(f"Add '{sk}' to your skills section if you have experience with it.")
    for kw in keywords_result["missing"][:3]:
        if kw not in skills_result["missing"]:
            recommendations.append(f"Mention '{kw}' in your professional summary or experience bullets.")
    if title_result["score"] < 60:
        missing_title = title_result.get("missing", [])[:2]
        if missing_title:
            recommendations.append(
                f"Include '{', '.join(missing_title)}' in your headline or summary to match the role title."
            )
    if experience_result["score"] < 70 and experience_result.get("cv_years") is not None:
        recommendations.append(experience_result["details"])

    # Determine match strength label
    if overall >= 75:
        strength = "Strong Match"
    elif overall >= 55:
        strength = "Moderate Match"
    else:
        strength = "Weak Match"

    return {
        "overall_score": overall,
        "strength": strength,
        "job_title": job_title,
        "categories": {
            "skills_match": skills_result,
            "keyword_density": keywords_result,
            "title_alignment": title_result,
            "experience_fit": experience_result,
        },
        "recommendations": recommendations,
    }


def generate_ai_match_report(cv_path: str, job_dict: dict, jd_text: str = "") -> str:
    """
    Backward-compatible wrapper: returns a human-readable text report.
    The full structured scorecard is available via generate_ats_scorecard().
    """
    sc = generate_ats_scorecard(cv_path, job_dict, jd_text)
    if "error" in sc:
        return sc["error"]

    overall = sc["overall_score"]
    job_title = sc["job_title"]
    cats = sc["categories"]

    report = f"**ATS Recruiter AI Analysis — {sc['strength']}**\n\n"
    report += f"CV evaluated against: **{job_title}**\n"
    report += f"Overall ATS Score: **{overall}%**\n\n"

    report += "**Score Breakdown:**\n"
    report += f"- Skills Match: {cats['skills_match']['score']}%\n"
    report += f"- Keyword Density: {cats['keyword_density']['score']}%\n"
    report += f"- Title Alignment: {cats['title_alignment']['score']}%\n"
    report += f"- Experience Fit: {cats['experience_fit']['score']}%\n\n"

    matched = cats["skills_match"]["matched"]
    missing = cats["skills_match"]["missing"]
    if matched:
        report += f"✔ Found skills: {', '.join(matched[:6])}\n"
    if missing:
        report += f"✖ Missing skills: {', '.join(missing[:6])}\n\n"

    if sc["recommendations"]:
        report += "**Recommendations:**\n"
        for r in sc["recommendations"][:5]:
            report += f"• {r}\n"

    return report
