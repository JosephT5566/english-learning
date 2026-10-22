from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.public_admission import AdmissionRejection, PublicAdmission, PublicPermit


def test_source_refill_and_denials_do_not_consume_global_tokens() -> None:
    now = [0.0]
    admission = PublicAdmission(Settings(), clock=lambda: now[0])
    for _ in range(2):
        permit = admission.try_acquire("a")
        assert isinstance(permit, PublicPermit)
        permit.release()
        permit.release()
    rejection = admission.try_acquire("a")
    assert rejection == AdmissionRejection("rate_limited", 10)
    assert admission._global.tokens == 8
    now[0] = 9
    assert admission.try_acquire("a") == AdmissionRejection("rate_limited", 1)
    now[0] = 10
    assert isinstance(admission.try_acquire("a"), PublicPermit)


def test_concurrent_callers_never_queue_or_consume_on_busy() -> None:
    admission = PublicAdmission(Settings(public_review_max_in_flight=1))
    barrier = Barrier(16)

    def acquire(index: int) -> PublicPermit | AdmissionRejection:
        barrier.wait()
        return admission.try_acquire(str(index))

    with ThreadPoolExecutor(max_workers=16) as executor:
        results = list(executor.map(acquire, range(16)))
    permits = [result for result in results if isinstance(result, PublicPermit)]
    assert len(permits) == 1
    assert all(
        isinstance(result, PublicPermit) or result == AdmissionRejection("busy", 1)
        for result in results
    )
    assert admission._global.tokens >= 9
    permits[0].release()
    assert admission._in_flight == 0


def test_global_bucket_covers_distinct_sources_and_processes_are_independent() -> None:
    settings = Settings(public_review_global_burst=1)
    first = PublicAdmission(settings, clock=lambda: 0)
    permit = first.try_acquire("a")
    assert isinstance(permit, PublicPermit)
    permit.release()
    assert first.try_acquire("b") == AdmissionRejection("rate_limited", 1)
    assert isinstance(PublicAdmission(settings).try_acquire("b"), PublicPermit)


def test_full_map_does_not_evict_active_buckets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.public_admission.SOURCE_CAPACITY", 1)
    now = [0.0]
    admission = PublicAdmission(Settings(), clock=lambda: now[0])
    permit = admission.try_acquire("a")
    assert isinstance(permit, PublicPermit)
    permit.release()
    assert admission.try_acquire("b") == AdmissionRejection("source_capacity", 1)
    now[0] = 599
    assert admission.try_acquire("b") == AdmissionRejection("source_capacity", 1)
    now[0] = 600
    assert isinstance(admission.try_acquire("b"), PublicPermit)
    assert "a" not in admission._sources


def test_client_keys_normalize_ip_and_share_unusable_fallback() -> None:
    admission = PublicAdmission(Settings())
    assert admission.client_key("::ffff:192.0.2.1") == admission.client_key("192.0.2.1")
    assert admission.client_key("2001:db8::1") == admission.client_key("2001:0db8:0::1")
    assert admission.client_key(None) == admission.client_key("not-ip")
    assert admission.client_key("192.0.2.1") != "192.0.2.1"
    assert admission.client_key("192.0.2.1") != PublicAdmission(Settings()).client_key(
        "192.0.2.1"
    )


@pytest.mark.parametrize(
    "field",
    [
        "public_review_requests_per_minute",
        "public_review_burst",
        "public_review_global_requests_per_minute",
        "public_review_global_burst",
        "public_review_max_in_flight",
        "public_review_query_timeout_ms",
    ],
)
@pytest.mark.parametrize("value", [0, -1, 1000000])
def test_settings_bound_admission_fields(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value})


@pytest.mark.parametrize(
    "value",
    [
        '["bad"]',
        '["10000000-0000-0000-0000-000000000001", "10000000-0000-0000-0000-000000000001"]',
        "not-json",
    ],
)
def test_public_deck_configuration_is_sanitized(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    from app.config import ConfigurationError, load_settings

    monkeypatch.setenv("PUBLIC_REVIEW_DECK_IDS", value)
    with pytest.raises(ConfigurationError) as caught:
        load_settings()
    assert value not in str(caught.value)


def test_expiry_never_resets_a_not_fully_refilled_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.public_admission.SOURCE_CAPACITY", 1)
    now = [0.0]
    admission = PublicAdmission(
        Settings(
            public_review_requests_per_minute=1,
            public_review_burst=20,
            public_review_global_burst=100,
        ),
        clock=lambda: now[0],
    )
    for _ in range(20):
        permit = admission.try_acquire("a")
        assert isinstance(permit, PublicPermit)
        permit.release()
    now[0] = 600
    assert admission.try_acquire("b") == AdmissionRejection("source_capacity", 1)
    now[0] = 1200
    assert isinstance(admission.try_acquire("b"), PublicPermit)


def test_global_refill_delay_is_derived_without_consuming_source_tokens() -> None:
    now = [0.0]
    admission = PublicAdmission(
        Settings(
            public_review_global_requests_per_minute=3, public_review_global_burst=1
        ),
        clock=lambda: now[0],
    )
    permit = admission.try_acquire("a")
    assert isinstance(permit, PublicPermit)
    permit.release()
    assert admission.try_acquire("b") == AdmissionRejection("rate_limited", 20)
    assert admission._sources["b"].tokens == 2
    now[0] = 19.5
    assert admission.try_acquire("b") == AdmissionRejection("rate_limited", 1)
    now[0] = 20
    assert isinstance(admission.try_acquire("b"), PublicPermit)
