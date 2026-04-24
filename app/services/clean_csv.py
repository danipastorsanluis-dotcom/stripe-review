import os
from typing import Any

from app.exports.normalized_csv import export_normalized_csv
from app.exports.normalized_xlsx import export_normalized_xlsx
from app.ingestion.stripe_mapper import map_dataframe_to_transactions
from app.ingestion.stripe_validator import validate_stripe_dataframe
from app.services.dataframe_prep import prepare_dataframe


def _serialize_transaction(tx) -> dict[str, Any]:
    return {
        "id": None if tx.id is None else str(tx.id),
        "payout_id": None if tx.payout_id is None else str(tx.payout_id),
        "type": None if tx.type is None else str(tx.type),
        "amount": str(tx.amount),
        "fee": str(tx.fee),
        "net": str(tx.net),
        "currency": None if tx.currency is None else str(tx.currency),
        "created": tx.created.isoformat() if tx.created is not None else None,
        "description": None if tx.description is None else str(tx.description),
    }


def clean_csv_file(input_path: str, output_dir: str) -> dict[str, Any]:
    if not input_path or not os.path.exists(input_path):
        raise FileNotFoundError(f"No existe el archivo de entrada: {input_path}")

    os.makedirs(output_dir, exist_ok=True)

    df = prepare_dataframe(input_path)
    detected_format = validate_stripe_dataframe(df)
    transactions = map_dataframe_to_transactions(df)

    if not transactions:
        raise ValueError("No se han podido mapear transacciones válidas desde el archivo")

    folder_name = os.path.basename(output_dir.rstrip(os.sep))
    normalized_csv_path = os.path.join(output_dir, f"{folder_name}_normalized_stripe.csv")
    normalized_xlsx_path = os.path.join(output_dir, f"{folder_name}_normalized_stripe.xlsx")

    export_normalized_csv(transactions, normalized_csv_path)
    normalized_xlsx_path = export_normalized_xlsx(transactions, normalized_xlsx_path)

    preview_rows = [_serialize_transaction(tx) for tx in transactions[:20]]

    return {
        "detected_format": detected_format,
        "transactions_count": len(transactions),
        "normalized_csv_path": normalized_csv_path,
        "normalized_xlsx_path": normalized_xlsx_path,
        "preview": {
            "rows": preview_rows,
            "preview_count": len(preview_rows),
        },
    }