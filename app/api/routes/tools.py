from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Cookie, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.config import APP_DB_PATH, MAX_UPLOAD_BYTES, SESSION_COOKIE_NAME, STORAGE_DIR
from app.core.errors import ValidationError
from app.services.clean_csv import clean_csv_file
from app.services.process_file import process_file
from app.storage.db import (
    connect_db,
    count_runs_in_current_month,
    ensure_tables,
    fetch_artifact_path,
    get_client,
    get_user_by_session_token,
)

router = APIRouter(prefix="/tools", tags=["tools"])

BASE_DIR = Path(STORAGE_DIR)
UPLOADS_DIR = BASE_DIR / "uploads"
OUTPUTS_DIR = BASE_DIR / "outputs"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Límite del plan free. Cuando haya planes de pago, mover a billing.py.
FREE_PLAN_MAX_RUNS_PER_MONTH = 10


def get_current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict:
    """
    Exige sesión válida siempre. Sin cookie o con cookie inválida => 401.
    Nunca devuelve un usuario fantasma id=0.
    """
    if not session_token:
        raise HTTPException(status_code=401, detail="Debes iniciar sesión")

    con = connect_db(APP_DB_PATH)
    try:
        ensure_tables(con)
        user = get_user_by_session_token(con, session_token)
    finally:
        con.close()

    if not user:
        raise HTTPException(status_code=401, detail="Sesión no válida o caducada")

    user_id = int(user.get("id", 0) or 0)
    if user_id <= 0:
        raise HTTPException(status_code=401, detail="Sesión no válida")

    return user


def _safe_filename(filename: str) -> str:
    if not filename:
        return "uploaded_file"
    return os.path.basename(filename).replace(" ", "_")


def _save_upload(file: UploadFile, target_path: Path) -> None:
    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    if size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"El archivo supera el límite permitido de {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )
    if size == 0:
        raise HTTPException(status_code=400, detail="El archivo está vacío")
    with target_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)


def _build_request_paths(file: UploadFile) -> tuple[Path, Path]:
    request_id = uuid.uuid4().hex
    safe_name = _safe_filename(file.filename)
    upload_path = UPLOADS_DIR / f"{request_id}_{safe_name}"
    output_dir = OUTPUTS_DIR / request_id
    output_dir.mkdir(parents=True, exist_ok=True)
    return upload_path, output_dir


def _validate_uploaded_extension(file: UploadFile, *, required: bool = True) -> None:
    if file is None:
        if required:
            raise HTTPException(status_code=400, detail="No se ha proporcionado ningún archivo")
        return
    if not file.filename:
        if required:
            raise HTTPException(status_code=400, detail="No se ha proporcionado ningún archivo")
        return
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".csv", ".xlsx", ".xls"}:
        raise HTTPException(status_code=400, detail="Formato no soportado. Sube un archivo CSV, XLSX o XLS")


def _artifact_url_or_none(run_id: int, enabled: bool, route: str) -> str | None:
    return f"{route}/{run_id}" if enabled else None


