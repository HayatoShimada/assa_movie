"""FastAPIアプリ本体。"""

import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.api import assist as assist_api
from backend.api import clips as clips_api
from backend.api import edits as edits_api
from backend.api import jobs as jobs_api
from backend.api import projects as projects_api
from backend.api import questions as questions_api
from backend.api import settings_api
from backend.api import transcripts as transcripts_api
from backend.core import project_settings
from backend.core.config import settings
from backend.jobs import attention_job  # noqa: F401  ジョブハンドラの登録に必要
from backend.jobs import export_job  # noqa: F401
from backend.jobs import filler_job  # noqa: F401
from backend.jobs import judge_job  # noqa: F401
from backend.jobs import resolve_job  # noqa: F401
from backend.jobs import terms_job  # noqa: F401
from backend.jobs import transcribe_job  # noqa: F401
from backend.jobs.queue import JobQueue
from backend.models import schema


def _report_startup_checks() -> None:
    """起動時の軽い確認だけを行う。

    GPU情報(torchの初期化)は実測5秒かかり、その間GILを握るため別スレッドに
    逃がしても起動が止まる。GPU・VRAM・Ollamaの詳細は GET /api/environment
    (設定タブの環境パネルが初回に1回だけ呼ぶ)に任せる。
    """
    from backend.core.device import probe_gpu
    from backend.pipeline.export import FFMPEG_MISSING_MSG, detect_encoder

    encoder = detect_encoder()  # ffmpeg -encoders の実行のみ(実測33ms)
    if encoder is None:
        print(f"⚠ 書き出しには ffmpeg が必要です。{FFMPEG_MISSING_MSG}")
    else:
        print(f"起動: 動画エンコーダ={encoder}")

    def warm_gpu_probe() -> None:
        """GPU情報を先に取っておく(子プロセスなのでGILを握らず起動を止めない)"""
        gpu = probe_gpu()
        if gpu.get("name"):
            print(f"環境: {gpu['name']} ({gpu['accel']}, VRAM {gpu['vram_total_mb'] / 1024:.0f}GB)")
        else:
            print(
                "⚠ torchがGPUを認識していません。`./dev.sh sync`(AMD)または "
                "WL_TORCH_GROUP=cu128(NVIDIA)で入れ直してください。CPUでも動きますが低速です。"
            )

    threading.Thread(target=warm_gpu_probe, daemon=True).start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _report_startup_checks()
    app.state.db = schema.init_db(settings.db_path)
    project_settings.load_global_overrides(app.state.db)  # UI変更値の復元
    app.state.jobs = JobQueue(app.state.db)
    orphaned = app.state.jobs.recover_orphans()  # 前回中断分の整理(--reload対策)
    if orphaned:
        print(f"⚠ 中断されたジョブ{orphaned}件を失敗としてマークしました(再実行してください)")
    app.state.jobs.start()
    yield
    app.state.jobs.stop()
    app.state.db.close()


app = FastAPI(title="Attention Subtitle Separate Application", lifespan=lifespan)
app.include_router(projects_api.router)
app.include_router(jobs_api.router)
app.include_router(transcripts_api.router)
app.include_router(settings_api.router)
app.include_router(edits_api.router)
app.include_router(questions_api.router)
app.include_router(assist_api.router)
app.include_router(clips_api.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
