#!/bin/bash
# Run the backend server from the backend directory
cd "$(dirname "$0")/backend" || exit 1
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

