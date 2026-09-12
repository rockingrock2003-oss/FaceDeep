'use client'

import { useEffect, useState } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { billingAPI, faceAPI } from '@/lib/api'
import { Users, Activity, Database, TrendingUp } from 'lucide-react'

export default function DashboardPage() {
  const { user } = useAuth()
  const [usage, setUsage] = useState<any>(null)
  const [persons, setPersons] = useState<any[]>([])

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    try {
      const [usageRes, personsRes] = await Promise.all([
        billingAPI.getUsage(),
        faceAPI.listPersons(),
      ])
      setUsage(usageRes.data)
      setPersons(personsRes.data.persons || [])
    } catch (error) {
      console.error('Failed to fetch data:', error)
    }
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
      name: 'API Calls',
      value: user?.number_of_api_use_for_service || 0,
      icon: Activity,
      color: 'bg-yellow-500',
    },
    {
      name: 'Current Plan',
      value: user?.plan || 'free',
      icon: TrendingUp,
      color: 'bg-purple-500',
    },
  ]

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-8">Dashboard</h1>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {stats.map((stat) => (
          <div
            key={stat.name}
            className="bg-white rounded-lg shadow p-6"
          >
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
            <a
              href="/faces"
              className="block p-3 bg-blue-50 text-blue-700 rounded-lg hover:bg-blue-100 transition-colors"
            >
              Enroll New Face →
            </a>
            <a
              href="/bulk-import"
              className="block p-3 bg-green-50 text-green-700 rounded-lg hover:bg-green-100 transition-colors"
            >
              Bulk Import Faces →
            </a>
            <a
              href="/api-keys"
              className="block p-3 bg-yellow-50 text-yellow-700 rounded-lg hover:bg-yellow-100 transition-colors"
            >
              Manage API Keys →
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}
