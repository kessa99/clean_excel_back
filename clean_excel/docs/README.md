# Clean Excel — Documentation

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Architecture du projet](#2-architecture-du-projet)
3. [Workflow complet](#3-workflow-complet)
4. [API Reference](#4-api-reference)
   - [POST /api/upload](#post-apiupload)
   - [POST /api/export](#post-apiexport)
5. [Modèles de données](#5-modèles-de-données)
6. [Gestion des erreurs](#6-gestion-des-erreurs)
7. [Guide d'intégration Frontend](#7-guide-dintégration-frontend)
8. [Configuration & démarrage](#8-configuration--démarrage)

---

## 1. Vue d'ensemble

**Clean Excel** est une API REST qui permet de :

1. Uploader un fichier Excel (ou CSV) dont la structure est inconnue à l'avance
2. Détecter automatiquement les données mal placées dans les mauvaises colonnes
3. Réorganiser intelligemment ces données
4. Télécharger le fichier corrigé

### Problème résolu

Dans beaucoup d'entreprises, les fichiers Excel arrivent corrompus structurellement : un salaire (`75000`) dans une colonne `Nom`, une ville (`Paris`) dans une colonne `Age`. L'API combine deux couches de détection :

- **Couche Pandas** — règles déterministes pour les cas évidents (type mismatch)
- **Couche IA (LangChain)** — analyse sémantique pour les cas ambigus

---

## 2. Architecture du projet

Le projet suit la **Clean Architecture** (aussi appelée Architecture Hexagonale). Le principe central : les couches internes ne dépendent jamais des couches externes.

```
src/
├── config/                     # Configuration globale
│   ├── settings.py             # Variables d'environnement (pydantic-settings)
│   └── llm_factory.py          # Initialisation du modèle LLM avec fallback
│
├── domain/                     # (réservé) Entités métier pures, sans framework
│
├── infrastructure/             # Implémentations techniques
│   ├── schemas.py              # Modèles Pydantic (ColonneSchema, Anomalie, etc.)
│   └── services/
│       ├── excel_service.py    # Lecture de fichiers, extraction d'échantillon, chunking
│       ├── schema_detector.py  # Détection du schéma via LangChain
│       ├── anomaly_detector.py # Détection des anomalies (Pandas + LangChain)
│       └── file_rebuilder.py   # Reconstruction et export du fichier corrigé
│
├── application/                # (réservé) Use cases métier
│
├── interface/                  # Couche présentation (FastAPI)
│   └── routers/
│       ├── upload.py           # Route POST /api/upload
│       └── export.py           # Route POST /api/export
│
└── main.py                     # Point d'entrée FastAPI
```

### Règle de dépendance

```
interface → infrastructure → config
              ↑
           (domain ← aucune dépendance externe)
```

- `interface` connaît `infrastructure` mais pas l'inverse
- `infrastructure` connaît `config` pour obtenir le LLM
- `domain` est agnostique de tout framework (FastAPI, Pandas, LangChain)

---

## 3. Workflow complet

### Étape 1 — Upload et lecture

```
Fichier (.xlsx / .xls / .csv)
        │
        ▼
lire_fichier()  →  pd.DataFrame
```

Le fichier est lu en mémoire via `pandas`. Aucune écriture sur disque.

---

### Étape 2 — Extraction d'échantillon

```
pd.DataFrame
      │
      ▼
extraire_echantillon()
      │
      ▼
{ "headers": ["Nom", "Age", "Email", ...],
  "lignes": [["Alice", "75000", "paris@..."], ...] }
```

Les 50 premières lignes sont extraites pour être envoyées à l'IA. Toutes les valeurs sont converties en `str` pour éviter les problèmes de sérialisation (NaN, Timestamp).

---

### Étape 3 — Détection du schéma (IA)

```
Échantillon (headers + 50 lignes)
        │
        ▼
  Prompt LangChain
        │
        ▼
     LLM (Anthropic / OpenAI / Mistral)
        │
        ▼
  JsonOutputParser
        │
        ▼
FichierSchema
  colonnes: [
    { nom: "Nom",   type_attendu: "texte",   description: "..." },
    { nom: "Age",   type_attendu: "nombre",  description: "..." },
    { nom: "Email", type_attendu: "email",   description: "..." },
    ...
  ]
```

L'IA analyse les headers et un échantillon de données pour inférer ce que chaque colonne **devrait** contenir.

**Modèles LLM supportés (par ordre de priorité) :**

| Priorité | Modèle                  | Clé requise         |
|----------|-------------------------|---------------------|
| 1        | claude-3-5-sonnet       | `ANTHROPIC_API_KEY` |
| 2        | gpt-4o                  | `OPENAI_API_KEY`    |
| 3        | mistral-large-latest    | `MISTRAL_API_KEY`   |

---

### Étape 4 — Détection des anomalies (Pandas + IA)

Le DataFrame est découpé en **chunks de 100 lignes**. Pour chaque chunk :

#### 4a — Couche Pandas (cas évidents)

| Type attendu | Anomalie détectée                             | Confiance |
|--------------|-----------------------------------------------|-----------|
| `nombre`     | Valeur non numérique dans la colonne          | 0.95      |
| `texte`      | Nombre pur (`75000.0`) dans la colonne        | 0.95      |
| `email`      | Valeur ne respectant pas `xxx@xxx.xxx`        | 0.95      |
| `telephone`  | Valeur ne respectant pas le format téléphone  | 0.95      |
| `date`       | Délégué à l'IA (trop ambigu pour des règles)  | —         |

Les lignes contenant des anomalies évidentes sont **extraites** et ne sont pas renvoyées à l'IA.

#### 4b — Couche LangChain (cas ambigus)

Les lignes restantes (sans anomalie évidente) sont envoyées à l'IA avec le schéma. L'IA retourne un tableau JSON d'anomalies avec :
- la colonne actuelle
- la valeur suspecte
- la colonne probable de destination
- un score de confiance (0 à 1)
- une raison textuelle

---

### Étape 5 — Reconstruction

```
Pour chaque anomalie :
  si colonne_probable != null ET confiance > 0.7 :
    → Créer colonne_probable si elle n'existe pas
    → Copier la valeur dans colonne_probable
    → Vider la cellule dans colonne_actuelle
```

---

### Étape 6 — Export

Le DataFrame corrigé est converti en fichier `.xlsx` via `openpyxl` et retourné en streaming (`BytesIO`). Aucun fichier n'est écrit sur le serveur.

---

## 4. API Reference

### POST /api/upload

Analyse un fichier Excel et retourne un rapport JSON des anomalies détectées.

#### Request

```
POST /api/upload
Content-Type: multipart/form-data
```

| Champ | Type   | Obligatoire | Description                        |
|-------|--------|-------------|------------------------------------|
| file  | File   | ✅           | Fichier `.xlsx`, `.xls` ou `.csv`  |

#### Response — 200 OK

```json
{
  "total_lignes": 150,
  "total_colonnes": 5,
  "total_anomalies": 3,
  "schema_detecte": {
    "colonnes": [
      {
        "nom": "Nom",
        "type_attendu": "texte",
        "description": "Prénom et nom de famille de l'employé"
      },
      {
        "nom": "Salaire",
        "type_attendu": "nombre",
        "description": "Salaire mensuel brut en euros"
      },
      {
        "nom": "Email",
        "type_attendu": "email",
        "description": "Adresse email professionnelle"
      }
    ]
  },
  "anomalies": [
    {
      "ligne": 4,
      "colonne_actuelle": "Nom",
      "valeur": "75000",
      "colonne_probable": "Salaire",
      "confiance": 0.95,
      "raison": "Valeur incompatible avec le type attendu 'texte'"
    },
    {
      "ligne": 12,
      "colonne_actuelle": "Age",
      "valeur": "Paris",
      "colonne_probable": "Ville",
      "confiance": 0.87,
      "raison": "Le mot 'Paris' est une ville, pas un âge"
    },
    {
      "ligne": 23,
      "colonne_actuelle": "Email",
      "valeur": "0612345678",
      "colonne_probable": "Telephone",
      "confiance": 0.91,
      "raison": "Format téléphone détecté dans une colonne email"
    }
  ]
}
```

#### Response — 400 Bad Request

```json
{
  "detail": "Format non supporté : 'fichier.pdf'. Formats acceptés : .xlsx, .xls, .csv"
}
```

---

### POST /api/export

Analyse le fichier, corrige les anomalies et retourne le fichier Excel nettoyé en téléchargement.

#### Request

```
POST /api/export
Content-Type: multipart/form-data
```

| Champ | Type   | Obligatoire | Description                        |
|-------|--------|-------------|------------------------------------|
| file  | File   | ✅           | Fichier `.xlsx`, `.xls` ou `.csv`  |

#### Response — 200 OK

```
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="cleaned_mon_fichier.xlsx"

[binary Excel file]
```

Le fichier retourné est un `.xlsx` avec :
- Les valeurs mal placées déplacées dans leurs colonnes correctes
- Les nouvelles colonnes créées si nécessaire
- Uniquement les anomalies avec `confiance > 0.7` et `colonne_probable != null` sont corrigées

#### Response — 400 Bad Request

```json
{
  "detail": "Format non supporté : 'fichier.pdf'. Formats acceptés : .xlsx, .xls, .csv"
}
```

---

## 5. Modèles de données

### ColonneSchema

| Champ         | Type   | Description                                               |
|---------------|--------|-----------------------------------------------------------|
| nom           | string | Nom exact de la colonne dans le fichier                   |
| type_attendu  | string | `texte` \| `nombre` \| `date` \| `email` \| `telephone`  |
| description   | string | Description du contenu attendu (générée par l'IA)         |

### FichierSchema

| Champ    | Type               | Description                        |
|----------|--------------------|------------------------------------|
| colonnes | ColonneSchema[]    | Liste des colonnes détectées        |

### Anomalie

| Champ             | Type           | Description                                                    |
|-------------------|----------------|----------------------------------------------------------------|
| ligne             | integer        | Index de la ligne dans le DataFrame (commence à 0)            |
| colonne_actuelle  | string         | Colonne où la valeur est actuellement mal placée               |
| valeur            | string         | La valeur suspecte                                             |
| colonne_probable  | string \| null | Colonne où la valeur devrait probablement être                 |
| confiance         | float [0-1]    | Score de confiance de la détection                            |
| raison            | string         | Explication textuelle de l'anomalie                           |

### ResultatAnalyse

| Champ           | Type           | Description                                    |
|-----------------|----------------|------------------------------------------------|
| total_lignes    | integer        | Nombre total de lignes dans le fichier         |
| total_colonnes  | integer        | Nombre total de colonnes dans le fichier       |
| total_anomalies | integer        | Nombre d'anomalies détectées                   |
| schema_detecte  | FichierSchema  | Schéma inféré par l'IA                         |
| anomalies       | Anomalie[]     | Liste complète des anomalies                   |

---

## 6. Gestion des erreurs

| Code HTTP | Cause                                      | Message type                                    |
|-----------|--------------------------------------------|-------------------------------------------------|
| 400       | Format de fichier non supporté             | `"Format non supporté : '.pdf'..."`             |
| 500       | Aucune clé API configurée                  | `"Aucune clé API disponible..."`                |
| 500       | Erreur interne (parsing IA, pandas, etc.)  | `"Internal Server Error"`                       |

---

## 7. Guide d'intégration Frontend

### Exemple — Appel à /api/upload (JavaScript fetch)

```javascript
async function analyserFichier(file) {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch('http://localhost:8000/api/upload', {
    method: 'POST',
    body: formData,
    // Ne pas définir Content-Type manuellement — fetch le fait automatiquement
  });

  if (!response.ok) {
    const erreur = await response.json();
    throw new Error(erreur.detail);
  }

  const resultat = await response.json();
  // resultat = { total_lignes, total_colonnes, total_anomalies, schema_detecte, anomalies }
  return resultat;
}
```

### Exemple — Appel à /api/export et téléchargement (JavaScript fetch)

```javascript
async function exporterFichierNettoye(file) {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch('http://localhost:8000/api/export', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const erreur = await response.json();
    throw new Error(erreur.detail);
  }

  // Récupérer le blob binaire et déclencher le téléchargement
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `cleaned_${file.name}`;
  a.click();
  URL.revokeObjectURL(url);
}
```

### Exemple — Axios

```javascript
import axios from 'axios';

async function analyserFichier(file) {
  const formData = new FormData();
  formData.append('file', file);

  const { data } = await axios.post('http://localhost:8000/api/upload', formData);
  return data;
}

async function exporterFichierNettoye(file) {
  const formData = new FormData();
  formData.append('file', file);

  const response = await axios.post('http://localhost:8000/api/export', formData, {
    responseType: 'blob',
  });

  const url = URL.createObjectURL(response.data);
  const a = document.createElement('a');
  a.href = url;
  a.download = `cleaned_${file.name}`;
  a.click();
  URL.revokeObjectURL(url);
}
```

### Headers CORS

Le serveur accepte toutes les origines (`*`). Aucune configuration CORS côté frontend nécessaire en développement.

### Points d'attention

- Ne pas définir `Content-Type: multipart/form-data` manuellement — le navigateur/axios le fait avec le bon `boundary`
- `/api/export` peut être lent (analyse complète + appel IA) — prévoir un indicateur de chargement
- L'index de ligne dans `Anomalie.ligne` correspond à l'index pandas (commence à 0, correspond à la ligne de données, pas au header)

---

## 8. Configuration & démarrage

### Variables d'environnement

Créer un fichier `.env` à la racine du projet (`clean_excel/`) en copiant `.env.example` :

```bash
cp .env.example .env
```

Renseigner au moins **une** des trois clés :

```env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
MISTRAL_API_KEY=...
```

La priorité de sélection du modèle est : **Anthropic → OpenAI → Mistral**.

### Installation et démarrage

```bash
# Installer les dépendances
cd clean_excel
poetry install

# Lancer le serveur de développement
PYTHONPATH=src .venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Documentation interactive (Swagger)

FastAPI génère automatiquement une interface Swagger disponible à :

```
http://localhost:8000/docs
```

Et la version ReDoc à :

```
http://localhost:8000/redoc
```
