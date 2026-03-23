# Clean Excel — Documentation du projet

## Présentation

**Clean Excel** est une application web qui analyse des fichiers Excel et détecte automatiquement les données mal placées dans les mauvaises colonnes. Elle utilise un LLM (modèle de langage) pour comprendre le contexte métier du fichier et proposer des corrections, tout en impliquant l'utilisateur pour valider les cas incertains.

---

## Le problème

Dans les fichiers Excel comptables ou métier (exports SYSCOHADA, journaux comptables, bases clients...), il est fréquent de retrouver des données dans les mauvaises colonnes :

- Un numéro de compte `101300` qui se retrouve dans la colonne `date_compta`
- Un email `john@gmail.com` stocké dans la colonne `nom`
- Un montant `75000.0` dans une colonne de type texte
- Des valeurs inversées entre deux colonnes suite à une mauvaise saisie

Ces erreurs passent souvent inaperçues dans Excel car le fichier s'ouvre sans erreur. Elles corrompent pourtant les analyses, les imports en base de données et les rapports financiers. Les corriger manuellement sur des fichiers de centaines ou milliers de lignes est chronophage et source de nouvelles erreurs.

---

## Ce que fait l'application

1. L'utilisateur **uploade un fichier Excel**
2. L'application **analyse automatiquement** la structure du fichier (colonnes, types attendus) via un LLM
3. Elle **détecte les anomalies** — valeurs incompatibles avec leur colonne
4. L'utilisateur voit les anomalies et peut **enrichir le schéma** (ajouter descriptions et exemples par colonne) pour affiner la détection
5. Pour les cas incertains, l'application **demande confirmation humaine** : supprimer, garder ou déplacer vers une autre colonne
6. Un clic sur "Clean" génère un **fichier Excel corrigé** à télécharger

---

## Stack technique

| Composant | Technologie |
|---|---|
| API backend | FastAPI + Uvicorn |
| LLM (IA) | Multi-provider via LangChain : Anthropic Claude, OpenAI GPT-4o, Mistral, Groq, Gemini, xAI Grok |
| Traitement données | Pandas + OpenPyXL |
| Validation schémas | Pydantic v2 |
| Configuration | pydantic-settings + fichier `.env` |
| Packaging | Poetry |
| Qualité code | Ruff (lint), mypy (types), pytest (tests) |

---

## Architecture du projet

```
clean_excel/
├── src/
│   ├── main.py                            # Point d'entrée FastAPI + middleware CORS
│   │
│   ├── config/
│   │   ├── settings.py                    # Lecture des variables d'environnement
│   │   └── llm_factory.py                 # Instancie le bon LLM selon la clé dispo
│   │
│   ├── infrastructure/
│   │   ├── schemas.py                     # Modèles Pydantic (données entrantes/sortantes)
│   │   └── services/
│   │       ├── excel_service.py           # Lecture fichier, échantillonnage, découpage chunks
│   │       ├── schema_detector.py         # LLM → inférence du schéma du fichier
│   │       ├── anomaly_detector.py        # Détection des anomalies (regex + LLM)
│   │       └── file_rebuilder.py          # Reconstruction et export du fichier nettoyé
│   │
│   └── interface/
│       └── routers/
│           ├── upload.py                  # POST /api/upload
│           └── export.py                  # POST /api/export
│
├── tests/                                 # Tests unitaires et d'intégration
├── docs/                                  # Documentation
├── pyproject.toml                         # Dépendances et config Poetry
└── .env                                   # Clés API (non versionné)
```

---

## Modèles de données

### `ColonneSchema` — Une colonne du fichier
```json
{
  "nom": "date_compta",
  "type_attendu": "date",
  "description": "Date de comptabilité au format JJ/MM/AAAA",
  "exemples": ["01/01/2024", "15/03/2024"]
}
```
Types supportés : `texte`, `nombre`, `date`, `email`, `telephone`

Les `exemples` sont optionnels à la détection automatique. L'utilisateur peut les enrichir dans l'interface pour améliorer la précision du LLM.

---

### `Anomalie` — Une donnée mal placée détectée
```json
{
  "ligne": 0,
  "colonne_actuelle": "date_compta",
  "valeur": "101300",
  "colonne_probable": null,
  "confiance": 0.95,
  "raison": "Valeur incompatible avec le type attendu 'date'",
  "necessite_confirmation": true
}
```

