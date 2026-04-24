import argparse

from app.services.process_file import process_file


def main():
    parser = argparse.ArgumentParser(description="Stripe Reconciliation MVP")
    parser.add_argument("--input", required=True, help="Ruta al CSV de Stripe")
    parser.add_argument("--out", default="output/", help="Directorio de salida")
    args = parser.parse_args()

    result = process_file(input_path=args.input, output_dir=args.out)

    print("[+] Procesamiento finalizado")
    print(f"    Run ID: {result['run_id']}")
    print(f"    Formato detectado: {result['detected_format']}")
    print(f"    Transacciones: {result['transactions_count']}")
    print(f"    Payouts: {result['payouts_count']}")
    print(f"    Issues: {result['issues_count']}")
    print(f"    Matched: {result['health']['matched_count']}")
    print(f"    Warnings: {result['health']['warning_count']}")
    print(f"    Issues graves: {result['health']['issue_count']}")
    print(f"    Multicurrency: {result['health']['multicurrency_count']}")
    print(f"    Sin payout: {result['health']['unassigned_count']}")
    print(f"    Negative net: {result['health']['negative_net_count']}")
    print(f"    Unhandled types: {result['health']['unhandled_types_count']}")
    print(f"    reconciliation.csv -> {result['reconciliation_path']}")
    print(f"    issues.csv         -> {result['issues_path']}")
    print(f"    a3_export.csv      -> {result['a3_path']}")


if __name__ == "__main__":
    main()