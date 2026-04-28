from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import core.age_queries as age_queries

router = APIRouter()


class KeywordSearchRequest(BaseModel):
    keywords: list[str]
    hops: int = 1


@router.get("/node/{node_id}")
def get_node(node_id: str):
    node = age_queries.get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


@router.get("/neighbors/{node_id}")
def get_neighbors(node_id: str, depth: int = 1):
    return age_queries.get_neighbors(node_id, depth=depth)


@router.get("/community/{community_id}")
def get_community(community_id: int):
    return age_queries.get_community(community_id)


@router.get("/god-nodes")
def god_nodes(limit: int = 10):
    return age_queries.god_nodes(limit=limit)


@router.get("/stats")
def graph_stats():
    return age_queries.graph_stats()


@router.get("/path")
def shortest_path(src: str, dst: str):
    path = age_queries.shortest_path(src, dst)
    if path is None or path == []:
        raise HTTPException(status_code=404, detail="No path found")
    return path


@router.post("/search")
def keyword_search(body: KeywordSearchRequest):
    return age_queries.keyword_search(body.keywords, hops=body.hops)
