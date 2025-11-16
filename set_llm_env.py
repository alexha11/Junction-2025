#!/usr/bin/env python3
"""Helper script to set LLM credentials in .env file."""
import os
from pathlib import Path

def update_env_file():
    env_file = Path(".env")
    if not env_file.exists():
        print("❌ .env file not found!")
        return
    
    print("Setting up LLM credentials for Featherless API...")
    print()
    
    api_base = input("FEATHERLESS_API_BASE (e.g., https://api.featherless.ai/v1): ").strip()
    api_key = input("FEATHERLESS_API_KEY: ").strip()
    llm_model = input("LLM_MODEL (default: llama-3.1-8b-instruct): ").strip() or "llama-3.1-8b-instruct"
    
    if not api_base or not api_key:
        print("❌ Both FEATHERLESS_API_BASE and FEATHERLESS_API_KEY are required!")
        return
    
    # Read existing .env file
    lines = []
    updated = {"FEATHERLESS_API_BASE": False, "FEATHERLESS_API_KEY": False, "LLM_MODEL": False}
    
    if env_file.exists():
        with open(env_file, 'r') as f:
            lines = f.readlines()
    
    # Update or add variables
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("FEATHERLESS_API_BASE="):
            new_lines.append(f"FEATHERLESS_API_BASE={api_base}\n")
            updated["FEATHERLESS_API_BASE"] = True
        elif stripped.startswith("FEATHERLESS_API_KEY="):
            new_lines.append(f"FEATHERLESS_API_KEY={api_key}\n")
            updated["FEATHERLESS_API_KEY"] = True
        elif stripped.startswith("LLM_MODEL="):
            new_lines.append(f"LLM_MODEL={llm_model}\n")
            updated["LLM_MODEL"] = True
        else:
            new_lines.append(line)
    
    # Add missing variables
    if not updated["FEATHERLESS_API_BASE"]:
        new_lines.append(f"FEATHERLESS_API_BASE={api_base}\n")
    if not updated["FEATHERLESS_API_KEY"]:
        new_lines.append(f"FEATHERLESS_API_KEY={api_key}\n")
    if not updated["LLM_MODEL"]:
        new_lines.append(f"LLM_MODEL={llm_model}\n")
    
    # Write back to file
    with open(env_file, 'w') as f:
        f.writelines(new_lines)
    
    print()
    print("✅ Credentials updated in .env file!")
    print()
    print("Updated values:")
    print(f"  FEATHERLESS_API_BASE={api_base}")
    print(f"  FEATHERLESS_API_KEY={'*' * min(10, len(api_key))}...")
    print(f"  LLM_MODEL={llm_model}")

if __name__ == "__main__":
    update_env_file()
