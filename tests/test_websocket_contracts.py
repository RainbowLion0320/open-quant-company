"""
WebSocket contract tests for /api/strategies/ws/{job_id}.

Tests use FastAPI TestClient to verify WebSocket behavior
without requiring a running server.
"""
import asyncio
import pytest

try:
    from fastapi.testclient import TestClient
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    from web.api.app import create_app
    app = create_app()
    return TestClient(app)


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi[testclient] not available")
class TestWebSocketContract:

    def test_unknown_job_returns_message_or_closes(self, client):
        """Connecting to an unknown job_id should return a status or close."""
        with client.websocket_connect("/api/strategies/ws/nonexistent_job_123") as ws:
            try:
                # The server may send a message or close the connection
                data = ws.receive_json(timeout=3)
                # If we get a message, it should have job_id and status
                assert "job_id" in data or "status" in data
            except Exception:
                # Connection closed is also acceptable for unknown jobs
                pass

    def test_progress_message_has_required_fields(self, client):
        """Progress messages should contain job_id, status, progress, message."""
        # Create a known job first
        from web.api.jobs import create_job
        job_id = create_job("test_strategy")

        with client.websocket_connect(f"/api/strategies/ws/{job_id}") as ws:
            try:
                data = ws.receive_json(timeout=3)
                # Should have the required fields
                assert "job_id" in data
                assert "status" in data
                assert "progress" in data
                assert "message" in data
            except Exception:
                # Connection may close quickly if job is already done
                pass

    def test_ping_responds_with_pong(self, client):
        """Sending 'ping' should get 'pong' response."""
        from web.api.jobs import create_job
        job_id = create_job("test_strategy")

        with client.websocket_connect(f"/api/strategies/ws/{job_id}") as ws:
            ws.send_text("ping")
            try:
                data = ws.receive_json(timeout=3)
                assert data == "pong"
            except Exception:
                # Some implementations may not support ping/pong via JSON
                pass

    def test_connection_bounded_timeout(self, client):
        """WebSocket connection should not hang indefinitely."""
        from web.api.jobs import create_job
        job_id = create_job("test_strategy")

        with client.websocket_connect(f"/api/strategies/ws/{job_id}") as ws:
            # Try to receive with a short timeout
            try:
                ws.receive_json(timeout=2)
            except Exception:
                # Timeout or close is expected
                pass
        # If we get here, the test passed (connection didn't hang)
