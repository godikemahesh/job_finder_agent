import logging
import re

from config import SKILL_KEYWORDS

try:
    from sentence_transformers import SentenceTransformer, util
except ImportError:
    SentenceTransformer = None
    util = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

_MODEL = None
_MODEL_LOAD_ATTEMPTED = False

KEYWORD_COMPONENT_WEIGHT = 0.18
SEMANTIC_COMPONENT_WEIGHT = 0.18
EXPERIENCE_WEIGHT = 0.24
MUST_HAVE_WEIGHT = 0.20
TITLE_WEIGHT = 0.12
SENIORITY_WEIGHT = 0.08

GENERIC_TITLE_TOKENS = {
    "ai",
    "ml",
    "genai",
    "engineer",
    "developer",
    "scientist",
    "specialist",
    "consultant",
    "architect",
    "analyst",
    "associate",
}

SENIORITY_PATTERNS = {
    "entry": 1,
    "intern": 1,
    "junior": 1,
    "associate": 2,
    "mid": 2,
    "senior": 3,
    "lead": 4,
    "staff": 4,
    "principal": 5,
    "architect": 5,
    "manager": 5,
    "director": 6,
}

SKILL_ALIASES = {
    "python": ["python"],
    "machine learning": ["machine learning", "ml"],
    "deep learning": ["deep learning"],
    "nlp": ["nlp", "natural language processing"],
    "computer vision": ["computer vision", "vision"],
    "data science": ["data science", "data scientist"],
    "pytorch": ["pytorch"],
    "tensorflow": ["tensorflow"],
    "transformers": ["transformers", "huggingface", "hugging face"],
    "sql": ["sql"],
    "cloud": ["cloud", "cloud platform", "cloud platforms"],
    "aws": ["aws", "amazon web services"],
    "azure": ["azure"],
    "gcp": ["gcp", "google cloud"],
    "model deployment": ["model deployment", "deploying models", "production-ready", "production ready"],
    "recommendation": ["recommendation", "recommender"],
    "ai": ["ai", "artificial intelligence"],
    "ml": ["ml", "machine learning"],
    "llm": ["llm", "llms", "large language model", "large language models", "genai", "gen ai"],
    "data engineering": ["data engineering", "data pipeline", "data pipelines", "etl"],
    "rag": ["rag", "retrieval augmented generation", "retrieval-augmented generation"],
    "agentic ai": ["agentic ai", "agents", "agent based", "agent-based"],
    "langchain": ["langchain"],
    "langgraph": ["langgraph"],
    "prompt engineering": ["prompt engineering"],
    "vector database": ["vector database", "vector databases", "vector store", "vector stores"],
    "tool calling": ["tool calling", "function calling"],
    "evaluation": ["evaluation", "retrieval evaluation", "precision", "recall", "mrr", "ndcg"],
    "openai": ["openai"],
    "anthropic": ["anthropic"],
    "gemini": ["gemini"],
    "groq": ["groq"],
    "mistral": ["mistral"],
    "mlops": ["mlops"],
    "llmops": ["llmops"],
    "cicd": ["ci/cd", "cicd"],
    "fastapi": ["fastapi", "fast api"],
    "api integration": ["api integration", "apis", "api"],
    "opencv": ["opencv"],
    "yolo": ["yolo"],
    "segmentation": ["segmentation", "segformer", "deeplabv3", "unet"],
    "tracking": ["tracking", "re-identification", "re identification", "reid"],
    "streamlit": ["streamlit"],
    "git": ["git", "github"],
    "docker": ["docker"],
    "kubernetes": ["kubernetes", "k8s"],
}

ALL_SKILLS = list(dict.fromkeys(list(SKILL_ALIASES.keys())))


def _get_model(model_name: str = "all-MiniLM-L6-v2"):
    global _MODEL, _MODEL_LOAD_ATTEMPTED
    if _MODEL is not None:
        return _MODEL
    if _MODEL_LOAD_ATTEMPTED:
        return None

    _MODEL_LOAD_ATTEMPTED = True
    if SentenceTransformer is None:
        logging.warning("sentence-transformers is not installed. Falling back to lexical overlap scoring.")
        return None

    try:
        logging.info("Loading sentence-transformers model: %s", model_name)
        _MODEL = SentenceTransformer(model_name)
    except Exception as error:
        logging.warning("Could not load sentence-transformers model. Falling back to lexical overlap scoring: %s", error)
        _MODEL = None
    return _MODEL


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def tokenize_text(text: str) -> set:
    normalized = normalize_text(text)
    return set(re.findall(r"[a-z0-9][a-z0-9+#./-]*", normalized))


