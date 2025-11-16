import os
import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client


port = int(os.environ.get("MCP_SERVER_PORT", 8080))
DEFAULT_MCP_SERVER_URL = "http://57.129.98.111:8080/sse"
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", DEFAULT_MCP_SERVER_URL)


def extract_text_content(result):
    if not result.content:
        return "<No Response Content>"

    if len(result.content) == 1:
        return result.content[0].text
    else:
        return [item.text for item in result.content]


async def main():
    transport = sse_client(MCP_SERVER_URL)

    try:
        async with transport as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # List available tools
                tools = await session.list_tools()
                print("Available tools:", [tool.name for tool in tools.tools])

                # Test browse variables (should now work with OPC UA server)
                result = await session.call_tool("browse_opcua_variables", {})
                print(f"Browse result: {extract_text_content(result)}")

                # Test reading a specific variable
                result = await session.call_tool(
                    "read_opcua_variable", {"variable_name": "WaterLevelInTunnel.L2.m"}
                )
                print(f"Read result: {extract_text_content(result)}")

                # Test writing to specific variable
                result = await session.call_tool(
                    "write_opcua_variable",
                    {"variable_name": "WaterLevelInTunnelL2", "value": 5.5},
                )
                print(f"Write result: {extract_text_content(result)}")

                # Test reading history from variable
                result = await session.call_tool(
                    "get_variable_history",
                    {"variable_name": "WaterLevelInTunnel.L2.m", "hours_back": 1},
                )
                print(f"History result: {extract_text_content(result)}")

                # Test aggregating variable data
                result = await session.call_tool(
                    "aggregate_variable_data",
                    {"variable_name": "WaterLevelInTunnel.L2.m", "hours_back": 1},
                )
                print(f"Aggregate result: {extract_text_content(result)}")

                # Test aggregating multiple variables
                result = await session.call_tool(
                    "aggregate_multiple_variables_data",
                    {
                        "variable_names": [
                            "WaterLevelInTunnel.L2.m",
                            "InflowToTunnel.F1.m3hper15min",
                        ],
                        "hours_back": 1,
                    },
                )
                print(f"Aggregate multiple result: {extract_text_content(result)}")
    except Exception as e:
        print(f"Make sure the MCP server is running at {MCP_SERVER_URL}/")


if __name__ == "__main__":
    asyncio.run(main())
