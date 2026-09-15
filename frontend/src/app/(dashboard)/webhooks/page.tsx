'use client'

import { useEffect, useState } from 'react'
import { webhookAPI } from '@/lib/api'
import { Plus, Trash2, Play, Eye, EyeOff, RefreshCw, ExternalLink } from 'lucide-react'

const SUPPORTED_EVENTS = [
  'bulk-import.completed',
  'recognition.event',
  'billing.alert',
  'face.enrolled',
  'face.deleted',
  '*',
]

interface Webhook {
  id: string
  url: string
  events: string[]
  is_active: boolean
  created_at: string
}

interface Delivery {
  id: string
  event: string
  status: string
  status_code: number | null
  attempts: number
  max_attempts: number
  created_at: string
  delivered_at: string | null
}

export default function WebhooksPage() {
  const [webhooks, setWebhooks] = useState<Webhook[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [newUrl, setNewUrl] = useState('')
  const [newEvents, setNewEvents] = useState<string[]>(['*'])
  const [creating, setCreating] = useState(false)
  const [selectedWebhook, setSelectedWebhook] = useState<string | null>(null)
  const [deliveries, setDeliveries] = useState<Delivery[]>([])
  const [deliveriesLoading, setDeliveriesLoading] = useState(false)
  const [testResult, setTestResult] = useState<any>(null)

  const fetchWebhooks = async () => {
    try {
      const res = await webhookAPI.list()
      setWebhooks(res.data)
    } catch (err) {
      console.error('Failed to fetch webhooks:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchWebhooks()
  }, [])

  const handleCreate = async () => {
    if (!newUrl) return
    setCreating(true)
    try {
      await webhookAPI.create({ url: newUrl, events: newEvents })
      setShowCreate(false)
      setNewUrl('')
      setNewEvents(['*'])
      fetchWebhooks()
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to create webhook')
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this webhook?')) return
    try {
      await webhookAPI.delete(id)
      fetchWebhooks()
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to delete')
    }
  }

  const handleTest = async (id: string) => {
    setTestResult(null)
    try {
      const res = await webhookAPI.test(id)
      setTestResult(res.data)
    } catch (err: any) {
      setTestResult({ status: 'error', message: err.response?.data?.detail || 'Test failed' })
    }
  }

  const handleToggle = async (id: string, currentActive: boolean) => {
    try {
      await webhookAPI.update(id, { is_active: !currentActive })
      fetchWebhooks()
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to update')
    }
  }

  const loadDeliveries = async (id: string) => {
    setSelectedWebhook(id)
    setDeliveriesLoading(true)
    try {
      const res = await webhookAPI.getDeliveries(id)
      setDeliveries(res.data)
    } catch (err) {
      console.error('Failed to load deliveries:', err)
    } finally {
      setDeliveriesLoading(false)
    }
  }

  const toggleEvent = (event: string) => {
    setNewEvents((prev) =>
      prev.includes(event) ? prev.filter((e) => e !== event) : [...prev, event]
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Webhooks</h1>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          <Plus className="w-4 h-4" />
          Add Webhook
        </button>
      </div>

      {showCreate && (
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="text-lg font-semibold mb-4">Create Webhook</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Endpoint URL (HTTPS)</label>
              <input
                type="url"
                value={newUrl}
                onChange={(e) => setNewUrl(e.target.value)}
                placeholder="https://your-server.com/webhook"
                className="w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Events</label>
              <div className="flex flex-wrap gap-2">
                {SUPPORTED_EVENTS.map((event) => (
                  <button
                    key={event}
                    onClick={() => toggleEvent(event)}
                    className={`px-3 py-1 rounded-full text-sm font-medium ${
                      newEvents.includes(event)
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    }`}
                  >
                    {event}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleCreate}
                disabled={creating || !newUrl}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {creating ? 'Creating...' : 'Create Webhook'}
              </button>
              <button
                onClick={() => setShowCreate(false)}
                className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {testResult && (
        <div className={`rounded-lg p-4 mb-6 ${testResult.status === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
          <p className="font-medium">{testResult.message}</p>
          <button onClick={() => setTestResult(null)} className="text-sm underline mt-1">Dismiss</button>
        </div>
      )}

      <div className="bg-white rounded-lg shadow">
        {loading ? (
          <div className="p-6 text-center text-gray-500">Loading webhooks...</div>
        ) : webhooks.length === 0 ? (
          <div className="p-6 text-center text-gray-500">
            No webhooks configured. Create one to get started.
          </div>
        ) : (
          <div className="divide-y">
            {webhooks.map((wh) => (
              <div key={wh.id} className="p-4">
                <div className="flex items-center justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${wh.is_active ? 'bg-green-500' : 'bg-gray-400'}`} />
                      <span className="font-medium text-sm truncate">{wh.url}</span>
                    </div>
                    <div className="flex gap-1 mt-1 flex-wrap">
                      {wh.events.map((e) => (
                        <span key={e} className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs">
                          {e}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 ml-4">
                    <button
                      onClick={() => handleToggle(wh.id, wh.is_active)}
                      className={`p-2 rounded-lg ${wh.is_active ? 'text-green-600 hover:bg-green-50' : 'text-gray-400 hover:bg-gray-50'}`}
                      title={wh.is_active ? 'Disable' : 'Enable'}
                    >
                      {wh.is_active ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                    </button>
                    <button
                      onClick={() => handleTest(wh.id)}
                      className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg"
                      title="Send test event"
                    >
                      <Play className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => loadDeliveries(wh.id)}
                      className="p-2 text-gray-600 hover:bg-gray-50 rounded-lg"
                      title="View deliveries"
                    >
                      <ExternalLink className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(wh.id)}
                      className="p-2 text-red-600 hover:bg-red-50 rounded-lg"
                      title="Delete"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {selectedWebhook === wh.id && (
                  <div className="mt-3 pt-3 border-t">
                    <h4 className="text-sm font-medium text-gray-700 mb-2">Recent Deliveries</h4>
                    {deliveriesLoading ? (
                      <p className="text-sm text-gray-500">Loading...</p>
                    ) : deliveries.length === 0 ? (
                      <p className="text-sm text-gray-500">No deliveries yet</p>
                    ) : (
                      <div className="space-y-1">
                        {deliveries.slice(0, 5).map((d) => (
                          <div key={d.id} className="flex items-center gap-3 text-xs">
                            <span className={`px-2 py-0.5 rounded-full font-medium ${
                              d.status === 'success' ? 'bg-green-100 text-green-700' :
                              d.status === 'failed' ? 'bg-red-100 text-red-700' :
                              'bg-yellow-100 text-yellow-700'
                            }`}>
                              {d.status}
                            </span>
                            <span className="text-gray-500">{d.event}</span>
                            <span className="text-gray-400">{d.status_code || '-'}</span>
                            <span className="text-gray-400">{d.attempts}/{d.max_attempts} attempts</span>
                            <span className="text-gray-400 ml-auto">
                              {new Date(d.created_at).toLocaleString()}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
