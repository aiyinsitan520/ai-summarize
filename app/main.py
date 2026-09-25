"""FastAPI service and bounded background worker pool."""

from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .config import Settings
from .media import MediaError
from .pipeline import analyze
from .provider import ProviderError
from .security import validate_video_url
from .store import TaskStore

STATIC_DIR = Path(__file__).parent / "static"


class TaskRequest(BaseModel):
    url: str = Field(min_length=10, max_length=2048)
    language: str = Field(default="中文", min_length=1, max_length=30)
    focus: str = Field(default="", max_length=1000)


class TaskRunner:
    def __init__(self, store: TaskStore, settings: Settings):
        self.store = store
        self.settings = settings
        self.pool = ThreadPoolExecutor(max_workers=settings.max_concurrent_tasks)
        self.tmp_root = settings.data_dir / "tmp"
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        self.tmp_root.mkdir(parents=True, exist_ok=True)

    def submit(self, task_id: str) -> None:
        self.pool.submit(self._run, task_id)

    def resume(self) -> None:
        for task in self.store.recover_pending():
            self.submit(task["id"])

    def _run(self, task_id: str) -> None:
        task = self.store.get(task_id)
        if task is None:
            return
        folder = self.tmp_root / task_id
        try:
            def progress(stage: str, percent: int) -> None:
                self.store.update(task_id, status="running", stage=stage, progress=percent)

            result = analyze(
                task["url"], task["platform"], task["language"], task["focus"],
                folder, self.settings, progress,
            )
            self.store.update(task_id, status="completed", stage="完成", progress=100,
                              result=result)
        except (MediaError, ProviderError, ValueError) as exc:
            self.store.update(task_id, status="failed", stage="失败", progress=0,
                              error=str(exc))
        except Exception:
            self.store.update(task_id, status="failed", stage="失败", progress=0,
                              error="处理失败，请查看服务日志")
            raise
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def close(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        load_dotenv(Path.cwd() / ".env")
        settings = Settings.from_env()
    store = TaskStore(settings.data_dir / "tasks.db")
    runner = TaskRunner(store, settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        runner.resume()
        yield
        runner.close()

    app = FastAPI(title="OmniVideo Insight", version="0.1.0", lifespan=lifespan)
    app.state.store = store
    app.state.runner = runner

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/app.js", include_in_schema=False)
    def script() -> FileResponse:
        return FileResponse(STATIC_DIR / "app.js", media_type="application/javascript")

    @app.get("/style.css", include_in_schema=False)
    def style() -> FileResponse:
        return FileResponse(STATIC_DIR / "style.css", media_type="text/css")

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "api_key_configured": bool(settings.api_key and settings.transcription_key),
        }

    @app.post("/api/tasks", status_code=202)
    def create_task(request: TaskRequest) -> dict:
        try:
            platform, url = validate_video_url(request.url)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not settings.api_key or not settings.transcription_key:
            raise HTTPException(status_code=503, detail="请先配置 API 密钥")
        task = store.create(url, platform, request.language, request.focus)
        runner.submit(task["id"])
        return task

    @app.get("/api/tasks")
    def list_tasks(limit: int = 20) -> list[dict]:
        return store.list(max(1, min(limit, 100)))

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str) -> dict:
        task = store.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return task

    return app


app = create_app()
