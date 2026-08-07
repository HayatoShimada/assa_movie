/**
 * 設定フォームの共有フィールド群。
 *
 * グローバル設定タブ(SettingsForm)とプロジェクト設定(作成ダイアログ・編集パネル)の
 * 両方から使う。値の保存先はonSetに委ねる。プロジェクトモードでは
 * overriddenKeys/onResetで「既定に戻す」を出す。
 */
import { useQuery } from '@tanstack/react-query'
import { api, type SettingsResponse } from '../../api/client'

export function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex items-center justify-between gap-4 py-2 text-sm">
      <span className="text-neutral-600 dark:text-neutral-400">{label}</span>
      {children}
    </label>
  )
}

export const selectCls =
  'rounded-md border border-neutral-300 bg-transparent px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900'

export const CONVERT_METHOD_LABELS: Record<string, string> = {
  crop: '中央クロップ(位置調整可)',
  blur_pad: 'ぼかし背景(全体表示)',
  face: '顔検出(1人=追従クロップ / 2人=上下分割)',
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
  meta: Pick<SettingsResponse, 'asr_models' | 'asr_engines' | 'llm_providers'>
  onSet: (key: string, value: unknown) => void
  idPrefix?: string
  /** プロジェクトモード: グローバルと異なるキー(「既定に戻す」を表示) */
  overriddenKeys?: Set<string>
  onReset?: (key: string) => void
}) {
  const fonts = useQuery({ queryKey: ['fonts'], queryFn: api.getFonts })
  const v = values
  const set = (key: string) => (value: unknown) => onSet(key, value)
  const asrNote = meta.asr_models.find((m) => m.id === v.asr_model)?.note

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
            checked={Boolean(v.diarization_enabled)}
            onChange={(e) => set('diarization_enabled')(e.target.checked)}
          />
        </Row>
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
        <Row label={`字幕サイズ: ${v.subtitle_font_size}px(1920px幅基準)`}>
          <input
            data-testid={`${idPrefix}-subtitle-font-size`}
            type="range"
            min={6}
            max={72}
            step={1}
            defaultValue={Number(v.subtitle_font_size ?? 48)}
            onMouseUp={(e) =>
              set('subtitle_font_size')(Number((e.target as HTMLInputElement).value))
            }
          />
        </Row>
        <Row label="文字色">
          <span className="flex items-center gap-1">
            <input
              data-testid={`${idPrefix}-subtitle-text-color`}
              type="color"
              value={String(v.subtitle_text_color ?? '#FFFFFF')}
              onChange={(e) => set('subtitle_text_color')(e.target.value.toUpperCase())}
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
                value={String(v.subtitle_bg_color ?? '#000000')}
                onChange={(e) => set('subtitle_bg_color')(e.target.value.toUpperCase())}
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
        <p className="text-xs text-neutral-500">
          {meta.llm_providers.find((p) => p.id === v.llm_provider)?.note}
        </p>
      </div>
    </div>
  )
}
