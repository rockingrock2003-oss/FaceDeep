'use client'

import { useAuth } from '@/hooks/useAuth'

export default function SettingsPage() {
  const { user } = useAuth()

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-8">Settings</h1>

      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-xl font-semibold mb-4">Account Information</h2>
        
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">Username</label>
            <p className="mt-1 p-3 bg-gray-50 rounded-lg">{user?.username}</p>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700">Email</label>
            <p className="mt-1 p-3 bg-gray-50 rounded-lg">{user?.email}</p>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700">Plan</label>
            <p className="mt-1 p-3 bg-gray-50 rounded-lg capitalize">{user?.plan}</p>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700">Total API Calls</label>
            <p className="mt-1 p-3 bg-gray-50 rounded-lg">{user?.number_of_api_use_for_service}</p>
          </div>
        </div>
      </div>
    </div>
  )
}
