"""
FastAPI ASGI Application Entry Point for Medical Bill Verification Backend.

This is the production-ready API server that exposes HTTP endpoints.
Separate from backend/main.py (CLI entry point) and app/main.py (service logic).

Run with:
    uvicorn backend.server:app --reload --port 8001
    
Or using the batch file:
    start_api_server.bat

Architecture:
- server.py: FastAPI app definition (THIS FILE)
- app/api/routes.py: API endpoint definitions
- app/main.py: Business logic (process_bill, etc.)
- backend/main.py: CLI entry point
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Add backend directory to Python path for absolute imports
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# FastAPI Application Instance
# ============================================================================
app = FastAPI(
    title="Medical Bill Verification API",
    description="AI-Powered Medical Bill Verification System for IOCL Employees",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# ============================================================================
# CORS Configuration (for Vite frontend)
# ============================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite default dev server
        "http://localhost:3000",  # Alternative frontend port
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# ============================================================================
# Startup Event: Dependency Validation
# ============================================================================
@app.on_event("startup")
async def startup_event():
    """Run startup checks when the server starts."""
    logger.info("="*80)
    logger.info("Starting Medical Bill Verification API Server")
    logger.info("="*80)
    
    try:
        from app.utils.dependency_check import check_all_dependencies, check_external_tools
        
        # Check Python dependencies
        check_all_dependencies()
        
        # Check external tools (MongoDB, Ollama, etc.) - warnings only
        check_external_tools()
        
        logger.info("✅ All startup checks passed. API server ready.")
        logger.info(f"📚 API Documentation: http://localhost:8001/docs")
        logger.info(f"🏥 Health Check: http://localhost:8001/health")
        
    except Exception as e:
        logger.error(f"❌ Startup validation failed: {e}")
        logger.warning("⚠️  Server will start but some features may not work correctly")

# ============================================================================
# Health Check Endpoint
# ============================================================================
@app.get("/health", tags=["System"])
async def health_check():
    """
    Health check endpoint to verify the API is running.
    
    Returns:
        JSON with status and version information
    """
    return {
        "status": "healthy",
        "service": "Medical Bill Verification API",
        "version": "2.0.0"
    }

# ============================================================================
# Root Endpoint
# ============================================================================
@app.get("/", tags=["System"])
async def root():
    """
    Root endpoint with API information.
    
    Returns:
        Welcome message with links to documentation
    """
    return {
        "message": "Medical Bill Verification API",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "upload": "POST /upload",
            "bills": "GET /bills",
            "status": "GET /status/{upload_id}",
            "verify": "POST /verify/{upload_id}",
            "tieups": "GET /tieups"
        }
    }

# ============================================================================
# Include API Routes
# ============================================================================
# Import and include the API routes from app/api/routes.py
try:
    from app.api.routes import router as api_router
    app.include_router(api_router)
    logger.info("✅ API routes loaded successfully")
except ImportError as e:
    logger.error(f"❌ Failed to load API routes: {e}")
    logger.error("Make sure app/api/routes.py exists and is properly configured")

# ============================================================================
# Global Exception Handler
# ============================================================================
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """
    Global exception handler for unhandled errors.
    
    This ensures the API always returns a JSON response, even for unexpected errors.
    """
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc),
            "type": type(exc).__name__
        }
    )

# ============================================================================
# Development Server (for testing only)
# ============================================================================
if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting development server...")
    logger.info("For production, use: uvicorn backend.server:app --port 8001")
    
    uvicorn.run(
        "backend.server:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info"
    )
