// ── Theme Configuration ──

export type ThemeKey = 'internet' | 'minimal' | 'government'

export interface ChatIdentityColors {
  bubbleColor: string
  textColor: string
}

export interface ThemeConfig {
  name: string
  key: ThemeKey
  colors: {
    primary: string
    primaryHover: string
    primaryText: string
    headerBg: string
    headerText: string
    headerBorder: string
    bodyBg: string
    sidebarBg: string
    sidebarBorder: string
    cardBg: string
    cardBorder: string
    inputBorder: string
    inputFocusBorder: string
    inputBg: string
    buttonBg: string
    buttonHoverBg: string
    buttonText: string
    textPrimary: string
    textSecondary: string
    textMuted: string
  }
  chatIdentities: {
    system: ChatIdentityColors
    file: ChatIdentityColors
    clause: ChatIdentityColors
    scorer: ChatIdentityColors
    support: ChatIdentityColors
    challenge: ChatIdentityColors
    arbitrator: ChatIdentityColors
    error: ChatIdentityColors
    user: ChatIdentityColors
  }
  borderRadius: {
    sm: string
    md: string
    lg: string
    xl: string
  }
  shadow: {
    none: string
    sm: string
    md: string
    lg: string
  }
  fontFamily: string
}

// ── Internet Style (互联网风格) ──
export const internetTheme: ThemeConfig = {
  name: '互联网风格',
  key: 'internet',
  colors: {
    primary: '#6366f1',
    primaryHover: '#4f46e5',
    primaryText: '#ffffff',
    headerBg: 'rgba(255, 255, 255, 0.85)',
    headerText: '#1e1b4b',
    headerBorder: '#e0e7ff',
    bodyBg: '#f8fafc',
    sidebarBg: '#f1f5f9',
    sidebarBorder: '#e0e7ff',
    cardBg: '#ffffff',
    cardBorder: '#e0e7ff',
    inputBorder: '#c7d2fe',
    inputFocusBorder: '#6366f1',
    inputBg: '#ffffff',
    buttonBg: '#6366f1',
    buttonHoverBg: '#4f46e5',
    buttonText: '#ffffff',
    textPrimary: '#1e1b4b',
    textSecondary: '#475569',
    textMuted: '#94a3b8',
  },
  chatIdentities: {
    system: { bubbleColor: '#E8F5E9', textColor: '#2E7D32' },
    file: { bubbleColor: '#E3F2FD', textColor: '#1565C0' },
    clause: { bubbleColor: '#FFF3E0', textColor: '#E65100' },
    scorer: { bubbleColor: '#F3E5F5', textColor: '#6A1B9A' },
    support: { bubbleColor: '#E8F5E9', textColor: '#2E7D32' },
    challenge: { bubbleColor: '#FFF3E0', textColor: '#F57C00' },
    arbitrator: { bubbleColor: '#E1F5FE', textColor: '#0277BD' },
    error: { bubbleColor: '#FFEBEE', textColor: '#C62828' },
    user: { bubbleColor: '#EEF2FF', textColor: '#3730A3' },
  },
  borderRadius: {
    sm: '8px',
    md: '12px',
    lg: '16px',
    xl: '20px',
  },
  shadow: {
    none: 'none',
    sm: '0 1px 3px rgba(99, 102, 241, 0.08)',
    md: '0 4px 12px rgba(99, 102, 241, 0.10)',
    lg: '0 8px 30px rgba(99, 102, 241, 0.15)',
  },
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
}

