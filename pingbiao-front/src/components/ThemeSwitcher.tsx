import type { ThemeKey } from '../theme'
import { THEMES } from '../theme'

interface Props {
  currentTheme: ThemeKey
  onThemeChange: (key: ThemeKey) => void
}

export default function ThemeSwitcher({ currentTheme, onThemeChange }: Props) {
  return (
    <div className="flex items-center gap-1 mr-2">
      {THEMES.map(theme => (
        <button
          key={theme.key}
          type="button"
          onClick={() => onThemeChange(theme.key)}
          className="relative px-3 py-1.5 text-xs font-medium rounded-md transition-all"
          style={{
            backgroundColor: currentTheme === theme.key ? theme.colors.primary : 'transparent',
            color: currentTheme === theme.key ? theme.colors.primaryText : theme.colors.textSecondary,
            border: `1px solid ${currentTheme === theme.key ? theme.colors.primary : theme.colors.inputBorder}`,
          }}
          title={theme.name}
        >
          {theme.name}
          {currentTheme === theme.key && (
            <span
              className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full"
              style={{ backgroundColor: theme.colors.primary }}
            />
          )}
        </button>
      ))}
    </div>
  )
}
