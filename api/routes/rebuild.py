from fastapi import APIRouter

import config
import core.age_queries as age_queries
from loader.age_loader import run_loader

router = APIRouter()


def _do_rebuild(rebuild_flag: dict) -> None:
    rebuild_flag["running"] = True
    try:
        run_loader(
            dsn=config.AGE_DSN,
            graph_name=config.AGE_GRAPH,
            graph_path=config.GRAPH_OUTPUT_PATH,
        )
        age_queries.init(config.AGE_DSN, config.AGE_GRAPH)
    finally:
        rebuild_flag["running"] = False


@router.post("/")
def trigger_rebuild():
    from api.main import rebuild_flag
    import threading
    t = threading.Thread(target=_do_rebuild, args=(rebuild_flag,), daemon=True)
    t.start()
    return {"status": "ok", "message": "Rebuild started"}
