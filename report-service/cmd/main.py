"""Main entry point."""

import logging

import uvicorn

from internal.config.config import get_settings
from internal.app.app import create_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()
app = create_app()


def main():
    """Run the application."""
    logger.info(f"Starting report service on port {settings.http_port}")
    uvicorn.run(app, host="0.0.0.0", port=settings.http_port, log_level="info")


if __name__ == "__main__":
    main()