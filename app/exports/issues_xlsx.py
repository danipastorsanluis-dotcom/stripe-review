import pandas as pd

from app.exports.excel_utils import save_as_professional_excel


def export_issues_xlsx(issues, path: str):
    rows = []

    for i in issues:
        rows.append(
            {
                "Severidad": "" if i.severity is None else str(i.severity).strip(),
                "Código": "" if i.code is None else str(i.code).strip(),
                "Mensaje": "" if i.message is None else str(i.message).strip(),
                "Payout ID": "" if i.payout_id is None else str(i.payout_id).strip(),
                "Transaction ID": "" if i.transaction_id is None else str(i.transaction_id).strip(),
                "Qué hacer": "" if i.suggested_action is None else str(i.suggested_action).strip(),
                "Bloqueante": bool(getattr(i, "is_blocking", False)),
            }
        )

    df = pd.DataFrame(
        rows,
        columns=[
            "Severidad",
            "Código",
            "Mensaje",
            "Payout ID",
            "Transaction ID",
            "Qué hacer",
            "Bloqueante",
        ],
    )

    return save_as_professional_excel(df, path, sheet_name="Incidencias")