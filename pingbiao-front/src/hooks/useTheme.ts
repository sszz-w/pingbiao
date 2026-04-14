import { useState } from 'react'
import { getThemeByKey, type ThemeKey } from '../theme'

const STORAGE_KEY = 'pingbiao_theme'

export function useTheme() {
  const [themeKey, setThemeKey] = useState<ThemeKey>(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'internet' || stored === 'minimal' || stored === 'government') {
      return stored
    }
    return 'internet'
  })

  const theme = getThemeByKey(themeKey)

  const setTheme = (key: ThemeKey) => {
    setThemeKey(key)
    localStorage.setItem(STORAGE_KEY, key)
  }

  return { theme, themeKey, setTheme }
}
