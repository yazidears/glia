try:
    import aikido_zen  # type: ignore[import-not-found]
except ImportError:
    AIKIDO_AVAILABLE = False
else:
    AIKIDO_AVAILABLE = aikido_zen is not None

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from glia.api import router
from glia.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Glia API",
        version="0.1.0",
        description="Realtime transcription and visual-intent API for Glia.",
    )
    app.state.aikido_available = AIKIDO_AVAILABLE
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )
    app.include_router(router)
    return app


app = create_app()
