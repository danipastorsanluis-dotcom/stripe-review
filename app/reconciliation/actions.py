def get_recommended_action(issue_code: str) -> str:
    mapping = {
        "MULTICURRENCY": "Separar por moneda antes de contabilidad.",
        "NO_PAYOUT": "No exportar todavía. Revisa si el archivo incluye payout_id.",
        "NEGATIVE_NET": "Revisar refunds, fees y ajustes del payout.",
        "COMPLEX_TYPES": "Revisar el impacto de disputes, reserves, transferencias o ajustes antes de exportar.",
        "UNHANDLED_TYPES": "Revisar manualmente los tipos no soportados antes de exportar.",
        "EMPTY_PAYOUT_EFFECT": "Comprobar si el payout solo contiene líneas no reconocidas.",
    }
    return mapping.get(issue_code, "Revisión manual recomendada.")
