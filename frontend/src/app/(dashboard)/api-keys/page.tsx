'use client'

import { authAPI, billingAPI } from '@/lib/api'
import { Copy, Eye, EyeOff, RefreshCw } from 'lucide-react'
import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  AreaChart,
  Area,
  ReferenceLine,
  Brush,
} from 'recharts'

interface Request {
  endpoint: string
  response_time_ms: number
  created_at: string
}

interface AggEntry {
  date: string
  Recognize_avg?: number | null
  Add_avg?: number | null
  Delete_avg?: number | null
  IsMatch_avg?: number | null
  Recognize_count?: number
  Add_count?: number
  Delete_count?: number
  IsMatch_count?: number
  overall_avg?: number
  total_count?: number
  cost?: number
  [key: string]: string | number | null | undefined
}

interface Summary {
  today: Record<string, number>
  this_month: Record<string, number>
  this_year: Record<string, number>
}

interface BillingInfo {
  plan: string
  daily_limit: number
  daily_used: number
  daily_remaining: number | string
  plan_price: number
  plan_expires_at: string | null
  total_requests: number
  total_cost: number
}

interface ApiStats {
  requests: Request[]
  daily_avg: AggEntry[]
  monthly: AggEntry[]
  yearly: AggEntry[]
  summary: Summary
  billing: BillingInfo
}

const COLORS: Record<string, string> = {
  Recognize: '#3b82f6',
  Add: '#22c55e',
  Delete: '#ef4444',
  IsMatch: '#f59e0b',
}
const OVERALL_COLOR = '#6b7280'
const COST_COLOR = '#8b5cf6'
const ENDPOINTS = Object.keys(COLORS)

const REFRESH_INTERVAL = 10000
const noAnimProps = { isAnimationActive: false }

function CrosshairTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-gray-900 text-white rounded-lg shadow-xl p-3 text-xs border border-gray-700 min-w-[160px]">
      <p className="font-semibold mb-1.5 border-b border-gray-700 pb-1">{label}</p>
      {payload
        .filter((p: any) => p.value != null)
        .map((p: any) => (
          <div key={p.dataKey} className="flex justify-between gap-4 py-0.5">
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }} />
              {p.name || p.dataKey}
            </span>
            <span className="font-mono font-bold">{p.value}ms</span>
          </div>
        ))}
    </div>
  )
}

function CostTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-gray-900 text-white rounded-lg shadow-xl p-3 text-xs border border-gray-700">
      <p className="font-semibold mb-1">{label}</p>
      <p className="font-mono font-bold text-purple-400">${payload[0]?.value?.toFixed(4) ?? '0'}</p>
    </div>
  )
}

function BarTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-gray-900 text-white rounded-lg shadow-xl p-3 text-xs border border-gray-700 min-w-[120px]">
      <p className="font-semibold mb-1">{label}</p>
      {payload
        .filter((p: any) => p.value != null && p.value > 0)
        .map((p: any) => (
          <div key={p.dataKey} className="flex justify-between gap-4 py-0.5">
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }} />
              {p.name}
            </span>
            <span className="font-mono font-bold">{p.value}ms</span>
          </div>
        ))}
    </div>
  )
}

