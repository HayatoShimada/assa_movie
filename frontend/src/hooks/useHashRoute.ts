/**
 * 最小のハッシュルーティング。ページ2枚(ホーム/エディタ)にライブラリは不要。
 *   #/            → { page: 'home' }
 *   #/media/3     → { page: 'editor', mediaId: 3 }
 */
import { useEffect, useState } from 'react'

export type Route = { page: 'home' } | { page: 'editor'; mediaId: number }

export function parseHash(hash: string): Route {
  const m = hash.match(/^#\/media\/(\d+)/)
  if (m) return { page: 'editor', mediaId: Number(m[1]) }
  return { page: 'home' }
}

export function navigate(route: Route) {
  window.location.hash = route.page === 'home' ? '#/' : `#/media/${route.mediaId}`
}

export function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash))
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}
