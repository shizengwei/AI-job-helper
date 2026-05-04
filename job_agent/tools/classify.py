"""Job classification tool."""

from __future__ import annotations

from job_agent.config import Settings
from job_agent.constants import (
    NEGATIVE_ROLE_KEYWORDS,
    POSITIVE_AI_KEYWORDS,
    POSITIVE_CAMPUS_KEYWORDS,
)
from job_agent.models import ClassificationResult, RawJobPosting
from job_agent.services.llm import OpenAILLMClient


class JobClassifier:
    def __init__(self, settings: Settings) -> None:
        self.llm = (
            OpenAILLMClient(settings.openai_api_key, settings.llm_model)
            if settings.llm_enabled
            else None
        )

    def classify(self, job: RawJobPosting) -> ClassificationResult:
        if self.llm is not None:
            llm_result = self.llm.classify_job(job)
            if llm_result is not None:
                return llm_result
        return self._heuristic_classify(job)

    def _heuristic_classify(self, job: RawJobPosting) -> ClassificationResult:
        title = job.title.lower()
        description = job.description.lower()
        text = f"{title}\n{description}"
        ai_score = sum(weight for keyword, weight in POSITIVE_AI_KEYWORDS.items() if keyword in text)
        campus_score = sum(
            weight for keyword, weight in POSITIVE_CAMPUS_KEYWORDS.items() if keyword in text
        )
        negative_score = sum(
            weight for keyword, weight in NEGATIVE_ROLE_KEYWORDS.items() if keyword in text
        )
        title_ai_bonus = 2 if any(keyword in title for keyword in POSITIVE_AI_KEYWORDS) else 0
        title_campus_bonus = 2 if any(keyword in title for keyword in POSITIVE_CAMPUS_KEYWORDS) else 0
        total_score = ai_score + campus_score + title_ai_bonus + title_campus_bonus - negative_score

        reasons: list[str] = []
        if ai_score:
            reasons.append(f"ai_score={ai_score}")
        if campus_score:
            reasons.append(f"campus_score={campus_score}")
        if title_ai_bonus:
            reasons.append(f"title_ai_bonus={title_ai_bonus}")
        if title_campus_bonus:
            reasons.append(f"title_campus_bonus={title_campus_bonus}")
        if negative_score:
            reasons.append(f"negative_score={negative_score}")

        has_campus_signal = any(keyword in text for keyword in POSITIVE_CAMPUS_KEYWORDS)
        accepted = (
            ai_score >= 3
            and has_campus_signal
            and (campus_score + title_campus_bonus) >= 2
            and negative_score <= 2
            and total_score >= 6
        )
        reason = ", ".join(reasons) if reasons else "no strong signal found"
        if not accepted and negative_score >= 3:
            reason = f"rejected due to negative role signals: {reason}"
        return ClassificationResult(accepted=accepted, score=total_score, reason=reason)
