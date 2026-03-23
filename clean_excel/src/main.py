from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from interface.routers import upload_router, analyse_router, export_router

app = FastAPI(
    title="Clean Excel API",
    description="Détecte et corrige les données mal placées dans les fichiers Excel.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router)
app.include_router(analyse_router)
app.include_router(export_router)