export default function ApiKeysPage() {
  const [apiKey, setApiKey] = useState<string | null>(null)
  const [showKey, setShowKey] = useState(false)
  const [copied, setCopied] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [error, setError] = useState('')
  const [stats, setStats] = useState<ApiStats | null>(null)
  const [statsLoading, setStatsLoading] = useState(true)
  const [graphView, setGraphView] = useState<'daily' | 'monthly' | 'yearly'>('daily')
  const [avgView, setAvgView] = useState<'daily' | 'monthly' | 'yearly'>('daily')
  const [costView, setCostView] = useState<'daily' | 'monthly' | 'yearly'>('daily')
  const [summaryRange, setSummaryRange] = useState<'today' | 'this_month' | 'this_year'>('today')
  const [realtime, setRealtime] = useState<any>(null)

  const fetchApiKey = useCallback(async () => {
    try {
      const res = await authAPI.getApiKey()
      setApiKey(res.data.api_key_prefix)
    } catch {
      setApiKey(null)
    }
  }, [])

  const fetchStats = useCallback(async () => {
    try {
      const res = await authAPI.getApiStats()
      setStats(res.data)
    } catch { /* keep stale */ }
    finally { setStatsLoading(false) }
  }, [])

  const fetchRealtime = useCallback(async () => {
    try {
      const res = await billingAPI.getRealtimeUsage()
      setRealtime(res.data)
    } catch { /* keep stale */ }
  }, [])

  useEffect(() => {
    fetchApiKey()
    fetchStats()
    fetchRealtime()
    const id = setInterval(() => {
      fetchStats()
      fetchRealtime()
    }, REFRESH_INTERVAL)
    return () => clearInterval(id)
  }, [fetchApiKey, fetchStats, fetchRealtime])

  const handleRegenerate = async () => {
    if (!confirm('Generate a new API key? The old key will stop working immediately.')) return
    setRegenerating(true)
    setError('')
    try {
      const res = await authAPI.regenerateApiKey()
      setApiKey(res.data.api_key)
      setShowKey(true)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to generate key')
    } finally { setRegenerating(false) }
  }

  const copyToClipboard = () => {
    if (apiKey) { navigator.clipboard.writeText(apiKey); setCopied(true); setTimeout(() => setCopied(false), 2000) }
  }

  const hourlyData = useMemo(() => {
    if (!stats?.requests?.length) return []
    const buckets: Record<string, { sums: Record<string, number>; counts: Record<string, number> }> = {}
    for (const r of stats.requests) {
      const d = new Date(r.created_at)
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:00`
      if (!buckets[key]) buckets[key] = { sums: {}, counts: {} }
      const ep = r.endpoint
      buckets[key].sums[ep] = (buckets[key].sums[ep] || 0) + r.response_time_ms
      buckets[key].counts[ep] = (buckets[key].counts[ep] || 0) + 1
    }
    return Object.entries(buckets)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([time, { sums, counts }]) => {
        const row: any = { date: time }
        let totalSum = 0, totalCount = 0
        for (const ep of ENDPOINTS) {
          if (counts[ep]) {
            row[`${ep}_avg`] = Math.round(sums[ep] / counts[ep])
            totalSum += sums[ep]
            totalCount += counts[ep]
          } else {
            row[`${ep}_avg`] = null
          }
        }
        row.overall_avg = totalCount > 0 ? Math.round(totalSum / totalCount) : 0
        row.total_count = totalCount
        return row
      })
  }, [stats])

  const graphData = useMemo(() => {
    if (!stats) return []
    if (graphView === 'daily') return hourlyData
    if (graphView === 'monthly') return stats.monthly
    return stats.yearly
  }, [stats, graphView, hourlyData])

  const avgChartData = useMemo(() => {
    if (!stats) return []
    if (avgView === 'daily') return hourlyData
    if (avgView === 'monthly') return stats.monthly
    return stats.yearly
  }, [stats, avgView, hourlyData])

  const overallAvg = useMemo(() => {
    const data = avgChartData
    if (!data.length) return { Recognize: 0, Add: 0, Delete: 0, IsMatch: 0, overall: 0 }
    const sums: Record<string, { total: number; count: number }> = {}
    for (const ep of ENDPOINTS) sums[ep] = { total: 0, count: 0 }
    let allTotal = 0, allCount = 0
    for (const row of data) {
      for (const ep of ENDPOINTS) {
        const val = Number(row[`${ep}_avg`])
        if (val > 0) { sums[ep].total += val; sums[ep].count += 1 }
      }
      const oa = Number(row.overall_avg)
      const tc = Number(row.total_count)
      if (oa > 0 && tc > 0) { allTotal += oa * tc; allCount += tc }
    }
    const result: Record<string, number> = {}
    for (const [ep, { total, count }] of Object.entries(sums)) {
      result[ep] = count > 0 ? Math.round(total / count) : 0
    }
    result.overall = allCount > 0 ? Math.round(allTotal / allCount) : 0
    return result
  }, [avgChartData])

  const costData = useMemo(() => {
    if (!stats) return []
    if (costView === 'daily') return hourlyData
    if (costView === 'monthly') return stats.monthly
    return stats.yearly
  }, [stats, costView, hourlyData])

  const summaryData = useMemo(() => {
    if (!stats?.summary) return []
    const data = stats.summary[summaryRange]
    return Object.entries(data).filter(([k]) => k !== 'overall').map(([endpoint, avg]) => ({ endpoint, avg: avg as number }))
  }, [stats, summaryRange])

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-8">API Keys</h1>

      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Your API Key</h2>
        <p className="text-gray-600 mb-4">
          Use this key for external API access. Include it in the{' '}
          <code className="bg-gray-100 px-1 rounded">X-API-Key</code> header.
        </p>
        {error && <div className="bg-red-50 text-red-600 p-3 rounded-md text-sm mb-4">{error}</div>}

      {realtime && (
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="bg-blue-50 rounded-lg p-3 text-center">
            <div className="text-xs text-gray-500">Requests/min</div>
            <div className="text-xl font-bold text-blue-600">{realtime.requests_this_minute}</div>
          </div>
          <div className="bg-green-50 rounded-lg p-3 text-center">
            <div className="text-xs text-gray-500">Requests today</div>
            <div className="text-xl font-bold text-green-600">{realtime.requests_today}</div>
          </div>
          <div className="bg-purple-50 rounded-lg p-3 text-center">
            <div className="text-xs text-gray-500">Cost this month</div>
            <div className="text-xl font-bold text-purple-600">${realtime.cost_this_month.toFixed(4)}</div>
          </div>
        </div>
      )}
        <div className="flex items-center gap-2 p-4 bg-gray-50 rounded-lg">
          <code className="flex-1 font-mono text-sm break-all">
            {showKey ? (apiKey || 'No key generated') : '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022'}
          </code>
          <button onClick={() => setShowKey(!showKey)} className="p-2 hover:bg-gray-200 rounded-lg">
            {showKey ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
          </button>
          {showKey && (
            <button onClick={copyToClipboard} className="p-2 hover:bg-gray-200 rounded-lg">
              <Copy className="w-5 h-5" />
            </button>
          )}
        </div>
        {copied && <p className="text-green-600 text-sm mt-2">Copied to clipboard!</p>}
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
{`curl -X POST https://facedeep.me/api/v2/face/recognize \\
  -H "X-API-Key: YOUR_API_KEY" \\
  -F "file=@face.jpg"`}
          </pre>
        </div>
      </div>

      {statsLoading ? (
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center gap-2 text-gray-500">
            <RefreshCw className="w-4 h-4 animate-spin" />
            Loading stats...
          </div>
        </div>
      ) : !stats ? (
        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-gray-500 text-center">No data yet.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {stats.billing && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-white rounded-lg shadow p-4">
                <div className="text-sm text-gray-500">Plan</div>
                <div className="text-2xl font-bold text-gray-900 capitalize">{stats.billing.plan}</div>
                <div className="text-xs text-gray-400">${stats.billing.plan_price}/mo</div>
              </div>
              <div className="bg-white rounded-lg shadow p-4">
                <div className="text-sm text-gray-500">Daily Limit</div>
                <div className="text-2xl font-bold text-gray-900">
                  {stats.billing.daily_remaining === 'unlimited' ? '\u221e' : stats.billing.daily_remaining}
                </div>
                <div className="text-xs text-gray-400">{stats.billing.daily_used} used today</div>
              </div>
              <div className="bg-white rounded-lg shadow p-4">
                <div className="text-sm text-gray-500">Total Requests</div>
                <div className="text-2xl font-bold text-gray-900">{stats.billing.total_requests.toLocaleString()}</div>
              </div>
              <div className="bg-white rounded-lg shadow p-4">
                <div className="text-sm text-gray-500">Total Cost</div>
                <div className="text-2xl font-bold text-gray-900">${stats.billing.total_cost.toFixed(2)}</div>
              </div>
            </div>
          )}

          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold">API Response Time</h3>
              <div className="flex bg-gray-100 rounded-lg p-1">
                {(['daily', 'monthly', 'yearly'] as const).map((v) => (
                  <button key={v} onClick={() => setGraphView(v)}
                    className={`px-3 py-1 rounded-md text-sm font-medium ${graphView === v ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-200'}`}>
                    {v === 'daily' ? 'Hourly' : v.charAt(0).toUpperCase() + v.slice(1)}
                  </button>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {ENDPOINTS.map((ep) => {
                const epAvg = overallAvg[ep]
                let lineData: any[]
                if (graphView === 'daily') {
                  lineData = (stats.requests || [])
                    .filter((r) => r.endpoint === ep)
                    .map((r) => {
                      const d = new Date(r.created_at)
                      return {
                        time: d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true }),
                        [ep]: r.response_time_ms,
                      }
                    })
                } else {
                  lineData = graphData.map((row: any) => ({
                    time: row.date,
                    [ep]: row[`${ep}_avg`] ?? null,
                  }))
                }
                const brushLen = Math.min(lineData.length, 15)
                return (
                  <div key={ep} className="border rounded-lg p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="w-3 h-3 rounded-full" style={{ backgroundColor: COLORS[ep] }} />
                        <span className="font-medium text-sm">{ep}</span>
                      </div>
                      <span className="text-xs font-bold px-2 py-0.5 rounded" style={{ backgroundColor: COLORS[ep] + '20', color: COLORS[ep] }}>
                        avg {epAvg}ms
                      </span>
                    </div>
                    <ResponsiveContainer width="100%" height={220}>
                      <LineChart data={lineData} margin={{ top: 5, right: 10, bottom: 0, left: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                        <XAxis dataKey="time" tick={false} label={{ value: 'Time', position: 'insideBottomRight', offset: -5, fontSize: 10, fill: '#9ca3af' }} />
                        <YAxis tick={{ fontSize: 10 }} unit="ms" width={45} />
                        <Tooltip
                          content={({ active, payload }: any) => {
                            if (!active || !payload?.length) return null
                            const d = payload[0]?.payload
                            return (
                              <div className="bg-gray-900 text-white rounded-lg shadow-xl p-3 text-xs border border-gray-700">
                                <p className="font-semibold mb-1">{d?.time}</p>
                                <p className="font-mono font-bold" style={{ color: COLORS[ep] }}>{d?.[ep]}ms</p>
                              </div>
                            )
                          }}
                        />
                        <ReferenceLine y={epAvg} stroke={COLORS[ep]} strokeDasharray="4 4" strokeOpacity={0.4} />
                        <ReferenceLine y={overallAvg.overall} stroke={OVERALL_COLOR} strokeDasharray="2 2" strokeOpacity={0.3} />
                        <Line type="monotone" dataKey={ep} stroke={COLORS[ep]} strokeWidth={2} dot={false} connectNulls {...noAnimProps} />
                        <Brush
                          dataKey="time"
                          height={20}
                          stroke={COLORS[ep]}
                          fill="#f9fafb"
                          travellerWidth={8}
                          startIndex={Math.max(0, lineData.length - brushLen)}
                          endIndex={lineData.length - 1}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold">Avg Response Time per API</h3>
              <div className="flex bg-gray-100 rounded-lg p-1">
                {(['daily', 'monthly', 'yearly'] as const).map((v) => (
                  <button key={v} onClick={() => setAvgView(v)}
                    className={`px-3 py-1 rounded-md text-sm font-medium ${avgView === v ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-200'}`}>
                    {v === 'daily' ? 'Hourly' : v.charAt(0).toUpperCase() + v.slice(1)}
                  </button>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-4">
              {ENDPOINTS.map((ep) => (
                <div key={ep} className="text-center p-3 bg-gray-50 rounded-lg">
                  <div className="text-xs text-gray-500">{ep}</div>
                  <div className="text-lg font-bold" style={{ color: COLORS[ep] }}>{overallAvg[ep]}ms</div>
                  <div className="text-xs text-gray-400">avg</div>
                </div>
              ))}
              <div className="text-center p-3 bg-gray-50 rounded-lg border-2 border-gray-300">
                <div className="text-xs text-gray-500">Overall</div>
                <div className="text-lg font-bold" style={{ color: OVERALL_COLOR }}>{overallAvg.overall}ms</div>
                <div className="text-xs text-gray-400">avg</div>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={avgChartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} interval={avgView === 'daily' ? Math.max(0, Math.floor(avgChartData.length / 12)) : 'preserveStartEnd'} />
                <YAxis tick={{ fontSize: 12 }} unit="ms" />
                <Tooltip content={<BarTooltip />} />
                {ENDPOINTS.map((ep) => (
                  <Bar key={ep} dataKey={`${ep}_avg`} name={ep} fill={COLORS[ep]} fillOpacity={0.8} {...noAnimProps} />
                ))}
                <Bar dataKey="overall_avg" name="Overall" fill={OVERALL_COLOR} fillOpacity={0.5} {...noAnimProps} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold">API Cost</h3>
              <div className="flex bg-gray-100 rounded-lg p-1">
                {(['daily', 'monthly', 'yearly'] as const).map((v) => (
                  <button key={v} onClick={() => setCostView(v)}
                    className={`px-3 py-1 rounded-md text-sm font-medium ${costView === v ? 'bg-purple-600 text-white' : 'text-gray-600 hover:bg-gray-200'}`}>
                    {v === 'daily' ? 'Hourly' : v.charAt(0).toUpperCase() + v.slice(1)}
                  </button>
                ))}
              </div>
            </div>
            <ResponsiveContainer width="100%" height={250}>
              <AreaChart data={costData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} interval={costView === 'daily' ? Math.max(0, Math.floor(costData.length / 12)) : 'preserveStartEnd'} />
                <YAxis tick={{ fontSize: 12 }} unit="$" />
                <Tooltip content={<CostTooltip />} />
                <Area type="monotone" dataKey="cost" stroke={COST_COLOR} fill={COST_COLOR} fillOpacity={0.2} strokeWidth={2} {...noAnimProps} />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="font-semibold mb-4">Plan & Credits</h3>
            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <span className="text-gray-600">Current Plan</span>
                <span className="font-semibold capitalize">{stats.billing.plan}</span>
              </div>
              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <span className="text-gray-600">Monthly Price</span>
                <span className="font-semibold">${stats.billing.plan_price}</span>
              </div>
              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <span className="text-gray-600">Daily Request Limit</span>
                <span className="font-semibold">
                  {stats.billing.daily_limit === -1 ? 'Unlimited' : stats.billing.daily_limit.toLocaleString()}
                </span>
              </div>
              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <span className="text-gray-600">Used Today</span>
                <span className="font-semibold">{stats.billing.daily_used.toLocaleString()}</span>
              </div>
              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <span className="text-gray-600">Remaining Today</span>
                <span className="font-semibold">
                  {stats.billing.daily_remaining === 'unlimited' ? 'Unlimited' : stats.billing.daily_remaining.toLocaleString()}
                </span>
              </div>
              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <span className="text-gray-600">Plan Expires</span>
                <span className="font-semibold">
                  {stats.billing.plan_expires_at ? new Date(stats.billing.plan_expires_at).toLocaleDateString() : 'Never (Free plan)'}
                </span>
              </div>
              {stats.billing.daily_limit !== -1 && (
                <div className="mt-3">
                  <div className="flex justify-between text-xs text-gray-500 mb-1">
                    <span>Used</span>
                    <span>{stats.billing.daily_used} / {stats.billing.daily_limit}</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-3">
                    <div
                      className={`h-3 rounded-full transition-all ${
                        stats.billing.daily_used / stats.billing.daily_limit > 0.8 ? 'bg-red-500'
                        : stats.billing.daily_used / stats.billing.daily_limit > 0.5 ? 'bg-amber-500'
                          : 'bg-green-500'
                      }`}
                      style={{ width: `${Math.min(100, (stats.billing.daily_used / stats.billing.daily_limit) * 100)}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
