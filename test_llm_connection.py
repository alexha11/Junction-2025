#!/usr/bin/env python3
"""Test LLM connection with credentials from .env"""
import os
import sys
from pathlib import Path

# Load .env file manually for testing
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / '.env'
    load_dotenv(env_path)
    print(f"✅ Loaded .env from: {env_path}")
except ImportError:
    print("⚠️ python-dotenv not installed, reading .env manually...")
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value
        print(f"✅ Loaded .env manually from: {env_path}")

api_base = os.getenv('FEATHERLESS_API_BASE')
api_key = os.getenv('FEATHERLESS_API_KEY')

print(f"\nFEATHERLESS_API_BASE: {api_base if api_base else '❌ NOT SET'}")
print(f"FEATHERLESS_API_KEY: {'✅ SET' if api_key else '❌ NOT SET'} ({'*' * 10 if api_key else 'None'})")

if api_base and api_key:
    print("\n✅ Credentials found! Testing LLM connection...")
    sys.path.insert(0, str(Path(__file__).parent))
    from agents.optimizer_agent.explainability import LLMExplainer
    explainer = LLMExplainer(api_base=api_base, api_key=api_key)
    print("✅ LLMExplainer created successfully!")
else:
    print("\n❌ Please set FEATHERLESS_API_BASE and FEATHERLESS_API_KEY in .env file")
