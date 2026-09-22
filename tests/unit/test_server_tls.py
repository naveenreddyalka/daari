"""Native TLS / mTLS wiring for daari serve (#932)."""

from __future__ import annotations

import ssl
from pathlib import Path

import pytest
from typer.testing import CliRunner

from daari.cli.app import app
from daari.config.settings import Settings, TlsSettings
from daari.server.tls import build_uvicorn_ssl_kwargs, materialize_tls_path


def _write_pem(path: Path, kind: str = "CERTIFICATE") -> Path:
    path.write_text(
        f"-----BEGIN {kind}-----\nMIIB\n-----END {kind}-----\n",
        encoding="utf-8",
    )
    return path


class TestTlsSettings:
    def test_defaults_empty(self) -> None:
        tls = TlsSettings()
        assert tls.cert_file == ""
        assert tls.key_file == ""
        assert tls.client_ca == ""

    def test_nested_under_server_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DAARI_SERVER__TLS__CERT_FILE", "/certs/tls.crt")
        monkeypatch.setenv("DAARI_SERVER__TLS__KEY_FILE", "/certs/tls.key")
        monkeypatch.setenv("DAARI_SERVER__TLS__CLIENT_CA", "/certs/ca.crt")
        settings = Settings()
        assert settings.server.tls.cert_file == "/certs/tls.crt"
        assert settings.server.tls.key_file == "/certs/tls.key"
        assert settings.server.tls.client_ca == "/certs/ca.crt"


class TestBuildUvicornSslKwargs:
    def test_empty_when_tls_unset(self) -> None:
        assert build_uvicorn_ssl_kwargs(TlsSettings()) == {}

    def test_https_with_cert_and_key(self, tmp_path: Path) -> None:
        cert = _write_pem(tmp_path / "tls.crt")
        key = _write_pem(tmp_path / "tls.key", "PRIVATE KEY")
        kwargs = build_uvicorn_ssl_kwargs(
            TlsSettings(cert_file=str(cert), key_file=str(key))
        )
        assert kwargs["ssl_certfile"] == str(cert)
        assert kwargs["ssl_keyfile"] == str(key)
        assert "ssl_ca_certs" not in kwargs
        assert "ssl_cert_reqs" not in kwargs

    def test_mtls_when_client_ca_set(self, tmp_path: Path) -> None:
        cert = _write_pem(tmp_path / "tls.crt")
        key = _write_pem(tmp_path / "tls.key", "PRIVATE KEY")
        ca = _write_pem(tmp_path / "ca.crt")
        kwargs = build_uvicorn_ssl_kwargs(
            TlsSettings(
                cert_file=str(cert),
                key_file=str(key),
                client_ca=str(ca),
            )
        )
        assert kwargs["ssl_ca_certs"] == str(ca)
        assert kwargs["ssl_cert_reqs"] == ssl.CERT_REQUIRED

    def test_key_accepts_secret_ref(self, tmp_path: Path) -> None:
        cert = _write_pem(tmp_path / "tls.crt")
        key_pem = tmp_path / "key.pem"
        key_pem.write_text(
            "-----BEGIN PRIVATE KEY-----\nSECRETKEY\n-----END PRIVATE KEY-----\n",
            encoding="utf-8",
        )
        ref = f"secret://exec/cat {key_pem}"
        kwargs = build_uvicorn_ssl_kwargs(
            TlsSettings(cert_file=str(cert), key_file=ref)
        )
        key_path = Path(kwargs["ssl_keyfile"])
        assert key_path.is_file()
        assert "PRIVATE KEY" in key_path.read_text(encoding="utf-8")
        assert kwargs["ssl_certfile"] == str(cert)

    def test_materialize_plain_path(self, tmp_path: Path) -> None:
        path = _write_pem(tmp_path / "ca.crt")
        assert materialize_tls_path(str(path)) == str(path)

    def test_requires_both_cert_and_key(self, tmp_path: Path) -> None:
        cert = _write_pem(tmp_path / "tls.crt")
        with pytest.raises(ValueError, match="cert_file|key_file"):
            build_uvicorn_ssl_kwargs(TlsSettings(cert_file=str(cert), key_file=""))


class TestServeTlsFlags:
    def test_serve_passes_ssl_kwargs_to_uvicorn(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        cert = _write_pem(tmp_path / "tls.crt")
        key = _write_pem(tmp_path / "tls.key", "PRIVATE KEY")
        captured: dict = {}

        def fake_load(*, strict: bool = False):
            return Settings.model_validate(
                {
                    "server": {
                        "host": "127.0.0.1",
                        "port": 11435,
                        "tls": {
                            "cert_file": str(cert),
                            "key_file": str(key),
                        },
                    },
                }
            )

        def fake_create_app(settings):
            return object()

        def fake_run(_app, **kwargs):
            captured.update(kwargs)

        monkeypatch.setattr("daari.cli.app.Settings.load", fake_load)
        monkeypatch.setattr("daari.cli.app.create_app", fake_create_app)
        monkeypatch.setattr("daari.cli.app.uvicorn.run", fake_run)

        runner = CliRunner()
        result = runner.invoke(app, ["serve"])
        assert result.exit_code == 0, result.output
        assert captured["ssl_certfile"] == str(cert)
        assert captured["ssl_keyfile"] == str(key)
        assert "https://" in result.output

    def test_cli_flags_override_settings(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        cert = _write_pem(tmp_path / "cli.crt")
        key = _write_pem(tmp_path / "cli.key", "PRIVATE KEY")
        captured: dict = {}

        def fake_load(*, strict: bool = False):
            return Settings.model_validate({"server": {"host": "127.0.0.1", "port": 11435}})

        monkeypatch.setattr("daari.cli.app.Settings.load", fake_load)
        monkeypatch.setattr("daari.cli.app.create_app", lambda settings: object())
        monkeypatch.setattr(
            "daari.cli.app.uvicorn.run",
            lambda _app, **kwargs: captured.update(kwargs),
        )

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["serve", "--tls-cert", str(cert), "--tls-key", str(key)],
        )
        assert result.exit_code == 0, result.output
        assert captured["ssl_certfile"] == str(cert)
        assert captured["ssl_keyfile"] == str(key)

    def test_cli_client_ca_enables_mtls(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        cert = _write_pem(tmp_path / "tls.crt")
        key = _write_pem(tmp_path / "tls.key", "PRIVATE KEY")
        ca = _write_pem(tmp_path / "ca.crt")
        captured: dict = {}

        monkeypatch.setattr(
            "daari.cli.app.Settings.load",
            lambda *, strict=False: Settings.model_validate(
                {"server": {"host": "127.0.0.1", "port": 11435}}
            ),
        )
        monkeypatch.setattr("daari.cli.app.create_app", lambda settings: object())
        monkeypatch.setattr(
            "daari.cli.app.uvicorn.run",
            lambda _app, **kwargs: captured.update(kwargs),
        )

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "serve",
                "--tls-cert",
                str(cert),
                "--tls-key",
                str(key),
                "--tls-client-ca",
                str(ca),
            ],
        )
        assert result.exit_code == 0, result.output
        assert captured["ssl_ca_certs"] == str(ca)
        assert captured["ssl_cert_reqs"] == ssl.CERT_REQUIRED
