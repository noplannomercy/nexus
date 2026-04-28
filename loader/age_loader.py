import json
import psycopg2

BATCH_SIZE = 100

FILE_TYPE_LABEL = {
    "code":     "CodeNode",
    "document": "DocumentNode",
    "image":    "ImageNode",
}


def _node_label(file_type: str) -> str:
    return FILE_TYPE_LABEL.get(file_type, "Node")


def _rel_type(relation: str) -> str:
    return relation.upper().replace(" ", "_").replace("-", "_")


def _cs(value) -> str:
    if value is None:
        return ""
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def _setup_age(cur) -> None:
    cur.execute("LOAD 'age';")
    cur.execute("SET search_path = ag_catalog, '$user', public;")


def _clear_graph(conn, cur, graph_name: str) -> None:
    try:
        cur.execute(f"""
            SELECT * FROM cypher('{graph_name}', $$
                MATCH (n) DETACH DELETE n
            $$) AS (n agtype);
        """)
        conn.commit()
    except Exception:
        conn.rollback()


def _insert_nodes(conn, cur, nodes: list, graph_name: str) -> tuple[int, int]:
    ok = fail = 0
    for i, node in enumerate(nodes):
        label = _node_label(node.get("file_type", "code"))
        community = int(node.get("community", -1))
        try:
            cur.execute(f"""
                SELECT * FROM cypher('{graph_name}', $$
                    CREATE (n:{label} {{
                        id:              '{_cs(node.get("id", ""))}',
                        label:           '{_cs(node.get("label", ""))}',
                        file_type:       '{_cs(node.get("file_type", ""))}',
                        source_file:     '{_cs(node.get("source_file", ""))}',
                        source_location: '{_cs(node.get("source_location", ""))}',
                        community:       {community},
                        norm_label:      '{_cs(node.get("norm_label", ""))}'
                    }})
                $$) AS (result agtype)
            """)
            ok += 1
        except Exception:
            conn.rollback()
            fail += 1
            continue
        if (i + 1) % BATCH_SIZE == 0:
            conn.commit()
    conn.commit()
    return ok, fail


def _insert_edges(conn, cur, edges: list, graph_name: str) -> tuple[int, int]:
    ok = fail = 0
    for i, edge in enumerate(edges):
        rtype = _rel_type(edge.get("relation", "RELATED"))
        confidence_score = float(edge.get("confidence_score", 0.0))
        weight = float(edge.get("weight", 1.0))
        try:
            cur.execute(f"""
                SELECT * FROM cypher('{graph_name}', $$
                    MATCH (a {{id: '{_cs(edge.get("source", ""))}'}}),
                          (b {{id: '{_cs(edge.get("target", ""))}'}})
                    CREATE (a)-[:{rtype} {{
                        confidence:       '{_cs(edge.get("confidence", ""))}',
                        confidence_score: {confidence_score},
                        weight:           {weight},
                        source_file:      '{_cs(edge.get("source_file", ""))}',
                        source_location:  '{_cs(edge.get("source_location", ""))}'
                    }}]->(b)
                $$) AS (result agtype)
            """)
            ok += 1
        except Exception:
            conn.rollback()
            fail += 1
            continue
        if (i + 1) % BATCH_SIZE == 0:
            conn.commit()
    conn.commit()
    return ok, fail


def _insert_hyperedges(conn, cur, hyperedges: list, graph_name: str) -> int:
    ok = 0
    for he in hyperedges:
        confidence_score = float(he.get("confidence_score", 0.0))
        try:
            cur.execute(f"""
                SELECT * FROM cypher('{graph_name}', $$
                    CREATE (n:HyperNode {{
                        id:               '{_cs(he.get("id", ""))}',
                        label:            '{_cs(he.get("label", ""))}',
                        relation:         '{_cs(he.get("relation", ""))}',
                        confidence:       '{_cs(he.get("confidence", ""))}',
                        confidence_score: {confidence_score},
                        source_file:      '{_cs(he.get("source_file", ""))}'
                    }})
                $$) AS (result agtype)
            """)
            for member_id in he.get("nodes", []):
                cur.execute(f"""
                    SELECT * FROM cypher('{graph_name}', $$
                        MATCH (h:HyperNode {{id: '{_cs(he["id"])}'}}),
                              (m {{id: '{_cs(member_id)}'}})
                        CREATE (m)-[:MEMBER_OF]->(h)
                    $$) AS (result agtype)
                """)
            ok += 1
        except Exception:
            conn.rollback()
            continue
    conn.commit()
    return ok


def run_loader(dsn: str, graph_name: str, graph_path: str) -> None:
    with open(graph_path, encoding="utf-8") as f:
        data = json.load(f)

    nodes = data.get("nodes", [])
    edges = data.get("links", [])
    hyperedges = data.get("graph", {}).get("hyperedges", [])

    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    conn.autocommit = True
    _setup_age(cur)
    conn.autocommit = False

    _clear_graph(conn, cur, graph_name)
    _insert_nodes(conn, cur, nodes, graph_name)
    _insert_edges(conn, cur, edges, graph_name)
    if hyperedges:
        _insert_hyperedges(conn, cur, hyperedges, graph_name)

    conn.close()
