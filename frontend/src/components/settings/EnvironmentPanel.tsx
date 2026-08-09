/**
 * 環境パネル(設定タブ先頭)。
 *
 * 起動時にスキャンした GPU / VRAM / エンコーダ / Ollama の状態を表示し、
 * VRAM割当の変更と「VRAMに収まる最良のASR・LLM」のワンクリック適用を提供する。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, machineQueryOptions } from '../../api/client'
import { Button } from '../ui'

const GB = (mb: number) => `${(mb / 1024).toFixed(1)}GB`

function Item({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3 text-sm">
      <span className="text-neutral-500">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  )
}

export function EnvironmentPanel() {
  const queryClient = useQueryClient()
  const env = useQuery({
    queryKey: ['environment'],
    queryFn: api.getEnvironment,
    ...machineQueryOptions,
  })
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  const update = useMutation({
    mutationFn: api.updateSettings,
    onSuccess: (data) => {
      queryClient.setQueryData(['settings'], data)
      // 割当VRAMを変えると推奨も変わるので、この操作の後だけ再スキャンする
      queryClient.invalidateQueries({ queryKey: ['environment'] })
    },
  })

  if (env.isPending)
    return (
      <div
        data-testid="environment-panel"
        className="mb-3 rounded-lg border border-neutral-200 p-3 text-sm text-neutral-500 dark:border-neutral-800"
      >
        <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">実行環境</h3>
        <p className="mt-1">確認中...</p>
      </div>
    )
  if (env.isError) return null
  const e = env.data
  const rec = e.recommendations
  const hasGpu = Boolean(e.gpu.name)
  const total = e.gpu.vram_total_mb ?? 0
  // エンジン名はバックエンドが返すラベルを使う(選択UIと表記を揃える)
  const engineLabel =
    settings.data?.asr_engines.find((x) => x.id === rec.asr_engine)?.label ?? rec.asr_engine

  return (
    <div
      data-testid="environment-panel"
      className="mb-3 space-y-2 rounded-lg border border-neutral-200 p-3 dark:border-neutral-800"
    >
      <h3 className="text-sm font-semibold">実行環境</h3>
      <Item
        label="GPU"
        value={
          hasGpu ? `${e.gpu.name}(${e.accel.toUpperCase()})` : 'なし(CPU実行・低速)'
        }
      />
      {hasGpu && (
        <Item label="VRAM" value={`${GB(total)}(空き ${GB(e.gpu.vram_free_mb ?? 0)})`} />
      )}
      <Item
        label="動画エンコード"
        value={
          e.ffmpeg
            ? (e.encoder ?? 'ソフトウェア')
            : '⚠ ffmpeg未インストール(書き出し不可)'
        }
      />
      <Item
        label="Ollama"
        value={
          e.ollama.reachable
            ? `稼働中(${e.ollama.models.length}モデル)`
            : '未起動(クラウドLLMは利用可)'
        }
      />

      {hasGpu && (
        <div className="pt-1">
          <label className="flex items-center justify-between text-sm">
            <span className="text-neutral-500">
              割当VRAM: {e.vram_budget_mb > 0 ? GB(e.vram_budget_mb) : `自動(全${GB(total)})`}
            </span>
            <input
              data-testid="env-vram-budget"
              type="range"
              min={0}
              max={total}
              step={1024}
              defaultValue={e.vram_budget_mb}
              onMouseUp={(ev) =>
                update.mutate({ vram_budget_mb: Number((ev.target as HTMLInputElement).value) })
              }
            />
          </label>
          <p className="text-xs text-neutral-500">
            0=自動。他のアプリとGPUを共有する場合に上限を下げます(ASR・話者分離に適用。
            Ollamaは目安表示のみ)。
          </p>
        </div>
      )}

      <div className="rounded bg-neutral-50 p-2 text-sm dark:bg-neutral-900">
        <p className="text-xs text-neutral-500">
          この環境(利用可能 {hasGpu ? GB(e.effective_vram_mb) : 'CPU'})でのおすすめ:
        </p>
        <p data-testid="env-recommendation" className="mt-0.5">
          ASR: {rec.asr_model}({engineLabel})
          {rec.ollama_model ? ` / LLM: ${rec.ollama_model}` : ''}
        </p>
        <Button
          data-testid="env-apply-recommendation"
          variant="ghost"
          disabled={update.isPending}
          onClick={() =>
            update.mutate({
              asr_model: rec.asr_model,
              // 具体名で固定すると、同梱物が増えて推奨が変わっても追従しない。
              // v0.9.5がここでfaster_whisperを書き込み、whisper.cppを同梱した
              // あともGPUが使われないままだった。表示はrec.asr_engine、保存はauto
              asr_engine: 'auto',
              ...(rec.ollama_model
                ? { llm_provider: 'ollama', ollama_model: rec.ollama_model }
                : {}),
            })
          }
        >
          おすすめ設定を適用
        </Button>
      </div>
      {update.isError && (
        <p className="text-xs text-red-600">適用に失敗しました: {String(update.error)}</p>
      )}
    </div>
  )
}