| Champ | Description |
|---|---|
| `ligne` | Index de la ligne dans le fichier (commence à 0) |
| `colonne_actuelle` | Colonne où la valeur se trouve actuellement |
| `valeur` | La valeur suspecte |
| `colonne_probable` | Colonne destination suggérée, ou `null` si inconnue |
| `confiance` | Score entre 0.0 et 1.0 |
| `necessite_confirmation` | `true` = l'utilisateur doit trancher |

---

### `DecisionHumain` — Choix de l'utilisateur sur une anomalie incertaine
```json
{
  "ligne": 0,
  "colonne_actuelle": "date_compta",
  "action": "supprimer",
  "colonne_cible": null
}
```

| `action` | Effet |
|---|---|
| `"supprimer"` | La cellule est vidée |
| `"garder"` | Rien ne change |
| `"deplacer"` | La valeur est déplacée vers `colonne_cible`, cellule actuelle vidée |

---

### `ResultatAnalyse` — Réponse de `/api/upload`
```json
{
  "total_lignes": 65,
  "total_colonnes": 24,
  "total_anomalies": 3,
  "schema_detecte": {
    "colonnes": [ ... ]
  },
  "anomalies": [ ... ]
}
```

---

## Endpoints API

### `POST /api/upload`

Analyse un fichier Excel et retourne le schéma détecté + les anomalies trouvées.

**Request :** `multipart/form-data`
```
file: File   (.xlsx, .xls, .csv)
```

**Response :** `200 application/json` — `ResultatAnalyse`

---

### `POST /api/export`

Applique les corrections et retourne le fichier Excel nettoyé.

**Request :** `multipart/form-data`
```
file           : File     Même fichier que l'upload
decisions      : string   JSON — liste de DecisionHumain (défaut: "[]")
schema_enrichi : string   JSON — FichierSchema enrichi par l'utilisateur (défaut: "")
```

Si `schema_enrichi` est fourni → l'appel LLM de détection de schéma est sauté (économie de tokens).

**Response :** `200 application/octet-stream` — fichier `.xlsx` en téléchargement

---

## Workflow détaillé

### Phase 1 — Upload et analyse

```
Fichier Excel
    │
    ▼
lire_fichier()
    Lit le fichier avec Pandas (xlsx, xls, csv)
    │
    ▼
extraire_echantillon()
    Extrait les en-têtes + les 50 premières lignes
    │
    ▼
detecter_schema()  ──── Appel LLM n°1
    Envoie les en-têtes + l'échantillon au LLM
    Le LLM identifie le type et la description de chaque colonne
    Retourne : FichierSchema
    │
    ▼
detecter_anomalies()
    Traite le fichier complet par chunks de 30 lignes
    │
    ├── filtrer_cas_evidents()   [regex, pas de LLM]
    │       Valide chaque valeur contre le type attendu de sa colonne
    │       Exemples détectés :
    │         - nombre dans colonne date → anomalie évidente
    │         - texte pur dans colonne nombre → anomalie évidente
    │         - valeur non-email dans colonne email → anomalie évidente
    │       Résultat : liste d'Anomalie avec confiance=0.95, colonne_probable=null
    │
    ├── enrichir_destinations()  ──── Appel LLM n°2
    │       Pour chaque anomalie évidente sans destination connue,
    │       demande au LLM : "dans quelle colonne cette valeur devrait-elle être ?"
    │       Si le LLM trouve une colonne valide → necessite_confirmation = false
    │       Si le LLM ne sait pas → necessite_confirmation = true
    │
    └── analyser_cas_ambigus()   ──── Appel LLM n°3
            Envoie les lignes non flaggées à l'étape précédente
            Le LLM cherche des anomalies subtiles (valeurs hors contexte métier)
            confiance >= 0.85 + colonne connue → necessite_confirmation = false
            confiance < 0.85 ou colonne inconnue → necessite_confirmation = true

    ▼
Retourne : ResultatAnalyse
```

### Phase 2 — Interaction utilisateur

