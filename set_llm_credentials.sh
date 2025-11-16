#!/bin/bash
# Helper script to set LLM credentials in .env file

echo "Setting up LLM credentials for Featherless API..."
echo ""
echo "Please provide your API credentials:"
echo ""

read -p "FEATHERLESS_API_BASE (e.g., https://api.featherless.ai/v1): " api_base
read -p "FEATHERLESS_API_KEY: " api_key
read -p "LLM_MODEL (default: llama-3.1-8b-instruct): " llm_model

# Use default if empty
llm_model=${llm_model:-llama-3.1-8b-instruct}

# Update .env file
env_file=".env"
if [ ! -f "$env_file" ]; then
    echo "Error: .env file not found!"
    exit 1
fi

# Update or add FEATHERLESS_API_BASE
if grep -q "^FEATHERLESS_API_BASE=" "$env_file"; then
    sed -i.bak "s|^FEATHERLESS_API_BASE=.*|FEATHERLESS_API_BASE=$api_base|" "$env_file"
else
    echo "FEATHERLESS_API_BASE=$api_base" >> "$env_file"
fi

# Update or add FEATHERLESS_API_KEY
if grep -q "^FEATHERLESS_API_KEY=" "$env_file"; then
    sed -i.bak "s|^FEATHERLESS_API_KEY=.*|FEATHERLESS_API_KEY=$api_key|" "$env_file"
else
    echo "FEATHERLESS_API_KEY=$api_key" >> "$env_file"
fi

# Update or add LLM_MODEL
if grep -q "^LLM_MODEL=" "$env_file"; then
    sed -i.bak "s|^LLM_MODEL=.*|LLM_MODEL=$llm_model|" "$env_file"
else
    echo "LLM_MODEL=$llm_model" >> "$env_file"
fi

# Clean up backup file
rm -f "${env_file}.bak"

echo ""
echo "✅ Credentials updated in .env file!"
echo ""
echo "Updated values:"
grep "FEATHERLESS_API_BASE\|FEATHERLESS_API_KEY\|LLM_MODEL" "$env_file" | sed 's/FEATHERLESS_API_KEY=.*/FEATHERLESS_API_KEY=***HIDDEN***/'
