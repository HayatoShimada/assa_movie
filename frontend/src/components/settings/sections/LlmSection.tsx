/**
 * AI(LLM)の設定(プロバイダ・モデル・APIキーの登録)。基本の項目。
 *
 * クラウドを選ぶには先にキーが要る。選択肢に「(APIキー未設定)」と出すだけでは
 * どこで登録するのか分からなかったので、選ぶその場に登録欄を出す。
 *
 * Ollamaのモデルは「インストール済み」を先に並べ、この機体のおすすめに印を付ける。
 * 未インストールのモデルを選んでいるときは、その場で直し方(ollama pull)を出す
 * (評価で、既定の未インストールモデルのままAI機能が全部失敗した)。
 */
import { useQuery } from '@tanstack/react-query'
import { api, machineQueryOptions } from '../../../api/client'
import { isInstalled, ollamaModelOptions } from '../../../lib/llm'
import { selectCls } from '../../ui'
import { CloudKeySetup } from '../ApiKeysPanel'
import { Row, Section, resetButton, showTier, type SectionProps } from './common'

const GB = (mb: number) => `${(mb / 1024).toFixed(1)}GB`

export function LlmSection(props: SectionProps) {
  const { values: v, meta, onSet, idPrefix } = props
  const set = (key: string) => (value: unknown) => onSet(key, value)
  const basic = showTier(props, 'basic')
  const env = useQuery({
    queryKey: ['environment'],
    queryFn: api.getEnvironment,
    ...machineQueryOptions,
    enabled: basic,
  })
  if (!basic) return null

  const current = String(v.ollama_model ?? '')
  const installed = env.data?.ollama_options ?? []
  const ollamaModels = ollamaModelOptions({
    current,
    installed,
    suggested: meta.llm_providers.find((p) => p.id === 'ollama')?.models ?? [],
    recommended: env.data?.recommendations.ollama_model ?? null,
  })
  const vram = env.data && env.data.profile.gpu !== 'cpu' ? env.data.profile.vram_total_mb : 0
  const reachable = env.data?.ollama.reachable
  const missing = env.data && reachable && !isInstalled(current, installed)

  const cloudModels = (provider: string) =>
    meta.llm_providers.find((p) => p.id === provider)?.models ?? []

  return (
    <Section title="AI">
      <Row
        label="使うAI"
        hint="切り抜き候補・AIに指示・指示語の解決・固有名詞のスキャンに使います。"
      >
        <select
          data-testid={`${idPrefix}-llm-provider`}
          className={selectCls}
          value={String(v.llm_provider)}
          onChange={(e) => set('llm_provider')(e.target.value)}
        >
          {meta.llm_providers.map((p) => (
            <option key={p.id} value={p.id} disabled={!p.ready}>
              {p.label}
              {!p.ready ? '(APIキー未設定)' : ''}
            </option>
          ))}
        </select>
      </Row>
      {/* クラウドプロバイダのキーは、選ぶその場で登録・差し替えできるようにする */}
      <CloudKeySetup
        providers={meta.llm_providers.filter((p) => !p.local).map((p) => p.id)}
        selected={String(v.llm_provider)}
      />
      {v.llm_provider === 'ollama' && (
        <>
          <Row label="AIモデル" hint="このPCに入れたOllamaのモデルから選びます。">
            <span>
              <select
                data-testid={`${idPrefix}-ollama-model`}
                className={`${selectCls} max-w-72`}
                value={current}
                onChange={(e) => set('ollama_model')(e.target.value)}
              >
                {ollamaModels.map((m) => (
                  <option key={m.name} value={m.name}>
                    {m.label}
                  </option>
                ))}
              </select>
              {resetButton(props, 'ollama_model')}
            </span>
          </Row>
          {env.data && !reachable && (
            <p data-testid={`${idPrefix}-ollama-unreachable`} className="text-xs text-amber-600">
              Ollama が起動していません。起動するとインストール済みのモデルが選べます
              (まだ入れていなければ ollama.com から導入できます)。
            </p>
          )}
          {missing && (
            <p data-testid={`${idPrefix}-ollama-missing`} className="text-xs text-amber-600">
              「{current}」はこのPCにインストールされていないため、このままではAI機能が失敗します。
              インストール済みのモデルを選ぶか、ターミナルで{' '}
              <code className="rounded bg-neutral-100 px-1 dark:bg-neutral-800">
                ollama pull {current}
              </code>{' '}
              を実行してください。
            </p>
          )}
          {/* VRAM目安の前提を書いておく。以前は説明なしに「⚠VRAM超過」とだけ出ていた */}
          <p data-testid={`${idPrefix}-ollama-vram-note`} className="text-xs text-neutral-500">
            {vram > 0
              ? `「必要メモリ」はモデルの大きさから見積もったGPUメモリ(VRAM)の目安です。` +
                `文字起こしとAIは同時には動かないので、このPCのGPUメモリ(${GB(vram)})に` +
                '収まれば快適に動きます。収まらないモデルも使えますが、一部をCPUで動かすため遅くなります。'
              : 'このPCはGPUを使わない構成のため、AIはCPUで動きます。小さいモデルほど速く終わります。'}
          </p>
        </>
      )}
      {v.llm_provider === 'gemini' && (
        <Row label="Geminiモデル">
          <select
            data-testid={`${idPrefix}-gemini-model`}
            className={selectCls}
            value={String(v.gemini_model ?? '')}
            onChange={(e) => set('gemini_model')(e.target.value)}
          >
            {cloudModels('gemini').map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </Row>
      )}
      {v.llm_provider === 'claude' && (
        <Row label="Claudeモデル">
          <select
            data-testid={`${idPrefix}-claude-model`}
            className={selectCls}
            value={String(v.claude_model ?? '')}
            onChange={(e) => set('claude_model')(e.target.value)}
          >
            {cloudModels('claude').map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </Row>
      )}
      <p className="text-xs text-neutral-500">
        {meta.llm_providers.find((p) => p.id === v.llm_provider)?.note}
      </p>
    </Section>
  )
}
