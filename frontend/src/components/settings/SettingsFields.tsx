/**
 * 設定フォームの共有フィールド群。
 *
 * グローバル設定タブ(SettingsForm)とプロジェクト設定(作成ダイアログ・編集パネル)の
 * 両方から使う。値の保存先はonSetに委ねる。プロジェクトモードでは
 * overriddenKeys/onResetで「既定に戻す」を出す。
 */
import { useQuery } from '@tanstack/react-query'
import { api, machineQueryOptions, type SettingsResponse } from '../../api/client'
import { CONVERT_METHOD_LABELS } from '../../lib/catalogs'
import { BASE_RES_X } from '../../lib/subtitleLayout'
import { selectCls } from '../ui'

/** これ未満は縦動画(1080px幅)で1桁pxになり読めない(1920px幅基準の値) */
const MIN_READABLE_FONT_SIZE = 20

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex items-center justify-between gap-4 py-2 text-sm">
      <span className="text-neutral-600 dark:text-neutral-400">{label}</span>
      {children}
    </label>
  )
}

export function SettingsFields({
  values,
  meta,
  onSet,
  idPrefix = 'setting',
  overriddenKeys,
  onReset,
}: {
  values: Record<string, unknown>
  meta: Pick<
    SettingsResponse,
    'asr_models' | 'asr_engines' | 'diarization_engines' | 'llm_providers'
  >
  onSet: (key: string, value: unknown) => void
  idPrefix?: string
  /** プロジェクトモード: グローバルと異なるキー(「既定に戻す」を表示) */
  overriddenKeys?: Set<string>
  onReset?: (key: string) => void
}) {
  const fonts = useQuery({ queryKey: ['fonts'], queryFn: api.getFonts, ...machineQueryOptions })
  const env = useQuery({
    queryKey: ['environment'],
    queryFn: api.getEnvironment,
    ...machineQueryOptions,
  })
  const v = values
  const set = (key: string) => (value: unknown) => onSet(key, value)
  const asrNote = meta.asr_models.find((m) => m.id === v.asr_model)?.note
  // 字幕サイズは1920px幅基準の値。実際の見え方は「画面幅の何%か」で決まる
  const fontRatioPct = (Number(v.subtitle_font_size ?? 48) / BASE_RES_X) * 100

  // Ollamaモデル: インストール済み(VRAM目安付き)+レジストリの推奨候補
  const installed = env.data?.ollama_options ?? []
  const suggested = meta.llm_providers.find((p) => p.id === 'ollama')?.models ?? []
  const ollamaModels = [
    ...installed.map((m) => ({
      name: m.name,
      label: `${m.name}(VRAM目安 ${(m.vram_mb / 1024).toFixed(1)}GB${m.fits ? '' : ' ⚠割当超過'})`,
    })),
    ...suggested
      .filter((name) => !installed.some((m) => m.name === name))
      .map((name) => ({ name, label: `${name}(未インストール)` })),
  ]
  if (v.ollama_model && !ollamaModels.some((m) => m.name === v.ollama_model)) {
    ollamaModels.unshift({ name: String(v.ollama_model), label: String(v.ollama_model) })
  }

  const resetBtn = (key: string) =>
    overriddenKeys?.has(key) && onReset ? (
      <button
        type="button"
        className="ml-1 text-xs text-blue-600 hover:underline"
        onClick={() => onReset(key)}
      >
        既定に戻す
      </button>
    ) : null

  return (
    <div className="divide-y divide-neutral-100 dark:divide-neutral-800">
      <div className="pb-2">
        <h3 className="mb-1 text-sm font-semibold">文字起こし</h3>
        <Row label="ASRモデル">
          <span>
            <select
              data-testid={`${idPrefix}-asr-model`}
              className={selectCls}
              value={String(v.asr_model)}
              onChange={(e) => set('asr_model')(e.target.value)}
            >
              {meta.asr_models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
            {resetBtn('asr_model')}
          </span>
        </Row>
        {asrNote && <p className="text-xs text-neutral-500">{asrNote}</p>}
        <Row label="ASRエンジン">
          <span>
            <select
              data-testid={`${idPrefix}-asr-engine`}
              className={selectCls}
              value={String(v.asr_engine ?? 'auto')}
              onChange={(e) => set('asr_engine')(e.target.value)}
            >
              {meta.asr_engines.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
            {resetBtn('asr_engine')}
          </span>
        </Row>
        <Row label="話者分離">
          <input
            type="checkbox"
            data-testid={`${idPrefix}-diarization-enabled`}
            checked={Boolean(v.diarization_enabled)}
            onChange={(e) => set('diarization_enabled')(e.target.checked)}
          />
        </Row>
        {Boolean(v.diarization_enabled) && (
          <Row label="話者分離エンジン">
            <span>
              <select
                data-testid={`${idPrefix}-diarization-engine`}
                className={selectCls}
                value={String(v.diarization_engine ?? 'auto')}
                onChange={(e) => set('diarization_engine')(e.target.value)}
              >
                {meta.diarization_engines.map((m) => (
                  // 未準備のエンジン(モデル未取得/HFトークン未設定)は選ばせない
                  <option key={m.id} value={m.id} disabled={!m.ready}>
                    {m.ready ? m.label : `${m.label}(未準備)`}
                  </option>
                ))}
              </select>
              {resetBtn('diarization_engine')}
            </span>
          </Row>
        )}
        <Row label="男性話者の表示名">
          <input
            className={selectCls}
            defaultValue={String(v.male_name)}
            onBlur={(e) => e.target.value !== v.male_name && set('male_name')(e.target.value)}
          />
        </Row>
        <Row label="女性話者の表示名">
          <input
            className={selectCls}
            defaultValue={String(v.female_name)}
            onBlur={(e) => e.target.value !== v.female_name && set('female_name')(e.target.value)}
          />
        </Row>
      </div>

      <div className="py-2">
        <h3 className="mb-1 text-sm font-semibold">レイアウト(縦横変換)</h3>
        <Row label="変換方式">
          <span>
            <select
              data-testid={`${idPrefix}-convert-method`}
              className={selectCls}
              value={String(v.convert_method ?? 'blur_pad')}
              onChange={(e) => set('convert_method')(e.target.value)}
            >
              {Object.entries(CONVERT_METHOD_LABELS).map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
            {resetBtn('convert_method')}
          </span>
        </Row>
        <p className="text-xs text-neutral-500">
          入力と出力の向きが違うとき(横→縦 等)の変換方法。クリップごとに上書きもできます。
        </p>
      </div>

      <div className="py-2">
        <h3 className="mb-1 text-sm font-semibold">指示語置換</h3>
        <Row label="有効">
          <input
            type="checkbox"
            checked={Boolean(v.pronoun_enabled)}
            onChange={(e) => set('pronoun_enabled')(e.target.checked)}
          />
        </Row>
        <Row label="積極性">
          <select
            className={selectCls}
            value={String(v.pronoun_level)}
            onChange={(e) => set('pronoun_level')(e.target.value)}
          >
            <option value="weak">弱(これ・それ・あれのみ)</option>
            <option value="medium">中(推奨)</option>
            <option value="strong">強(そういう系も対象)</option>
          </select>
        </Row>
        <Row label="表現形式">
          <select
            data-testid={`${idPrefix}-pronoun-form`}
            className={selectCls}
            value={String(v.pronoun_form)}
            onChange={(e) => set('pronoun_form')(e.target.value)}
          >
            <option value="annotate">注釈: それ(先月のイベント)(推奨)</option>
            <option value="replace">置換: 先月のイベント</option>
            <option value="complete">補完(全件レビュー必須)</option>
          </select>
        </Row>
        <Row label="適用モード">
          <select
            className={selectCls}
            value={String(v.pronoun_apply_mode)}
            onChange={(e) => set('pronoun_apply_mode')(e.target.value)}
          >
            <option value="full_auto">全自動</option>
            <option value="auto_and_review">確実なものは自動、迷いはレビュー(推奨)</option>
            <option value="all_review">全件レビュー</option>
          </select>
        </Row>
      </div>

      <div className="py-2">
        <h3 className="mb-1 text-sm font-semibold">字幕</h3>
        <Row label="字幕モード">
          <select
            data-testid={`${idPrefix}-subtitle-mode`}
            className={selectCls}
            value={String(v.subtitle_mode)}
            onChange={(e) => set('subtitle_mode')(e.target.value)}
          >
            <option value="all">全文字幕(全セグメントを表示)</option>
            <option value="selective">選択字幕(必要なものだけ)</option>
          </select>
        </Row>
        {v.subtitle_mode === 'selective' && (
          <Row label={`採用率 ${Math.round(Number(v.subtitle_adoption_rate) * 100)}%`}>
            <input
              type="range"
              min={0.1}
              max={1}
              step={0.05}
              defaultValue={Number(v.subtitle_adoption_rate)}
              onMouseUp={(e) =>
                set('subtitle_adoption_rate')(Number((e.target as HTMLInputElement).value))
              }
            />
          </Row>
        )}
        <Row label="フォント">
          <span>
            <select
              data-testid={`${idPrefix}-subtitle-font-family`}
              className={`${selectCls} max-w-52`}
              value={String(v.subtitle_font_family ?? 'Noto Sans JP')}
              onChange={(e) => set('subtitle_font_family')(e.target.value)}
            >
              {(fonts.data?.fonts ?? ['Noto Sans JP']).map((f) => (
                <option key={f} value={f} style={{ fontFamily: f }}>
                  {f}
                </option>
              ))}
            </select>
            {resetBtn('subtitle_font_family')}
          </span>
        </Row>
        <Row
          label={`字幕サイズ: ${v.subtitle_font_size}px(画面幅の${fontRatioPct.toFixed(1)}%)`}
        >
          <input
            data-testid={`${idPrefix}-subtitle-font-size`}
            type="range"
            // 値は1920px幅基準。これ未満は縦動画(1080px幅)で数pxになり読めない
            min={MIN_READABLE_FONT_SIZE}
            max={96}
            step={1}
            value={Number(v.subtitle_font_size ?? 48)}
            onChange={(e) => set('subtitle_font_size')(Number(e.target.value))}
          />
        </Row>
        {Number(v.subtitle_font_size ?? 48) < MIN_READABLE_FONT_SIZE && (
          <p data-testid={`${idPrefix}-subtitle-font-size-warning`} className="text-xs text-amber-600">
            ⚠ 小さすぎます。書き出すと縦動画で約
            {Math.round((Number(v.subtitle_font_size) * 1080) / 1920)}px になり、ほぼ見えません。
            {MIN_READABLE_FONT_SIZE}以上にしてください。
          </p>
        )}
        <Row label="文字色">
          <span className="flex items-center gap-1">
            <input
              data-testid={`${idPrefix}-subtitle-text-color`}
              type="color"
              // color入力はドラッグ中も連続でchangeが飛ぶため、確定時にだけ保存する
              defaultValue={String(v.subtitle_text_color ?? '#FFFFFF')}
              onBlur={(e) => set('subtitle_text_color')(e.target.value.toUpperCase())}
            />
            {resetBtn('subtitle_text_color')}
          </span>
        </Row>
        <Row label="話者ごとの色分け">
          <input
            type="checkbox"
            checked={Boolean(v.subtitle_speaker_colors ?? true)}
            onChange={(e) => set('subtitle_speaker_colors')(e.target.checked)}
          />
        </Row>
        <Row label="背景">
          <span>
            <select
              data-testid={`${idPrefix}-subtitle-bg`}
              className={selectCls}
              value={String(v.subtitle_bg ?? 'none')}
              onChange={(e) => set('subtitle_bg')(e.target.value)}
            >
              <option value="none">なし(縁取りのみ)</option>
              <option value="box">背景ボックス</option>
            </select>
            {resetBtn('subtitle_bg')}
          </span>
        </Row>
        {v.subtitle_bg === 'box' && (
          <>
            <Row label="背景色">
              <input
                data-testid={`${idPrefix}-subtitle-bg-color`}
                type="color"
                defaultValue={String(v.subtitle_bg_color ?? '#000000')}
                onBlur={(e) => set('subtitle_bg_color')(e.target.value.toUpperCase())}
              />
            </Row>
            <Row label={`背景の不透明度: ${Math.round(Number(v.subtitle_bg_opacity ?? 0.5) * 100)}%`}>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                defaultValue={Number(v.subtitle_bg_opacity ?? 0.5)}
                onMouseUp={(e) =>
                  set('subtitle_bg_opacity')(Number((e.target as HTMLInputElement).value))
                }
              />
            </Row>
          </>
        )}
        <Row label="字幕位置(既定)">
          <select
            data-testid={`${idPrefix}-subtitle-position`}
            className={selectCls}
            value={String(v.subtitle_position ?? 'bottom')}
            onChange={(e) => set('subtitle_position')(e.target.value)}
          >
            <option value="top">上</option>
            <option value="center">中央</option>
            <option value="bottom">下</option>
          </select>
        </Row>
        <Row label={`字幕の上下微調整(既定): ${v.subtitle_offset_y ?? 0}px`}>
          <input
            data-testid={`${idPrefix}-subtitle-offset`}
            type="range"
            min={-120}
            max={120}
            step={1}
            defaultValue={Number(v.subtitle_offset_y ?? 0)}
            onMouseUp={(e) => set('subtitle_offset_y')(Number((e.target as HTMLInputElement).value))}
          />
        </Row>
        <Row label={`1行の最大文字数: ${v.subtitle_max_chars_per_line}`}>
          <input
            type="range"
            min={10}
            max={20}
            defaultValue={Number(v.subtitle_max_chars_per_line)}
            onMouseUp={(e) =>
              set('subtitle_max_chars_per_line')(Number((e.target as HTMLInputElement).value))
            }
          />
        </Row>
        <Row label="フィラー排除">
          <select
            data-testid={`${idPrefix}-filler-level`}
            className={selectCls}
            value={String(v.filler_level)}
            onChange={(e) => set('filler_level')(e.target.value)}
          >
            <option value="off">無効(言い淀みも残す)</option>
            <option value="weak">弱(明らかな言い淀みのみ)</option>
            <option value="strong">強(曖昧なものはLLM判定+質問)</option>
          </select>
        </Row>
      </div>

      <div className="py-2">
        <h3 className="mb-1 text-sm font-semibold">LLM</h3>
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
              {resetBtn('ollama_model')}
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
              {(meta.llm_providers.find((p) => p.id === 'gemini')?.models ?? []).map((m) => (
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
              {(meta.llm_providers.find((p) => p.id === 'claude')?.models ?? []).map((m) => (
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
      </div>
    </div>
  )
}
