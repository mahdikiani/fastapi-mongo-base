from pathlib import Path

from server import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn

    module = Path(__file__).stem
    uvicorn.run(
        f"{module}:app",
        host="0.0.0.0",
        port=8000,
        access_log=True,
    )
