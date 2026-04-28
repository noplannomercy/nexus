import json
import pytest
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

TEST_GRAPH = "codebase_test"
TEST_DSN   = os.environ["AGE_DSN"]

TEST_NODES = [
    {"id": "UserService",  "label": "UserService",  "file_type": "code",     "source_file": "/src/UserService.java",  "source_location": "L1",  "community": 0, "norm_label": "userservice"},
    {"id": "UserRepo",     "label": "UserRepo",     "file_type": "code",     "source_file": "/src/UserRepo.java",     "source_location": "L1",  "community": 0, "norm_label": "userrepo"},
    {"id": "Article",      "label": "Article",      "file_type": "code",     "source_file": "/src/Article.java",      "source_location": "L1",  "community": 1, "norm_label": "article"},
    {"id": "README",       "label": "README",       "file_type": "document", "source_file": "/README.md",             "source_location": "L1",  "community": 2, "norm_label": "readme"},
]
TEST_EDGES = [
    {"source": "UserService", "target": "UserRepo",  "relation": "calls",   "confidence": "EXTRACTED", "confidence_score": 0.95, "weight": 1.0},
    {"source": "UserService", "target": "Article",   "relation": "imports", "confidence": "EXTRACTED", "confidence_score": 0.80, "weight": 1.0},
]


def _cs(v):
    if v is None:
        return ""
    return str(v).replace("\\", "\\\\").replace("'", "\\'")


def _setup_age(cur):
    cur.execute("LOAD 'age';")
    cur.execute("SET search_path = ag_catalog, '$user', public;")


@pytest.fixture(scope="session")
def age_conn():
    conn = psycopg2.connect(TEST_DSN)
    cur  = conn.cursor()

    conn.autocommit = True
    _setup_age(cur)

    try:
        cur.execute(f"SELECT drop_graph('{TEST_GRAPH}', true);")
    except Exception:
        pass

    cur.execute(f"SELECT create_graph('{TEST_GRAPH}');")
    conn.autocommit = False

    for node in TEST_NODES:
        label = {"code": "CodeNode", "document": "DocumentNode"}.get(node["file_type"], "Node")
        cur.execute(f"""
            SELECT * FROM cypher('{TEST_GRAPH}', $$
                CREATE (n:{label} {{
                    id:              '{_cs(node["id"])}',
                    label:           '{_cs(node["label"])}',
                    file_type:       '{_cs(node["file_type"])}',
                    source_file:     '{_cs(node["source_file"])}',
                    source_location: '{_cs(node["source_location"])}',
                    community:       {int(node["community"])},
                    norm_label:      '{_cs(node["norm_label"])}'
                }})
            $$) AS (result agtype)
        """)
    conn.commit()

    for edge in TEST_EDGES:
        rtype = edge["relation"].upper()
        cur.execute(f"""
            SELECT * FROM cypher('{TEST_GRAPH}', $$
                MATCH (a {{id: '{_cs(edge["source"])}'}}),
                      (b {{id: '{_cs(edge["target"])}'}})
                CREATE (a)-[:{rtype} {{
                    confidence:       '{_cs(edge["confidence"])}',
                    confidence_score: {float(edge["confidence_score"])},
                    weight:           {float(edge["weight"])}
                }}]->(b)
            $$) AS (result agtype)
        """)
    conn.commit()

    yield conn

    conn.autocommit = True
    _setup_age(cur)
    try:
        cur.execute(f"SELECT drop_graph('{TEST_GRAPH}', true);")
    except Exception:
        pass
    conn.close()
