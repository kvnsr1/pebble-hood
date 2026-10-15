import copy
import threading
import time
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from .store import from_env, digest
from .finance import chart_pixels
from .providers import DemoProvider, RobinhoodProvider, ProviderError

PAGE_SIZE = 6
TTL = 60


class Pair(BaseModel):
    code: str = Field(min_length=12, max_length=64)


def create_app(vault=None, clock=time.time):
    vault = vault or from_env()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    providers = {"demo": DemoProvider(), "robinhood": RobinhoodProvider(vault)}
    lock = threading.RLock()
    attempts = []

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
        return JSONResponse(
            {"state": exc.code},
            status_code=401 if exc.code.startswith("AUTH_") else 503,
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
        return {"token": token}

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
