import json

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate

from config import get_llm
from infrastructure.schemas import FichierSchema


_PROMPT = PromptTemplate(
    input_variables=["headers", "lignes"],
    template="""Tu es un expert en analyse de données tabulaires.

Voici les colonnes d'un fichier Excel :
{headers}

Voici un échantillon de données (50 premières lignes) :
{lignes}

Analyse ces données et retourne UNIQUEMENT un objet JSON valide décrivant chaque colonne.
N'ajoute aucun texte avant ou après le JSON.

Le JSON doit avoir cette structure exacte :
{{
  "colonnes": [
    {{
      "nom": "nom_de_la_colonne",
      "type_attendu": "texte|nombre|date|email|telephone",
      "description": "description courte du contenu attendu"
    }}
  ]
}}
""",
)


def detecter_schema(echantillon: dict) -> FichierSchema:
    llm = get_llm()
    parser = JsonOutputParser()
    chain = _PROMPT | llm | parser

    resultat = chain.invoke(
        {
            "headers": json.dumps(echantillon["headers"], ensure_ascii=False),
            "lignes": json.dumps(echantillon["lignes"], ensure_ascii=False),
        }
    )

    return FichierSchema(**resultat)
