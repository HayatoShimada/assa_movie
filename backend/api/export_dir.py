"""書き出し先(フォルダ)の表示と、ファイラーで開くAPI。

書き出し先そのものは設定(export_dir。PATCH /api/settings)で変える。
ここは「今どこに書き出されるか」を画面に出すためのもの。空の設定を
既定の場所に解決するのはバックエンドだけが知っている(OSごとに違う)。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core import paths
from backend.core import reveal as reveal_mod
from backend.core.project_settings import resolve_settings
from backend.pipeline.export import check_export_dir, resolve_export_dir

router = APIRouter(prefix="/api", tags=["export"])


class ExportDir(BaseModel):
    # 実際に書き出されるフォルダ(絶対パス)
    path: str
    # 設定が空のときに使う場所(「既定に戻す」で戻る先)
    default_path: str
    is_default: bool


def _current() -> ExportDir:
    s = resolve_settings()
    default = paths.default_export_dir()
    return ExportDir(
        path=str(resolve_export_dir(s.export_dir)),
        default_path=str(default),
        is_default=not s.export_dir.strip(),
    )


@router.get("/export-dir", response_model=ExportDir)
def get_export_dir() -> ExportDir:
    return _current()


@router.post("/export-dir/reveal", response_model=ExportDir)
def reveal_export_dir() -> ExportDir:
    """書き出し先のフォルダをOSのファイラーで開く(まだ無ければ作る)。

    開くのは設定された書き出し先だけ。任意のパスは受け取らない。
    """
    s = resolve_settings()
    problem = check_export_dir(s.export_dir)
    if problem:
        raise HTTPException(400, problem)
    current = _current()
    try:
        reveal_mod.open_folder(resolve_export_dir(s.export_dir))
    except OSError as e:
        raise HTTPException(500, f"フォルダを開けませんでした({e})。場所: {current.path}")
    return current
