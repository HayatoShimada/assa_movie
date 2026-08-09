"""ジョブの中止。

長い処理(文字起こし・書き出し)を途中で止められるようにする。止め方は2つ要る。

1. 進捗通知の時点で JobCancelled を送出する
   ハンドラは定期的に進捗を返すので、そこで例外にすればfinallyが走って
   自然にほどける。ハンドラ側に中止の分岐を書かずに済む。

2. 子プロセスを殺す
   whisper-cli や ffmpeg は動いている間こちらへ制御を返さないので、
   フラグを立てても次の進捗通知まで止まらない(数十分単位になりうる)。
   実行中の子プロセスを登録しておき、中止時に直接止める。

登録はスレッドローカルにする。ジョブはワーカースレッドで動くので、
ハンドラは自分の job_id を知らなくても「いま自分が動かしている子プロセス」を
登録できる。テストで複数のキューを同時に動かしても混ざらない。
"""

import threading

_local = threading.local()


class JobCancelled(Exception):
    """中止要求。ワーカーが受け取って status を cancelled にする"""


def bind(queue, job_id: int) -> None:
    """このスレッドで動かすジョブを設定する(ワーカーが呼ぶ)"""
    _local.queue = queue
    _local.job_id = job_id


def unbind() -> None:
    _local.queue = None
    _local.job_id = None


def register_process(proc) -> None:
    """実行中ジョブの子プロセスを登録する。

    ジョブ以外の文脈(CLI・テスト)から呼ばれても黙って何もしない。
    """
    queue = getattr(_local, "queue", None)
    job_id = getattr(_local, "job_id", None)
    if queue is None or job_id is None:
        return
    queue.attach_process(job_id, proc)
