"""
tests/test_mcp_bridge.py — Comprehensive unit tests for Model Context Protocol (MCP) Bridge.
"""
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.neo_mcp_bridge import (
    MCPStdioClient,
    NEOMCPBridge,
    MCPToolDefinition,
    mcp_bridge,
)
from actions.mcp_control import mcp_control


class TestMCPStdioClient(unittest.TestCase):
    def test_schema_conversion_and_tool_discovery(self):
        client = MCPStdioClient(name="test_server", command="echo")

        # Mock _send_request to return a valid MCP tools/list response
        sample_tools_resp = {
            "result": {
                "tools": [
                    {
                        "name": "query_db",
                        "description": "Executes SQL query on database",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "sql": {"type": "string", "description": "SQL query string"}
                            },
                            "required": ["sql"],
                        },
                    }
                ]
            }
        }

        with patch.object(client, "_send_request", return_value=sample_tools_resp):
            client._fetch_tools()

        self.assertEqual(len(client.tools), 1)
        tool_decl = list(client.tools.values())[0]
        self.assertEqual(tool_decl.declared_name, "mcp_test_server_query_db")
        self.assertEqual(tool_decl.original_name, "query_db")
        self.assertEqual(tool_decl.server_name, "test_server")
        # Ensure 'OBJECT' type translation for Gemini compatibility
        self.assertEqual(tool_decl.parameters.get("type"), "OBJECT")
        self.assertIn("sql", tool_decl.parameters.get("properties", {}))

    def test_call_tool_formatting(self):
        client = MCPStdioClient(name="test_server", command="echo")
        client._is_connected = True
        client._process = MagicMock()
        client._process.poll.return_value = None

        mock_resp = {
            "result": {
                "content": [
                    {"type": "text", "text": "Row count: 42"},
                    {"type": "text", "text": "Status: OK"}
                ]
            }
        }

        with patch.object(client, "_send_request", return_value=mock_resp):
            out = client.call_tool("query_db", {"sql": "SELECT COUNT(*) FROM users"})
            self.assertIn("Row count: 42", out)
            self.assertIn("Status: OK", out)


class TestNEOMCPBridge(unittest.TestCase):
    def setUp(self):
        self.bridge = NEOMCPBridge()
        self.bridge.shutdown()

    def tearDown(self):
        self.bridge.shutdown()

    def test_tool_declarations_and_dispatch(self):
        mock_client = MagicMock()
        mock_client.name = "mock_cloud"
        mock_client.is_connected = True
        mock_client.tools = {
            "mcp_mock_cloud_deploy": MCPToolDefinition(
                server_name="mock_cloud",
                original_name="deploy",
                declared_name="mcp_mock_cloud_deploy",
                description="Deploys container cluster",
                parameters={"type": "OBJECT", "properties": {"cluster": {"type": "string"}}},
            )
        }
        mock_client.call_tool.return_value = "Deployment initiated: pod-778"

        self.bridge.register_client(mock_client)

        self.assertTrue(self.bridge.has("mcp_mock_cloud_deploy"))
        decls = self.bridge.get_tool_declarations()
        self.assertEqual(len(decls), 1)
        self.assertEqual(decls[0]["name"], "mcp_mock_cloud_deploy")
        self.assertIn("[MCP: mock_cloud]", decls[0]["description"])

        # Execute call
        result = self.bridge.run("mcp_mock_cloud_deploy", {"cluster": "production"})
        self.assertEqual(result, "Deployment initiated: pod-778")
        mock_client.call_tool.assert_called_once_with("deploy", {"cluster": "production"})

    def test_mcp_control_action(self):
        res = mcp_control({"action": "list_servers"})
        self.assertIn("mcp_control", res)
        self.assertIn("status=done", res)


if __name__ == "__main__":
    unittest.main()
