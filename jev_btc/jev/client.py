"""Thin adapter around the Jev (TypeSafe AI) System One HTTP API.

Everything that depends on the exact API shape lives in THIS file, so if the official
docs differ, only this file needs to change.

API shape used (from TypeSafe's published curl example; TODO(verify) against
https://docs.typesafe.ai before a long run - it could not be opened from the dev environment):

  POST {JEV_BASE_URL}/v1/systemone
  Authorization: Bearer <JEV_API_KEY>
  {
    "model": "jev-latest",
    "state": "<context string>",
    "questions": {
      "<name>": {"type": "choice", "instructions": "...", "criteria": {"up": "...", "down": "..."}}
    }
  }
  ->
  {
    "model": "jev-1.13.0",
    "answers": {"<name>": {"type": "choice", "choice": "up", "confidence": 0.8,
                            "probabilities": {"up": 0.78, "down": 0.22}}},
    "usage": {"input_tokens": 382, "output_tokens": 55}
  }

Run `python main.py jev-test` to print one raw response and check this.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field

import httpx

from config import Config

log = logging.getLogger(__name__)


# ---------------- errors ----------------
class JevError(Exception):
    kind = "error"


class JevTimeout(JevError):
    kind = "timeout"


class JevRateLimited(JevError):
    kind = "rate_limited"

    def __init__(self, msg: str, retry_after: float | None = None):
        super().__init__(msg)
        self.retry_after = retry_after


class JevHTTPError(JevError):
    kind = "http_error"

    def __init__(self, msg: str, status: int):
        super().__init__(msg)
        self.status = status


class JevMalformedResponse(JevError):
    kind = "malformed"


# ---------------- result ----------------
@dataclass
class ChoiceAnswer:
    choice: str
    probabilities: dict[str, float]
    confidence: float | None


@dataclass
class JevResult:
    model: str
    answers: dict[str, ChoiceAnswer]
    input_tokens: int
    output_tokens: int
    latency_ms: float
    attempts: int
    raw: dict = field(repr=False, default_factory=dict)


@dataclass
class CallRecord:
    """One HTTP attempt, for cost / reliability accounting."""

    ok: bool
    error_type: str | None
    http_status: int | None
    latency_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


# ---------------- rate limiter ----------------
class RateLimiter:
    """Allows at most `rate` calls per second (evenly spaced)."""

    def __init__(self, rate: float):
        self.interval = 1.0 / rate if rate > 0 else 0.0
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._next > now:
                await asyncio.sleep(self._next - now)
            self._next = max(now, self._next) + self.interval

    def penalize(self, seconds: float) -> None:
        """After a 429: block everyone for a while."""
        self._next = max(self._next, time.monotonic() + seconds)


# ---------------- parsing ----------------
def parse_choice(answer: dict, options: list[str]) -> ChoiceAnswer:
    """Validate one choice answer. Raises JevMalformedResponse on anything unexpected."""
    if not isinstance(answer, dict):
        raise JevMalformedResponse(f"answer is not an object: {answer!r:.200}")
    probs = answer.get("probabilities")
    if not isinstance(probs, dict):
        raise JevMalformedResponse(f"missing probabilities: {answer!r:.200}")
    out: dict[str, float] = {}
    for opt in options:
        v = probs.get(opt)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not (0.0 <= v <= 1.0):
            raise JevMalformedResponse(f"bad probability for {opt!r}: {v!r}")
        out[opt] = float(v)
    total = sum(out.values())
    if not (0.98 <= total <= 1.02):
        raise JevMalformedResponse(f"probabilities sum to {total:.3f}")
    out = {k: v / total for k, v in out.items()}
    conf = answer.get("confidence")
    if conf is not None and (not isinstance(conf, (int, float)) or not (0.0 <= conf <= 1.0)):
        raise JevMalformedResponse(f"bad confidence: {conf!r}")
    choice = answer.get("choice")
    if choice not in options:
        choice = max(out, key=out.get)
    return ChoiceAnswer(choice=choice, probabilities=out, confidence=None if conf is None else float(conf))


# ---------------- clients ----------------
class JevClient:
    def __init__(self, cfg: Config, on_call=None):
        """on_call(CallRecord) is called after every HTTP attempt (for cost logging)."""
        if not cfg.jev_api_key:
            raise ValueError("JEV_API_KEY is empty. Put it in .env, or set JEV_MOCK=1 to test without it.")
        self.cfg = cfg
        self.on_call = on_call or (lambda rec: None)
        self.limiter = RateLimiter(cfg.jev_max_calls_per_sec)
        self.http = httpx.AsyncClient(
            base_url=cfg.jev_base_url,
            headers={"Authorization": f"Bearer {cfg.jev_api_key}", "Content-Type": "application/json"},
            timeout=httpx.Timeout(cfg.jev_timeout_sec),
            limits=httpx.Limits(max_connections=cfg.jev_max_inflight * 2, max_keepalive_connections=cfg.jev_max_inflight),
        )

    async def aclose(self) -> None:
        await self.http.aclose()

    def _cost(self, inp: int, out: int) -> float:
        return inp / 1e6 * self.cfg.jev_cost_per_m_input + out / 1e6 * self.cfg.jev_cost_per_m_output

    async def raw_request(self, state: str, questions: dict) -> tuple[int, dict | str, float, httpx.Headers]:
        payload = {"model": self.cfg.jev_model, "state": state, "questions": questions}
        t0 = time.perf_counter()
        r = await self.http.post("/v1/systemone", json=payload)
        ms = (time.perf_counter() - t0) * 1000
        try:
            body = r.json()
        except ValueError:
            body = r.text
        return r.status_code, body, ms, r.headers

    async def _attempt(self, state: str, questions: dict, choice_options: dict[str, list[str]]) -> JevResult:
        await self.limiter.wait()
        try:
            status, body, ms, headers = await self.raw_request(state, questions)
        except httpx.TimeoutException as e:
            self.on_call(CallRecord(False, "timeout", None, self.cfg.jev_timeout_sec * 1000))
            raise JevTimeout(str(e)) from e
        except httpx.HTTPError as e:
            self.on_call(CallRecord(False, "network", None, 0.0))
            raise JevError(f"network: {e!r}") from e

        if status == 429:
            try:
                ra = float(headers.get("Retry-After", ""))
            except ValueError:
                ra = None
            self.on_call(CallRecord(False, "rate_limited", status, ms))
            raise JevRateLimited("429 rate limited", ra)
        if status >= 400:
            self.on_call(CallRecord(False, "http_error", status, ms))
            raise JevHTTPError(f"HTTP {status}: {str(body)[:300]}", status)
        if not isinstance(body, dict) or not isinstance(body.get("answers"), dict):
            self.on_call(CallRecord(False, "malformed", status, ms))
            raise JevMalformedResponse(f"unexpected body: {str(body)[:300]}")

        usage = body.get("usage") or {}
        inp = int(usage.get("input_tokens") or 0)
        out = int(usage.get("output_tokens") or 0)
        try:
            answers = {name: parse_choice(body["answers"].get(name), opts) for name, opts in choice_options.items()}
        except JevMalformedResponse:
            # tokens were still consumed -> still count the cost
            self.on_call(CallRecord(False, "malformed", status, ms, inp, out, self._cost(inp, out)))
            raise
        self.on_call(CallRecord(True, None, status, ms, inp, out, self._cost(inp, out)))
        return JevResult(str(body.get("model", "")), answers, inp, out, ms, 1, raw=body)

    async def decide(self, state: str, questions: dict) -> JevResult:
        """Ask choice questions. Retries timeouts / 429 / 5xx up to JEV_MAX_RETRIES times."""
        choice_options = {n: list(q["criteria"].keys()) for n, q in questions.items() if q.get("type") == "choice"}
        attempt = 0
        while True:
            attempt += 1
            try:
                res = await self._attempt(state, questions, choice_options)
                res.attempts = attempt
                return res
            except JevRateLimited as e:
                wait = e.retry_after or 2.0 ** attempt
                self.limiter.penalize(wait)
                err: JevError = e
            except JevHTTPError as e:
                if e.status < 500:  # 4xx other than 429: our request is wrong, do not retry
                    raise
                err = e
            except (JevTimeout, JevError) as e:
                if isinstance(e, JevMalformedResponse):
                    raise
                err = e
            if attempt > self.cfg.jev_max_retries:
                raise err
            await asyncio.sleep(0.2 * attempt + random.uniform(0, 0.2))


class MockJevClient:
    """Random predictions with the same interface. No network, no cost.

    Useful to test the whole pipeline, and as a sanity check: its accuracy MUST be ~50%.
    """

    def __init__(self, cfg: Config, on_call=None):
        self.cfg = cfg
        self.on_call = on_call or (lambda rec: None)
        self.delay = (0.05, 0.15)  # fake latency range in seconds

    async def aclose(self) -> None:
        pass

    async def decide(self, state: str, questions: dict) -> JevResult:
        await asyncio.sleep(random.uniform(*self.delay))
        answers = {}
        for name, q in questions.items():
            opts = list(q["criteria"].keys())
            p = random.betavariate(2, 2)
            probs = {opts[0]: p, opts[1]: 1 - p} if len(opts) == 2 else {o: 1 / len(opts) for o in opts}
            answers[name] = ChoiceAnswer(max(probs, key=probs.get), probs, abs(2 * p - 1))
        inp = len(state) // 4
        self.on_call(CallRecord(True, None, 200, 100.0, inp, 0, 0.0))
        return JevResult("mock", answers, inp, 0, 100.0, 1)


def make_client(cfg: Config, on_call=None):
    return MockJevClient(cfg, on_call) if cfg.jev_mock else JevClient(cfg, on_call)
