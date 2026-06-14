"""Live broker adapters.

Live adapters must fail closed. They never fall back to PaperBroker.
"""

from broker.live.qmt import MiniQmtLiveBroker

__all__ = ["MiniQmtLiveBroker"]
