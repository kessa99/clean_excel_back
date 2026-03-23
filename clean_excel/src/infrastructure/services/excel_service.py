import io
import re

import pandas as pd
from fastapi import HTTPException, UploadFile

from infrastructure.schemas import ColonneSchema, FichierSchema


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


def _detecter_type_colonne(serie: pd.Series) -> str:
    echantillon = serie.dropna().astype(str).head(20)
    if echantillon.empty:
        return "texte"

    if pd.api.types.is_numeric_dtype(serie):
        return "nombre"

    if pd.api.types.is_datetime64_any_dtype(serie):
        return "date"

    email_pattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    if echantillon.apply(lambda v: bool(email_pattern.match(v.strip()))).mean() > 0.7:
        return "email"

    tel_pattern = re.compile(r"^[\d\s\+\-\.\(\)]{7,15}$")
    if echantillon.apply(lambda v: bool(tel_pattern.match(v.strip()))).mean() > 0.7:
        return "telephone"

    date_patterns = [
        re.compile(r"^\d{2}/\d{2}/\d{4}$"),
        re.compile(r"^\d{4}-\d{2}-\d{2}$"),
        re.compile(r"^\d{2}-\d{2}-\d{4}$"),
    ]
    for pat in date_patterns:
        if echantillon.apply(lambda v: bool(pat.match(v.strip()))).mean() > 0.7:
            return "date"

    nombre_pattern = re.compile(r"^-?\d+(\.\d+)?$")
    if echantillon.apply(lambda v: bool(nombre_pattern.match(v.strip()))).mean() > 0.7:
        return "nombre"

    return "texte"


def detecter_schema_pandas(df: pd.DataFrame) -> FichierSchema:
    colonnes = []
    for col in df.columns:
        type_attendu = _detecter_type_colonne(df[col])
        colonnes.append(
            ColonneSchema(
                nom=col,
                type_attendu=type_attendu,
                description="",
                exemples=[],
            )
        )
    return FichierSchema(colonnes=colonnes)


def decouper_en_chunks(df: pd.DataFrame, taille: int = 100) -> list[pd.DataFrame]:
    return [df.iloc[i : i + taille] for i in range(0, len(df), taille)]
