#!/usr/bin/env python3
"""Run the NI model MCP server over stdio."""

from src.ni_model.mcp.server import mcp

if __name__ == "__main__":
    mcp.run()
