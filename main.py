from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"version": "0.1.0"}
