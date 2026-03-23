import json

from fastapi import APIRouter, File, Form, UploadFile

from infrastructure.schemas import FichierSchema, ResultatAnalyse
from infrastructure.services import lire_fichier, detecter_anomalies

router = APIRouter()


@router.post("/api/analyse", response_model=ResultatAnalyse)
async def analyse(
    file: UploadFile = File(...),
    schema_enrichi: str = Form(...),
):
    df = await lire_fichier(file)
    schema = FichierSchema(**json.loads(schema_enrichi))
    anomalies = detecter_anomalies(df, schema)

    return ResultatAnalyse(
        total_lignes=len(df),
        total_colonnes=len(df.columns),
        total_anomalies=len(anomalies),
        schema_detecte=schema,
        anomalies=anomalies,
    )
