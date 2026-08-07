import { Editor } from './pages/Editor'
import { Home } from './pages/Home'
import { useHashRoute } from './hooks/useHashRoute'

export default function App() {
  const route = useHashRoute()
  if (route.page === 'editor') return <Editor mediaId={route.mediaId} />
  return <Home />
}
