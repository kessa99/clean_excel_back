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
    "date": lambda v: False,
}


def _est_numerique(valeur: str) -> bool:
    try:
        float(valeur)
        return True
    except ValueError:
        return False


def _est_numerique_strict(valeur: str) -> bool:
    return bool(re.fullmatch(r"-?\d+(\.\d+)?", valeur.strip()))


def _est_email(valeur: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", valeur.strip()))


def _est_telephone(valeur: str) -> bool:
    return bool(re.fullmatch(r"[\d\s\+\-\.\(\)]{7,15}", valeur.strip()))


_PROMPT_FUSIONNE = PromptTemplate(
    input_variables=["schema", "anomalies_evidentes", "lignes_ambigues"],
    template="""Tu es un expert en qualité de données.

Voici le schéma du fichier. Pour chaque colonne : nom, type attendu, description et exemples de valeurs valides :
{schema}

TÂCHE 1 — Ces valeurs ont été détectées comme incompatibles avec leur colonne.
Pour chacune, identifie la colonne du schéma où elle devrait se trouver (ou null si vraiment inconnue) :
{anomalies_evidentes}

TÂCHE 2 — Analyse ces lignes et détecte toute valeur mal placée dans sa colonne :
{lignes_ambigues}

Retourne UNIQUEMENT ce JSON, sans aucun texte avant ou après :
{{
  "destinations": [
    {{
      "ligne": <int>,
      "colonne_actuelle": "<colonne actuelle>",
      "colonne_probable": "<colonne du schéma ou null>"
    }}
  ],
  "anomalies": [
    {{
      "ligne": <int>,
      "colonne_actuelle": "<colonne>",
      "valeur": "<valeur suspecte>",
      "colonne_probable": "<colonne destination ou null>",
      "confiance": <float 0-1>,
      "raison": "<explication courte>"
    }}
  ]
}}

Si aucune anomalie pour la tâche 2, retourne "anomalies": [].
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


def analyser_chunk(
    anomalies_evidentes: list[Anomalie],
    lignes_ambigues: pd.DataFrame,
    schema: FichierSchema,
) -> list[Anomalie]:
    if not anomalies_evidentes and lignes_ambigues.empty:
        return []

    llm = get_llm()
    parser = JsonOutputParser()
    chain = _PROMPT_FUSIONNE | llm | parser

    schema_json = json.dumps(
        [col.model_dump() for col in schema.colonnes], ensure_ascii=False
    )
    anomalies_json = json.dumps(
        [
            {
                "ligne": a.ligne,
                "colonne_actuelle": a.colonne_actuelle,
                "valeur": a.valeur,
            }
            for a in anomalies_evidentes
        ],
        ensure_ascii=False,
    )
    lignes_json = json.dumps(
        lignes_ambigues.reset_index().astype(str).to_dict(orient="records"),
        ensure_ascii=False,
    )

    try:
        resultat = chain.invoke(
            {
                "schema": schema_json,
                "anomalies_evidentes": anomalies_json,
                "lignes_ambigues": lignes_json,
            }
        )
    except Exception:
        return anomalies_evidentes

    colonnes_valides = {col.nom for col in schema.colonnes}

    destinations: dict[tuple[int, str], str | None] = {
        (item["ligne"], item["colonne_actuelle"]): item.get("colonne_probable")
        for item in resultat.get("destinations", [])
        if isinstance(item, dict)
    }

    toutes: list[Anomalie] = []

    for a in anomalies_evidentes:
        dest = destinations.get((a.ligne, a.colonne_actuelle))
        colonne_probable = dest if dest and dest in colonnes_valides else None
        toutes.append(
            a.model_copy(
                update={
                    "colonne_probable": colonne_probable,
                    "necessite_confirmation": colonne_probable is None,
                }
            )
        )

    for item in resultat.get("anomalies", []):
        try:
            a = Anomalie(**item)
            if a.confiance < 0.85 or a.colonne_probable is None:
                a = a.model_copy(update={"necessite_confirmation": True})
            toutes.append(a)
        except Exception:
            continue

    return toutes


def detecter_anomalies(df: pd.DataFrame, schema: FichierSchema) -> list[Anomalie]:
    chunks = decouper_en_chunks(df, taille=50)
    toutes_anomalies: list[Anomalie] = []

    for chunk in chunks:
        anomalies_evidentes, lignes_ambigues = filtrer_cas_evidents(chunk, schema)
        anomalies = analyser_chunk(anomalies_evidentes, lignes_ambigues, schema)
        toutes_anomalies.extend(anomalies)

    return toutes_anomalies
