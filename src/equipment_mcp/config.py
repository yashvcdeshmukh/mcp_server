"""Where the equipment server listens. The client imports this, not the server."""

HOST = "127.0.0.1"
PORT = 8000
PATH = "/mcp"
MCP_URL = f"http://{HOST}:{PORT}{PATH}"
