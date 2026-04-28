import os
from dotenv import load_dotenv

load_dotenv()

AGE_DSN        = os.environ["AGE_DSN"]
AGE_GRAPH      = os.getenv("AGE_GRAPH", "codebase")
API_PORT       = int(os.getenv("API_PORT", "8004"))
MCP_PORT       = int(os.getenv("MCP_PORT", "8006"))
API_KEY        = os.getenv("API_KEY", "")

GRAPHIFY_PATH     = os.getenv("GRAPHIFY_PATH", "graphify")
SOURCE_DIR        = os.getenv("SOURCE_DIR", ".")
GRAPH_OUTPUT_PATH = os.getenv("GRAPH_OUTPUT_PATH", "graphify-out/graph.json")
