import socket

import pytest

from ai_signal_api.modules.collection.collectors import validate_public_url


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.1.2.3",
        "169.254.169.254",
        "::1",
        "fc00::1",
    ],
)
def test_source_url_rejects_non_public_dns_targets(
    monkeypatch: pytest.MonkeyPatch,
    address: str,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (
                socket.AF_INET6 if ":" in address else socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                (address, 443),
            )
        ],
    )

    with pytest.raises(ValueError, match="SOURCE_URL_PRIVATE_ADDRESS"):
        validate_public_url("https://example.test/feed.xml")


def test_source_url_rejects_credentials_before_network_lookup() -> None:
    with pytest.raises(ValueError, match="SOURCE_URL_UNSAFE"):
        validate_public_url(
            "https://test-only-user:test-only-password@example.test/feed.xml"
        )