```
Panneau gauche — Schéma détecté :
  Pour chaque colonne :
    - Nom + type (texte / nombre / date / ...)
    - Description auto-générée
    - [Optionnel] L'utilisateur enrichit :
        → Description plus précise
        → Exemples de valeurs valides
          ex: compte → ["101300", "401000", "512000"]

Liste des anomalies :
  necessite_confirmation = false
    → Affichées comme "seront corrigées automatiquement"
    → ex: "john@gmail.com déplacé de 'nom' vers 'email'"

  necessite_confirmation = true
    → L'utilisateur doit choisir :
        [Supprimer]            → cellule vidée
        [Garder]               → rien ne change
        [Déplacer vers ▼]     → sélectionner la colonne cible
        [X ignorer]            → anomalie exclue du traitement
```

### Phase 3 — Export et nettoyage

```
Fichier original + decisions + schema_enrichi (optionnel)
    │
    ▼
Si schema_enrichi fourni  →  utilise le schéma utilisateur (0 appel LLM schéma)
Sinon                     →  re-détecte le schéma (1 appel LLM)
    │
    ▼
detecter_anomalies() avec le schéma enrichi
    Les exemples fournis par l'utilisateur enrichissent les prompts LLM
    → meilleure précision, même avec un modèle moins puissant
    │
    ▼
reconstruire_avec_decisions()
    Pour chaque anomalie :

    necessite_confirmation = true :
      action "supprimer"  → df.at[ligne, colonne] = None
      action "deplacer"   → valeur copiée vers colonne_cible, cellule vidée
      action "garder"     → aucun changement
      pas de décision     → aucun changement (sécurité)

    necessite_confirmation = false :
      colonne_probable connue → valeur déplacée automatiquement
      colonne_probable null   → cellule vidée (valeur clairement invalide)
      confiance <= 0.7        → ignorée (trop incertaine)
    │
    ▼
exporter_excel()
    Génère un fichier .xlsx en mémoire (BytesIO)
    │
    ▼
StreamingResponse → téléchargement automatique côté client
```

---

## Multi-provider LLM

L'application supporte plusieurs fournisseurs de LLM. La sélection est automatique selon les clés présentes dans `.env`, par ordre de priorité :

| Priorité | Fournisseur | Modèle | Remarque |
|---|---|---|---|
| 1 | Anthropic | claude-3-5-sonnet-20241022 | Meilleure qualité |
| 2 | OpenAI | gpt-4o | Très performant |
| 3 | Mistral | mistral-large-latest | Bon rapport qualité/prix |
| 4 | xAI Grok | grok-3 | Clé préfixe `xai-` |
| 5 | Google Gemini | gemini-2.0-flash | Clé préfixe `AIza` |
| 6 | Groq | llama-3.1-8b-instant | Gratuit, limité en tokens/jour |

---

## Optimisation des tokens

L'enrichissement du schéma par l'utilisateur réduit directement les coûts LLM :

| Sans enrichissement | Avec enrichissement |
|---|---|
| Le LLM doit deviner le sens de chaque colonne | Le LLM a une description + exemples → moins d'inférence |
| 3 appels LLM complets à chaque export | Schema skipé si fourni → 2 appels LLM |
| Gros modèle requis pour la précision | Petit modèle (llama-3.1-8b) suffisant avec bon contexte |

---

## Installation et lancement local

### Prérequis
- Python 3.11+
- Poetry

### Clés API
Créer un fichier `.env` dans `clean_excel/` :
```env
# Choisir au moins un fournisseur
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
MISTRAL_API_KEY=...
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=AIza...
GROK_API_KEY=xai-...
```

### Commandes
```bash
cd clean_excel

# Installer les dépendances
poetry install

# Lancer le serveur
PYTHONPATH=src poetry run uvicorn main:app --reload --port 8001
```

API disponible sur : `http://127.0.0.1:8001`
Documentation interactive (Swagger) : `http://127.0.0.1:8001/docs`

---

## Limites connues

| Limite | Détail |
|---|---|
| Rate limit Groq (plan gratuit) | 100k tokens/jour, 6k tokens/min |
| Fichiers volumineux | Chunking par 30 lignes — les très gros fichiers génèrent beaucoup d'appels LLM |
| Type `date` | Non validé par regex (trop ambigu) — entièrement délégué au LLM |
| CORS | Configuré pour `http://localhost:8080` uniquement — à adapter en production |
