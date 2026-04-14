import type { ClauseItem, ScoreResult } from '../types'
import type { ThemeConfig } from '../theme'

interface Props {
  clauseList: ClauseItem[]
  bidFiles: string[]
  scoreMatrix: ScoreResult[]
  theme?: ThemeConfig
}

export default function Sidebar({ clauseList, bidFiles, scoreMatrix, theme }: Props) {
  return (
    <div
      className="w-80 overflow-y-auto flex flex-col"
      style={{
        borderLeft: `1px solid ${theme?.colors.sidebarBorder ?? '#e5e7eb'}`,
        backgroundColor: theme?.colors.sidebarBg ?? '#f9fafb',
        fontFamily: theme?.fontFamily,
      }}
    >
      {/* Clause List */}
      <div
        className="p-4"
        style={{ borderBottom: `1px solid ${theme?.colors.sidebarBorder ?? '#e5e7eb'}` }}
      >
        <h3
          className="text-sm font-semibold mb-3"
          style={{ color: theme?.colors.textPrimary ?? '#374151' }}
        >
          条款列表 {clauseList.length > 0 && `(${clauseList.length})`}
        </h3>
        {clauseList.length === 0 ? (
          <p className="text-xs" style={{ color: theme?.colors.textMuted ?? '#9ca3af' }}>
            等待提取...
          </p>
        ) : (
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {clauseList.map((clause, i) => (
              <div
                key={i}
                className="p-2 text-xs"
                style={{
                  backgroundColor: theme?.colors.cardBg ?? '#ffffff',
                  borderRadius: theme?.borderRadius.md ?? '8px',
                  border: `1px solid ${theme?.colors.cardBorder ?? '#e5e7eb'}`,
                }}
              >
                <div
                  className="font-medium mb-1"
                  style={{ color: theme?.colors.textPrimary ?? '#374151' }}
                >
                  {i + 1}. {clause.条款描述.slice(0, 40)}{clause.条款描述.length > 40 ? '...' : ''}
                </div>
                <div
                  className="text-[10px]"
                  style={{ color: theme?.colors.textMuted ?? '#6b7280' }}
                >
                  {clause.评分标准.slice(0, 50)}{clause.评分标准.length > 50 ? '...' : ''}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Bid Files */}
      <div
        className="p-4"
        style={{ borderBottom: `1px solid ${theme?.colors.sidebarBorder ?? '#e5e7eb'}` }}
      >
        <h3
          className="text-sm font-semibold mb-3"
          style={{ color: theme?.colors.textPrimary ?? '#374151' }}
        >
          投标文件 {bidFiles.length > 0 && `(${bidFiles.length})`}
        </h3>
        {bidFiles.length === 0 ? (
          <p className="text-xs" style={{ color: theme?.colors.textMuted ?? '#9ca3af' }}>
            等待上传...
          </p>
        ) : (
          <ul className="space-y-1.5">
            {bidFiles.map((name, i) => (
              <li key={i} className="flex items-center gap-2 text-xs" style={{ color: theme?.colors.textSecondary ?? '#4b5563' }}>
                <svg
                  className="w-4 h-4 shrink-0"
                  style={{ color: theme?.colors.primary ?? '#3b82f6' }}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <span className="truncate">{name}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Score Summary */}
      <div className="p-4 flex-1">
        <h3
          className="text-sm font-semibold mb-3"
          style={{ color: theme?.colors.textPrimary ?? '#374151' }}
        >
          评分汇总
        </h3>
        {scoreMatrix.length === 0 ? (
          <p className="text-xs" style={{ color: theme?.colors.textMuted ?? '#9ca3af' }}>
            等待评审...
          </p>
        ) : (
          <div className="space-y-3">
            {bidFiles.map(bidName => {
              const scores = scoreMatrix.filter(s => s.bidName === bidName)
              const total = scores.reduce((sum, s) => sum + (s.data ? parseInt(s.data.打分) || 0 : 0), 0)
              const completed = scores.filter(s => s.data !== null).length

              return (
                <div
                  key={bidName}
                  className="p-3"
                  style={{
                    backgroundColor: theme?.colors.cardBg ?? '#ffffff',
                    borderRadius: theme?.borderRadius.md ?? '8px',
                    border: `1px solid ${theme?.colors.cardBorder ?? '#e5e7eb'}`,
                  }}
                >
                  <div
                    className="text-xs font-medium mb-1 truncate"
                    style={{ color: theme?.colors.textPrimary ?? '#374151' }}
                  >
                    {bidName}
                  </div>
                  <div
                    className="text-lg font-bold"
                    style={{ color: theme?.colors.primary ?? '#2563eb' }}
                  >
                    {total}
                  </div>
                  <div
                    className="text-[10px] mt-1"
                    style={{ color: theme?.colors.textMuted ?? '#9ca3af' }}
                  >
                    已评 {completed}/{clauseList.length} 条
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
