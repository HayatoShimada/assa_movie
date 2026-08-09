"""設定・パス・デバイス検出・ライセンス・起動まわり(backend/core)。

OS判定は必ず `os_name=` で注入する。実行中のOSに任せると、Linuxで書いた
期待値がWindows/macOSで落ちる(M24が丸ごとそうなっていた)。
"""
