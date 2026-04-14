"""
agent.py — Resume parsing and job search logic.

Uses the existing matcher.py for skill extraction and scoring,
and job_fetcher.py for Adzuna API / CSV fallback.
"""

import json
import logging
import re

from config import (
    GROQ_API_KEY,
    GROQ_MODEL,
    JOB_ROLE_QUERY,
    MINIMUM_SCORE,
    SKILL_KEYWORDS,
    TOP_JOBS_TO_RETURN,
)
from job_fetcher import fetch_adzuna_jobs
from matcher import (
    extract_resume_experience_years,
    extract_skills,
    rank_jobs,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Resume Parsing
# ---------------------------------------------------------------------------

def _extract_role_from_text(text: str) -> str:
    """Try to guess the user's current/target role from their resume."""
    # Look for common role patterns like "AI Engineer", "Data Scientist", etc.
    role_patterns = [
        r"(?:position|role|title|designation)[:\s]*([^\n,]+)",
        r"(?:^|\n)\s*([\w\s&/]+(?:engineer|developer|scientist|analyst|architect|manager|lead|intern))\b",
    ]
    lower = text.lower()
    for pattern in role_patterns:
        match = re.search(pattern, lower, re.IGNORECASE)
        if match:
            role = match.group(1).strip().title()
            if 3 < len(role) < 60:
                return role

    # Fallback: check for common ML/AI role keywords
    role_keywords = {
        "machine learning engineer": "Machine Learning Engineer",
        "ai engineer": "AI Engineer",
        "data scientist": "Data Scientist",
        "data engineer": "Data Engineer",
        "software engineer": "Software Engineer",
        "ml engineer": "ML Engineer",
        "computer vision engineer": "Computer Vision Engineer",
        "nlp engineer": "NLP Engineer",
        "deep learning engineer": "Deep Learning Engineer",
        "full stack developer": "Full Stack Developer",
        "backend developer": "Backend Developer",
        "python developer": "Python Developer",
    }
    for keyword, role_name in role_keywords.items():
        if keyword in lower:
            return role_name

    return "AI/ML Professional"


def _extract_location_from_text(text: str) -> str:
    """Try to extract location from the resume text."""
    location_patterns = [
        r"(?:location|city|based in|residing in|address)[:\s]*([^\n,]+)",
        r"(?:^|\n)\s*(?:location)[:\s]*([^\n]+)",
    ]
    for pattern in location_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            loc = match.group(1).strip()
            if 2 < len(loc) < 50:
                return loc
    return ""


def _parse_resume_with_llm(resume_text: str) -> dict | None:
    """Use Groq LLM for smarter resume parsing (optional)."""
    if not GROQ_API_KEY:
        return None

    try:
        from groq import Groq
    except ImportError:
        logger.warning("groq library not installed. Using rule-based parsing.")
        return None

    try:
        client = Groq(api_key=GROQ_API_KEY)
        # Send up to 8000 chars to the LLM for thorough parsing of long resumes
        resume_chunk = resume_text[:8000]
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a resume parsing assistant. Extract structured information "
                        "from the resume and return ONLY valid JSON with these keys: "
                        '"skills" (list of ALL technical skills found), "role" (string — primary job role), '
                        '"experience_years" (number), "location" (string). '
                        "Be thorough — extract every skill, framework, tool, and technology mentioned."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Parse this resume and extract structured data:\n\n{resume_chunk}",
                },
            ],
            temperature=0.0,
            max_tokens=1000,
        )
        raw = response.choices[0].message.content.strip()

        # Try to extract JSON from the response
        if "{" in raw and "}" in raw:
            json_str = raw[raw.find("{"):raw.rfind("}") + 1]
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                logger.info("LLM resume parsing successful")
                return {
                    "skills": parsed.get("skills", []),
                    "role": parsed.get("role", ""),
                    "experience_years": float(parsed.get("experience_years", 0)),
                    "location": parsed.get("location", ""),
                }
    except Exception as e:
        logger.error("LLM resume parsing failed: %s", e)

    return None


def parse_resume(resume_text: str) -> dict:
    """
    Extract structured data from raw resume text.

    Returns a dict with:
      - skills (list of str)
      - role (str)
      - experience_years (float)
      - location (str)

    Tries LLM parsing first (if Groq is configured), falls back to
    rule-based extraction using matcher.py functions.
    """
    # Try LLM-powered parsing first
    llm_result = _parse_resume_with_llm(resume_text)
    if llm_result and llm_result.get("skills"):
        logger.info("Using LLM-parsed resume data")
        return llm_result

    # Fall back to rule-based extraction
    logger.info("Using rule-based resume parsing")
    skills = extract_skills(resume_text)
    experience_years = extract_resume_experience_years(resume_text)
    role = _extract_role_from_text(resume_text)
    location = _extract_location_from_text(resume_text)

    parsed = {
        "skills": skills,
        "role": role,
        "experience_years": experience_years,
        "location": location,
    }
    logger.info(
        "Parsed resume: role=%s, experience=%.1f yrs, %d skills, location=%s",
        role, experience_years, len(skills), location or "N/A",
    )
    return parsed


