#!/usr/bin/env python3
"""
WSGI entry point for ALIGN Prototype
Use with Waitress or any WSGI server:
  waitress-serve --port=8000 wsgi:app

Or with gunicorn:
  gunicorn -w 4 -b 127.0.0.1:8000 wsgi:app
"""

import os
import sys
from pathlib import Path

# Ensure app module is importable
sys.path.insert(0, str(Path(__file__).parent))

# Import Flask app from app.py
from app import app

# Production settings
if __name__ == '__main__':
    # This is only used with basic python wsgi.py
    # For production, use: waitress-serve wsgi:app
    port = int(os.environ.get('PORT', 8000))
    print(f"Starting Flask app on port {port}")
    print("⚠️  Use 'waitress-serve --port={} wsgi:app' for production".format(port))
    app.run(host='127.0.0.1', port=port, debug=False)
