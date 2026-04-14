import { useEffect } from 'react'

interface Props {
  message: string
  onClose: () => void
}

export default function ErrorToast({ message, onClose }: Props) {
  useEffect(() => {
    const timer = setTimeout(onClose, 5000)
    return () => clearTimeout(timer)
  }, [message, onClose])

  if (!message) return null

  return (
    <div className="fixed top-4 right-4 z-50 max-w-sm animate-slide-in">
      <div className="bg-red-50 border border-red-200 rounded-lg shadow-lg p-4 flex items-start gap-3">
        <svg className="w-5 h-5 text-red-500 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <div className="flex-1">
          <p className="text-sm text-red-800">{message}</p>
        </div>
        <button
          type="button"
          className="text-red-400 hover:text-red-600"
          onClick={onClose}
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  )
}
