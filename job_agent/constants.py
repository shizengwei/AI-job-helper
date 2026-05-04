"""Project-wide constants."""

CSV_FIELDS = [
    "title",
    "company",
    "location",
    "salary",
    "tech_tags",
    "requirements",
    "source",
    "job_url",
]

SOURCE_DOMAINS = [
    "job-boards.greenhouse.io",
    "jobs.lever.co",
]

GREENHOUSE_BOARD_TOKENS = [
    "anthropic",
    "doordashusa",
    "figma",
    "janestreet",
    "modernizingmedicineinc",
    "ripplematchinterns",
    "scaleai",
    "toshibaglobalcommercesolutions",
    "transcarent",
    "vianttechnology",
]

LEVER_BOARD_TOKENS = [
    "anchorage",
    "cognitiv",
    "crossing-minds",
    "matchgroup",
    "mistral",
    "shopback-2",
    "sylvera",
    "woven-by-toyota",
    "zoox",
]

LEVER_BOARD_COMPANIES = {
    "anchorage": "Anchorage Digital",
    "cognitiv": "Cognitiv",
    "crossing-minds": "Crossing Minds",
    "matchgroup": "Match Group",
    "mistral": "Mistral AI",
    "shopback-2": "ShopBack",
    "sylvera": "Sylvera",
    "woven-by-toyota": "Woven by Toyota",
    "zoox": "Zoox",
}

ROLE_KEYWORD_TIERS = [
    [
        "AI Engineer",
        "Machine Learning Engineer",
        "LLM Engineer",
        "NLP Engineer",
    ],
    [
        "Applied Scientist",
        "Computer Vision Engineer",
        "Deep Learning Engineer",
        "Algorithm Engineer",
    ],
    [
        "Recommendation Engineer",
        "Data Intelligence Engineer",
        "ML Research Engineer",
        "AI Research Engineer",
    ],
]

CAMPUS_KEYWORDS = [
    "intern",
    "internship",
    "new grad",
    "graduate",
    "campus",
    "university",
    "student",
]

POSITIVE_AI_KEYWORDS = {
    "ai engineer": 4,
    "machine learning": 3,
    "ml engineer": 3,
    "deep learning": 3,
    "llm": 4,
    "large language model": 4,
    "nlp": 3,
    "natural language processing": 3,
    "computer vision": 3,
    "cv model": 2,
    "recommendation": 2,
    "recommender": 2,
    "applied scientist": 3,
    "algorithm engineer": 2,
    "data intelligence": 2,
    "rag": 2,
    "fine-tuning": 2,
    "finetuning": 2,
    "pytorch": 1,
    "tensorflow": 1,
    "transformer": 2,
    "multimodal": 2,
}

POSITIVE_CAMPUS_KEYWORDS = {
    "intern": 2,
    "internship": 2,
    "new grad": 3,
    "graduate": 2,
    "campus": 2,
    "university": 2,
    "student": 2,
    "fellow": 2,
    "fellowship": 2,
    "apprentice": 2,
}

NEGATIVE_ROLE_KEYWORDS = {
    "backend engineer": 3,
    "frontend engineer": 3,
    "full stack engineer": 3,
    "qa engineer": 4,
    "test engineer": 4,
    "sre": 4,
    "devops": 4,
    "sales": 4,
    "account executive": 4,
    "business development": 4,
    "manager": 5,
    "director": 5,
    "head of": 5,
    "staff ": 4,
    "senior ": 4,
    "sr.": 4,
    "principal": 4,
    "lead ": 4,
    "counsel": 5,
    "attorney": 5,
}

TECH_TAG_CATALOG = {
    "LLM": ["llm", "large language model", "gpt", "rag", "prompt"],
    "NLP": ["nlp", "natural language processing", "text classification"],
    "CV": ["computer vision", "image", "vision model", "cv"],
    "ML": ["machine learning", "supervised learning", "model training"],
    "DL": ["deep learning", "neural network", "pytorch", "tensorflow"],
    "Recommendation": ["recommendation", "ranking", "retrieval"],
    "MLOps": ["mlops", "model deployment", "inference", "airflow", "kubeflow"],
    "Data": ["sql", "spark", "pandas", "etl", "data pipeline"],
    "Python": ["python"],
}

REQUIREMENT_HINTS = [
    "require",
    "experience",
    "proficiency",
    "familiar",
    "knowledge",
    "python",
    "machine learning",
    "deep learning",
    "llm",
    "nlp",
    "vision",
    "sql",
]

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
)

MAX_SUMMARY_CHARS = 320
