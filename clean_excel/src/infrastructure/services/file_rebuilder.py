from io import BytesIO

import pandas as pd

from infrastructure.schemas import Anomalie


def reconstruire_fichier(df: pd.DataFrame, anomalies: list[Anomalie]) -> pd.DataFrame:
    df = df.copy()

    for anomalie in anomalies:
        if anomalie.colonne_probable is None or anomalie.confiance <= 0.7:
            continue

        if anomalie.colonne_probable not in df.columns:
            df[anomalie.colonne_probable] = None

        df.at[anomalie.ligne, anomalie.colonne_probable] = anomalie.valeur
        df.at[anomalie.ligne, anomalie.colonne_actuelle] = None

    return df


def exporter_excel(df: pd.DataFrame) -> BytesIO:
    buffer = BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    buffer.seek(0)
    return buffer
