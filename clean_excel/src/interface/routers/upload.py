from fastapi import APIRouter, UploadFile, File

from infrastructure.schemas import ResultatAnalyse
from infrastructure.services import (
    lire_fichier,
    extraire_echantillon,
    detecter_schema,
    detecter_anomalies,
)

router = APIRouter()


@router.post("/api/upload", response_model=ResultatAnalyse)
async def upload(file: UploadFile = File(...)):
    df = await lire_fichier(file)
    echantillon = extraire_echantillon(df)
    schema = detecter_schema(echantillon)
    anomalies = detecter_anomalies(df, schema)

    return ResultatAnalyse(
        total_lignes=len(df),
        total_colonnes=len(df.columns),
        total_anomalies=len(anomalies),
        schema_detecte=schema,
        anomalies=anomalies,
    )
