import json

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import StreamingResponse

from infrastructure.schemas import DecisionHumain, FichierSchema, Anomalie
from infrastructure.services import lire_fichier, reconstruire_avec_decisions, exporter_excel

router = APIRouter()


@router.post("/api/export")
async def export(
    file: UploadFile = File(...),
    anomalies: str = Form(default="[]"),
    decisions: str = Form(default="[]"),
):
    anomalies_parsed: list[Anomalie] = [
        Anomalie(**a) for a in json.loads(anomalies)
    ]
    decisions_parsed: list[DecisionHumain] = [
        DecisionHumain(**d) for d in json.loads(decisions)
    ]

    df = await lire_fichier(file)
    df_propre = reconstruire_avec_decisions(df, anomalies_parsed, decisions_parsed)
    buffer = exporter_excel(df_propre)

    nom_fichier = f"cleaned_{file.filename or 'export.xlsx'}"

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nom_fichier}"'},
    )