def _resolve_run_file(run_id: int, artifact_kind: str, current_user: dict) -> Path:
    user_id = int(current_user["id"])
    con = connect_db(APP_DB_PATH)
    try:
        ensure_tables(con)
        file_path = fetch_artifact_path(
            con,
            run_id=run_id,
            artifact_type=artifact_kind,
            user_id=user_id,
        )
    finally:
        con.close()
    if not file_path:
        # 404 aunque el run exista pero sea de otro usuario: no se debe revelar la existencia
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    path = Path(file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return path


def _resolve_named_file(filename: str, current_user: dict) -> Path:
    """
    Solo busca archivos dentro de la carpeta del usuario autenticado.
    Actualmente 'clean-stripe-csv' no usa run_id, por lo que se usa un prefijo por usuario
    basado en el id. Si una versión anterior dejó archivos globales, no se exponen.
    """
    safe_name = os.path.basename(filename)
    user_id = int(current_user["id"])
    # Limitamos la búsqueda a ficheros cuyo directorio padre fue creado en esta sesión de uploads.
    # Como fallback, exigimos que el path contenga el uid en algún segmento.
    matches = [
        p for p in OUTPUTS_DIR.rglob(safe_name)
        if p.exists() and f"_uid{user_id}_" in p.name
    ]
    if not matches:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return max(matches, key=lambda p: p.stat().st_mtime)


@router.post("/reconcile-stripe")
async def reconcile_stripe_tool(
    file: UploadFile = File(...),
    bank_file: UploadFile | None = File(None),
    client_id: int | None = Form(None),
    current_user=Depends(get_current_user),
):
    _validate_uploaded_extension(file)
    _validate_uploaded_extension(bank_file, required=False)

    user_id = int(current_user["id"])

    # Enforcement del plan free
    con = connect_db(APP_DB_PATH)
    try:
        ensure_tables(con)
        runs_this_month = count_runs_in_current_month(con, user_id=user_id)
    finally:
        con.close()

    if runs_this_month >= FREE_PLAN_MAX_RUNS_PER_MONTH:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Has alcanzado el límite del plan gratuito "
                f"({FREE_PLAN_MAX_RUNS_PER_MONTH} análisis al mes). "
                f"El contador se reinicia el día 1 de cada mes."
            ),
        )

    upload_path, output_dir = _build_request_paths(file)
    bank_upload_path = None

    con = connect_db(APP_DB_PATH)
    try:
        ensure_tables(con)
        client = None
        if client_id is not None:
            client = get_client(con, client_id=client_id, user_id=user_id)
            if not client:
                raise HTTPException(status_code=404, detail="Cliente no encontrado")
    finally:
        con.close()

    try:
        _save_upload(file, upload_path)
        if bank_file and bank_file.filename:
            bank_upload_path, _ = _build_request_paths(bank_file)
            _save_upload(bank_file, bank_upload_path)

        result = process_file(
            str(upload_path),
            str(output_dir),
            str(bank_upload_path) if bank_upload_path else None,
            user_id=user_id,
            client_id=client_id,
            client=client,
        )
        bank_matches_enabled = result["bank_file_provided"] and result["bank_matches_count"] > 0
        return {
            "ok": True,
            "message": "Archivo procesado correctamente",
            "run_id": result["run_id"],
            "detected_format": result["detected_format"],
            "bank_detected_format": result["bank_detected_format"],
            "transactions_count": result["transactions_count"],
            "bank_transactions_count": result["bank_transactions_count"],
            "payouts_count": result["payouts_count"],
            "issues_count": result["issues_count"],
            "health": result["health"],
            "bank_used": result["bank_used"],
            "bank_file_provided": result["bank_file_provided"],
            "bank_check_status": result["bank_check_status"],
            "bank_matches_count": result["bank_matches_count"],
            "bank_unmatched_count": result["bank_unmatched_count"],
            "bank_review_count": result["bank_review_count"],
            "can_export_accounting": result["can_export_accounting"],
            "requires_review": result["requires_review"],
            "has_blocking_issues": result["has_blocking_issues"],
            "issue_codes": result["issue_codes"],
            "safe_to_export_count": result["safe_to_export_count"],
            "processable_count": result["processable_count"],
            "total_payouts": result["total_payouts"],
            "accounting_summary_text": result["accounting_summary_text"],
            "preview": result["preview"],
            "downloads": {
                "reconciliation_csv": f"/tools/download/reconciliation/{result['run_id']}",
                "reconciliation_xlsx": f"/tools/download/reconciliation-xlsx/{result['run_id']}",
                "issues_csv": f"/tools/download/issues/{result['run_id']}",
                "issues_xlsx": f"/tools/download/issues-xlsx/{result['run_id']}",
                "bank_matches_csv": _artifact_url_or_none(result["run_id"], bank_matches_enabled, "/tools/download/bank-matches"),
                "bank_matches_xlsx": _artifact_url_or_none(result["run_id"], bank_matches_enabled, "/tools/download/bank-matches-xlsx"),
                "accounting_csv": _artifact_url_or_none(result["run_id"], result["can_export_accounting"], "/tools/download/accounting"),
                "accounting_xlsx": _artifact_url_or_none(result["run_id"], result["can_export_accounting"], "/tools/download/accounting-xlsx"),
            },
        }
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        try:
            file.file.close()
        except Exception:
            pass
        if bank_file is not None:
            try:
                bank_file.file.close()
            except Exception:
                pass


