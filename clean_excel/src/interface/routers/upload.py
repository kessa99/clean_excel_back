from fastapi import APIRouter, UploadFile, File

from infrastructure.schemas import ResultatAnalyse, FichierSchema
from infrastructure.services import lire_fichier, detecter_schema_pandas

router = APIRouter()


@router.post("/api/upload", response_model=FichierSchema)
async def upload(file: UploadFile = File(...)):
    df = await lire_fichier(file)
    schema = detecter_schema_pandas(df)
    return schema
