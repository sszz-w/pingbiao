import { useRef } from 'react'

interface Props {
  tenderFile: File | null
  bidFiles: File[]
  onTenderChange: (file: File | null) => void
  onBidFilesChange: (files: File[]) => void
  disabled?: boolean
}

export default function UploadPanel({
  tenderFile, bidFiles,
  onTenderChange, onBidFilesChange,
  disabled,
}: Props) {
  const tenderRef = useRef<HTMLInputElement>(null)
  const bidRef = useRef<HTMLInputElement>(null)

  const handleTender = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file && !file.name.endsWith('.pdf')) {
      alert('仅支持 PDF 文件')
      return
    }
    onTenderChange(file ?? null)
  }

  const handleBids = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    const invalid = files.find(f => !f.name.endsWith('.pdf'))
    if (invalid) {
      alert('仅支持 PDF 文件')
      return
    }
    onBidFilesChange([...bidFiles, ...files])
  }

  const removeBid = (index: number) => {
    onBidFilesChange(bidFiles.filter((_, i) => i !== index))
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">文件上传</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* 招标文件 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            招标文件（单个 PDF）
          </label>
          <input
            ref={tenderRef}
            type="file"
            accept=".pdf"
            className="hidden"
            onChange={handleTender}
            disabled={disabled}
          />
          <button
            type="button"
            className="w-full border-2 border-dashed border-gray-300 rounded-lg p-6 text-center hover:border-blue-400 hover:bg-blue-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={() => tenderRef.current?.click()}
            disabled={disabled}
          >
            {tenderFile ? (
              <div className="flex items-center justify-center gap-2">
                <svg className="w-5 h-5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span className="text-sm text-gray-700 truncate">{tenderFile.name}</span>
                <button
                  type="button"
                  className="text-red-500 hover:text-red-700 ml-2"
                  onClick={e => { e.stopPropagation(); onTenderChange(null); }}
                >
                  ✕
                </button>
              </div>
            ) : (
              <div>
                <svg className="w-8 h-8 text-gray-400 mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                <span className="text-sm text-gray-500">点击选择招标文件</span>
              </div>
            )}
          </button>
        </div>

        {/* 投标文件 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            投标文件（多个 PDF）
          </label>
          <input
            ref={bidRef}
            type="file"
            accept=".pdf"
            multiple
            className="hidden"
            onChange={handleBids}
            disabled={disabled}
          />
          <button
            type="button"
            className="w-full border-2 border-dashed border-gray-300 rounded-lg p-6 text-center hover:border-blue-400 hover:bg-blue-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={() => bidRef.current?.click()}
            disabled={disabled}
          >
            <svg className="w-8 h-8 text-gray-400 mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <span className="text-sm text-gray-500">点击选择投标文件</span>
          </button>
          {bidFiles.length > 0 && (
            <ul className="mt-3 space-y-1">
              {bidFiles.map((f, i) => (
                <li key={`${f.name}-${i}`} className="flex items-center justify-between text-sm text-gray-700 bg-gray-50 px-3 py-1.5 rounded">
                  <span className="truncate">{f.name}</span>
                  <button
                    type="button"
                    className="text-red-500 hover:text-red-700 ml-2 shrink-0"
                    onClick={() => removeBid(i)}
                    disabled={disabled}
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
