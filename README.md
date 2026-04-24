# StripeReview

> Herramienta web gratuita y de código abierto para revisar payouts de Stripe antes de contabilidad. Agrupa, separa fees/refunds, detecta incidencias y genera un Excel revisable.

[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE)

## ¿Qué problema resuelve?

Un payout de Stripe agrupa decenas o cientos de transacciones individuales (ventas, comisiones, refunds, ajustes, conversiones FX). Solo el importe neto final se deposita en tu banco. Cuando un asesor o un autónomo intenta reconciliar esos payouts con sus ventas, se encuentra con:

- Comisiones que no aparecen como línea separada en el banco
- Refunds que reducen el payout del mes (o del siguiente)
- Disputes que retiran importes a posteriori
- Desfases temporales entre la venta y el depósito
- Multi-moneda si vendes fuera de la UE

Este proyecto automatiza la parte mecánica: lees un CSV/XLSX exportado de Stripe, el sistema agrupa por `payout_id`, separa categorías y te da un Excel revisable con un semáforo claro: **Listo / Revisar / Bloqueado**.

## Características

- 📊 **Agrupación automática** por `payout_id` con separación de ventas/fees/refunds
- ⚠️ **Detección de incidencias**: multi-moneda, tipos complejos, neto negativo, transacciones huérfanas
- 🏦 **Matching bancario opcional**: si subes también el extracto bancario, cruza importes
- 📝 **Explicación humana** de cada payout (por qué cuadra o no)
- 🔒 **Multi-tenant** con usuarios y clientes separados
- 📄 **Exports Excel + CSV** descargables
- 🌐 **Blog SEO** integrado para contenido

## Stack técnico

- **Backend**: FastAPI + Pydantic v2
- **Data**: pandas + openpyxl + XlsxWriter
- **DB**: SQLite (PostgreSQL ready vía SQLAlchemy si se migra)
- **Auth**: bcrypt + cookies HttpOnly + rate limiting
- **Deploy**: Docker + Railway

## Arquitectura

```
app/
├── api/routes/         # FastAPI endpoints (auth, tools, clients, billing, blog)
├── core/               # Config, errors, utils
├── domain/             # Modelos de dominio (enums, dataclasses)
├── ingestion/          # Parsers CSV/Excel + validadores + mappers
├── reconciliation/     # Engine de reconciliación + explain + bank matching
├── exports/            # Generadores CSV/XLSX
├── services/           # Orchestradores de alto nivel
├── storage/            # BD (SQLite)
└── web/                # UI HTML/JS + blog posts
```

El engine de reconciliación (`app/reconciliation/engine.py`) es el corazón: toma una lista de transacciones normalizadas, las agrupa por payout+moneda, calcula totales, detecta incidencias y emite un `PayoutSummary` con estado.

## Ejecutar localmente

```bash
git clone https://github.com/danipastorsanluis-dotcom/stripe-review.git
cd stripe-review
python -m venv .venv && source .venv/bin/activate  # o .venv\Scripts\activate en Windows
pip install -r requirements.txt
APP_ENV=development AUTH_REQUIRED=false python run_api.py
```

Abrir [http://localhost:8000](http://localhost:8000).

### Ejecutar tests

```bash
python -m pytest -v
```

Incluye tests de:
- Engine de reconciliación
- API endpoints (auth, tools, clients)
- Data leak cross-user bloqueado
- Rate limiting en login
- Logout invalida sesión

## Ejecutar con Docker

```bash
docker-compose up --build
```

## Cómo usarlo

1. Regístrate en `/#register` (email + password, sin confirmación por email)
2. Crea un cliente en el dashboard (para organizar análisis por empresa)
3. Exporta desde Stripe: `Informes → Payout reconciliation (itemized)`
4. Sube el CSV en el dashboard
5. Descarga el Excel resultante

## Limitaciones honestas

- **No integra con A3/Contasol/Holded**: el output es un Excel genérico, no el formato específico de importación de esos programas. Por eso la herramienta se posiciona como "revisión previa", no "contabilidad automática".
- **Bank matching básico**: hace matching por importe y referencia, no por combinaciones complejas.
- **SQLite**: suficiente para una app personal, no para multi-instancia a escala.
- **Sin Stripe Billing integrado**: es gratis por ahora.

## Contexto del proyecto

Este proyecto nació como validación de una hipótesis: que existe suficiente dolor en conciliar Stripe manualmente como para justificar una herramienta. La hipótesis se basa en [esta investigación de demanda](./docs/demand-research.md) y está siendo validada mediante tráfico orgánico y uso de la herramienta gratuita.

## Licencia

MIT. Libre de usar, modificar y redistribuir.

## Autor

Hecho por Dani. Si te resulta útil, una estrella en GitHub me hace ilusión. Si tienes feedback, abre un issue.