// ── Minimalist Style (简约风格) ──
export const minimalTheme: ThemeConfig = {
  name: '简约风格',
  key: 'minimal',
  colors: {
    primary: '#000000',
    primaryHover: '#1a1a1a',
    primaryText: '#ffffff',
    headerBg: '#ffffff',
    headerText: '#000000',
    headerBorder: '#e5e5e5',
    bodyBg: '#ffffff',
    sidebarBg: '#fafafa',
    sidebarBorder: '#e5e5e5',
    cardBg: '#ffffff',
    cardBorder: '#e5e5e5',
    inputBorder: '#d4d4d4',
    inputFocusBorder: '#000000',
    inputBg: '#ffffff',
    buttonBg: '#000000',
    buttonHoverBg: '#262626',
    buttonText: '#ffffff',
    textPrimary: '#000000',
    textSecondary: '#525252',
    textMuted: '#a3a3a3',
  },
  chatIdentities: {
    system: { bubbleColor: '#f5f5f5', textColor: '#404040' },
    file: { bubbleColor: '#f5f5f5', textColor: '#404040' },
    clause: { bubbleColor: '#f5f5f5', textColor: '#404040' },
    scorer: { bubbleColor: '#f0f0f0', textColor: '#262626' },
    support: { bubbleColor: '#f5f5f5', textColor: '#404040' },
    challenge: { bubbleColor: '#f5f5f5', textColor: '#404040' },
    arbitrator: { bubbleColor: '#f0f0f0', textColor: '#262626' },
    error: { bubbleColor: '#fafafa', textColor: '#dc2626' },
    user: { bubbleColor: '#f5f5f5', textColor: '#171717' },
  },
  borderRadius: {
    sm: '2px',
    md: '4px',
    lg: '6px',
    xl: '8px',
  },
  shadow: {
    none: 'none',
    sm: 'none',
    md: 'none',
    lg: 'none',
  },
  fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
}

// ── Government/Enterprise Style (政企风格) ──
export const governmentTheme: ThemeConfig = {
  name: '政企风格',
  key: 'government',
  colors: {
    primary: '#1a365d',
    primaryHover: '#153e75',
    primaryText: '#ffffff',
    headerBg: '#1a365d',
    headerText: '#ffffff',
    headerBorder: '#c53030',
    bodyBg: '#f7f7f5',
    sidebarBg: '#f0f0ee',
    sidebarBorder: '#d4d4cf',
    cardBg: '#ffffff',
    cardBorder: '#d4d4cf',
    inputBorder: '#b5b5b0',
    inputFocusBorder: '#1a365d',
    inputBg: '#ffffff',
    buttonBg: '#1a365d',
    buttonHoverBg: '#153e75',
    buttonText: '#ffffff',
    textPrimary: '#1a202c',
    textSecondary: '#4a5568',
    textMuted: '#a0aec0',
  },
  chatIdentities: {
    system: { bubbleColor: '#EBF4FF', textColor: '#1a365d' },
    file: { bubbleColor: '#EBF8FF', textColor: '#2a4365' },
    clause: { bubbleColor: '#FEFCBF', textColor: '#744210' },
    scorer: { bubbleColor: '#EBF4FF', textColor: '#1a365d' },
    support: { bubbleColor: '#F0FFF4', textColor: '#22543d' },
    challenge: { bubbleColor: '#FFF5F5', textColor: '#c53030' },
    arbitrator: { bubbleColor: '#EBF4FF', textColor: '#1a365d' },
    error: { bubbleColor: '#FFF5F5', textColor: '#c53030' },
    user: { bubbleColor: '#F7FAFC', textColor: '#2d3748' },
  },
  borderRadius: {
    sm: '2px',
    md: '4px',
    lg: '6px',
    xl: '8px',
  },
  shadow: {
    none: 'none',
    sm: '0 1px 2px rgba(0, 0, 0, 0.05)',
    md: '0 2px 4px rgba(0, 0, 0, 0.06)',
    lg: '0 4px 8px rgba(0, 0, 0, 0.08)',
  },
  fontFamily: '"SimSun", "宋体", "Microsoft YaHei", "微软雅黑", serif',
}

// ── Theme registry ──
export const THEMES: ThemeConfig[] = [internetTheme, minimalTheme, governmentTheme]

export function getThemeByKey(key: ThemeKey): ThemeConfig {
  return THEMES.find(t => t.key === key) || internetTheme
}
