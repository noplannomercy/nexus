import json
import psycopg2
from psycopg2.pool import ThreadedConnectionPool

_pool: ThreadedConnectionPool | None = None
_graph: str = "codebase"


def init(dsn: str, graph: str) -> None:
    global _pool, _graph
    _graph = graph
    _pool = ThreadedConnectionPool(1, 10, dsn)


def _get_conn():
    conn = _pool.getconn()
    cur = conn.cursor()
    cur.execute("LOAD 'age';")
    cur.execute("SET search_path = ag_catalog, '$user', public;")
    cur.close()
    return conn


def _put_conn(conn) -> None:
    _pool.putconn(conn)


def _cs(v) -> str:
    if v is None:
        return ""
    return str(v).replace("\\", "\\\\").replace("'", "\\'")


def _parse(row) -> dict | None:
    if row is None:
        return None
    raw = row[0]
    if raw is None:
        return None
    if isinstance(raw, str):
        return json.loads(raw)
    return dict(raw)


def _resolve_id(cur, node_id: str) -> str:
    """Return actual graph ID for node_id, falling back to fuzzy norm_label match."""
    cur.execute(f"""
        SELECT * FROM cypher('{_graph}', $$
            MATCH (n {{id: '{_cs(node_id)}'}}) RETURN n.id LIMIT 1
        $$) AS (result agtype)
    """)
    row = cur.fetchone()
    if row:
        raw = row[0]
        return json.loads(raw) if isinstance(raw, str) else str(raw)
    normalized = _cs(node_id.lower().replace("_", "").replace(" ", ""))
    cur.execute(f"""
        SELECT * FROM cypher('{_graph}', $$
            MATCH (n)
            WHERE toLower(n.norm_label) CONTAINS '{normalized}'
               OR toLower(n.id) CONTAINS '{normalized}'
            RETURN n.id LIMIT 1
        $$) AS (result agtype)
    """)
    row = cur.fetchone()
    if row:
        raw = row[0]
        return json.loads(raw) if isinstance(raw, str) else str(raw)
    return node_id


def get_node(node_id: str) -> dict | None:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        resolved = _resolve_id(cur, node_id)
        cur.execute(f"""
            SELECT * FROM cypher('{_graph}', $$
                MATCH (n {{id: '{_cs(resolved)}'}})
                RETURN properties(n)
            $$) AS (result agtype)
        """)
        row = cur.fetchone()
        cur.close()
        return _parse(row)
    finally:
        _put_conn(conn)


def get_neighbors(node_id: str, depth: int = 1) -> list[dict]:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        resolved = _resolve_id(cur, node_id)
        cur.execute(f"""
            SELECT * FROM cypher('{_graph}', $$
                MATCH (src {{id: '{_cs(resolved)}'}})-[r*1..{int(depth)}]-(n)
                WHERE n.id <> '{_cs(resolved)}'
                RETURN properties(n), properties(r[0])
            $$) AS (node agtype, edge agtype)
        """)
        rows = cur.fetchall()
        cur.close()
        results = []
        seen = set()
        for row in rows:
            node = json.loads(row[0]) if isinstance(row[0], str) else dict(row[0])
            edge = json.loads(row[1]) if isinstance(row[1], str) else dict(row[1])
            nid = node.get("id", "")
            if nid not in seen:
                seen.add(nid)
                results.append({"node": node, "edge": edge})
        return results
    finally:
        _put_conn(conn)


def get_community(community_id: int) -> list[dict]:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT * FROM cypher('{_graph}', $$
                MATCH (n {{community: {int(community_id)}}})
                RETURN properties(n)
            $$) AS (result agtype)
        """)
        rows = cur.fetchall()
        cur.close()
        return [json.loads(r[0]) if isinstance(r[0], str) else dict(r[0]) for r in rows]
    finally:
        _put_conn(conn)


def god_nodes(limit: int = 10) -> list[dict]:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT * FROM cypher('{_graph}', $$
                MATCH (n)-[r]-()
                WITH n, count(r) AS deg
                ORDER BY deg DESC
                LIMIT {int(limit)}
                RETURN properties(n)
            $$) AS (result agtype)
        """)
        rows = cur.fetchall()
        cur.close()
        return [json.loads(r[0]) if isinstance(r[0], str) else dict(r[0]) for r in rows]
    finally:
        _put_conn(conn)


def graph_stats() -> dict:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT * FROM cypher('{_graph}', $$
                MATCH (n) RETURN count(n)
            $$) AS (result agtype)
        """)
        node_count = int(cur.fetchone()[0])
        cur.execute(f"""
            SELECT * FROM cypher('{_graph}', $$
                MATCH ()-[r]->() RETURN count(r)
            $$) AS (result agtype)
        """)
        edge_count = int(cur.fetchone()[0])
        cur.close()
        return {"nodes": node_count, "edges": edge_count}
    finally:
        _put_conn(conn)


def shortest_path(src_id: str, dst_id: str) -> list[dict] | None:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        src_resolved = _resolve_id(cur, src_id)
        dst_resolved = _resolve_id(cur, dst_id)
        cur.execute(f"""
            SELECT * FROM cypher('{_graph}', $$
                MATCH path = (a {{id: '{_cs(src_resolved)}' }})-[*1..15]->(b {{id: '{_cs(dst_resolved)}'}})
                RETURN [n IN nodes(path) | properties(n)]
                LIMIT 1
            $$) AS (result agtype)
        """)
        row = cur.fetchone()
        cur.close()
        if row is None or row[0] is None:
            return None
        raw = row[0]
        nodes = json.loads(raw) if isinstance(raw, str) else list(raw)
        return nodes if nodes else None
    finally:
        _put_conn(conn)


def keyword_search(keywords: list[str], hops: int = 1) -> list[dict]:
    conn = _get_conn()
    try:
        cur = conn.cursor()
        results = []
        seen = set()

        for kw in keywords:
            kw_escaped = _cs(kw.lower())
            cur.execute(f"""
                SELECT * FROM cypher('{_graph}', $$
                    MATCH (n)
                    WHERE toLower(n.id) CONTAINS '{kw_escaped}'
                       OR toLower(n.label) CONTAINS '{kw_escaped}'
                       OR toLower(n.norm_label) CONTAINS '{kw_escaped}'
                    RETURN properties(n)
                $$) AS (result agtype)
            """)
            seed_rows = cur.fetchall()
            seed_ids = []
            for row in seed_rows:
                node = json.loads(row[0]) if isinstance(row[0], str) else dict(row[0])
                nid = node.get("id", "")
                if nid not in seen:
                    seen.add(nid)
                    results.append(node)
                    seed_ids.append(nid)

            for sid in seed_ids:
                cur.execute(f"""
                    SELECT * FROM cypher('{_graph}', $$
                        MATCH (seed {{id: '{_cs(sid)}' }})-[*1..{int(hops)}]-(n)
                        WHERE n.id <> '{_cs(sid)}'
                        RETURN properties(n)
                    $$) AS (result agtype)
                """)
                for row in cur.fetchall():
                    node = json.loads(row[0]) if isinstance(row[0], str) else dict(row[0])
                    nid = node.get("id", "")
                    if nid not in seen:
                        seen.add(nid)
                        results.append(node)

        cur.close()
        return results
    finally:
        _put_conn(conn)
