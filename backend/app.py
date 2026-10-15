import copy
import os
import threading
import time
from pathlib import Path
import httpx
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from .store import from_env, digest
from .finance import chart_pixels
from .providers import DemoProvider, RobinhoodProvider, ProviderError
from .oauth import BrowserOAuth, COOKIE, SESSION_TTL, origin

PAGE_SIZE = 6
TTL = 60


class Pair(BaseModel):
    code: str = Field(min_length=12, max_length=64)


class BrowserAction(BaseModel):
    csrf: str = Field(min_length=32, max_length=100)


def create_app(
    vault=None, clock=time.time, backend_url=None, oauth_client_factory=None
):
    vault = vault or from_env()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    providers = {"demo": DemoProvider(), "robinhood": RobinhoodProvider(vault)}
    lock = threading.RLock()
    attempts = []
    backend_url = (
        (
            os.environ.get("HOOD_BACKEND_URL")
            or os.environ.get("RENDER_EXTERNAL_URL", "")
        )
        if backend_url is None
        else backend_url
    )
    if backend_url:
        backend_url = origin(backend_url)
    oauth = BrowserOAuth(vault, backend_url, clock, oauth_client_factory)

    @app.middleware("http")
    async def secure(request, call_next):
        response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            }
        )
        if backend_url:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    def auth(request: Request):
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer ") or len(header) > 100:
            raise HTTPException(401, detail="AUTH_REQUIRED")
        key = "device:" + digest(header[7:])
        if not vault.get(key):
            raise HTTPException(401, detail="AUTH_EXPIRED")
        return key

    def provider(name):
        if name not in providers:
            raise HTTPException(400, detail="INVALID_PROVIDER")
        return providers[name]

    @app.exception_handler(ProviderError)
    async def error(request, exc):
        status = 503
        if exc.code == "BROWSER_AUTH_REQUIRED":
            status = 403
        elif exc.code == "RATE_LIMITED":
            status = 429
        elif exc.code.startswith("AUTH_"):
            status = 401
        return JSONResponse(
            {"state": exc.code},
            status_code=status,
        )

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/configure")
    def configure():
        return FileResponse(Path(__file__).parent.parent / "config/index.html")

    @app.get("/config.js")
    def config_js():
        return FileResponse(
            Path(__file__).parent.parent / "config/config.js",
            media_type="application/javascript",
        )

    @app.get("/config.css")
    def config_css():
        return FileResponse(
            Path(__file__).parent.parent / "config/config.css", media_type="text/css"
        )

    @app.post("/v1/pair")
    def pair(body: Pair):
        with lock:
            now = clock()
            attempts[:] = [x for x in attempts if now - x < 60]
            if len(attempts) >= 10:
                raise HTTPException(429, detail="RATE_LIMITED")
            attempts.append(now)
            token = vault.exchange(body.code)
        if not token:
            raise HTTPException(401, detail="PAIRING_EXPIRED")
        response = JSONResponse({"token": token})
        response.set_cookie(
            COOKIE,
            oauth.authorize_browser("device:" + digest(token)),
            max_age=SESSION_TTL,
            secure=True,
            httponly=True,
            samesite="lax",
        )
        return response

    @app.get("/v1/connection")
    def connection(request: Request, device=Depends(auth)):
        with lock:
            return oauth.status(request.cookies.get(COOKIE), device)

    @app.post("/v1/connection/start")
    def connect_browser(body: BrowserAction, request: Request, device=Depends(auth)):
        try:
            with lock:
                return {
                    "url": oauth.start(request.cookies.get(COOKIE), device, body.csrf)
                }
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise ProviderError("OAUTH_PROVIDER_FAILURE") from None

    @app.get("/oauth/robinhood/callback")
    def callback(request: Request):
        result = "CONNECTED"
        q = request.query_params
        try:
            if any(len(q.getlist(k)) > 1 for k in ("state", "code", "iss", "error")):
                raise ProviderError("OAUTH_STATE_INVALID")
            with lock:
                oauth.complete(
                    request.cookies.get(COOKIE),
                    q.get("state"),
                    q.get("code"),
                    q.get("iss"),
                    q.get("error"),
                )
        except ProviderError as exc:
            result = exc.code
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            result = "OAUTH_PROVIDER_FAILURE"
        # The callback query may contain credentials. Never echo it or log requests.
        return RedirectResponse("/configure#robinhood=" + result, status_code=303)

    @app.post("/v1/connection/disconnect")
    def disconnect_broker(body: BrowserAction, request: Request, device=Depends(auth)):
        with lock:
            oauth.require_operator(request.cookies.get(COOKIE), device, body.csrf)
            oauth.clear_broker_data()
            vault.delete_prefixes(("device:", "browser:", "pair:"))
        response = JSONResponse({"disconnected": True, "remote_revocation": False})
        response.delete_cookie(COOKIE, secure=True, httponly=True, samesite="lax")
        return response

    @app.get("/v1/accounts")
    def accounts(source: str = "demo", device=Depends(auth)):
        provider(source)
        with lock:
            key = "accounts:" + source
            record = vault.get(key)
            now = int(clock())
            if not record or now - record["fetched"] >= TTL:
                record = {"fetched": now, "accounts": provider(source).accounts()}
                vault.put(key, record)
            return {"accounts": record["accounts"], "provider": source}

    @app.get("/v1/portfolio")
    def portfolio(
        account: str = "demo-main",
        source: str = "demo",
        page: int = 0,
        device=Depends(auth),
    ):
        if len(account) > 96 or page < 0 or page > 166:
            raise HTTPException(400, detail="INVALID_PAGE")
        p = provider(source)
        key = "snapshot:" + digest(source + ":" + account)
        with lock:
            record = vault.get(key)
            now = int(clock())
            if (
                record is None
                or now - record.get("attempted", record["fetched"]) >= TTL
            ):
                try:
                    snapshot = p.snapshot(account, now=now)
                    if len(snapshot["holdings"]) > 1000:
                        raise ProviderError("PORTFOLIO_TOO_LARGE")
                    record = {"fetched": now, "snapshot": snapshot}
                    vault.put(key, record)
                    # Observed balances only. Never interpreted as investment returns.
                    if source != "demo" and snapshot["total"] is not None:
                        history = vault.get("history:" + key, [])
                        if not history or snapshot["as_of"] > history[-1]["at"]:
                            history.append(
                                {"at": snapshot["as_of"], "value": snapshot["total"]}
                            )
                        vault.put("history:" + key, history[-288:])
                except ProviderError as e:
                    if (
                        not record
                        or e.code.startswith("AUTH_")
                        or e.code == "SCHEMA_UNVERIFIED"
                    ):
                        raise
                    record = copy.deepcopy(record)
                    record["snapshot"]["state"] = e.code
                    record["snapshot"]["stale"] = True
                    record["attempted"] = now
                    vault.put(key, record)
            s = copy.deepcopy(record["snapshot"])
            if source != "demo":
                history = vault.get("history:" + key, [])
                s["history"]["points"] = history
                if history:
                    from datetime import datetime, timezone

                    start_label = datetime.fromtimestamp(
                        history[0]["at"], timezone.utc
                    ).strftime("%m/%d %H:%M")
                    s["history"]["label"] = "Balances since " + start_label + "Z"
            s["history"]["pixels"] = chart_pixels(s["history"]["points"])
            rows = s["holdings"]
            start = page * PAGE_SIZE
            if start >= len(rows) and page:
                raise HTTPException(400, detail="INVALID_PAGE")
            s.update(
                holdings=rows[start : start + PAGE_SIZE],
                page=page,
                pages=max(1, (len(rows) + PAGE_SIZE - 1) // PAGE_SIZE),
                holdings_count=len(rows),
            )
            s["stale"] = s["stale"] or now - s["as_of"] > 300
            return s

    @app.post("/v1/disconnect")
    def disconnect(device=Depends(auth)):
        vault.delete(device)
        return {"disconnected": True}

    return app
