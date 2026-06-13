from typing import List, Optional
from pydantic import BaseModel


class TranslationStatusResponse(BaseModel):
    provider: str
    configured: bool
    can_translate: bool
    model: Optional[str] = None
    reason: Optional[str] = None


class BackfillErrorDetail(BaseModel):
    article_id: str
    title: str
    error: str


class BackfillResult(BaseModel):
    status: str               # "ok" | "partial" | "skipped"
    provider_ready: bool
    checked: int
    candidates: int
    translated: int
    retranslated_fake: int = 0      # articles re-translated from a fake/stub translation
    forced_retranslated: int = 0    # articles re-translated via force=true
    skipped_hebrew: int
    skipped_already_translated: int
    skipped_provider_not_ready: int
    language_corrected: int
    failed: int
    dry_run: bool
    reason: Optional[str] = None
    errors: List[BackfillErrorDetail] = []
