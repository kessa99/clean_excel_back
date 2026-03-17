import io

import pandas as pd
from fastapi import HTTPException, UploadFile


async def lire_fichier(file: UploadFile) -> pd.DataFrame:
    contenu = await file.read()
    nom = file.filename or ""

    if nom.endswith(".csv"):
        return pd.read_csv(io.BytesIO(contenu))

    if nom.endswith(".xlsx"):
        return pd.read_excel(io.BytesIO(contenu), engine="openpyxl")

    if nom.endswith(".xls"):
        return pd.read_excel(io.BytesIO(contenu), engine="xlrd")

    raise HTTPException(
        status_code=400,
        detail=f"Format non supporté : '{nom}'. Formats acceptés : .xlsx, .xls, .csv",
    )


def extraire_echantillon(df: pd.DataFrame) -> dict:
    return {
        "headers": df.columns.tolist(),
        "lignes": df.head(20).astype(str).values.tolist(),
    }


def decouper_en_chunks(df: pd.DataFrame, taille: int = 100) -> list[pd.DataFrame]:
    return [df.iloc[i : i + taille] for i in range(0, len(df), taille)]
