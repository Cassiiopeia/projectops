import DefaultTheme from 'vitepress/theme'
import type { Theme } from 'vitepress'
import { toLegacyRedirectPath } from '../locale-paths.mts'
import './custom.css'

// Old URL (/en/*, /CLI, etc.) > new URL redirect (#976)
// GitHub Pages has no server redirects, so missing paths land on 404.html > rewrite here (hash kept)
function redirectLegacyUrl() {
  const base = import.meta.env.BASE_URL.replace(/\/$/, '')
  const { pathname, search, hash } = window.location
  if (!pathname.startsWith(base)) return
  const target = toLegacyRedirectPath(pathname.slice(base.length) || '/')
  if (target) window.location.replace(`${base}${target}${search}${hash}`)
}

export default {
  extends: DefaultTheme,
  enhanceApp() {
    if (typeof window !== 'undefined') redirectLegacyUrl()
  },
} satisfies Theme
