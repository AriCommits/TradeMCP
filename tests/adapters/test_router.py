from __future__ import annotations

from pathlib import Path

from trading.adapters import BrokerRouter, build_router_from_config_dir


def test_router_loads_adapters_from_config_dir() -> None:
    cfg_dir = Path(__file__).resolve().parents[2] / "config/integrations/adapters"
    router = build_router_from_config_dir(cfg_dir)
    names = router.registered()
    assert set(names) == {
        "tradingview",
        "fidelity_active_trader",
        "robinhood_crypto",
        "gemini",
        "forex_com",
    }


def test_router_dispatches_submit_and_cancel(monkeypatch) -> None:
    monkeypatch.setenv("TRADINGVIEW_WEBHOOK_URL", "https://example.com/webhook")

    cfg_dir = Path(__file__).resolve().parents[2] / "config/integrations/adapters"
    router = build_router_from_config_dir(cfg_dir)

    fidelity_res = router.submit_order(
        "fidelity_active_trader",
        {"symbol": "AAPL", "side": "buy", "quantity": 10},
    )
    assert "ticket_path" in fidelity_res.result

    robinhood_res = router.submit_order(
        "robinhood_crypto",
        {"symbol": "BTC-USD", "side": "buy", "quantity": 0.01},
    )
    assert robinhood_res.result.get("dry_run") is True

    cancel_res = router.cancel_order("robinhood_crypto", "abc123")
    assert cancel_res.result.get("dry_run") is True


def test_router_ping_all(monkeypatch) -> None:
    monkeypatch.setenv("TRADINGVIEW_WEBHOOK_URL", "https://example.com/webhook")
    cfg_dir = Path(__file__).resolve().parents[2] / "config/integrations/adapters"
    router = build_router_from_config_dir(cfg_dir)
    ping = router.ping_all()

    assert "tradingview" in ping
    assert "gemini" in ping
    assert "forex_com" in ping


def test_router_capabilities_and_open_orders(monkeypatch) -> None:
    monkeypatch.setenv("TRADINGVIEW_WEBHOOK_URL", "https://example.com/webhook")
    cfg_dir = Path(__file__).resolve().parents[2] / "config/integrations/adapters"
    router = build_router_from_config_dir(cfg_dir)

    caps = router.capabilities("robinhood_crypto").result
    assert caps["submit_order"] is True
    assert caps["close_position"] is True

    open_orders = router.get_open_orders("robinhood_crypto").result
    assert isinstance(open_orders, dict)
