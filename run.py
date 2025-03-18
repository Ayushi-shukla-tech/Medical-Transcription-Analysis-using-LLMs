#!/usr/bin/env python
"""
Medical Transcription Application

This script runs the Medical Transcription Application using Uvicorn.
"""

import uvicorn
import os
import sys
import argparse
import webbrowser
import time
from dotenv import load_dotenv
from web.models.init_db import reset_database

# Load environment variables from .env file
load_dotenv()

# Get configuration from environment variables
PORT = int(os.getenv("PORT", 8000))
DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "t")

def main():
    parser = argparse.ArgumentParser(description="Run the Medical Transcription Application")
    parser.add_argument("--reset-db", action="store_true", help="Reset database before starting")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser automatically")
    args = parser.parse_args()

    # Print welcome message
    print("\n" + "="*80)
    print("           MEDICAL TRANSCRIPTION APPLICATION STARTUP")
    print("="*80)
    
    if args.reset_db:
        print("\nResetting database...")
        try:
            reset_database()
            print("Database reset successfully!")
        except Exception as e:
            print(f"Error resetting database: {str(e)}")
            print("You may want to manually delete the SQLite file and retry.")
            if not args.debug:
                sys.exit(1)
    
    # Ensure required directories exist
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("web/static/css", exist_ok=True)
    os.makedirs("web/static/js", exist_ok=True)
    print("\nDirectory structure verified.")
    
    # Provide login information
    print("\nLogin credentials:")
    print("  Admin:  username=admin, password=admin123")
    print("  Doctor: username=doctor, password=doctor123")
    print("  Patient: ID=P00001, password=patient123")
    
    host = "127.0.0.1"
    port = 8000
    
    print(f"\nStarting server at http://{host}:{port}")
    print("\n*** AUTHENTICATION FIX APPLIED: Cookie-based auth now available ***")
    print("="*80 + "\n")
    
    # Open browser after a slight delay
    if not args.no_browser:
        def open_browser():
            time.sleep(2)
            webbrowser.open(f"http://{host}:{port}")
        
        import threading
        threading.Thread(target=open_browser, daemon=True).start()
    
    # Start the uvicorn server
    uvicorn.run(
        "web.app:app", 
        host=host, 
        port=port, 
        reload=args.debug,
        log_level="debug" if args.debug else "info"
    )

if __name__ == "__main__":
    main() 