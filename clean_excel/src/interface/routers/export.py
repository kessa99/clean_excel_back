import json

from fastapi import APIRouter, Form, UploadFile, File
from fastapi.responses import StreamingResponse

from infrastructure.schemas import DecisionHumain, FichierSchema
from infrastructure.services import (
    lire_fichier,
    extraire_echantillon,
    detecter_schema,
    detecter_anomalies,
    reconstruire_avec_decisions,
    exporter_excel,
)

router = APIRouter()


@router.post("/api/export")
async def export(
    file: UploadFile = File(...),
    decisions: str = Form(default="[]"),
    schema_enrichi: str = Form(default=""),
):
    decisions_parsed: list[DecisionHumain] = [
        DecisionHumain(**d) for d in json.loads(decisions)
    ]

    df = await lire_fichier(file)

    if schema_enrichi:
        schema = FichierSchema(**json.loads(schema_enrichi))
    else:
        echantillon = extraire_echantillon(df)
        schema = detecter_schema(echantillon)

    anomalies = detecter_anomalies(df, schema)
    df_propre = reconstruire_avec_decisions(df, anomalies, decisions_parsed)
    buffer = exporter_excel(df_propre)

    nom_fichier = f"cleaned_{file.filename or 'export.xlsx'}"

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nom_fichier}"'},
    )
