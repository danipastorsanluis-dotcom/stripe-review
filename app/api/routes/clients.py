from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.routes.tools import get_current_user
from app.core.config import APP_DB_PATH
from app.storage.db import (
    connect_db,
    create_client,
    delete_client,
    ensure_tables,
    fetch_runs_by_client,
    get_client,
    list_clients,
    update_client,
)

router = APIRouter(prefix="/clients", tags=["clients"])


class ClientPayload(BaseModel):
    name: str
    nif: str = ""
    default_chart: str = "pgc_pyme"
    default_account_sales: str = "700"
    default_account_fees: str = "626"
    default_account_refunds: str = "708"
    default_account_bank: str = "572"
    journal_code: str = "STR"


@router.get("")
def get_clients(current_user=Depends(get_current_user)):
    con = connect_db(APP_DB_PATH)
    try:
        ensure_tables(con)
        return {"ok": True, "items": list_clients(con, user_id=int(current_user["id"]))}
    finally:
        con.close()


@router.post("")
def post_client(payload: ClientPayload, current_user=Depends(get_current_user)):
    con = connect_db(APP_DB_PATH)
    try:
        ensure_tables(con)
        client = create_client(con, user_id=int(current_user["id"]), **payload.model_dump())
        return {"ok": True, "item": client}
    finally:
        con.close()


@router.get("/{client_id}")
def get_client_detail(client_id: int, current_user=Depends(get_current_user)):
    con = connect_db(APP_DB_PATH)
    try:
        ensure_tables(con)
        client = get_client(con, client_id=client_id, user_id=int(current_user["id"]))
        if not client:
            raise HTTPException(status_code=404, detail="Cliente no encontrado")
        runs = fetch_runs_by_client(con, user_id=int(current_user["id"]), client_id=client_id)
        return {"ok": True, "item": client, "runs": runs}
    finally:
        con.close()


@router.put("/{client_id}")
def put_client(client_id: int, payload: ClientPayload, current_user=Depends(get_current_user)):
    con = connect_db(APP_DB_PATH)
    try:
        ensure_tables(con)
        client = update_client(con, client_id=client_id, user_id=int(current_user["id"]), payload=payload.model_dump())
        if not client:
            raise HTTPException(status_code=404, detail="Cliente no encontrado")
        return {"ok": True, "item": client}
    finally:
        con.close()


@router.delete("/{client_id}")
def remove_client(client_id: int, current_user=Depends(get_current_user)):
    con = connect_db(APP_DB_PATH)
    try:
        ensure_tables(con)
        deleted = delete_client(con, client_id=client_id, user_id=int(current_user["id"]))
        if not deleted:
            raise HTTPException(status_code=404, detail="Cliente no encontrado")
        return {"ok": True}
    finally:
        con.close()