# ---------------------------------------------------------------------------
#  Job Search
# ---------------------------------------------------------------------------

def search_jobs(parsed_data: dict, resume_text: str = "") -> list:
    """
    Search for relevant jobs based on the user's parsed resume data.

    Uses the role from parsed_data as the search query, fetches jobs from
    Adzuna (or CSV fallback), then ranks them using matcher.rank_jobs().

    Returns a list of matched job dicts, sorted by best fit.
    """
    role = parsed_data.get("role", JOB_ROLE_QUERY)
    skills = parsed_data.get("skills", [])

    # Build a search query from role + top skills
    query_parts = [role]
    if skills:
        query_parts.extend(skills[:3])  # Add top 3 skills to narrow results
    search_query = " ".join(query_parts)

    logger.info("Searching jobs with query: '%s'", search_query)

    # Fetch jobs from Adzuna API (or CSV fallback)
    jobs = fetch_adzuna_jobs(what=search_query)
    if not jobs:
        logger.warning("No jobs fetched from Adzuna or fallback CSV")
        return []

    logger.info("Fetched %d raw jobs, now ranking...", len(jobs))

    # Build a synthetic resume text from parsed_data if none provided
    if not resume_text:
        resume_text = _build_resume_from_parsed(parsed_data)

    # Rank and filter jobs using matcher.py
    matched_jobs = rank_jobs(
        jobs=jobs,
        resume_text=resume_text,
        skill_keywords=SKILL_KEYWORDS,
        min_score=MINIMUM_SCORE,
    )

    logger.info("Ranked %d jobs above threshold", len(matched_jobs))
    return matched_jobs[:TOP_JOBS_TO_RETURN]


def _build_resume_from_parsed(parsed_data: dict) -> str:
    """Build a rough resume-like string from parsed data for scoring."""
    parts = []
    if parsed_data.get("role"):
        parts.append(f"Role: {parsed_data['role']}")
    if parsed_data.get("experience_years"):
        parts.append(f"Experience: {parsed_data['experience_years']} years")
    if parsed_data.get("skills"):
        parts.append(f"Skills: {', '.join(parsed_data['skills'])}")
    if parsed_data.get("location"):
        parts.append(f"Location: {parsed_data['location']}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
#  Format results for WhatsApp
# ---------------------------------------------------------------------------

def format_job_summary(jobs: list) -> str:
    """Format a short summary of all matched jobs (sent as the first message)."""
    if not jobs:
        return (
            "😔 *No matching jobs found right now.*\n\n"
            "Try updating your resume with more details, "
            "or check back later for new postings!"
        )

    lines = [f"🎯 *Found {len(jobs)} matching jobs for you!*\n"]
    for i, job in enumerate(jobs, 1):
        title = job.get("title", "Unknown Role")
        company = job.get("company", "Unknown Company")
        score = job.get("hiring_score", 0)
        lines.append(f"  {i}. *{title}* — {company} (⭐ {score}/100)")

    lines.append("")
    lines.append("📩 _Sending detailed cards with draft emails for each job below..._")
    return "\n".join(lines)


def _truncate_description(description: str, max_length: int = 500) -> str:
    """Truncate a job description to fit in WhatsApp, breaking at a sentence."""
    if not description:
        return "_No description available._"
    if len(description) <= max_length:
        return description

    # Try to cut at a sentence boundary
    truncated = description[:max_length]
    last_period = truncated.rfind(".")
    if last_period > max_length // 2:
        truncated = truncated[:last_period + 1]
    else:
        truncated = truncated.rstrip() + "..."

    return truncated


def generate_draft_email(job: dict, user_name: str, parsed_data: dict) -> str:
    """
    Generate a personalized draft application email for a specific job.

    Uses the user's stored name, role, skills, and experience to create
    a ready-to-send email body. Tries LLM first, falls back to template.
    """
    title = job.get("title", "the role")
    company = job.get("company", "your company")
    role = parsed_data.get("role", "AI/ML Professional")
    experience = parsed_data.get("experience_years", 0)
    skills = parsed_data.get("skills", [])
    matched_skills = job.get("matched_skills", "")
    location = parsed_data.get("location", "")

    # Pick the most relevant skills (matched > general)
    if matched_skills:
        highlight_skills = matched_skills
    elif skills:
        highlight_skills = ", ".join(skills[:6])
    else:
        highlight_skills = "AI and machine learning"

    # --- Try LLM-generated email ---
    if GROQ_API_KEY:
        try:
            from groq import Groq
            client = Groq(api_key=GROQ_API_KEY)
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a professional job application email writer. "
                            "Write a concise, compelling application email (under 250 words). "
                            "Use the candidate's details to personalize it. "
                            "Do NOT include a subject line — just the email body. "
                            "Start with 'Dear Hiring Manager,' and end with the candidate's name."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Write an application email for:\n"
                            f"Job Title: {title}\n"
                            f"Company: {company}\n"
                            f"Candidate Name: {user_name}\n"
                            f"Current Role: {role}\n"
                            f"Experience: {experience} years\n"
                            f"Key Skills: {highlight_skills}\n"
                            f"Location: {location or 'Not specified'}"
                        ),
                    },
                ],
                temperature=0.3,
                max_tokens=400,
            )
            email_body = response.choices[0].message.content.strip()
            if email_body and len(email_body) > 50:
                logger.info("LLM draft email generated for %s at %s", title, company)
                return email_body
        except Exception as e:
            logger.warning("LLM email generation failed, using template: %s", e)

    # --- Fallback: template-based email ---
    email = (
        f"Dear Hiring Manager,\n\n"
        f"I am writing to express my strong interest in the *{title}* position at *{company}*.\n\n"
        f"As a {role} with {experience} year(s) of experience, I bring hands-on expertise in "
        f"{highlight_skills}. My background includes building production-ready solutions "
        f"and delivering measurable results in these areas.\n\n"
        f"I am confident that my skills and passion for innovation make me a strong fit "
        f"for this role. I would welcome the opportunity to discuss how my experience "
        f"aligns with your team's goals.\n\n"
        f"Thank you for your time and consideration.\n\n"
        f"Best regards,\n"
        f"{user_name}"
    )
    if location:
        email = email.replace(
            "Thank you for your time",
            f"I am based in {location} and open to relocation if needed.\n\nThank you for your time",
        )

    return email


