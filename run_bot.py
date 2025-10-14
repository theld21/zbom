#!/usr/bin/env python3
"""
Entry point for the bot application
"""
import asyncio
import logging
import os
import sys

# Add the app directory to Python path
sys.path.insert(0, '/app')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Import and run the main application
from app.main import app, startup

if __name__ == "__main__":
    # Start the startup sequence in background
    import threading
    import asyncio
    
    def run_startup():
        asyncio.run(startup())
    
    # Start startup in background thread
    startup_thread = threading.Thread(target=run_startup, daemon=True)
    startup_thread.start()
    
    # Run the FastAPI app
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
