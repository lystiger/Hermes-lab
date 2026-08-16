from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    return {"status": "ready"}


@app.get("/version")
def version():
    return {"version": "0.1.0"}


@app.get("/info")
def info():
    return {
        "name": "Hermes Lab",
        "version": "0.1.0",
        "environment": "development",
    }


@app.get("/metrics")
def metrics():
    return {
        "uptime_seconds": 0,
        "requests_handled": 0,
    }
