/**
 * 初回セットアップ。
 *
 * インストール版の利用者は、設定タブのどこに何があるかを知らない。
 * 環境の確認・AIの選択・モデルの取得を1本道で案内する。
 *
 * ここに固有のロジックは置かない。表示も保存も設定タブと同じAPIを使う
 * (/api/environment, /api/settings, /api/keys, /api/setup)。
 * ウィザード用の別経路を作ると、片方だけ直す事故が起きるため。
 * だからここで決めたことは、あとから設定タブで同じように変えられる。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, machineQueryOptions } from '../../api/client'
import { SetupItemRow } from '../settings/SetupPanel'
import { Button, selectCls } from '../ui'

const STEPS = ['環境', 'AI', '話者分離', '完了'] as const

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <h3 className="mb-2 text-sm font-semibold">{title}</h3>
      {children}
    </div>
  )
}

function Line({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1 text-sm">
      <span className="text-neutral-500">{label}</span>
      <span className={ok === false ? 'text-amber-700 dark:text-amber-400' : 'font-medium'}>
        {value}
      </span>
    </div>
  )
}

/** 1. 環境を見て、この機体に合う設定を当てる */
function EnvironmentStep() {
  const queryClient = useQueryClient()
  const env = useQuery({ queryKey: ['environment'], queryFn: api.getEnvironment, ...machineQueryOptions })
  const apply = useMutation({
    mutationFn: (patch: Record<string, unknown>) => api.updateSettings(patch),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['settings'] }),
  })

  if (!env.data) return <p className="text-sm text-neutral-500">環境を調べています…</p>
  const e = env.data
  const rec = e.recommendations

  return (
    <Section title="この機体の環境">
      <div data-testid="wizard-env">
        <Line
          label="GPU"
          value={e.gpu.name || '見つかりません'}
          ok={Boolean(e.gpu.name) && e.gpu_compute}
        />
        {e.gpu.vram_total_mb ? (
          <Line label="VRAM" value={`${(e.gpu.vram_total_mb / 1024).toFixed(1)}GB`} />
        ) : null}
        <Line
          label="ffmpeg"
          value={e.ffmpeg ? `あり(${e.encoder})` : '見つかりません'}
          ok={e.ffmpeg}
        />
      </div>
      {!e.ffmpeg && (
        <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">
          書き出しにffmpegが必要です。Windows版は同梱していますが、見つからない場合は
          インストールし直すか、公式サイトから導入してPATHを通してください。
        </p>
      )}
      <p className="mt-2 text-xs text-neutral-500">
        この環境なら <b>{rec.asr_model}</b>({rec.asr_engine})が適しています。
      </p>
      <div className="mt-2">
        <Button
          data-testid="wizard-apply-recommended"
          type="button"
          // エンジンは固定しない。autoのままにしておくと、GPUや同梱物が変わったとき
          // 実行時に選び直される。以前ここで固定していたため、あとから
          // whisper.cppを同梱してもfaster-whisperのまま使われ続けていた
          onClick={() => apply.mutate({ asr_model: rec.asr_model, asr_engine: 'auto' })}
          disabled={apply.isPending}
        >
          {apply.isSuccess ? '適用しました' : '推奨設定を適用'}
        </Button>
      </div>
    </Section>
  )
}

/** 2. どのAIで文章を扱うかを決める(キーの登録まで) */
function LlmStep() {
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.getSettings })
  const keys = useQuery({ queryKey: ['keys'], queryFn: api.getApiKeys })
  const env = useQuery({ queryKey: ['environment'], queryFn: api.getEnvironment, ...machineQueryOptions })
  const [key, setKey] = useState('')

  const provider = String(settings.data?.values?.llm_provider ?? 'gemini')
  // クラウドを先に並べる。Ollamaは別途の導入が要るので、初回はキーを1本
  // 登録するだけで使えるほうを主線にする(設定タブでは従来どおりの並び)
  const providers = [...(settings.data?.llm_providers ?? [])].sort(
    (a, b) => Number(a.local) - Number(b.local),
  )
  const current = providers.find((p) => p.id === provider)

  const choose = useMutation({
    mutationFn: (id: string) => api.updateSettings({ llm_provider: id }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['settings'] }),
  })
  const register = useMutation({
    mutationFn: () => api.registerApiKey(provider, key.trim()),
    onSuccess: () => {
      setKey('')
      queryClient.invalidateQueries({ queryKey: ['keys'] })
      // キーが入るとプロバイダのready状態が変わる
      queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
  })

  if (!settings.data) return <p className="text-sm text-neutral-500">読み込み中…</p>

  return (
    <Section title="使うAI">
      <p className="mb-2 text-xs text-neutral-500">
        指示語の解決・切り抜き候補・タイトル生成に使います。あとから変更できます。
      </p>
      <select
        data-testid="wizard-llm-provider"
        className={selectCls}
        value={provider}
        onChange={(e) => choose.mutate(e.target.value)}
      >
        {providers.map((p) => (
          <option key={p.id} value={p.id}>
            {p.label}
            {p.local ? '(ローカル)' : '(クラウド)'}
          </option>
        ))}
      </select>
      {current?.note && <p className="mt-1 text-xs text-neutral-500">{current.note}</p>}

      {current && !current.local && (
        <div className="mt-3" data-testid="wizard-key-form">
          {keys.data?.[provider]?.configured ? (
            <p data-testid="wizard-key-ready" className="text-sm text-green-700 dark:text-green-400">
              APIキーは登録済みです(…{keys.data[provider].hint})
            </p>
          ) : (
            <>
              <input
                data-testid="wizard-key-input"
                type="password"
                className="w-full rounded-md border border-neutral-300 bg-transparent px-2 py-1 text-sm dark:border-neutral-700"
                placeholder="APIキーを貼り付け"
                value={key}
                onChange={(e) => setKey(e.target.value)}
              />
              <div className="mt-2">
                <Button
                  data-testid="wizard-key-save"
                  type="button"
                  onClick={() => register.mutate()}
                  disabled={!key.trim() || register.isPending}
                >
                  {register.isPending ? '確認中…' : '登録する'}
                </Button>
              </div>
              {register.isError && (
                <p data-testid="wizard-key-error" className="mt-1 text-xs text-red-600">
                  {(register.error as Error).message}
                </p>
              )}
            </>
          )}
        </div>
      )}

      {current?.local && (
        <p
          data-testid="wizard-ollama-state"
          className={`mt-3 text-sm ${
            env.data?.ollama.reachable
              ? 'text-green-700 dark:text-green-400'
              : 'text-amber-700 dark:text-amber-400'
          }`}
        >
          {env.data?.ollama.reachable
            ? `Ollamaが動いています(モデル${env.data.ollama.models.length}件)`
            : 'Ollamaが見つかりません。ollama.com から導入して起動してください'}
        </p>
      )}
    </Section>
  )
}

