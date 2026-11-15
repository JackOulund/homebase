from fastapi import FastAPI

app = FastAPI(title="homebase")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
