'use client'

import { useEffect, useState } from 'react'
import { slaAPI } from '@/lib/api'
import { CheckCircle, AlertTriangle, Clock, RefreshCw } from 'lucide-react'

interface StatusData {
  status: string
  service: string
  current_version: string
  supported_versions: string[]
  uptime_seconds: number
  incident_history: any[]
  last_updated: string
}

export default function StatusPage() {
  const [status, setStatus] = useState<StatusData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const fetchStatus = async () => {
    setLoading(true)
    setError(false)
    try {
      const res = await slaAPI.getStatus()
      setStatus(res.data)
    } catch (err) {
      setError(true)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStatus()
    const interval = setInterval(fetchStatus, 30000)
    return () => clearInterval(interval)
  }, [])

  const isOperational = status?.status === 'operational'
  const uptimeHours = Math.floor((status?.uptime_seconds || 0) / 3600)
  const uptimeMinutes = Math.floor(((status?.uptime_seconds || 0) % 3600) / 60)

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-3xl font-bold text-gray-900 mb-8 text-center">System Status</h1>

      <div className={`rounded-lg p-8 mb-6 text-center ${isOperational ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
        {loading ? (
          <div className="flex items-center justify-center gap-2 text-gray-500">
            <RefreshCw className="w-5 h-5 animate-spin" />
            Checking status...
          </div>
        ) : error ? (
          <div className="flex items-center justify-center gap-2 text-red-600">
            <AlertTriangle className="w-5 h-5" />
            Unable to reach status endpoint
          </div>
        ) : isOperational ? (
          <>
            <CheckCircle className="w-12 h-12 text-green-500 mx-auto mb-3" />
            <h2 className="text-2xl font-bold text-green-800">All Systems Operational</h2>
            <p className="text-green-600 mt-2">All services are running normally</p>
          </>
        ) : (
          <>
            <AlertTriangle className="w-12 h-12 text-red-500 mx-auto mb-3" />
            <h2 className="text-2xl font-bold text-red-800">System Degraded</h2>
            <p className="text-red-600 mt-2">Some services may be experiencing issues</p>
          </>
        )}
      </div>

      {status && (
        <div className="space-y-4">
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="font-semibold mb-4">Service Information</h3>
            <div className="space-y-3">
              <div className="flex justify-between p-3 bg-gray-50 rounded-lg">
                <span className="text-gray-600">Service</span>
                <span className="font-medium">{status.service}</span>
              </div>
              <div className="flex justify-between p-3 bg-gray-50 rounded-lg">
                <span className="text-gray-600">API Version</span>
                <span className="font-medium">{status.current_version}</span>
              </div>
              <div className="flex justify-between p-3 bg-gray-50 rounded-lg">
                <span className="text-gray-600">Supported Versions</span>
                <span className="font-medium">{status.supported_versions?.join(', ')}</span>
              </div>
              <div className="flex justify-between p-3 bg-gray-50 rounded-lg">
                <span className="text-gray-600">Uptime</span>
                <span className="font-medium flex items-center gap-1">
                  <Clock className="w-4 h-4" />
                  {uptimeHours}h {uptimeMinutes}m
                </span>
              </div>
              <div className="flex justify-between p-3 bg-gray-50 rounded-lg">
                <span className="text-gray-600">Last Updated</span>
                <span className="font-medium">
                  {status.last_updated ? new Date(status.last_updated).toLocaleString() : '-'}
                </span>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="font-semibold mb-4">Incident History</h3>
            {status.incident_history?.length === 0 ? (
              <div className="text-center py-6 text-gray-500">
                <CheckCircle className="w-8 h-8 mx-auto mb-2 text-green-400" />
                No incidents recorded
              </div>
            ) : (
              <div className="space-y-2">
                {status.incident_history?.map((incident: any, i: number) => (
                  <div key={i} className="p-3 bg-gray-50 rounded-lg">
                    <div className="font-medium text-sm">{incident.title}</div>
                    <div className="text-xs text-gray-500">{incident.date}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
