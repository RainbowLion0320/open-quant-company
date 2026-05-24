"""Hindsight 知识图谱 — 可视化数据端点"""
from fastapi import APIRouter
import httpx
import os

router = APIRouter(prefix="/api/hindsight", tags=["Hindsight"])

HINDSIGHT = (
    os.environ.get("ASTROLABE_HINDSIGHT_URL", "")
    or os.environ.get("XINGPAN_HINDSIGHT_URL", "")
    or "http://localhost:9177"
).rstrip("/")
PRIMARY_BANK = (
    os.environ.get("ASTROLABE_HINDSIGHT_BANK", "")
    or os.environ.get("XINGPAN_HINDSIGHT_BANK", "")
    or "astrolabe-quant"
).strip() or "astrolabe-quant"
_legacy_banks_raw = (
    os.environ.get("ASTROLABE_HINDSIGHT_LEGACY_BANKS", "")
    or os.environ.get("XINGPAN_HINDSIGHT_LEGACY_BANKS", "")
    or "quant-agent,xingpan"
)
LEGACY_BANKS = [
    bank.strip()
    for bank in _legacy_banks_raw.split(",")
    if bank.strip()
]


def _candidate_banks() -> list[str]:
    banks = [PRIMARY_BANK]
    banks.extend(bank for bank in LEGACY_BANKS if bank not in banks)
    return banks


def _get_memories(bank_id: str) -> list[dict]:
    """拉取 Hindsight 所有记忆"""
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(f"{HINDSIGHT}/v1/default/banks/{bank_id}/memories/list")
            r.raise_for_status()
            data = r.json()
            return data.get("items", [])
    except Exception:
        return []


def _get_stats(bank_id: str) -> dict:
    """拉取统计信息"""
    try:
        with httpx.Client(timeout=5) as client:
            r = client.get(f"{HINDSIGHT}/v1/default/banks/{bank_id}/stats")
            r.raise_for_status()
            return r.json()
    except Exception:
        return {}


def _has_bank_data(memories: list[dict], stats: dict) -> bool:
    if memories:
        return True
    for key in ("total_nodes", "total_memories", "document_count"):
        try:
            if int(stats.get(key, 0) or 0) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _load_bank_data() -> tuple[str, list[dict], dict]:
    """
    星盘使用 Astrolabe Quant OS 作为英文项目名，但历史 Hindsight 数据仍可能
    保存在 legacy `quant-agent` bank。优先读 ASTROLABE_HINDSIGHT_BANK，空库时回退。
    """
    for bank_id in _candidate_banks():
        memories = _get_memories(bank_id)
        stats = _get_stats(bank_id)
        if _has_bank_data(memories, stats):
            return bank_id, memories, stats
    return PRIMARY_BANK, [], {}


def _build_graph(memories: list[dict]) -> dict:
    """
    从记忆列表构建图谱:
    - nodes: 每个记忆一个节点
    - links: entity 共享 + document_id 聚合 + consolidation 关系
    """
    nodes = []
    node_ids = set()
    id_map = {}  # memory id → node index

    for i, m in enumerate(memories):
        mid = m.get("id", f"node-{i}")
        node = {
            "id": mid,
            "index": i,
            "label": _truncate(m.get("text", ""), 80),
            "fullText": m.get("text", ""),
            "type": m.get("fact_type", "observation"),
            "entities": m.get("entities", []) if isinstance(m.get("entities"), list) else [],
            "tags": m.get("tags", []),
            "date": m.get("date", ""),
            "documentId": m.get("document_id"),
            "chunkId": m.get("chunk_id"),
            "consolidatedAt": m.get("consolidated_at"),
            "proofCount": m.get("proof_count", 1),
        }
        nodes.append(node)
        node_ids.add(mid)
        id_map[mid] = i

    # Build links
    links = []
    link_set = set()

    def add_link(src: str, tgt: str, ltype: str, label: str = ""):
        if src == tgt:
            return
        key = tuple(sorted([src, tgt]) + [ltype])
        if key in link_set:
            return
        link_set.add(key)
        links.append({
            "source": id_map[src],
            "target": id_map[tgt],
            "type": ltype,
            "label": label,
        })

    # 1) Entity 共享链接 — 两个节点共享同一个 entity
    entity_nodes: dict[str, list[str]] = {}
    for n in nodes:
        for ent in n["entities"]:
            entity_nodes.setdefault(ent, []).append(n["id"])

    for ent, mids in entity_nodes.items():
        for i in range(len(mids)):
            for j in range(i + 1, len(mids)):
                add_link(mids[i], mids[j], "semantic", ent)

    # 2) Document 聚合 — 同一 document_id 下的节点互连
    doc_nodes: dict[str, list[str]] = {}
    for n in nodes:
        if n["documentId"]:
            doc_nodes.setdefault(n["documentId"], []).append(n["id"])

    for doc_id, mids in doc_nodes.items():
        for i in range(len(mids)):
            for j in range(i + 1, len(mids)):
                add_link(mids[i], mids[j], "temporal", "同轮对话")

    # 3) Consolidation 关系 — observation → experience
    #    通过 chunk_id 前缀匹配 (observation.chunk_id is null, experience.chunk_id exists)
    #    如果两个节点 text 非常相似且一个是 observation 一个是 experience，建立链接
    for n in nodes:
        if n["type"] != "experience" or not n["chunkId"]:
            continue
        # 找同一 document 内的 observation
        for other in nodes:
            if other["id"] == n["id"]:
                continue
            if other["type"] == "observation" and other["documentId"] == n["documentId"]:
                add_link(other["id"], n["id"], "consolidation", "合并提炼")

    # 4) Tags 共享
    tag_nodes: dict[str, list[str]] = {}
    for n in nodes:
        for tag in n["tags"]:
            tag_nodes.setdefault(tag, []).append(n["id"])

    for tag, mids in tag_nodes.items():
        for i in range(len(mids)):
            for j in range(i + 1, len(mids)):
                add_link(mids[i], mids[j], "tag", tag)

    return {"nodes": nodes, "links": links}


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


@router.get("/graph")
async def get_graph():
    """返回 Hindsight 知识图谱数据 (nodes + links)"""
    bank_id, memories, stats = _load_bank_data()
    graph = _build_graph(memories)
    return {
        "bank_id": bank_id,
        "legacy_bank_ids": [bank for bank in LEGACY_BANKS if bank != bank_id],
        "nodes": graph["nodes"],
        "links": graph["links"],
        "stats": {
            "total_nodes": stats.get("total_nodes", len(memories)),
            "total_links": stats.get("total_links", len(graph["links"])),
            "links_by_type": stats.get("links_by_link_type", {}),
            "nodes_by_type": stats.get("nodes_by_fact_type", {}),
            "last_consolidated": stats.get("last_consolidated_at"),
        },
    }