/** 3. 話者分離などの追加モデル(無くても文字起こしはできる) */
function ModelsStep() {
  const setup = useQuery({ queryKey: ['setup'], queryFn: api.getSetupStatus })
  if (!setup.data) return <p className="text-sm text-neutral-500">読み込み中…</p>
  const items = Object.entries(setup.data)

  return (
    <Section title="追加のモデル">
      <p className="mb-2 text-xs text-neutral-500">
        無くても文字起こしはできます。揃えると話者を見分けられ、文字起こしも速くなります。
        あとから設定タブでも取得できます。
      </p>
      <div data-testid="wizard-models">
        {items.map(([id, item]) => (
          <SetupItemRow key={id} id={id} item={item} />
        ))}
      </div>
    </Section>
  )
}

function DoneStep() {
  return (
    <Section title="準備ができました">
      <p data-testid="wizard-done-text" className="text-sm text-neutral-600 dark:text-neutral-400">
        プロジェクトを作って動画を登録すると、文字起こしを始められます。
        <br />
        ここで決めた内容は、いつでも<b>設定タブ</b>から変更できます。
      </p>
    </Section>
  )
}

export function SetupWizard() {
  const queryClient = useQueryClient()
  const [step, setStep] = useState(0)
  // 完了を記録すると設定が変わり、呼び出し側(App)がこの画面を出さなくなる。
  // 閉じる状態を別に持たないので、設定タブから「やり直す」で何度でも開ける
  const finish = useMutation({
    mutationFn: () => api.updateSettings({ setup_completed: true }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['settings'] }),
  })

  const last = step === STEPS.length - 1

  return (
    <div
      data-testid="setup-wizard"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
    >
      <div className="max-h-full w-full max-w-lg overflow-y-auto rounded-lg bg-white p-4 shadow-xl dark:bg-neutral-900">
        <h2 className="mb-1 text-base font-semibold">はじめの設定</h2>
        <ol className="mb-4 flex gap-2 text-xs">
          {STEPS.map((label, i) => (
            <li
              key={label}
              data-testid={`wizard-step-${i}`}
              className={
                i === step
                  ? 'font-semibold text-neutral-900 dark:text-neutral-100'
                  : 'text-neutral-400'
              }
            >
              {i + 1}. {label}
            </li>
          ))}
        </ol>

        {step === 0 && <EnvironmentStep />}
        {step === 1 && <LlmStep />}
        {step === 2 && <ModelsStep />}
        {step === 3 && <DoneStep />}

        <div className="mt-4 flex items-center justify-between gap-2 border-t border-neutral-200 pt-3 dark:border-neutral-800">
          {/* 途中で抜けても再度出さない(毎回出ると邪魔になる)。設定タブからやり直せる */}
          <button
            data-testid="wizard-skip"
            type="button"
            className="text-xs text-neutral-500 underline"
            onClick={() => finish.mutate()}
          >
            あとで設定する
          </button>
          <div className="flex gap-2">
            {step > 0 && (
              <Button data-testid="wizard-back" type="button" onClick={() => setStep(step - 1)}>
                戻る
              </Button>
            )}
            <Button
              data-testid="wizard-next"
              type="button"
              onClick={() => (last ? finish.mutate() : setStep(step + 1))}
              disabled={finish.isPending}
            >
              {last ? '始める' : '次へ'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
