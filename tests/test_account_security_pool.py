"""Security transport reuse must never reuse account decisions or concurrent sessions."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest.mock import Mock, patch

import pytest

from backend.services.account_security import AccountSecurityService


def session():
    value = Mock()
    value.post.return_value.json.return_value = {
        "users": [{"localId": "account", "emailVerified": True, "mfaInfo": []}]}
    return value


def test_reuses_transport_but_reads_current_policy_for_every_request():
    transport = session()
    service = AccountSecurityService(Mock(), max_idle_sessions=2)
    with patch("backend.services.account_security.AuthorizedSession", return_value=transport) as factory:
        assert service.read("account")["mfa_enabled"] is False
        transport.post.return_value.json.return_value["users"][0]["mfaInfo"] = [{"totpInfo": {}}]
        assert service.read("account")["mfa_enabled"] is True
    factory.assert_called_once()
    assert transport.post.call_count == 2
    assert transport.post.return_value.close.call_count == 2
    transport.close.assert_not_called()
    service.close()
    service.close()
    transport.close.assert_called_once()
    with pytest.raises(RuntimeError, match="closed"):
        service.read("account")


@pytest.mark.parametrize("phase", ["post", "raise_for_status", "json"])
def test_failures_discard_the_transport_and_next_request_can_recover(phase):
    broken, working = session(), session()
    target = broken.post if phase == "post" else getattr(broken.post.return_value, phase)
    target.side_effect = RuntimeError("PRIVATE_FAILURE")
    service = AccountSecurityService(Mock(), max_idle_sessions=1)
    with patch("backend.services.account_security.AuthorizedSession", side_effect=[broken, working]):
        with pytest.raises(RuntimeError):
            service.read("account")
        assert service.read("account")["mfa_enabled"] is False
    broken.close.assert_called_once()
    working.close.assert_not_called()
    service.close()
    working.close.assert_called_once()


def test_simultaneous_requests_exclusively_borrow_sessions_and_bound_idle_connections():
    ready = Barrier(5)
    transports = [session() for _ in range(4)]
    for transport in transports:
        original = transport.post.return_value
        def post(*args, response=original, **kwargs):
            ready.wait(timeout=5)
            return response
        transport.post.side_effect = post
    service = AccountSecurityService(Mock(), max_idle_sessions=2)
    with patch("backend.services.account_security.AuthorizedSession", side_effect=transports), ThreadPoolExecutor(4) as pool:
        futures = [pool.submit(service.read, "account") for _ in range(4)]
        ready.wait(timeout=5)
        assert all(future.result(timeout=5)["mfa_enabled"] is False for future in futures)
    assert all(transport.post.call_count == 1 for transport in transports)
    assert sum(transport.close.call_count for transport in transports) == 2
    service.close()
    assert all(transport.close.call_count == 1 for transport in transports)


def test_shutdown_closes_an_active_session_when_it_returns():
    started, release = Event(), Event()
    transport = session()
    response = transport.post.return_value
    def post(*args, **kwargs):
        started.set()
        assert release.wait(5)
        return response
    transport.post.side_effect = post
    service = AccountSecurityService(Mock(), max_idle_sessions=1)
    with patch("backend.services.account_security.AuthorizedSession", return_value=transport), ThreadPoolExecutor(1) as pool:
        pending = pool.submit(service.read, "account")
        try:
            assert started.wait(5)
            service.close()
        finally:
            release.set()
        assert pending.result(timeout=5)["mfa_enabled"] is False
    transport.close.assert_called_once()
