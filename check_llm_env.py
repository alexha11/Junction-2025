#!/usr/bin/env python3
"""Quick script to check LLM environment variables."""
import os

print("Checking LLM environment variables...")
print(f"FEATHERLESS_API_BASE: {'✅ SET' if os.getenv('FEATHERLESS_API_BASE') else '❌ NOT SET'} ({os.getenv('FEATHERLESS_API_BASE', 'None')[:50] if os.getenv('FEATHERLESS_API_BASE') else 'None'})")
api_key = os.getenv('FEATHERLESS_API_KEY')
print(f"FEATHERLESS_API_KEY: {'✅ SET' if api_key else '❌ NOT SET'} ({'*' * min(10, len(api_key)) if api_key else 'None'})")
print(f"LLM_MODEL: {os.getenv('LLM_MODEL', 'llama-3.1-8b-instruct')}")

if os.getenv('FEATHERLESS_API_BASE') and os.getenv('FEATHERLESS_API_KEY'):
    print("\n✅ LLM credentials are configured!")
else:
    print("\n❌ LLM credentials are missing!")
    print("Please edit .env file and set:")
    print("  FEATHERLESS_API_BASE=your_api_base_url")
    print("  FEATHERLESS_API_KEY=your_api_key")
