# main.py
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config.settings import settings
from core.agent import SupplyChainAgent
from api.routes import router as api_router

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("--- Initializing Master Supply Chain Agent ---")
    agent = SupplyChainAgent()
    try:
        agent.odoo_service.connect()
        logger.info("Agent initialization complete. Odoo connection successful.")
    except Exception as e:
        logger.error(f"FATAL ERROR: Could not connect to Odoo during startup. Error: {e}")
        raise

    # Store the single agent instance in the application's state.
    # This is the recommended way to share resources.
    app.state.agent = agent
    
    yield
    
    logger.info("--- Shutting down Supply Chain Agent ---")
    app.state.agent = None # Clean up

# Initialize the FastAPI application
app = FastAPI(
    title="Supply Chain Planning Agent",
    version="1.0.0",
    description="AI-powered supply chain planning assistant with Odoo integration",
    lifespan=lifespan
)

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the API routes with the prefix
app.include_router(api_router, prefix="/api")

# REMOVED ALL THE OVERRIDE LOGIC - IT'S NOT NEEDED

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)