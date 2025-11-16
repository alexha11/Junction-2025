#!/usr/bin/env python3
"""
Run the backend server from anywhere in the project.
Usage: python3 run_backend.py
"""
import os
import subprocess
import sys
from pathlib import Path

# Get the project root (where this script is located)
project_root = Path(__file__).parent.resolve()
backend_dir = project_root / "backend"

# Change to backend directory
os.chdir(backend_dir)

# Run uvicorn
cmd = [
    sys.executable,
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    "8000",
    "--reload",
]

print(f"Running backend from: {backend_dir}")
subprocess.run(cmd)

