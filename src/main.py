from fastapi import FastAPI
from src.api.routes import router
from src.services.db_service import init_db

# Initialize DB on startup
init_db()

app = FastAPI(title="Research Paper RAG Assistant")
app.include_router(router)

@app.get("/")
def read_root():
    return {"message": "RAG API is running. Visit /docs for endpoints."}