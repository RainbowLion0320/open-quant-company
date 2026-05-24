def test_hindsight_empty_astrolabe_bank_falls_back_to_legacy(monkeypatch):
    from web.api.routes import hindsight

    monkeypatch.setattr(hindsight, "PRIMARY_BANK", "astrolabe-quant")
    monkeypatch.setattr(hindsight, "LEGACY_BANKS", ["quant-agent"])
    def fake_memories(bank: str) -> list[dict]:
        return [{"id": "m1", "text": "old"}] if bank == "quant-agent" else []

    monkeypatch.setattr(hindsight, "_get_memories", fake_memories)
    monkeypatch.setattr(
        hindsight,
        "_get_stats",
        lambda bank: {"total_nodes": 1} if bank == "quant-agent" else {"total_nodes": 0},
    )

    bank_id, memories, stats = hindsight._load_bank_data()

    assert bank_id == "quant-agent"
    assert memories[0]["id"] == "m1"
    assert stats["total_nodes"] == 1
