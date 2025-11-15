python3.13 -m venv venv
pip install -r requirements.txt

echo ""
echo "OPC UA Client"
python opcua_client.py

echo ""
echo "MCP Client"
python mcp_client.py
