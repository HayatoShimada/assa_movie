"""faster-whisper(CPU機)に辞書のプロンプトが渡ることを見る(モデル不要)。"""

from types import SimpleNamespace

import numpy as np

from backend.engines.asr.fasterwhisper import FasterWhisperEngine
from backend.engines.asr.prompt import VERBATIM_STYLE, build_initial_prompt


class _FakeModel:
    def __init__(self):
        self.kwargs: dict = {}

    def transcribe(self, audio, **kwargs):
        self.kwargs = kwargs
        seg = SimpleNamespace(start=0.0, end=1.0, text=" 半導体", words=[], avg_logprob=-0.1)
        return iter([seg]), SimpleNamespace(language="ja", language_probability=1.0)


def _engine_with_fake_model():
    engine = FasterWhisperEngine()
    engine._model = _FakeModel()
    return engine


def test_辞書のプロンプトがinitial_promptに渡る():
    engine = _engine_with_fake_model()
    prompt = build_initial_prompt(VERBATIM_STYLE, ["半導体"])
    engine.transcribe(np.zeros(16000, dtype=np.float32), language="ja", initial_prompt=prompt)
    assert engine._model.kwargs["initial_prompt"] == f"{VERBATIM_STYLE} 半導体。"


def test_hotwordsは使わない():
    """hotwordsは30秒ごとの窓すべてで直前の文脈(最大223トークン)に上乗せされ、
    1窓448トークンの枠を圧迫して発話の取りこぼしを招くので渡さない
    (BACKEND_DESIGN.md「利用者の辞書」)"""
    engine = _engine_with_fake_model()
    engine.transcribe(np.zeros(16000, dtype=np.float32), language="ja", initial_prompt="半導体。")
    assert "hotwords" not in engine._model.kwargs
