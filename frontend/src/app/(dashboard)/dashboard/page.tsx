'use client'

import { useEffect, useState } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { billingAPI, faceAPI, slaAPI } from '@/lib/api'
import { Users, Activity, Database, TrendingUp, Zap, DollarSign, Clock } from 'lucide-react'

export default function DashboardPage() {
  const { user } = useAuth()
  const [usage, setUsage] = useState<any>(null)
  const [realtime, setRealtime] = useState<any>(null)
  const [persons, setPersons] = useState<any[]>([])
  const [status, setStatus] = useState<any>(null)

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchRealtime, 10000)
    return () => clearInterval(interval)
  }, [])

  const fetchData = async () => {
    try {
      const [usageRes, personsRes, statusRes] = await Promise.all([
        billingAPI.getUsage(),
        faceAPI.listPersons(),
        slaAPI.getStatus().catch(() => null),
      ])
      setUsage(usageRes.data)
      setPersons(personsRes.data.persons || [])
      if (statusRes) setStatus(statusRes.data)
    } catch (error) {
      console.error('Failed to fetch data:', error)
    }
  }

  const fetchRealtime = async () => {
    try {
      const res = await billingAPI.getRealtimeUsage()
      setRealtime(res.data)
    } catch { /* keep stale */ }
  }

  const stats = [
    {
      name: 'Total Faces',
      value: user?.entry_in_chroma_db || 0,
      icon: Database,
      color: 'bg-blue-500',
    },
    {
      name: 'Total Persons',
      value: persons.length,
      icon: Users,
      color: 'bg-green-500',
    },
    {
      name: 'Requests Today',
      value: realtime?.requests_today ?? usage?.daily_used ?? 0,
      icon: Activity,
      color: 'bg-yellow-500',
    },
    {
      name: 'Current Plan',
      value: (user?.plan || 'free').charAt(0).toUpperCase() + (user?.plan || 'free').slice(1),
      icon: TrendingUp,
      color: 'bg-purple-500',
    },
  ]

  const realtimeStats = realtime ? [
    { label: 'Requests/min', value: realtime.requests_this_minute, icon: Zap, color: 'text-blue-600' },
    { label: 'Cost/month', value: `$${realtime.cost_this_month.toFixed(4)}`, icon: DollarSign, color: 'text-green-600' },
    { label: 'Daily Used', value: realtime.requests_today, icon: Activity, color: 'text-yellow-600' },
  ] : []

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
        {status && (
          <div className="flex items-center gap-2 text-sm">
            <span className={`w-2 h-2 rounded-full ${status.status === 'operational' ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-gray-500">v{status.current_version} &middot; {status.status}</span>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {stats.map((stat) => (
          <div key={stat.name} className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center">
              <div className={`p-3 rounded-full ${stat.color}`}>
                <stat.icon className="w-6 h-6 text-white" />
              </div>
              <div className="ml-4">
                <p className="text-sm text-gray-500">{stat.name}</p>
                <p className="text-2xl font-semibold text-gray-900">{stat.value}</p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {realtime && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          {realtimeStats.map((rs) => (
            <div key={rs.label} className="bg-white rounded-lg shadow p-4">
              <div className="flex items-center gap-3">
                <rs.icon className={`w-5 h-5 ${rs.color}`} />
                <div>
                  <p className="text-xs text-gray-500">{rs.label}</p>
                  <p className="text-lg font-bold">{rs.value}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Recent Persons</h2>
          {persons.length === 0 ? (
            <p className="text-gray-500">No persons enrolled yet</p>
          ) : (
            <div className="space-y-3">
              {persons.slice(0, 5).map((person) => (
                <div
                  key={person.person_id}
                  className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
                >
                  <span className="font-medium">{person.person_id}</span>
                  <span className="text-sm text-gray-500">
                    {person.face_count} face(s)
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Quick Actions</h2>
          <div className="space-y-3">
            <a href="/faces" className="block p-3 bg-blue-50 text-blue-700 rounded-lg hover:bg-blue-100 transition-colors">
              Enroll New Face →
            </a>
            <a href="/bulk-import" className="block p-3 bg-green-50 text-green-700 rounded-lg hover:bg-green-100 transition-colors">
              Bulk Import Faces →
            </a>
            <a href="/webhooks" className="block p-3 bg-purple-50 text-purple-700 rounded-lg hover:bg-purple-100 transition-colors">
              Manage Webhooks →
            </a>
            <a href="/api-docs" className="block p-3 bg-gray-50 text-gray-700 rounded-lg hover:bg-gray-100 transition-colors">
              View API Documentation →
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}
