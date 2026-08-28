from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from daari.config.settings import Settings
from daari.setup.daemon import ensure_local_daemon
from daari.setup.doctor import doctor_exit_code
from daari.setup.doctor import run_doctor as run_doctor_checks
from daari.setup.models import fetch_ollama_models, model_present, pull_ollama_model

OLLAMA_DOWNLOAD_URL = "https://ollama.com/download"


@dataclass(frozen=True)
class OnboardStep:
    name: str
    ok: bool
    detail: str


@dataclass
class OnboardReport:
    steps: list[OnboardStep] = field(default_factory=list)
    pulled: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    ready: bool = False
    served: bool = False

    def step(self, name: str) -> OnboardStep | None:
        for item in self.steps:
            if item.name == name:
                return item
        return None


def default_onboard_models(
    settings: Settings,
    *,
    pull_l4: bool = False,
    pull_l5: bool = False,
    minimal: bool = False,
) -> list[str]:
    models = [settings.models.l3]
    if not minimal:
        models.append(settings.cache.l1.embedding_model)
    if pull_l4:
        models.append(settings.models.l4)
    if pull_l5:
        models.append(settings.models.l5)
    return models


def run_onboard(
    settings: Settings | None = None,
    *,
    pull: bool = True,
    run_doctor: bool = True,
    pull_l4: bool = False,
    pull_l5: bool = False,
    minimal: bool = False,
    httpx_client: httpx.Client | None = None,
    pull_fn: Callable[[str], bool] | None = None,
    fetch_models_fn: Callable[[], list[str]] | None = None,
    doctor_fn: Callable[..., list] | None = None,
    start_serve: bool = False,
    serve_fn: Callable[[], bool] | None = None,
) -> OnboardReport:
    cfg = settings or Settings.load()
    report = OnboardReport()
    py = sys.version_info
    py_ok = py >= (3, 12)
    report.steps.append(
        OnboardStep(
            name="python",
            ok=py_ok,
            detail=f"{py.major}.{py.minor}.{py.micro}"
            + ("" if py_ok else " (requires Python 3.12+)"),
        )
    )

    available: list[str] | None = None
    fetch = fetch_models_fn
    if fetch is None:

        def fetch() -> list[str]:
            return fetch_ollama_models(cfg.ollama.base_url, client=httpx_client)

    try:
        available = fetch()
        report.steps.append(
            OnboardStep(name="ollama", ok=True, detail=f"reachable at {cfg.ollama.base_url}")
        )
    except Exception as exc:
        report.steps.append(
            OnboardStep(
                name="ollama",
                ok=False,
                detail=f"unreachable at {cfg.ollama.base_url} ({exc}). Install from {OLLAMA_DOWNLOAD_URL}",
            )
        )

    pulls_ok = True
    if pull and available is not None:
        do_pull = pull_fn or pull_ollama_model
        for model in default_onboard_models(
            cfg, pull_l4=pull_l4, pull_l5=pull_l5, minimal=minimal
        ):
            if model_present(model, available):
                report.skipped.append(model)
                continue
            if do_pull(model):
                report.pulled.append(model)
                report.steps.append(OnboardStep(name=f"pull:{model}", ok=True, detail="pulled"))
            else:
                pulls_ok = False
                report.steps.append(
                    OnboardStep(
                        name=f"pull:{model}",
                        ok=False,
                        detail=f"failed — run: ollama pull {model}",
                    )
                )

    doctor_ok = True
    if run_doctor:
        check = doctor_fn or (
            lambda *_a, **_k: run_doctor_checks(cfg, httpx_client=httpx_client)
        )
        results = check(cfg, httpx_client=httpx_client)
        doctor_ok = doctor_exit_code(results) == 0
        report.steps.append(
            OnboardStep(
                name="doctor",
                ok=doctor_ok,
                detail="passed" if doctor_ok else "failed — run: daari doctor",
            )
        )

    ollama_ok = report.step("ollama") is not None and report.step("ollama").ok
    report.ready = py_ok and ollama_ok and pulls_ok and doctor_ok
    if not ollama_ok:
        report.next_steps.append(f"Install Ollama from {OLLAMA_DOWNLOAD_URL}")
    if start_serve and report.ready:
        start = serve_fn or (lambda: ensure_local_daemon(cfg))
        ok = start()
        listen = f"http://{cfg.server.host}:{cfg.server.port}/v1"
        report.served = ok
        report.steps.append(
            OnboardStep(
                name="serve",
                ok=ok,
                detail=f"listening at {listen}" if ok else "failed to become healthy",
            )
        )
        report.ready = report.ready and ok
        if ok:
            report.next_steps.append(listen)
            report.next_steps.append(f"GET http://{cfg.server.host}:{cfg.server.port}/ready")
        else:
            report.next_steps.append("daari serve")
    else:
        report.next_steps.append("daari serve")
    return report
