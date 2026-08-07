# M2 検証手順

curlのみで「動画登録 → 文字起こしジョブ → SSE進捗 → セグメント取得 → 手動修正」が通ることを確認する。

## 準備

```bash
uv run uvicorn backend.app:app --port 8000
```

別ターミナルで以下を順に実行する(`jq` があると見やすい)。

## 1. ヘルスチェック

```bash
curl -s localhost:8000/api/health
# => {"status":"ok"}
```

## 2. プロジェクトとメディアの登録

```bash
PID=$(curl -s -X POST localhost:8000/api/projects \
  -H 'Content-Type: application/json' \
  -d '{"name":"対談"}' | jq -r .id)

MID=$(curl -s -X POST localhost:8000/api/projects/$PID/media \
  -H 'Content-Type: application/json' \
  -d "{\"path\":\"$PWD/tests/golden/smoke.wav\"}" | jq -r .id)

echo "project=$PID media=$MID"
```

`duration` がffprobeで取得されていることを確認:

```bash
curl -s localhost:8000/api/projects/$PID/media | jq '.[0] | {path, duration, status}'
```

## 3. 文字起こしジョブの投入

```bash
JID=$(curl -s -X POST localhost:8000/api/media/$MID/jobs \
  -H 'Content-Type: application/json' \
  -d '{"type":"transcribe","params":{"language":"ja"}}' | jq -r .id)
```

## 4. SSEで進捗を受信

```bash
curl -N localhost:8000/api/jobs/$JID/events
# progress イベントが流れ、status が completed になったらストリームが閉じる
```

## 5. セグメントの取得

```bash
curl -s "localhost:8000/api/media/$MID/segments" | jq 'length'
curl -s "localhost:8000/api/media/$MID/segments" | jq '.[0] | {idx,start,end,speaker,text,is_aizuchi}'

# 相槌を除いた一覧
curl -s "localhost:8000/api/media/$MID/segments?include_aizuchi=false" | jq 'length'
```

## 6. セグメントの手動修正

```bash
SID=$(curl -s "localhost:8000/api/media/$MID/segments" | jq -r '.[0].id')
curl -s -X PATCH localhost:8000/api/segments/$SID \
  -H 'Content-Type: application/json' \
  -d '{"text":"手動修正しました"}' | jq '{text, original_text, edited_by_user}'
# => text は変わり、original_text は原文のまま、edited_by_user は true
```

## 期待結果

- 手順2〜6がすべてエラーなく完了する
- 手順5でセグメントが取得でき、話者ラベル(はやまる/高田さん等)が入っている
- 手順6で `original_text` が保持され `edited_by_user` が true になる
