/**
 * 文字起こしの設定。
 *
 * どのエンジンで動かすかは実行環境で決まっている(設定タブの「実行環境」)。
 * ここで選ぶのはモデルと話者分離まわりだけ。
 */
import { selectCls } from '../../ui'
import { Row, Section, resetButton, type SectionProps } from './common'

export function TranscriptionSection(props: SectionProps) {
  const { values: v, meta, onSet, idPrefix } = props
  const set = (key: string) => (value: unknown) => onSet(key, value)
  const asrNote = meta.asr_models.find((m) => m.id === v.asr_model)?.note

  return (
    <Section title="文字起こし">
      <Row label="モデル">
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
          {resetButton(props, 'asr_model')}
        </span>
      </Row>
      {asrNote && <p className="text-xs text-neutral-500">{asrNote}</p>}

      <Row label="話者分離">
        <input
          type="checkbox"
          data-testid={`${idPrefix}-diarization-enabled`}
          checked={Boolean(v.diarization_enabled)}
          onChange={(e) => set('diarization_enabled')(e.target.checked)}
        />
      </Row>
      {/* 設定はONでもモデルが無ければ実際には分離されない。黙って効かないのが
          いちばん困るので、その状態をここで伝える(取得は上のセットアップから) */}
      {Boolean(v.diarization_enabled) && !meta.diarization_ready && (
        <p data-testid={`${idPrefix}-diarization-unavailable`} className="text-xs text-amber-600">
          話者分離モデルが未取得のため、いまは話者を分けられません。
          上の「セットアップ」から取得してください。
        </p>
      )}
      {Boolean(v.diarization_enabled) && (
        <>
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
        </>
      )}
    </Section>
  )
}