def _contains_pattern(text: str, pattern: str) -> bool:
    pattern = normalize_text(pattern)
    if not pattern:
        return False

    if re.fullmatch(r"[a-z0-9+#./-]+", pattern) and len(pattern) <= 3:
        return re.search(rf"(?<![a-z0-9]){re.escape(pattern)}(?![a-z0-9])", text) is not None
    return pattern in text


def _dedupe_preserve_order(values: list) -> list:
    seen = set()
    ordered = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def extract_skills(text: str) -> list:
    normalized = normalize_text(text)
    found = []
    for skill in ALL_SKILLS:
        patterns = SKILL_ALIASES.get(skill, [skill])
        if any(_contains_pattern(normalized, pattern) for pattern in patterns):
            found.append(skill)
    return _dedupe_preserve_order(found)


def _extract_number(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def extract_resume_experience_years(resume_text: str) -> float:
    lower = (resume_text or "").lower()
    patterns = [
        r"(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)\s+of\s+(?:industry\s+)?experience",
        r"experience[^.\n]{0,50}?(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)",
        r"\|\s*(\d+(?:\.\d+)?)\s*(?:year|years|yr|yrs)\b",
    ]

    candidates = []
    for pattern in patterns:
        for match in re.finditer(pattern, lower):
            years = _extract_number(match.group(1))
            if 0 < years <= 40:
                candidates.append(years)

    return max(candidates) if candidates else 0.0


def extract_required_experience(job_text: str) -> tuple[float | None, float | None]:
    normalized = normalize_text(job_text)
    ranges = []
    singles = []

    range_patterns = [
        r"(?:experience|exp|minimum|at least|relevant experience)[^.\n:]{0,40}?(\d+(?:\.\d+)?)\s*(?:\+)?\s*(?:-|to|–|—)\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?)",
        r"(\d+(?:\.\d+)?)\s*(?:\+)?\s*(?:-|to|–|—)\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?)",
    ]
    single_patterns = [
        r"(?:experience|exp|minimum|at least|relevant experience)[^.\n:]{0,40}?(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)",
        r"(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:hands-on\s+)?experience",
    ]

    for pattern in range_patterns:
        for match in re.finditer(pattern, normalized):
            minimum = _extract_number(match.group(1))
            maximum = _extract_number(match.group(2))
            if 0 < minimum <= 40 and 0 < maximum <= 40 and minimum <= maximum:
                ranges.append((minimum, maximum))

    for pattern in single_patterns:
        for match in re.finditer(pattern, normalized):
            value = _extract_number(match.group(1))
            if 0 < value <= 40:
                singles.append(value)

    if not ranges and not singles:
        return None, None

    minimum_candidates = [minimum for minimum, _ in ranges] + singles
    required_min = max(minimum_candidates) if minimum_candidates else None
    required_max_candidates = [maximum for minimum, maximum in ranges if minimum == required_min]
    required_max = max(required_max_candidates) if required_max_candidates else None
    return required_min, required_max


def detect_seniority_level(text: str, fallback_years: float | None = None) -> int:
    normalized = normalize_text(text)
    detected = 0
    for token, level in SENIORITY_PATTERNS.items():
        if _contains_pattern(normalized, token):
            detected = max(detected, level)

    if detected:
        return detected

    years = fallback_years or 0.0
    if years >= 9:
        return 5
    if years >= 6:
        return 4
    if years >= 3:
        return 3
    if years >= 1.5:
        return 2
    if years > 0:
        return 1
    return 0


def extract_must_have_skills(job_text: str) -> list:
    required_cues = ["must have", "required", "requirements", "requirement", "mandatory", "hands-on", "proficiency", "expertise", "strong background"]
    optional_cues = ["good to have", "nice to have", "preferred", "plus"]
    must_have = []
    in_required_block = False
    for chunk in re.split(r"[\n\r•;]", job_text or ""):
        normalized = normalize_text(chunk)
        if not normalized:
            in_required_block = False
            continue
        if any(cue in normalized for cue in optional_cues):
            in_required_block = False
            continue
        if any(cue in normalized for cue in required_cues):
            in_required_block = True
            must_have.extend(extract_skills(normalized))
            continue
        if in_required_block:
            must_have.extend(extract_skills(normalized))
    return _dedupe_preserve_order(must_have)


def compute_semantic_score(job_embedding, resume_embedding) -> float:
    """Compute semantic similarity between two embeddings."""
    if job_embedding is None or resume_embedding is None:
        return 0.0
    similarity = util.cos_sim(job_embedding, resume_embedding)
    return float(similarity.cpu().numpy().item())


def compute_overlap_score(job_text: str, resume_text: str) -> float:
    """Fallback semantic proxy based on shared normalized tokens."""
    job_tokens = tokenize_text(job_text)
    resume_tokens = tokenize_text(resume_text)
    if not job_tokens or not resume_tokens:
        return 0.0
    overlap = len(job_tokens & resume_tokens)
    universe = len(job_tokens | resume_tokens)
    return overlap / universe if universe else 0.0


def compute_keyword_score(job_skills: list, resume_skills: list) -> tuple[float, list, list]:
    if not job_skills:
        return 0.0, [], []

    resume_skill_set = set(resume_skills)
    matched_skills = [skill for skill in job_skills if skill in resume_skill_set]
    missing_skills = [skill for skill in job_skills if skill not in resume_skill_set]
    score = len(matched_skills) / len(job_skills)
    return score, matched_skills, missing_skills


def compute_title_score(job_title: str, resume_text: str, resume_skills: list) -> float:
    title_skills = extract_skills(job_title)
    if title_skills:
        title_matches = [skill for skill in title_skills if skill in set(resume_skills)]
        return len(title_matches) / len(title_skills)

    title_tokens = [token for token in tokenize_text(job_title) if token not in GENERIC_TITLE_TOKENS and len(token) > 2]
    if not title_tokens:
        return 0.65
    resume_tokens = tokenize_text(resume_text)
    matched = sum(1 for token in title_tokens if token in resume_tokens)
    return matched / len(title_tokens)


def compute_experience_score(resume_years: float, required_min: float | None, required_max: float | None) -> float:
    if required_min is None:
        return 0.65
    if resume_years <= 0:
        return 0.20
    if resume_years < required_min:
        return max(0.05, min(0.95, resume_years / required_min))
    if required_max is not None and resume_years > required_max + 3:
        return 0.80
    return 1.0


def compute_seniority_score(job_text: str, resume_years: float, resume_text: str) -> float:
    required_min, _ = extract_required_experience(job_text)
    job_level = detect_seniority_level(job_text, fallback_years=required_min)
    resume_level = detect_seniority_level(resume_text, fallback_years=resume_years)

    if job_level == 0:
        return 0.65
    if resume_level >= job_level:
        return max(0.75, 1.0 - (0.08 * (resume_level - job_level)))
    return max(0.0, 1.0 - (0.35 * (job_level - resume_level)))


def compute_must_have_score(must_have_skills: list, resume_skills: list, keyword_score: float) -> tuple[float, list]:
    if not must_have_skills:
        return keyword_score, []

    resume_skill_set = set(resume_skills)
    matched = [skill for skill in must_have_skills if skill in resume_skill_set]
    score = len(matched) / len(must_have_skills)
    return score, matched


def format_experience_range(required_min: float | None, required_max: float | None) -> str:
    if required_min is None:
        return "not specified"
    if required_max is None:
        return f"{required_min:g}+ years"
    return f"{required_min:g}-{required_max:g} years"


def compute_hiring_score(
    final_score: float,
    experience_score: float,
    must_have_score: float,
    seniority_score: float,
    resume_years: float,
    required_min: float | None,
) -> int:
    score = 100 * (
        (0.45 * final_score)
        + (0.25 * experience_score)
        + (0.20 * must_have_score)
        + (0.10 * seniority_score)
    )

    if required_min is not None and resume_years > 0 and resume_years < required_min:
        gap_ratio = resume_years / required_min
        score *= 0.30 + (0.70 * gap_ratio)

    return int(round(max(0.0, min(score, 100.0))))


def build_match_reasoning(
    resume_years: float,
    required_min: float | None,
    required_max: float | None,
    matched_skills: list,
    missing_skills: list,
    must_have_skills: list,
    title_score: float,
    semantic_score: float,
) -> str:
    reasons = []
    reasons.append(
        f"Experience fit: resume {resume_years:g} years vs job {format_experience_range(required_min, required_max)}."
        if resume_years
        else f"Experience fit: job asks {format_experience_range(required_min, required_max)}, but resume years were not detected."
    )

    if matched_skills:
        reasons.append(f"Matched skills: {', '.join(matched_skills[:8])}.")
    else:
        reasons.append("Matched skills: none of the tracked core skills were strongly detected.")

    if must_have_skills:
        reasons.append(f"Must-have signals in job: {', '.join(must_have_skills[:6])}.")

    if missing_skills:
        reasons.append(f"Potential gaps: {', '.join(missing_skills[:6])}.")

    reasons.append(f"Title alignment score: {title_score:.2f}.")
    reasons.append(f"Semantic fit score: {semantic_score:.2f}.")
    return " ".join(reasons)


def analyze_resume(resume_text: str) -> dict:
    return {
        "experience_years": extract_resume_experience_years(resume_text),
        "skills": extract_skills(resume_text),
    }


def score_job(job: dict, resume_embedding, resume_text: str, resume_profile: dict, model_name: str = "all-MiniLM-L6-v2") -> dict:
    title = job.get("title", "")
    company = job.get("company", "")
    description = job.get("description", "")
    combined_text = " ".join([title, company, description])

    resume_years = resume_profile["experience_years"]
    resume_skills = resume_profile["skills"]
    job_skills = extract_skills(combined_text)
    keyword_score, matched_skills, missing_skills = compute_keyword_score(job_skills, resume_skills)
    required_min, required_max = extract_required_experience(combined_text)
    experience_score = compute_experience_score(resume_years, required_min, required_max)
    title_score = compute_title_score(title, resume_text, resume_skills)
    seniority_score = compute_seniority_score(combined_text, resume_years, resume_text)
    must_have_skills = extract_must_have_skills(combined_text)
    must_have_score, matched_must_have = compute_must_have_score(must_have_skills, resume_skills, keyword_score)

    model = _get_model(model_name)
    if model is not None and resume_embedding is not None:
        job_embedding = model.encode(combined_text, convert_to_tensor=True)
        semantic_score = compute_semantic_score(job_embedding, resume_embedding)
    else:
        semantic_score = compute_overlap_score(combined_text, resume_text)

    final_score = (
        (KEYWORD_COMPONENT_WEIGHT * keyword_score)
        + (SEMANTIC_COMPONENT_WEIGHT * semantic_score)
        + (EXPERIENCE_WEIGHT * experience_score)
        + (MUST_HAVE_WEIGHT * must_have_score)
        + (TITLE_WEIGHT * title_score)
        + (SENIORITY_WEIGHT * seniority_score)
    )
    hiring_score = compute_hiring_score(final_score, experience_score, must_have_score, seniority_score, resume_years, required_min)
    reasoning = build_match_reasoning(
        resume_years=resume_years,
        required_min=required_min,
        required_max=required_max,
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        must_have_skills=must_have_skills,
        title_score=title_score,
        semantic_score=semantic_score,
    )

    job.update(
        {
            "keyword_score": round(keyword_score, 4),
            "semantic_score": round(semantic_score, 4),
            "experience_score": round(experience_score, 4),
            "must_have_score": round(must_have_score, 4),
            "title_score": round(title_score, 4),
            "seniority_score": round(seniority_score, 4),
            "resume_experience_years": round(resume_years, 2),
            "required_experience_min": required_min if required_min is not None else "",
            "required_experience_max": required_max if required_max is not None else "",
            "matched_skills": ", ".join(matched_skills[:10]),
            "missing_skills": ", ".join(missing_skills[:10]),
            "must_have_skills": ", ".join(must_have_skills[:10]),
            "matched_must_have_skills": ", ".join(matched_must_have[:10]),
            "hiring_score": hiring_score,
            "match_reasoning": reasoning,
            "final_score": round(final_score, 4),
        }
    )
    return job


def rank_jobs(jobs: list, resume_text: str, skill_keywords: list, min_score: float = 0.30) -> list:
    """Score jobs and return the filtered list sorted by overall hiring fit."""
    del skill_keywords  # The matcher now derives skill coverage from canonical aliases and the resume itself.

    scored_jobs = []
    model = _get_model()
    resume_embedding = model.encode(resume_text or "", convert_to_tensor=True) if model is not None else None
    resume_profile = analyze_resume(resume_text or "")

    for job in jobs:
        try:
            scored_job = score_job(job, resume_embedding, resume_text or "", resume_profile)
            if scored_job["final_score"] >= min_score:
                scored_jobs.append(scored_job)
        except Exception as error:
            logging.error("Failed to score job %s: %s", job.get("title"), error)

    scored_jobs.sort(key=lambda item: (item.get("hiring_score", 0), item["final_score"]), reverse=True)
    logging.info("Ranked jobs. %s jobs kept after threshold filtering.", len(scored_jobs))
    return scored_jobs
