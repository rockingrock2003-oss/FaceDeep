'use client'

import { useState, useEffect } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { authAPI, organizationAPI } from '@/lib/api'
import { KeyRound, Shield, RefreshCw } from 'lucide-react'

interface AuditEntry {
  id: string
  action: string
  resource_type: string
  resource_id: string | null
  details: string | null
  ip_address: string | null
  created_at: string
}

export default function SettingsPage() {
  const { user } = useAuth()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [auditLog, setAuditLog] = useState<AuditEntry[]>([])
  const [auditLoading, setAuditLoading] = useState(false)

  useEffect(() => {
    fetchAuditLog()
  }, [])

  const fetchAuditLog = async () => {
    setAuditLoading(true)
    try {
      const res = await organizationAPI.list()
      const orgs = res.data.organizations || []
      if (orgs.length > 0) {
        const logRes = await organizationAPI.getAuditLog(orgs[0].id, 20)
        setAuditLog(logRes.data.logs || [])
      }
    } catch {
      // No orgs or no audit log
    } finally {
      setAuditLoading(false)
    }
  }

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    setMessage('')
    setError('')

    if (newPassword !== confirmPassword) {
      setError('New passwords do not match')
      return
    }

    if (newPassword.length < 6) {
      setError('New password must be at least 6 characters')
      return
    }

    setLoading(true)
    try {
      const response = await authAPI.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      })
      setMessage(response.data.message)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to change password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-8">Settings</h1>

      <div className="bg-white rounded-lg shadow p-6 mb-6">
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
            <label className="block text-sm font-medium text-gray-700">Total API Requests</label>
            <p className="mt-1 p-3 bg-gray-50 rounded-lg">{user?.number_of_api_use_for_service}</p>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <KeyRound className="w-5 h-5" />
          Change Password
        </h2>

        {message && (
          <div className="mb-4 p-3 bg-green-50 text-green-700 rounded-lg text-sm">{message}</div>
        )}
        {error && (
          <div className="mb-4 p-3 bg-red-50 text-red-700 rounded-lg text-sm">{error}</div>
        )}

        <form onSubmit={handleChangePassword} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">Current Password</label>
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
              className="mt-1 w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">New Password</label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              minLength={6}
              className="mt-1 w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Confirm New Password</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              minLength={6}
              className="mt-1 w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? 'Changing...' : 'Change Password'}
          </button>
        </form>
      </div>

      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <Shield className="w-5 h-5" />
            Audit Log
          </h2>
          <button
            onClick={fetchAuditLog}
            disabled={auditLoading}
            className="flex items-center gap-1 px-3 py-1 bg-gray-200 text-gray-700 rounded-lg text-sm hover:bg-gray-300"
          >
            <RefreshCw className={`w-3 h-3 ${auditLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>

        {auditLoading ? (
          <p className="text-sm text-gray-500">Loading audit log...</p>
        ) : auditLog.length === 0 ? (
          <p className="text-sm text-gray-500">No audit entries yet. Create an organization to start tracking.</p>
        ) : (
          <div className="space-y-2">
            {auditLog.map((entry) => (
              <div key={entry.id} className="flex items-center gap-3 text-sm p-3 bg-gray-50 rounded-lg">
                <span className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs font-medium min-w-[100px] text-center">
                  {entry.action}
                </span>
                <span className="text-gray-500">{entry.resource_type}</span>
                {entry.details && <span className="text-gray-400 truncate flex-1">{entry.details}</span>}
                {entry.ip_address && <span className="text-gray-400 text-xs">{entry.ip_address}</span>}
                <span className="text-gray-400 text-xs ml-auto whitespace-nowrap">
                  {new Date(entry.created_at).toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
