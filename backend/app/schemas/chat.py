from typing import List, Optional
from pydantic import BaseModel


class ChatRequest(BaseModel):
    tenant_id: str
    question: str
    top_k: Optional[int] = 5


class TicketRow(BaseModel):
    source: str = ""
    ticket_id: str = ""
    ticket_description: str = ""
    resolution: str = ""
    root_cause: str = ""
    issue_type: str = ""
    status: str = ""
    priority: str = ""
    confidence_score: Optional[float] = None   # ✅ None for open tickets
    source_url: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    tickets: List[TicketRow] = []
    sources: List[dict] = []
    llm_model: str
    embedding_model: str
    vector_store: str