@router.post("/clean-stripe-csv")
async def clean_stripe_csv_tool(file: UploadFile = File(...), current_user=Depends(get_current_user)):
    _validate_uploaded_extension(file)
    user_id = int(current_user["id"])

    # Prefijamos el output_dir con el uid para que _resolve_named_file lo pueda filtrar.
    request_id = uuid.uuid4().hex
    safe_name = _safe_filename(file.filename)
    upload_path = UPLOADS_DIR / f"{request_id}_uid{user_id}_{safe_name}"
    output_dir = OUTPUTS_DIR / f"{request_id}_uid{user_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        _save_upload(file, upload_path)
        result = clean_csv_file(str(upload_path), str(output_dir))

        # Renombramos los archivos de salida para incluir el uid y evitar accesos cruzados.
        def _tag_with_uid(path_str: str) -> str:
            p = Path(path_str)
            new_p = p.with_name(f"{p.stem}_uid{user_id}{p.suffix}")
            if p.exists() and p != new_p:
                p.rename(new_p)
            return str(new_p)

        normalized_csv_path = _tag_with_uid(result["normalized_csv_path"])
        normalized_xlsx_path = _tag_with_uid(result["normalized_xlsx_path"])

        return {
            "ok": True,
            "message": "Archivo limpiado correctamente",
            "detected_format": result["detected_format"],
            "transactions_count": result["transactions_count"],
            "preview": result["preview"],
            "downloads": {
                "normalized_csv": f"/tools/download/normalized-csv/{os.path.basename(normalized_csv_path)}",
                "normalized_xlsx": f"/tools/download/normalized-xlsx/{os.path.basename(normalized_xlsx_path)}",
            },
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        try:
            file.file.close()
        except Exception:
            pass


@router.get("/download/reconciliation/{run_id}")
async def download_reconciliation_csv(run_id: int, current_user=Depends(get_current_user)):
    path = _resolve_run_file(run_id, "reconciliation_csv", current_user)
    return FileResponse(str(path), media_type="text/csv", filename="stripe-resumen-reconciliado.csv")


@router.get("/download/reconciliation-xlsx/{run_id}")
async def download_reconciliation_xlsx(run_id: int, current_user=Depends(get_current_user)):
    path = _resolve_run_file(run_id, "reconciliation_xlsx", current_user)
    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="stripe-resumen-reconciliado.xlsx",
    )


@router.get("/download/issues/{run_id}")
async def download_issues_csv(run_id: int, current_user=Depends(get_current_user)):
    path = _resolve_run_file(run_id, "issues_csv", current_user)
    return FileResponse(str(path), media_type="text/csv", filename="stripe-incidencias.csv")


@router.get("/download/issues-xlsx/{run_id}")
async def download_issues_xlsx(run_id: int, current_user=Depends(get_current_user)):
    path = _resolve_run_file(run_id, "issues_xlsx", current_user)
    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="stripe-incidencias.xlsx",
    )


@router.get("/download/bank-matches/{run_id}")
async def download_bank_matches_csv(run_id: int, current_user=Depends(get_current_user)):
    path = _resolve_run_file(run_id, "bank_matches_csv", current_user)
    return FileResponse(str(path), media_type="text/csv", filename="stripe-bank-matching.csv")


@router.get("/download/bank-matches-xlsx/{run_id}")
async def download_bank_matches_xlsx(run_id: int, current_user=Depends(get_current_user)):
    path = _resolve_run_file(run_id, "bank_matches_xlsx", current_user)
    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="stripe-bank-matching.xlsx",
    )


@router.get("/download/accounting/{run_id}")
async def download_accounting_csv(run_id: int, current_user=Depends(get_current_user)):
    path = _resolve_run_file(run_id, "accounting_csv", current_user)
    return FileResponse(str(path), media_type="text/csv", filename="stripe-resumen-contable-generic.csv")


@router.get("/download/accounting-xlsx/{run_id}")
async def download_accounting_xlsx(run_id: int, current_user=Depends(get_current_user)):
    path = _resolve_run_file(run_id, "accounting_xlsx", current_user)
    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="stripe-a3-import.xlsx",
    )


@router.get("/download/normalized-csv/{filename}")
async def download_normalized_csv(filename: str, current_user=Depends(get_current_user)):
    path = _resolve_named_file(filename, current_user)
    return FileResponse(str(path), media_type="text/csv", filename="stripe-csv-limpio.csv")


@router.get("/download/normalized-xlsx/{filename}")
async def download_normalized_xlsx(filename: str, current_user=Depends(get_current_user)):
    path = _resolve_named_file(filename, current_user)
    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="stripe-csv-limpio.xlsx",
    )
