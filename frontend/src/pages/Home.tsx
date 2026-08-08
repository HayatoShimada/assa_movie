/** ホーム: プロジェクト・メディアの登録と、文字起こしジョブの投入・進捗表示。 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { api, type Media, type Project } from '../api/client'
import { Button, Card, ProgressBar, formatTime } from '../components/ui'
import { CreateProjectForm } from '../components/project/CreateProjectForm'
import { ProjectSettingsPanel } from '../components/project/ProjectSettingsPanel'
import { templateFor } from '../lib/catalogs'
import { useJobProgress } from '../hooks/useJobProgress'
import { navigate } from '../hooks/useHashRoute'

function MediaRow({ media }: { media: Media }) {
  const queryClient = useQueryClient()
  const [jobId, setJobId] = useState<number | null>(null)
  const progress = useJobProgress(jobId, () => {
    queryClient.invalidateQueries({ queryKey: ['media', media.project_id] })
    queryClient.invalidateQueries({ queryKey: ['segments', media.id] })
  })

  const transcribe = useMutation({
    mutationFn: () => api.createJob(media.id, 'transcribe', { language: 'ja' }),
    onSuccess: (job) => setJobId(job.id),
  })

  const running = progress.status === 'running' || progress.status === 'queued'
  const name = media.path.split('/').pop()

  return (
    <li
      data-testid={`media-${media.id}`}
      className="flex items-center gap-3 border-b border-neutral-100 py-2 last:border-0 dark:border-neutral-800"
    >
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{name}</p>
        <p className="text-xs text-neutral-500">
          {media.duration ? formatTime(media.duration) : '長さ不明'} ・ {media.status}
        </p>
        {jobId !== null && progress.status !== 'idle' && (
          <div className="mt-1">
            <ProgressBar
              value={progress.progress}
              label={
                progress.status === 'failed'
                  ? `失敗: ${progress.error?.split('\n')[0] ?? ''}`
                  : progress.status === 'completed'
                    ? '文字起こし完了'
                    : `文字起こし中... ${Math.round(progress.progress * 100)}%`
              }
            />
          </div>
        )}
      </div>
      <Button
        variant="ghost"
        disabled={running || transcribe.isPending}
        onClick={() => transcribe.mutate()}
      >
        {media.status === 'transcribed' ? '再文字起こし' : '文字起こし'}
      </Button>
      <Button
        disabled={media.status !== 'transcribed'}
        onClick={() => navigate({ page: 'editor', mediaId: media.id })}
      >
        開く
      </Button>
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
  const remove = useMutation({
    mutationFn: () => api.deleteProject(project.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['projects'] }),
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

  return (
    <Card title={project.name}>
      <div className="mb-2 flex items-center gap-2">
        {templateLabel && (
          <span
            data-testid={`project-template-badge-${project.id}`}
            className="rounded-full bg-neutral-100 px-2 py-0.5 text-xs text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300"
          >
            {templateLabel}
          </span>
        )}
        <Button
          data-testid={`project-settings-${project.id}`}
          variant="ghost"
          className="ml-auto"
          onClick={() => setShowSettings((s) => !s)}
        >
          設定
        </Button>
        <Button
          data-testid={`project-delete-${project.id}`}
          variant="ghost"
          disabled={remove.isPending}
          onClick={() => {
            if (
              window.confirm(
                `プロジェクト「${project.name}」を削除します。動画の文字起こし・クリップも全て消えます。よろしいですか?`,
              )
            )
              remove.mutate()
          }}
        >
          削除
        </Button>
      </div>
      {showSettings && <ProjectSettingsPanel project={project} />}
      {media.data?.length ? (
        <ul>
          {media.data.map((m) => (
            <MediaRow key={m.id} media={m} />
          ))}
        </ul>
      ) : (
        <p className="text-sm text-neutral-500">動画がまだありません</p>
      )}
      <form
        className="mt-3 flex gap-2"
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
        <input
          className="flex-1 rounded-md border border-neutral-300 px-2 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          placeholder="動画ファイルのパス(例: /home/user/対談.mov)"
          value={path}
          onChange={(e) => setPath(e.target.value)}
        />
        <Button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={adding}
        >
          動画を追加
        </Button>
        <Button type="submit" variant="ghost" disabled={adding}>
          パスで追加
        </Button>
      </form>
      {addError && (
        <p className="mt-1 text-xs text-red-600">{String(addError.message)}</p>
      )}
    </Card>
  )
}

export function Home() {
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.listProjects })

  return (
    <main className="mx-auto max-w-3xl space-y-4 p-6">
      <h1 className="text-xl font-bold">KirinukiStudio</h1>

      <CreateProjectForm />

      {projects.isError && (
        <p className="text-sm text-red-600">
          バックエンドに接続できません。`./dev.sh api` で起動してください。
        </p>
      )}
      {projects.data?.map((p) => <ProjectCard key={p.id} project={p} />)}
      {projects.data?.length === 0 && (
        <p className="text-sm text-neutral-500">プロジェクトを作成して動画を追加してください。</p>
      )}
    </main>
  )
}
