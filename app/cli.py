"""CLI entry points for running the application."""
import sys
import uvicorn


def main():
    """Run the FastAPI application with uvicorn."""
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
    )


def dev():
    """Run the FastAPI application with uvicorn in development mode (with reload)."""
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
    )
