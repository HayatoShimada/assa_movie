/** ホーム: プロジェクト・メディアの登録と、文字起こしジョブの投入・進捗表示。 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { api, type Media, type Project } from '../api/client'
import { JobStatus } from '../components/JobStatus'
import { Button, StateBadge, formatTime } from '../components/ui'
import { FilmIcon, SettingsIcon, TrashIcon, UploadIcon } from '../components/icons'
import { CreateProjectForm } from '../components/project/CreateProjectForm'
import { ProjectSettingsPanel } from '../components/project/ProjectSettingsPanel'
import { templateFor } from '../lib/catalogs'
import { jobSlots } from '../lib/jobs'
import { mediaDisplayName, mediaState } from '../lib/media'
import { useTrackedJob } from '../hooks/useTrackedJob'
import { navigate } from '../hooks/useHashRoute'

/** 横長の画から縦長の1枚を切り出す図。このアプリがやることそのもの */
function BrandMark() {
  return (
    <svg viewBox="0 0 40 28" aria-hidden="true" className="h-7 w-10 shrink-0">
      <rect
        x="1"
        y="1"
        width="38"
        height="26"
        rx="3"
        className="fill-none stroke-neutral-400 dark:stroke-neutral-500"
        strokeWidth="2"
      />
      <rect x="15" y="1" width="10" height="26" className="fill-blue-600 dark:fill-blue-500" />
    </svg>
  )
}

function MediaRow({ media }: { media: Media }) {
  const queryClient = useQueryClient()
  const [confirmingRetranscribe, setConfirmingRetranscribe] = useState(false)
  // ジョブIDは行の外に預ける(編集画面との行き来・再読み込みで進捗と中止ボタンを失わない)
  const { jobId, progress, busy, start } = useTrackedJob(jobSlots.transcribe(media.id), () => {
    queryClient.invalidateQueries({ queryKey: ['media', media.project_id] })
    queryClient.invalidateQueries({ queryKey: ['segments', media.id] })
  })

  const transcribe = useMutation({
    mutationFn: () => api.createJob(media.id, 'transcribe', { language: 'ja' }),
    onSuccess: (job) => {
      setConfirmingRetranscribe(false)
      start(job.id)
    },
  })

  const cancel = useMutation({
    mutationFn: () => api.cancelJob(jobId as number),
  })

  const running = busy
  const transcribed = media.status === 'transcribed'
  const state = mediaState(media.status, progress.status)

  return (
    <li
      data-testid={`media-${media.id}`}
      className="border-b border-neutral-100 px-4 py-3 last:border-0 dark:border-neutral-800"
    >
      <div className="flex items-center gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-neutral-100 text-neutral-500 dark:bg-neutral-800 dark:text-neutral-400">
          <FilmIcon className="h-5 w-5" />
        </span>
        <div className="min-w-0 flex-1">
          {/* フルパスは長すぎるので名前だけ。どこにあるかはホバーで確かめられる */}
          <p className="truncate text-sm font-medium" title={media.path}>
            {mediaDisplayName(media.path)}
          </p>
          <p className="mt-0.5 flex items-center gap-2 text-xs text-neutral-500">
            <StateBadge data-testid={`media-state-${media.id}`} tone={state.tone}>
              {state.label}
            </StateBadge>
            <span className="tabular-nums">
              {media.duration ? formatTime(media.duration) : '長さ不明'}
            </span>
          </p>
        </div>

        {/* 次にやることだけを主ボタンにする。文字起こし前は開けないので「開く」は出さない */}
        <div className="flex shrink-0 items-center gap-2">
          {/* 文字起こしは長いと数十分かかる。間違えて始めたら待つしかない状態にしない */}
          {running ? (
            <Button
              data-testid={`media-cancel-${media.id}`}
              variant="ghost"
              disabled={cancel.isPending}
              onClick={() => cancel.mutate()}
            >
              中止
            </Button>
          ) : transcribed ? (
            !confirmingRetranscribe && (
              <>
                <Button
                  data-testid={`media-transcribe-${media.id}`}
                  variant="ghost"
                  className="border-transparent text-neutral-600 dark:border-transparent dark:text-neutral-300"
                  disabled={transcribe.isPending}
                  onClick={() => setConfirmingRetranscribe(true)}
                >
                  再文字起こし
                </Button>
                <Button onClick={() => navigate({ page: 'editor', mediaId: media.id })}>
                  開く
                </Button>
              </>
            )
          ) : (
            <Button
              data-testid={`media-transcribe-${media.id}`}
              disabled={transcribe.isPending}
              onClick={() => transcribe.mutate()}
            >
              文字起こし
            </Button>
          )}
        </div>
      </div>

      {/* 再文字起こしはセグメントを作り直すので、手直しとレビュー結果が消える。
          破壊的な操作は確認を挟む(FRONTEND_DESIGN.md 非機能) */}
      {confirmingRetranscribe && !running && (
        <div className="mt-2 flex flex-wrap items-center gap-2 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-200">
          <span className="flex-1">やり直すと、手で直した文字起こしとレビュー結果は消えます。</span>
          <Button
            data-testid={`media-retranscribe-confirm-${media.id}`}
            variant="danger"
            disabled={transcribe.isPending}
            onClick={() => transcribe.mutate()}
          >
            やり直す
          </Button>
          <Button variant="ghost" onClick={() => setConfirmingRetranscribe(false)}>
            やめる
          </Button>
        </div>
      )}

      {progress.status !== 'idle' && (
        <div className="mt-2 pl-12">
          {/* 工程名はジョブが報告する(話者分離中→文字起こし中→保存中) */}
          <JobStatus
            progress={progress}
            running="文字起こし中"
            done="文字起こし完了"
            data-testid={`media-progress-${media.id}`}
          />
        </div>
      )}
      {transcribe.isError && (
        <p className="mt-1 pl-12 text-xs text-red-600 dark:text-red-400">
          文字起こしを始められませんでした: {transcribe.error.message}
        </p>
      )}
    </li>
  )
}

