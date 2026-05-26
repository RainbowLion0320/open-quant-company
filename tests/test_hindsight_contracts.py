def test_hindsight_loader_uses_primary_astrolabe_bank_only(monkeypatch):
    from web.api.routes import hindsight

    monkeypatch.setattr(hindsight, "PRIMARY_BANK", "astrolabe-quant")
    def fake_memories(bank: str) -> list[dict]:
        return [{"id": "m1", "text": "current"}] if bank == "astrolabe-quant" else []

    monkeypatch.setattr(hindsight, "_get_memories", fake_memories)
    monkeypatch.setattr(
        hindsight,
        "_get_stats",
        lambda bank: {"total_nodes": 1} if bank == "astrolabe-quant" else {"total_nodes": 0},
    )

    bank_id, memories, stats = hindsight._load_bank_data()

    assert bank_id == "astrolabe-quant"
    assert memories[0]["id"] == "m1"
    assert stats["total_nodes"] == 1
