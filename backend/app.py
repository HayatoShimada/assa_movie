"""FastAPIアプリ本体。"""

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


def _scan_and_report_environment() -> None:
    """起動時に環境をスキャンして1行サマリを出す(詳細は GET /api/environment)"""
    from backend.core.environment import scan_environment

    try:
        env = scan_environment(settings)
    except Exception:
        return
    gpu = env["gpu"]
    if gpu:
        vram = f"{gpu['vram_total_mb'] / 1024:.0f}GB"
        print(
            f"環境: {gpu['name']} ({env['accel']}, VRAM {vram}) / "
            f"エンコーダ: {env['encoder'] or 'ffmpeg未検出'} / "
            f"Ollama: {'稼働中 ' + str(len(env['ollama']['models'])) + 'モデル' if env['ollama']['reachable'] else '未起動'}"
        )
    else:
        print(
            "⚠ torchがGPUを認識していません。"
            "`./dev.sh sync`(AMD)または WL_TORCH_GROUP=cu128(NVIDIA)で"
            "GPU向けwheelを入れ直してください。CPUでも動作しますが低速です。"
        )
    if not env["ffmpeg"]:
        print("⚠ ffmpegが見つかりません。書き出しには `sudo apt install ffmpeg` が必要です。")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _scan_and_report_environment()
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
