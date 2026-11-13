"""Question answering: prepare (pseudonymise + send preview) -> run (approve + answer); uploaded documents."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..deps import get_ctx, get_pipeline, require_pack, require_token
from ..pipeline.orchestrator import QueryPipeline
from ..schemas import PrepareRequest, RunRequest
from ..services import documents as docs
from ..state import AppContext

router = APIRouter(prefix="/v1", dependencies=[Depends(require_token)])


@router.post("/queries", tags=["query"], status_code=201)
def prepare_query(body: PrepareRequest, ctx: AppContext = Depends(require_pack), pipe: QueryPipeline = Depends(get_pipeline)) -> dict:
    """Step 1. Pseudonymises on the device and returns the SEND PREVIEW (exact text that may leave, placeholders highlighted).
    Nothing is sent. With `auto_run` and automatic approval switched on, the answer is returned directly."""
    try:
        prepared = pipe.prepare(body)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if body.auto_run and ctx.user_settings()["auto_approve_send"] and not prepared["requires_review"]:
        return {"prepared": prepared, "answer": pipe.run(prepared["query_id"], RunRequest())}
    return prepared


@router.post("/queries/{query_id}/run", tags=["query"])
def run_query(query_id: str, body: RunRequest | None = None, ctx: AppContext = Depends(require_pack), pipe: QueryPipeline = Depends(get_pipeline)) -> dict:
    """Step 2. The user approved the preview (optionally edited it). Runs understanding, retrieval, generation and verification."""
    try:
        return pipe.run(query_id, body or RunRequest())
    except KeyError:
        raise HTTPException(404, "query not found or expired: prepare it again")


@router.get("/queries/{query_id}/progress", tags=["query"])
def query_progress(query_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    """What the agent is doing now (steps with status and duration); polled by the app while a question runs."""
    from ..pipeline import progress as P

    return P.snapshot(ctx.progress, query_id) or {"steps": [], "done": False}


@router.post("/queries/{query_id}/cancel", tags=["query"])
def cancel_query(query_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    """The user declined the send preview: the pending (pseudonymised) query is deleted."""
    ctx.db.execute("DELETE FROM pending_query WHERE query_id=?", (query_id,))
    return {"status": "cancelled", "query_id": query_id}


# ------------------------------------------------------------------------------------------------------ documents
@router.post("/documents", tags=["documents"], status_code=201)
async def upload_document(file: UploadFile = File(...), case_id: str | None = Form(None), ctx: AppContext = Depends(get_ctx)) -> dict:
    """OCR / extraction and detection run on the device. The file is not kept: only extracted text (encrypted) is stored."""
    content = await file.read()
    if len(content) > ctx.settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "file too large")
    try:
        return docs.ingest(ctx, file.filename or "upload", content, case_id or ctx.db.create_case())
    except docs.UnsupportedDocument as e:
        raise HTTPException(415, str(e))


@router.post("/documents/{doc_id}/review", tags=["documents"])
def review_document(doc_id: str, mark_terms: list[str] = [], confirm: bool = False, ctx: AppContext = Depends(get_ctx)) -> dict:
    """The user marks names the detector missed and confirms. Low-confidence documents cannot be used before this."""
    try:
        return docs.review(ctx, doc_id, mark_terms, confirm)
    except KeyError:
        raise HTTPException(404)


@router.get("/documents/{doc_id}/read", tags=["documents"])
def read_document(doc_id: str, as_of: date | None = None, ctx: AppContext = Depends(get_ctx)) -> dict:
    """Notice / summons / contract / judgment reader: dates, cited articles and their text. No assessment of the document."""
    try:
        return docs.read_notice(ctx, doc_id, as_of)
    except KeyError:
        raise HTTPException(404)


@router.delete("/documents/{doc_id}", tags=["documents"], status_code=204)
def delete_document(doc_id: str, ctx: AppContext = Depends(get_ctx)) -> None:
    ctx.db.execute("DELETE FROM document WHERE doc_id=?", (doc_id,))
