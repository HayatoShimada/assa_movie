/**
 * 実行環境パネル(設定タブ先頭)。
 *
 * 実行環境(OS×GPU)は初回起動で1回検出して固定される(backend/core/hwprofile.py)。
 * ここではその確定内容と、そこから決まる文字起こしの構成を表示し、
 * 環境が変わったとき用の「再検出」を提供する。
 * エンジンは選ばせない(選択を誤ると「遅い」「動かない」になるため)。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { GPU_LABELS, OS_LABELS, api, machineQueryOptions } from '../../api/client'
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
  const redetect = useMutation({
    mutationFn: api.redetectEnvironment,
    onSuccess: (data) => {
      queryClient.setQueryData(['environment'], data)
      // 構成が変われば必要なモデルも変わる
      queryClient.invalidateQueries({ queryKey: ['setup'] })
    },
  })
  const applyModel = useMutation({
    mutationFn: api.updateSettings,
    onSuccess: (data) => queryClient.setQueryData(['settings'], data),
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
  const hasGpu = e.profile.gpu !== 'cpu'

  return (
    <div
      data-testid="environment-panel"
      className="mb-3 space-y-2 rounded-lg border border-neutral-200 p-3 dark:border-neutral-800"
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">実行環境</h3>
        <Button
          data-testid="env-redetect"
          variant="ghost"
          disabled={redetect.isPending}
          onClick={() => redetect.mutate()}
        >
          {redetect.isPending ? '検出中…' : '再検出'}
        </Button>
      </div>
      <p className="text-xs text-neutral-500">
        この端末の構成は初回起動時に確定しています。GPUを増設したり
        ドライバを入れ直したときは「再検出」してください。
      </p>

      <Item
        label="この端末"
        value={
          <span data-testid="env-profile">
            {OS_LABELS[e.profile.os]} / {GPU_LABELS[e.profile.gpu]}
            {e.profile.gpu_name ? `(${e.profile.gpu_name})` : ''}
          </span>
        }
      />
      <Item
        label="文字起こし"
        value={<span data-testid="env-resolved">{e.resolved.label}</span>}
      />
      {hasGpu && e.profile.vram_total_mb > 0 && (
        <Item label="VRAM" value={GB(e.profile.vram_total_mb)} />
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

      {e.warnings.map((warning) => (
        <p
          key={warning}
          data-testid="env-warning"
          className="text-xs text-amber-700 dark:text-amber-400"
        >
          {warning}
        </p>
      ))}

      <div className="rounded bg-neutral-50 p-2 text-sm dark:bg-neutral-900">
        <p className="text-xs text-neutral-500">この構成でのおすすめモデル:</p>
        <p data-testid="env-recommendation" className="mt-0.5">
          文字起こし: {rec.asr_model}
          {rec.ollama_model ? ` / LLM: ${rec.ollama_model}` : ''}
        </p>
        <Button
          data-testid="env-apply-recommendation"
          variant="ghost"
          disabled={applyModel.isPending}
          onClick={() =>
            applyModel.mutate({
              asr_model: rec.asr_model,
              ...(rec.ollama_model
                ? { llm_provider: 'ollama', ollama_model: rec.ollama_model }
                : {}),
            })
          }
        >
          おすすめ設定を適用
        </Button>
      </div>
      {(applyModel.isError || redetect.isError) && (
        <p className="text-xs text-red-600">
          失敗しました: {String(applyModel.error ?? redetect.error)}
        </p>
      )}
    </div>
  )
}
