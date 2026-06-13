from typing import List, Optional
from pydantic import BaseModel


class BackfillErrorDetail(BaseModel):
    article_id: str
    title: str
    error: str


class BackfillResult(BaseModel):
    status: str
    checked: int
    candidates: int
    translated: int
    skipped_hebrew: int
    skipped_already_translated: int
    failed: int
    dry_run: bool
    errors: List[BackfillErrorDetail] = []
