'use client'

import { useAuth } from '@/hooks/useAuth'
import { Copy, Eye, EyeOff } from 'lucide-react'
import { useState } from 'react'

export default function ApiKeysPage() {
  const { apiKey } = useAuth()
  const [showKey, setShowKey] = useState(false)
  const [copied, setCopied] = useState(false)

  const copyToClipboard = () => {
    if (apiKey) {
      navigator.clipboard.writeText(apiKey)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-8">API Keys</h1>

      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-xl font-semibold mb-4">Your API Key</h2>
        <p className="text-gray-600 mb-4">
          Use this key to authenticate all API requests. Include it in the{' '}
          <code className="bg-gray-100 px-1 rounded">X-API-Key</code> header.
        </p>

        <div className="flex items-center gap-2 p-4 bg-gray-50 rounded-lg">
          <code className="flex-1 font-mono text-sm break-all">
            {showKey ? apiKey : '••••••••••••••••••••••••••••••••'}
          </code>
          <button
            onClick={() => setShowKey(!showKey)}
            className="p-2 hover:bg-gray-200 rounded-lg"
          >
            {showKey ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
          </button>
          <button
            onClick={copyToClipboard}
            className="p-2 hover:bg-gray-200 rounded-lg"
          >
            <Copy className="w-5 h-5" />
          </button>
        </div>

        {copied && (
          <p className="text-green-600 text-sm mt-2">Copied to clipboard!</p>
        )}

        <div className="mt-6 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
          <p className="text-yellow-800 text-sm">
            <strong>Important:</strong> This API key is shown only once during registration.
            If you lose it, you'll need to register a new account.
          </p>
        </div>

        <div className="mt-6">
          <h3 className="font-semibold mb-2">Example Usage</h3>
          <pre className="bg-gray-900 text-green-400 p-4 rounded-lg text-sm overflow-auto">
{`curl -X POST https://facedeep.me/api/v1/face/enroll \\
  -H "X-API-Key: ${apiKey || 'YOUR_API_KEY'}" \\
  -F "file=@face.jpg" \\
  -F "person_id=emp_001"`}
          </pre>
        </div>
      </div>
    </div>
  )
}