def format_single_job_card(job: dict, index: int, total: int,
                           user_name: str, parsed_data: dict) -> str:
    """
    Format a single job with full details + draft email for WhatsApp.

    Each job is sent as an individual message containing:
    - Job details (title, company, location, score, skills)
    - Truncated job description
    - Ready-to-use draft application email
    """
    title = job.get("title", "Unknown Role")
    company = job.get("company", "Unknown Company")
    location = job.get("location", "Not specified")
    score = job.get("hiring_score", 0)
    url = job.get("url", "")
    description = job.get("description", "")
    matched = job.get("matched_skills", "")

    lines = [
        f"━━━━━━━━━━━━━━━",
        f"📋 *Job {index}/{total}*",
        f"",
        f"*{title}*",
        f"🏢 {company}",
        f"📍 {location}",
        f"⭐ Match: {score}/100",
    ]

    if matched:
        lines.append(f"🔧 Matched Skills: {matched}")

    if url:
        lines.append(f"🔗 Apply: {url}")

    # Job description
    lines.append("")
    lines.append("📝 *Job Description:*")
    lines.append(_truncate_description(description))

    # Draft application email
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append("✉️ *Draft Application Email:*")
    lines.append("")
    lines.append(f"*Subject:* Application for {title} — {user_name}")
    lines.append("")

    draft_email = generate_draft_email(job, user_name, parsed_data)
    lines.append(draft_email)

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━")

    return "\n".join(lines)


def format_profile(user: dict) -> str:
    """Format user profile (parsed resume data) for WhatsApp display."""
    parsed = user.get("parsed_data", {})
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except json.JSONDecodeError:
            parsed = {}

    name = user.get("name", "Unknown")
    skills = parsed.get("skills", [])
    role = parsed.get("role", "Not detected")
    exp = parsed.get("experience_years", 0)
    location = parsed.get("location", "Not specified")

    lines = [
        f"👤 *Your Profile*",
        f"",
        f"📛 *Name:* {name}",
        f"💼 *Role:* {role}",
        f"📅 *Experience:* {exp} years",
        f"📍 *Location:* {location or 'Not specified'}",
        f"",
        f"🛠️ *Skills ({len(skills)}):*",
    ]

    if skills:
        # Show skills in a compact format
        skill_text = ", ".join(skills[:15])
        if len(skills) > 15:
            skill_text += f" (+{len(skills) - 15} more)"
        lines.append(skill_text)
    else:
        lines.append("_No skills detected yet_")

    lines.append("")
    lines.append("💡 _Send /update to refresh your resume, or 'search job for me' to find jobs._")

    return "\n".join(lines)
