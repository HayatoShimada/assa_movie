/**
 * LLMの設定(プロバイダ・モデル・APIキーの登録)。
 *
 * クラウドを選ぶには先にキーが要る。選択肢に「(APIキー未設定)」と出すだけでは
 * どこで登録するのか分からなかったので、選ぶその場に登録欄を出す。
 */
import { useQuery } from '@tanstack/react-query'
import { api, machineQueryOptions } from '../../../api/client'
import { selectCls } from '../../ui'
import { CloudKeySetup } from '../ApiKeysPanel'
import { Row, Section, resetButton, type SectionProps } from './common'

export function LlmSection(props: SectionProps) {
  const { values: v, meta, onSet, idPrefix } = props
  const set = (key: string) => (value: unknown) => onSet(key, value)
  const env = useQuery({
    queryKey: ['environment'],
    queryFn: api.getEnvironment,
    ...machineQueryOptions,
  })

  // Ollamaモデル: インストール済み(VRAM目安付き)+レジストリの推奨候補
  const installed = env.data?.ollama_options ?? []
  const suggested = meta.llm_providers.find((p) => p.id === 'ollama')?.models ?? []
  const ollamaModels = [
    ...installed.map((m) => ({
      name: m.name,
      label: `${m.name}(VRAM目安 ${(m.vram_mb / 1024).toFixed(1)}GB${m.fits ? '' : ' ⚠VRAM超過'})`,
    })),
    ...suggested
      .filter((name) => !installed.some((m) => m.name === name))
      .map((name) => ({ name, label: `${name}(未インストール)` })),
  ]
  if (v.ollama_model && !ollamaModels.some((m) => m.name === v.ollama_model)) {
    ollamaModels.unshift({ name: String(v.ollama_model), label: String(v.ollama_model) })
  }

  const cloudModels = (provider: string) =>
    meta.llm_providers.find((p) => p.id === provider)?.models ?? []

  return (
    <Section title="LLM">
      <Row label="プロバイダ">
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
        <Row label="Ollamaモデル">
          <span>
            <select
              data-testid={`${idPrefix}-ollama-model`}
              className={`${selectCls} max-w-64`}
              value={String(v.ollama_model ?? '')}
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
