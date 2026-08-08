/**
 * UI用のアイコン(インラインSVG)。
 *
 * 外部アイコンライブラリを足さずに済むよう、使う分だけここに置く。
 * 線画で統一し、色は currentColor に従わせる(ダークモード対応のため)。
 */
type IconProps = { className?: string }

function Svg({ className = 'h-4 w-4', children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {children}
    </svg>
  )
}

/** トランスクリプト: 文書の行 */
export const TranscriptIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 5h16M4 10h16M4 15h11M4 20h7" />
  </Svg>
)

/** レビュー: チェック付きの書類 */
export const ReviewIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
    <path d="M14 3v6h6" />
    <path d="M9 14.5l2 2 4-4" />
  </Svg>
)

/** 質問: 吹き出しに「?」 */
export const QuestionIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M21 12a8 8 0 0 1-8 8H7l-4 3v-5.5A8 8 0 0 1 11 4h2a8 8 0 0 1 8 8z" />
    <path d="M10 10a2 2 0 1 1 2.5 1.9c-.5.2-.5.6-.5 1.1" />
    <path d="M12 16h.01" />
  </Svg>
)

/** クリップ: フィルムの一場面を切り出す */
export const ClipIcon = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3" y="5" width="18" height="14" rx="2" />
    <path d="M9 5v14M15 5v14" />
  </Svg>
)

/** 書き出し: 箱から出る矢印 */
export const ExportIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 15V3" />
    <path d="M8 7l4-4 4 4" />
    <path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" />
  </Svg>
)

/** 削除: ゴミ箱 */
export const TrashIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 7h16" />
    <path d="M10 11v6M14 11v6" />
    <path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12" />
    <path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
  </Svg>
)

/** 設定: スライダー(歯車より意味が伝わる) */
export const SettingsIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h8M16 18h4" />
    <circle cx="16" cy="6" r="2" />
    <circle cx="10" cy="12" r="2" />
    <circle cx="14" cy="18" r="2" />
  </Svg>
)
