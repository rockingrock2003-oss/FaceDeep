'use client'

import { authAPI } from '@/lib/api'
import { Copy, Eye, EyeOff, RefreshCw } from 'lucide-react'
import { useState, useEffect } from 'react'

export default function ApiKeysPage() {
  const [apiKey, setApiKey] = useState<string | null>(null)
  const [showKey, setShowKey] = useState(false)
  const [copied, setCopied] = useState(false)
  const [regenerating, setRegenerating] = useState(false)

  useEffect(() => {
    fetchApiKey()
  }, [])

  const fetchApiKey = async () => {
    try {
      const res = await authAPI.getApiKey()
      setApiKey(res.data.api_key_prefix)
    } catch {
      setApiKey(null)
    }
  }

  const handleRegenerate = async () => {
    if (!confirm('Generate a new API key? The old key will stop working immediately.')) return
    setRegenerating(true)
    try {
      const res = await authAPI.regenerateApiKey()
      setApiKey(res.data.api_key)
      setShowKey(true)
    } catch {
      // ignore
    } finally {
      setRegenerating(false)
    }
  }

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
          Use this key for external API access. Include it in the{' '}
          <code className="bg-gray-100 px-1 rounded">X-API-Key</code> header.
        </p>

        <div className="flex items-center gap-2 p-4 bg-gray-50 rounded-lg">
          <code className="flex-1 font-mono text-sm break-all">
            {showKey ? (apiKey || 'No key generated') : '••••••••••••••••••••••••••••••••'}
          </code>
          <button
            onClick={() => setShowKey(!showKey)}
            className="p-2 hover:bg-gray-200 rounded-lg"
          >
            {showKey ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
          </button>
          {showKey && (
            <button
              onClick={copyToClipboard}
              className="p-2 hover:bg-gray-200 rounded-lg"
            >
              <Copy className="w-5 h-5" />
            </button>
          )}
        </div>

        {copied && (
          <p className="text-green-600 text-sm mt-2">Copied to clipboard!</p>
        )}

        <button
          onClick={handleRegenerate}
          disabled={regenerating}
          className="mt-4 flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${regenerating ? 'animate-spin' : ''}`} />
          {regenerating ? 'Generating...' : 'Generate New Key'}
        </button>

        <div className="mt-6">
          <h3 className="font-semibold mb-2">Example Usage</h3>
          <pre className="bg-gray-900 text-green-400 p-4 rounded-lg text-sm overflow-auto">
{`curl -X POST https://facedeep.me/api/v1/face/enroll \\
  -H "X-API-Key: YOUR_API_KEY" \\
  -F "file=@face.jpg" \\
  -F "person_id=emp_001"`}
          </pre>
        </div>
      </div>
    </div>
  )
}
