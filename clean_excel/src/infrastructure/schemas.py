from pydantic import BaseModel, Field


class ColonneSchema(BaseModel):
    nom: str
    type_attendu: str = Field(
        description="Type attendu parmi : texte, nombre, date, email, telephone"
    )
    description: str


class FichierSchema(BaseModel):
    colonnes: list[ColonneSchema]


class Anomalie(BaseModel):
    ligne: int
    colonne_actuelle: str
    valeur: str
    colonne_probable: str | None = None
    confiance: float = Field(ge=0.0, le=1.0)
    raison: str


class ResultatAnalyse(BaseModel):
    total_lignes: int
    total_colonnes: int
    total_anomalies: int
    schema_detecte: FichierSchema
    anomalies: list[Anomalie]
