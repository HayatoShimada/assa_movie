"""保存済みのAI(LLM)設定で、実際にAI機能が動くかを押す前に調べる。

評価で、既定の Ollama モデル(qwen3:32b)が入っていない機体だと、切り抜き候補・
AIに指示・指示語の解決・固有名詞スキャンが全部失敗するまで気付けなかった。
ホーム/編集画面はこの結果で警告と直し方(おすすめを適用・別のモデルを選ぶ・
ollama pull)を出す。

判定は diagnose()(純関数)。実行時に別のモデルへ黙って切り替えることはしない
(「実行時に判定しない・フォールバックしない」設計。直すのは利用者の操作だけ)。
"""

from backend.core import environment
from backend.engines.llm.errors import PROVIDER_NAMES, no_key_message

# AIを使う機能(警告文で「何が使えないか」を伝える)
AI_FEATURES = "切り抜き候補・AIに指示・指示語の解決・固有名詞のスキャン"


def _same_model(a: str, b: str) -> bool:
    """Ollamaのモデル名の一致。タグ省略は :latest と同じ"""
    def norm(name: str) -> str:
        return name if ":" in name else f"{name}:latest"

    return norm(a) == norm(b)


def diagnose(
    provider: str, model: str, ollama: dict, *, key_ready: bool, recommended: str | None,
) -> dict:
    """AI設定の診断(純関数)。

    ollama: scan_ollama() の戻り値({reachable, models})
    key_ready: クラウドのAPIキーが登録済みか
    recommended: この機体でのおすすめOllamaモデル(environment.recommend)
    """
    installed = [m["name"] for m in ollama.get("models", [])]
    out = {
        "ok": True,
        "code": None,
        "message": "",
        "provider": provider,
        "provider_label": PROVIDER_NAMES.get(provider, provider),
        "model": model,
        "installed_models": installed,
        "recommended_model": recommended if recommended in installed else None,
        "pull_command": None,
    }

    if provider == "ollama":
        if not ollama.get("reachable"):
            return {**out, "ok": False, "code": "ollama_unreachable", "message": (
                f"Ollama が起動していません。このままではAI機能({AI_FEATURES})が使えません。"
                "Ollama を起動してください(まだ入れていなければ ollama.com から導入できます)。"
                "クラウドのAI(Gemini / Claude)を使う場合は、設定タブの「AI」で切り替えてください。"
            )}
        if not any(_same_model(model, name) for name in installed):
            return {**out, "ok": False, "code": "model_not_installed",
                    "pull_command": f"ollama pull {model}", "message": (
                        f"設定されているAIモデル「{model}」がこのPCにインストールされていません。"
                        f"このままではAI機能({AI_FEATURES})が使えません。"
                    )}
        return out

    if not key_ready:
        return {**out, "ok": False, "code": "no_key", "message": no_key_message(provider)}
    return out


def llm_status(settings, *, key_ready: bool, recommended_from_env) -> dict:
    """解決済み設定(resolve_settings の戻り値)で診断する。

    recommended_from_env: Ollamaのモデル一覧を受け取り、おすすめを返す関数
    (VRAMの前提は settings_api が知っている)
    """
    provider = settings.llm_provider
    model = {
        "ollama": settings.ollama_model,
        "gemini": settings.gemini_model,
        "claude": settings.claude_model,
    }.get(provider, "")
    # クラウドを使うときはOllamaを見に行かない(2秒待つことがある)
    # モジュール経由で呼ぶ(E2Eサーバーが environment.scan_ollama を差し替えるため)
    ollama = (
        environment.scan_ollama(settings.ollama_url)
        if provider == "ollama"
        else {"reachable": False, "models": []}
    )
    recommended = recommended_from_env(ollama["models"]) if provider == "ollama" else None
    return diagnose(provider, model, ollama, key_ready=key_ready, recommended=recommended)
