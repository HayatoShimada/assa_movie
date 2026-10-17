/**
 * 文字起こしの設定。
 *
 * どのエンジンで動かすかは実行環境で決まっている(設定タブの「実行環境」)。
 * ここで選ぶのはモデル・名前と用語の辞書を使うか・話者分離まわりだけ。
 * 話者分離と話者名は基本、モデルの選択と辞書の利用は詳しい設定に置く
 * (モデル名は専門用語で、辞書は既定のままで使えるため)。
 */
import { selectCls } from '../../ui'
import { Row, Section, resetButton, showTier, type SectionProps } from './common'

export function TranscriptionSection(props: SectionProps) {
  const { values: v, meta, onSet, idPrefix } = props
  const set = (key: string) => (value: unknown) => onSet(key, value)
  const asrNote = meta.asr_models.find((m) => m.id === v.asr_model)?.note
  const basic = showTier(props, 'basic')
  const advanced = showTier(props, 'advanced')

  return (
    <Section title="文字起こし">
      {advanced && (
        <>
          <Row
            label="文字起こしモデル"
            hint="音声を文字にするAIの種類。既定(large-v3)が最も正確です。速さを優先するときだけ変えます。"
          >
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

          <Row
            label="名前・用語の辞書を使う"
            hint="質問タブで答えた名前や用語を、文字起こしで正しく書くためのヒントにします。辞書の中身は設定タブの「名前・用語の辞書」で見直せます。"
          >
            <span>
              <input
                type="checkbox"
                data-testid={`${idPrefix}-asr-use-user-terms`}
                checked={Boolean(v.asr_use_user_terms)}
                onChange={(e) => set('asr_use_user_terms')(e.target.checked)}
              />
              {resetButton(props, 'asr_use_user_terms')}
            </span>
          </Row>
        </>
      )}

      {basic && (
        <>
          <Row label="話者分離" hint="誰が話したかを声で見分けて、話者ごとに名前と色を付けます。">
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
            <p
              data-testid={`${idPrefix}-diarization-unavailable`}
              className="text-xs text-amber-600"
            >
              話者分離モデルが未取得のため、いまは話者を分けられません。
              上の「セットアップ」から取得してください。
            </p>
          )}
          {Boolean(v.diarization_enabled) && (
            <>
              {/* 効くのは文字起こしのときだけ(transcribe_job → labels.build_label_map)。
                  2人で声の高さを測れたときに低い方へ male_name、高い方へ female_name。
                  それ以外は「話者1/話者2」になる */}
              <p className="text-xs text-neutral-500">
                文字起こしのときに付ける名前です(2人の対談で、声の高さで見分けられたとき)。
                文字起こしの後は、文字起こし画面で話者名を押して変えられます。
              </p>
              <Row label="声の低い方の初期名">
                <input
                  className={selectCls}
                  defaultValue={String(v.male_name)}
                  onBlur={(e) => e.target.value !== v.male_name && set('male_name')(e.target.value)}
                />
              </Row>
              <Row label="声の高い方の初期名">
                <input
                  className={selectCls}
                  defaultValue={String(v.female_name)}
                  onBlur={(e) =>
                    e.target.value !== v.female_name && set('female_name')(e.target.value)
                  }
                />
              </Row>
            </>
          )}
        </>
      )}
    </Section>
  )
}
