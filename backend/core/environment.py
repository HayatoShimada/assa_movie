"""環境情報のスキャンと、VRAMに応じたモデル推奨。

実行環境(OS×GPUクラス)は初回起動で確定したハードウェアプロファイル
(backend/core/hwprofile.py)が持つ。ここではプロファイルの表示用整形と、
その構成でのASRモデル・LLMモデルの推奨だけを行う。
スキャン結果は GET /api/environment で返り、設定タブの環境パネルに表示される。
"""

from urllib.parse import urlparse

from backend.core import hwprofile
from backend.core.hwprofile import EngineSpec, HwProfile

# OllamaのVRAM目安 = モデルファイルサイズ × オーバーヘッド係数(KVキャッシュ等)
OLLAMA_VRAM_FACTOR = 1.15


def scan_ollama(ollama_url: str) -> dict:
    """Ollamaの稼働状態とインストール済みモデル(VRAM目安付き)を返す"""
    import requests

    parsed = urlparse(ollama_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    try:
        resp = requests.get(f"{base}/api/tags", timeout=2)
        if resp.status_code != 200:
            return {"reachable": False, "models": []}
        models = [
            {
                "name": m["name"],
                "vram_mb": int(m.get("size", 0) / 1024**2 * OLLAMA_VRAM_FACTOR),
            }
            for m in resp.json().get("models", [])
        ]
        return {"reachable": True, "models": models}
    except Exception:
        return {"reachable": False, "models": []}


def profile_warnings(profile: HwProfile, spec: EngineSpec) -> list[str]:
    """検出結果の注意点(環境パネル・ウィザードに琥珀色で表示する)を組み立てる(純関数)"""
    warnings = []
    if profile.gpu != "cpu" and not profile.whispercpp_ok:
        warnings.append(
            "GPUを検出しましたが、whisper.cppを起動できないためCPUで実行します。"
            "アプリを入れ直すか「再検出」を試してください。"
        )
    return warnings


def scan_environment(settings) -> dict:
    """環境パネル用の情報一式(プロファイル・確定構成・エンコーダ・Ollama)"""
    from backend.pipeline.export import detect_encoder

    profile = hwprofile.current()
    spec = hwprofile.resolve_spec(profile)
    encoder = detect_encoder()
    return {
        "profile": profile.to_dict(),
        "resolved": {
            "engine": spec.engine,
            "device": spec.device,
            "compute_type": spec.compute_type,
            "label": spec.label,
            "needs_whispercpp_model": spec.needs_whispercpp_model,
        },
        "warnings": profile_warnings(profile, spec),
        "gpu": (
            {"name": profile.gpu_name, "vram_total_mb": profile.vram_total_mb}
            if profile.gpu_name
            else {}
        ),
        "ffmpeg": encoder is not None,
        "encoder": encoder,
        "ollama": scan_ollama(settings.ollama_url),
    }


def recommend(vram_mb: int, engine: str, ollama_models: list[dict]) -> dict:
    """VRAMに収まる範囲で最良のASRモデルとLLMを選ぶ(純関数)。

    エンジンの選択はプロファイルで確定済みなので、ここではモデルだけを決める。
    ASRとLLMは直列実行(ASRはunloadしてからLLM)なので、それぞれ個別に判定する。
    """
    from backend.engines.asr.registry import MODELS

    if engine == "faster_whisper":
        # CPU実行はVRAM制約なし。実用速度を優先して速い方(rtfが大きい)を推奨
        asr_model = max(MODELS.values(), key=lambda m: m.rtf).id
    else:
        # 精度優先(rtfが小さい=低速だが高精度)で、収まる最大モデルを選ぶ。
        # 何も収まらなければ最も軽いものを提示する
        ordered = sorted(MODELS.values(), key=lambda m: m.rtf)
        asr_model = next(
            (m.id for m in ordered if m.vram_mb <= vram_mb), ordered[-1].id
        )

    # LLM: インストール済みOllamaモデルのうち収まる最大(=最も高性能とみなす)
    fitting = [m for m in ollama_models if 0 < m["vram_mb"] <= vram_mb]
    ollama_model = max(fitting, key=lambda m: m["vram_mb"])["name"] if fitting else None

    return {"asr_model": asr_model, "ollama_model": ollama_model}
