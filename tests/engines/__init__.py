"""差し替え可能な実装のテスト(backend/engines)。

ASR・話者分離・LLMのどれも、実モデルや実APIは呼ばない。
LLMは必ず FakeLLMClient で確かめる(CLAUDE.md)。
"""
