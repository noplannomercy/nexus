import json
import uvicorn
from mcp.server import Server
from mcp.server.sse import SseServerTransport
import mcp.types as types
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route

import config
import core.age_queries as age_queries

mcp_server = Server("nexus")


@mcp_server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_node",
            description="Get a single node by its ID",
            inputSchema={
                "type": "object",
                "properties": {"node_id": {"type": "string"}},
                "required": ["node_id"],
            },
        ),
        types.Tool(
            name="get_neighbors",
            description="Get neighboring nodes within N hops",
            inputSchema={
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "depth": {"type": "integer", "default": 1},
                },
                "required": ["node_id"],
            },
        ),
        types.Tool(
            name="get_community",
            description="Get all nodes in a community by community ID",
            inputSchema={
                "type": "object",
                "properties": {"community_id": {"type": "integer"}},
                "required": ["community_id"],
            },
        ),
        types.Tool(
            name="god_nodes",
            description="Get highest-degree nodes (architectural hubs)",
            inputSchema={
                "type": "object",
                "properties": {"limit": {"type": "integer", "default": 10}},
            },
        ),
        types.Tool(
            name="graph_stats",
            description="Get total node and edge counts",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="shortest_path",
            description="Find shortest directed path between two nodes",
            inputSchema={
                "type": "object",
                "properties": {
                    "src_id": {"type": "string"},
                    "dst_id": {"type": "string"},
                },
                "required": ["src_id", "dst_id"],
            },
        ),
        types.Tool(
            name="keyword_search",
            description="Search nodes by keywords and expand to neighbors",
            inputSchema={
                "type": "object",
                "properties": {
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "hops": {"type": "integer", "default": 1},
                },
                "required": ["keywords"],
            },
        ),
    ]


def _text(obj) -> types.TextContent:
    return types.TextContent(type="text", text=json.dumps(obj, ensure_ascii=False))


@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "get_node":
        result = age_queries.get_node(arguments["node_id"])
        return [_text(result)]

    if name == "get_neighbors":
        result = age_queries.get_neighbors(
            arguments["node_id"], depth=arguments.get("depth", 1)
        )
        return [_text(result)]

    if name == "get_community":
        result = age_queries.get_community(arguments["community_id"])
        return [_text(result)]

    if name == "god_nodes":
        result = age_queries.god_nodes(limit=arguments.get("limit", 10))
        return [_text(result)]

    if name == "graph_stats":
        result = age_queries.graph_stats()
        return [_text(result)]

    if name == "shortest_path":
        result = age_queries.shortest_path(arguments["src_id"], arguments["dst_id"])
        return [_text(result)]

    if name == "keyword_search":
        result = age_queries.keyword_search(
            arguments["keywords"], hops=arguments.get("hops", 1)
        )
        return [_text(result)]

    raise ValueError(f"Unknown tool: {name}")


def build_starlette_app() -> Starlette:
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> Response:
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await mcp_server.run(
                streams[0], streams[1], mcp_server.create_initialization_options()
            )
        return Response()

    return Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse, methods=["GET"]),
            Mount("/messages/", app=sse.handle_post_message),
        ]
    )


def main() -> None:
    age_queries.init(config.AGE_DSN, config.AGE_GRAPH)
    app = build_starlette_app()
    uvicorn.run(app, host="0.0.0.0", port=config.MCP_PORT)


if __name__ == "__main__":
    main()