function ProjectCard({ project }: { project: Project }) {
  const queryClient = useQueryClient()
  const media = useQuery({
    queryKey: ['media', project.id],
    queryFn: () => api.listMedia(project.id),
    // 画面外(CLI・別タブ)で始まった文字起こしの完了も反映したいので緩く監視する。
    // UIから始めたジョブはSSE完了時にinvalidateされるため、これは保険。
    // 未処理のメディアが残っている間だけ回す(タブが非表示の間は自動で止まる)
    refetchInterval: (query) =>
      (query.state.data ?? []).some((m) => m.status !== 'transcribed') ? 30000 : false,
  })
  const [showSettings, setShowSettings] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const remove = useMutation({
    mutationFn: () => api.deleteProject(project.id),
    onSuccess: () => {
      setConfirming(false)
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
  const templateLabel = templateFor(project)?.label
  const [path, setPath] = useState('')
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const addMedia = useMutation({
    mutationFn: () => api.addMedia(project.id, path),
    onSuccess: () => {
      setPath('')
      queryClient.invalidateQueries({ queryKey: ['media', project.id] })
    },
  })
  const uploadMedia = useMutation({
    mutationFn: (file: File) => api.uploadMedia(project.id, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['media', project.id] })
    },
  })

  const adding = addMedia.isPending || uploadMedia.isPending
  const addError = addMedia.error ?? uploadMedia.error
  const count = media.data?.length ?? 0

  return (
    <section className="overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-800">
      <div className="flex items-center gap-2 border-b border-neutral-200 px-4 py-2.5 dark:border-neutral-800">
        <h3 className="min-w-0 truncate font-semibold">{project.name}</h3>
        {templateLabel && (
          <span
            data-testid={`project-template-badge-${project.id}`}
            title="元動画の向き → 書き出しの向き"
            className="shrink-0 rounded-full bg-neutral-100 px-2 py-0.5 text-xs text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300"
          >
            {templateLabel}
          </span>
        )}
        {media.data && <span className="shrink-0 text-xs text-neutral-500">動画 {count}本</span>}
        <div className="ml-auto flex shrink-0 items-center gap-1">
          <Button
            data-testid={`project-settings-${project.id}`}
            variant="ghost"
            aria-expanded={showSettings}
            className={`flex items-center gap-1 border-transparent dark:border-transparent ${
              showSettings ? 'bg-neutral-100 dark:bg-neutral-800' : ''
            }`}
            onClick={() => setShowSettings((s) => !s)}
          >
            <SettingsIcon />
            設定
          </Button>
          <Button
            data-testid={`project-delete-${project.id}`}
            variant="ghost"
            aria-expanded={confirming}
            className="flex items-center gap-1 border-transparent text-neutral-600 hover:text-red-700 dark:border-transparent dark:text-neutral-300 dark:hover:text-red-400"
            onClick={() => setConfirming(true)}
          >
            <TrashIcon />
            削除
          </Button>
        </div>
      </div>

      {/* window.confirm はwebviewによって出方が変わる(Tauriのデスクトップ版で
          押しても何も起きない事象があった)。画面内で確認する */}
      {confirming && (
        <div className="flex flex-wrap items-center gap-2 border-b border-red-200 bg-red-50 px-4 py-2 text-sm text-red-900 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
          <span className="flex-1">
            このプロジェクトを削除すると、文字起こしとクリップも消えます。元の動画ファイルは残ります。
          </span>
          <Button
            data-testid={`project-delete-confirm-${project.id}`}
            variant="danger"
            disabled={remove.isPending}
            onClick={() => remove.mutate()}
          >
            {remove.isPending ? '削除中…' : '削除する'}
          </Button>
          <Button variant="ghost" onClick={() => setConfirming(false)}>
            やめる
          </Button>
        </div>
      )}
      {remove.isError && (
        <p
          data-testid={`project-delete-error-${project.id}`}
          className="px-4 pt-2 text-xs text-red-600 dark:text-red-400"
        >
          削除できませんでした: {(remove.error as Error).message}
        </p>
      )}
      {showSettings && (
        <div className="border-b border-neutral-200 px-4 py-3 dark:border-neutral-800">
          <ProjectSettingsPanel project={project} />
        </div>
      )}

      {count > 0 ? (
        <ul>
          {media.data!.map((m) => (
            <MediaRow key={m.id} media={m} />
          ))}
        </ul>
      ) : (
        media.data && (
          <p className="px-4 py-4 text-sm text-neutral-500">
            動画がまだありません。下の「動画ファイルを選ぶ」から追加してください。
          </p>
        )
      )}

      <form
        className="flex flex-wrap items-center gap-2 border-t border-dashed border-neutral-200 bg-neutral-50 px-4 py-3 dark:border-neutral-800 dark:bg-neutral-900/50"
        onSubmit={(e) => {
          e.preventDefault()
          if (path.trim()) addMedia.mutate()
        }}
      >
        <input
          data-testid={`media-file-input-${project.id}`}
          ref={fileInputRef}
          type="file"
          accept="video/*,audio/*,.wav,.mp3,.m4a,.mov,.mp4,.mkv"
          className="hidden"
          onChange={(e) => {
            const file = e.currentTarget.files?.[0]
            if (file) uploadMedia.mutate(file)
            e.currentTarget.value = ''
          }}
        />
        <Button
          type="button"
          variant="ghost"
          className="flex items-center gap-1.5 bg-white dark:bg-neutral-900"
          onClick={() => fileInputRef.current?.click()}
          disabled={adding}
        >
          <UploadIcon />
          {uploadMedia.isPending ? '取り込み中…' : '動画ファイルを選ぶ'}
        </Button>
        <span className="text-xs text-neutral-500">または</span>
        <input
          aria-label="動画ファイルのパス"
          className="min-w-48 flex-1 rounded-md border border-neutral-300 bg-white px-2 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          placeholder="ファイルのパスを貼り付け"
          value={path}
          onChange={(e) => setPath(e.target.value)}
        />
        <Button type="submit" variant="ghost" disabled={adding || !path.trim()}>
          パスで追加
        </Button>
      </form>
      {addError && (
        <p className="px-4 pb-3 text-xs text-red-600 dark:text-red-400">
          追加できませんでした: {String(addError.message)}
        </p>
      )}
    </section>
  )
}

export function Home() {
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.listProjects })

  return (
    <main className="mx-auto max-w-3xl px-6 pb-16 pt-8">
      <header className="mb-6 flex items-center gap-3">
        <BrandMark />
        <h1 className="text-xl font-bold tracking-tight">Kirinuki Studio</h1>
        <p className="ml-auto hidden text-xs text-neutral-500 sm:block">
          対談動画を文字起こしして、字幕つきの切り抜きを作る
        </p>
        {/* 文字起こし前でも設定を見直せるように、全体の設定はホームから開ける */}
        <Button
          data-testid="open-global-settings"
          variant="ghost"
          className="ml-auto flex shrink-0 items-center gap-1 sm:ml-0"
          title="すべてのプロジェクトに共通の設定(文字起こし・字幕・AIなど)"
          onClick={() => navigate({ page: 'settings' })}
        >
          <SettingsIcon />
          全体の設定
        </Button>
      </header>

      <CreateProjectForm />

      <section className="mt-8 space-y-4" aria-labelledby="projects-heading">
        <h2 id="projects-heading" className="text-sm font-semibold text-neutral-500">
          プロジェクト{projects.data?.length ? `(${projects.data.length})` : ''}
        </h2>
        {projects.isError && (
          <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
            処理用のプログラムに接続できません。アプリを再起動してください (開発中は{' '}
            <code>./dev.sh</code> でバックエンドを起動します)。
          </p>
        )}
        {projects.data?.map((p) => (
          <ProjectCard key={p.id} project={p} />
        ))}
        {projects.data?.length === 0 && (
          <p
            data-testid="projects-empty"
            className="rounded-lg border border-dashed border-neutral-300 px-4 py-6 text-center text-sm text-neutral-500 dark:border-neutral-700"
          >
            まだプロジェクトがありません。上でプロジェクト名を入れて「作成」を押すと、動画を追加できます。
          </p>
        )}
      </section>
    </main>
  )
}
