"""起動時の環境スキャンと、VRAMに応じたASR/LLMモデルの推奨。

スキャン結果は GET /api/environment で返り、設定タブの環境パネルに表示される。
推奨ロジックは純関数(recommend)としてテーブル駆動テストする。
"""

import shutil
from urllib.parse import urlparse

from backend.core.device import detect_accel, gpu_info

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


def scan_environment(settings) -> dict:
    """GPU・エンコーダ・ffmpeg・Ollamaをスキャンする(起動時と設定タブで使用)"""
    from backend.pipeline.export import detect_encoder

    return {
        "accel": detect_accel(),
        "gpu": gpu_info(),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "encoder": detect_encoder(),
        "ollama": scan_ollama(settings.ollama_url),
    }


def recommend(vram_mb: int, accel: str, ollama_models: list[dict]) -> dict:
    """割当VRAMに収まる範囲で最も性能の良いASRエンジン・モデル・LLMを選ぶ(純関数)。

    ASRとLLMは直列実行(ASRはunloadしてからLLM)なので、それぞれ個別に判定する。
    """
    from backend.engines.asr.registry import MODELS

    # エンジン: CUDA→faster-whisper(最速) / ROCm→transformers(CTranslate2非対応)
    engine = "transformers" if accel == "rocm" else "faster_whisper"

    if accel == "cpu":
        # CPUはVRAM制約なし。実用速度を優先してturboを推奨
        asr_model = "large-v3-turbo"
    else:
        # 精度優先: 収まる最大モデル。何も収まらなければ最小を提示
        ordered = ["large-v3", "large-v3-turbo"]
        vram_of = {
            m: (MODELS[m].vram_tf_mb if engine == "transformers" else MODELS[m].vram_fw_mb)
            for m in ordered
        }
        asr_model = next((m for m in ordered if vram_of[m] <= vram_mb), ordered[-1])

    # LLM: インストール済みOllamaモデルのうち収まる最大(=最も高性能とみなす)
    fitting = [m for m in ollama_models if 0 < m["vram_mb"] <= vram_mb]
    ollama_model = max(fitting, key=lambda m: m["vram_mb"])["name"] if fitting else None

    return {"asr_engine": engine, "asr_model": asr_model, "ollama_model": ollama_model}
