import json
import re

import pandas as pd
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate

from config import get_llm
from infrastructure.schemas import Anomalie, FichierSchema
from infrastructure.services.excel_service import decouper_en_chunks


_TYPE_VALIDATORS = {
    "nombre": lambda v: not _est_numerique(v),
    "texte": lambda v: _est_numerique_strict(v),
    "email": lambda v: not _est_email(v),
    "telephone": lambda v: not _est_telephone(v),
    "date": lambda v: False,  # laissé à l'IA — trop ambigu pour Pandas
}


def _est_numerique(valeur: str) -> bool:
    try:
        float(valeur)
        return True
    except ValueError:
        return False


def _est_numerique_strict(valeur: str) -> bool:
    """Détecte un float pur dans une colonne texte (ex: 75000.0)."""
    return bool(re.fullmatch(r"-?\d+(\.\d+)?", valeur.strip()))


def _est_email(valeur: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", valeur.strip()))


def _est_telephone(valeur: str) -> bool:
    return bool(re.fullmatch(r"[\d\s\+\-\.\(\)]{7,15}", valeur.strip()))


_PROMPT_AMBIGUS = PromptTemplate(
    input_variables=["schema", "lignes"],
    template="""Tu es un expert en qualité de données.

Voici le schéma attendu du fichier (colonnes et leurs types) :
{schema}

Voici des lignes de données suspectes à analyser :
{lignes}

Pour chaque cellule dont la valeur semble mal placée dans sa colonne, retourne UNIQUEMENT un tableau JSON.
N'ajoute aucun texte avant ou après le JSON.

Format attendu :
[
  {{
    "ligne": <numéro de ligne entier>,
    "colonne_actuelle": "<nom de la colonne actuelle>",
    "valeur": "<valeur suspecte>",
    "colonne_probable": "<nom de la colonne où cette valeur devrait être, ou null>",
    "confiance": <float entre 0 et 1>,
    "raison": "<explication courte>"
  }}
]

Si aucune anomalie n'est détectée, retourne un tableau vide : []
""",
)


def filtrer_cas_evidents(
    chunk: pd.DataFrame, schema: FichierSchema
) -> tuple[list[Anomalie], pd.DataFrame]:
    types_par_colonne = {col.nom: col.type_attendu for col in schema.colonnes}
    anomalies: list[Anomalie] = []
    indices_evidents: set[int] = set()

    for col in chunk.columns:
        type_attendu = types_par_colonne.get(col)
        if not type_attendu or type_attendu not in _TYPE_VALIDATORS:
            continue

        est_anomalie = _TYPE_VALIDATORS[type_attendu]

        for idx, valeur in chunk[col].items():
            valeur_str = str(valeur).strip()
            if valeur_str in ("", "nan", "None"):
                continue
            if est_anomalie(valeur_str):
                anomalies.append(
                    Anomalie(
                        ligne=int(idx),
                        colonne_actuelle=col,
                        valeur=valeur_str,
                        colonne_probable=None,
                        confiance=0.95,
                        raison=f"Valeur incompatible avec le type attendu '{type_attendu}'",
                    )
                )
                indices_evidents.add(int(idx))

    lignes_ambigues = chunk.drop(index=list(indices_evidents), errors="ignore")
    return anomalies, lignes_ambigues


def analyser_cas_ambigus(
    lignes_ambigues: pd.DataFrame, schema: FichierSchema
) -> list[Anomalie]:
    if lignes_ambigues.empty:
        return []

    llm = get_llm()
    parser = JsonOutputParser()
    chain = _PROMPT_AMBIGUS | llm | parser

    lignes_json = lignes_ambigues.reset_index().astype(str).to_dict(orient="records")

    resultat = chain.invoke(
        {
            "schema": json.dumps(
                [col.model_dump() for col in schema.colonnes], ensure_ascii=False
            ),
            "lignes": json.dumps(lignes_json, ensure_ascii=False),
        }
    )

    anomalies = []
    for item in resultat:
        try:
            anomalies.append(Anomalie(**item))
        except Exception:
            continue

    return anomalies


def detecter_anomalies(df: pd.DataFrame, schema: FichierSchema) -> list[Anomalie]:
    chunks = decouper_en_chunks(df, taille=100)
    toutes_anomalies: list[Anomalie] = []

    for chunk in chunks:
        anomalies_evidentes, lignes_ambigues = filtrer_cas_evidents(chunk, schema)
        anomalies_ambigues = analyser_cas_ambigus(lignes_ambigues, schema)
        toutes_anomalies.extend(anomalies_evidentes)
        toutes_anomalies.extend(anomalies_ambigues)

    return toutes_anomalies
