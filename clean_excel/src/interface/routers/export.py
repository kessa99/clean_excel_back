from fastapi import APIRouter, UploadFile, File
from fastapi.responses import StreamingResponse

from infrastructure.services import (
    lire_fichier,
    extraire_echantillon,
    detecter_schema,
    detecter_anomalies,
    reconstruire_fichier,
    exporter_excel,
)

router = APIRouter()


@router.post("/api/export")
async def export(file: UploadFile = File(...)):
    df = await lire_fichier(file)
    echantillon = extraire_echantillon(df)
    schema = detecter_schema(echantillon)
    anomalies = detecter_anomalies(df, schema)
    df_propre = reconstruire_fichier(df, anomalies)
    buffer = exporter_excel(df_propre)

    nom_fichier = f"cleaned_{file.filename or 'export.xlsx'}"

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nom_fichier}"'},
    )
