# ── Stage 1 : builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Installer poetry
RUN pip install --no-cache-dir poetry==2.3.2

# Copier uniquement les fichiers de dépendances pour profiter du cache Docker
COPY pyproject.toml poetry.lock ./

# Installer les dépendances dans un venv isolé (sans le projet lui-même)
RUN poetry config virtualenvs.in-project true \
    && poetry install --only main --no-root --no-interaction --no-ansi


# ── Stage 2 : runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Utilisateur non-root pour la sécurité
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Copier le venv construit dans le stage builder
COPY --from=builder /app/.venv /app/.venv

# Copier le code source
COPY src/ ./src/

# S'assurer que le venv est utilisé
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
