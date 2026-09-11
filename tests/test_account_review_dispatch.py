from types import SimpleNamespace
from unittest.mock import Mock

from toujing_core_runtime.review import ReviewRuntime


def test_account_scope_dispatch_does_not_require_or_fabricate_episode():
    review = ReviewRuntime.__new__(ReviewRuntime)
    service = Mock()
    review._account_service = service
    params = {"scope_kind": "account", "subject_id": "owned", "account_id": "account", "data_mode": "real_user"}
    for method in ("context", "start", "poll"):
        getattr(service, method).return_value = {"method": method}
        assert getattr(review, method)(params) == {"method": method}
        getattr(service, method).assert_called_once_with(params)
    assert "episode_id" not in params


def test_delete_account_cleans_both_review_scopes_and_preserves_other_accounts():
    review = ReviewRuntime.__new__(ReviewRuntime)
    review._account_service = Mock()
    review.store = Mock()
    owned = {"scope": ("owned", "one", "episode"), "cancelled": Mock(), "future": Mock()}
    other = {"scope": ("owned", "two", "episode"), "cancelled": Mock(), "future": Mock()}
    review.jobs = {"owned": owned, "other": other}
    review.drop_account("owned", "one")
    review._account_service.drop_account.assert_called_once_with("owned", "one")
    review.store.delete_account_read_models.assert_called_once_with("owned", "one")
    owned["cancelled"].set.assert_called_once()
    owned["future"].cancel.assert_called_once()
    other["cancelled"].set.assert_not_called()
    assert review.jobs == {"other": other}


def test_runtime_shutdown_closes_account_worker_too():
    review = ReviewRuntime.__new__(ReviewRuntime)
    review._account_service = Mock()
    review.jobs = {}
    review.executor = Mock()
    review.close()
    review._account_service.close.assert_called_once()
    review.executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
