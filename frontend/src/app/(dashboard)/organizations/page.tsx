'use client'

import { useEffect, useState } from 'react'
import { organizationAPI } from '@/lib/api'
import { Plus, Users, Key, Shield, Trash2 } from 'lucide-react'

interface Organization {
  id: string
  name: string
  slug: string
  owner_id: string
  plan: string
  created_at: string
}

interface AuditLogEntry {
  id: string
  action: string
  resource_type: string
  resource_id: string | null
  details: string | null
  ip_address: string | null
  created_at: string
}

const ROLES = ['admin', 'editor', 'viewer']

export default function OrganizationsPage() {
  const [orgs, setOrgs] = useState<Organization[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newSlug, setNewSlug] = useState('')
  const [creating, setCreating] = useState(false)
  const [selectedOrg, setSelectedOrg] = useState<string | null>(null)
  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([])
  const [auditLoading, setAuditLoading] = useState(false)
  const [showAddMember, setShowAddMember] = useState(false)
  const [memberUserId, setMemberUserId] = useState('')
  const [memberRole, setMemberRole] = useState('viewer')

  const fetchOrgs = async () => {
    try {
      const res = await organizationAPI.list()
      setOrgs(res.data.organizations || [])
    } catch (err) {
      console.error('Failed to fetch organizations:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchOrgs()
  }, [])

  const handleCreate = async () => {
    if (!newName || !newSlug) return
    setCreating(true)
    try {
      await organizationAPI.create({ name: newName, slug: newSlug })
      setShowCreate(false)
      setNewName('')
      setNewSlug('')
      fetchOrgs()
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to create organization')
    } finally {
      setCreating(false)
    }
  }

  const loadAuditLog = async (orgId: string) => {
    setSelectedOrg(orgId)
    setAuditLoading(true)
    try {
      const res = await organizationAPI.getAuditLog(orgId)
      setAuditLog(res.data.logs || [])
    } catch (err) {
      console.error('Failed to load audit log:', err)
    } finally {
      setAuditLoading(false)
    }
  }

  const handleAddMember = async () => {
    if (!selectedOrg || !memberUserId) return
    try {
      await organizationAPI.addMember(selectedOrg, { user_id: memberUserId, role: memberRole })
      setShowAddMember(false)
      setMemberUserId('')
      setMemberRole('viewer')
      alert('Member added successfully')
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to add member')
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Organizations</h1>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          <Plus className="w-4 h-4" />
          New Organization
        </button>
      </div>

      {showCreate && (
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="text-lg font-semibold mb-4">Create Organization</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="My Organization"
                className="w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Slug</label>
              <input
                type="text"
                value={newSlug}
                onChange={(e) => setNewSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-'))}
                placeholder="my-org"
                className="w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleCreate}
                disabled={creating || !newName || !newSlug}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {creating ? 'Creating...' : 'Create'}
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1">
          <div className="bg-white rounded-lg shadow">
            <div className="p-4 border-b">
              <h2 className="font-semibold">Your Organizations</h2>
            </div>
            {loading ? (
              <div className="p-4 text-center text-gray-500">Loading...</div>
            ) : orgs.length === 0 ? (
              <div className="p-4 text-center text-gray-500">No organizations yet</div>
            ) : (
              <div className="divide-y">
                {orgs.map((org) => (
                  <button
                    key={org.id}
                    onClick={() => loadAuditLog(org.id)}
                    className={`w-full p-4 text-left hover:bg-gray-50 ${selectedOrg === org.id ? 'bg-blue-50' : ''}`}
                  >
                    <div className="font-medium">{org.name}</div>
                    <div className="text-sm text-gray-500">{org.slug}</div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs px-2 py-0.5 bg-gray-100 rounded-full capitalize">{org.plan}</span>
                      <span className="text-xs text-gray-400">
                        {new Date(org.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="lg:col-span-2">
          {selectedOrg ? (
            <div className="space-y-6">
              <div className="bg-white rounded-lg shadow p-6">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="font-semibold flex items-center gap-2">
                    <Users className="w-5 h-5" />
                    Team Members
                  </h2>
                  <button
                    onClick={() => setShowAddMember(!showAddMember)}
                    className="flex items-center gap-1 px-3 py-1 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700"
                  >
                    <Plus className="w-3 h-3" />
                    Add Member
                  </button>
                </div>

                {showAddMember && (
                  <div className="p-4 bg-gray-50 rounded-lg mb-4 space-y-3">
                    <input
                      type="text"
                      value={memberUserId}
                      onChange={(e) => setMemberUserId(e.target.value)}
                      placeholder="User ID"
                      className="w-full px-3 py-2 border rounded-lg text-sm"
                    />
                    <div className="flex gap-2">
                      <select
                        value={memberRole}
                        onChange={(e) => setMemberRole(e.target.value)}
                        className="px-3 py-2 border rounded-lg text-sm"
                      >
                        {ROLES.map((r) => (
                          <option key={r} value={r}>{r}</option>
                        ))}
                      </select>
                      <button
                        onClick={handleAddMember}
                        className="px-3 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700"
                      >
                        Add
                      </button>
                    </div>
                  </div>
                )}

                <p className="text-sm text-gray-500">
                  Members are managed through team assignments. Contact your admin to add team members.
                </p>
              </div>

              <div className="bg-white rounded-lg shadow p-6">
                <h2 className="font-semibold flex items-center gap-2 mb-4">
                  <Shield className="w-5 h-5" />
                  RBAC Roles
                </h2>
                <div className="grid grid-cols-3 gap-3">
                  {ROLES.map((role) => (
                    <div key={role} className="p-3 bg-gray-50 rounded-lg text-center">
                      <div className="font-medium capitalize">{role}</div>
                      <div className="text-xs text-gray-500 mt-1">
                        {role === 'admin' ? 'Full access' : role === 'editor' ? 'Read & write' : 'Read only'}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="bg-white rounded-lg shadow p-6">
                <h2 className="font-semibold flex items-center gap-2 mb-4">
                  <Key className="w-5 h-5" />
                  Team API Keys
                </h2>
                <p className="text-sm text-gray-500 mb-3">
                  Team API keys are scoped to this organization. Create them via the API.
                </p>
                <pre className="bg-gray-900 text-green-400 p-3 rounded-lg text-xs overflow-auto">
{`curl -X POST https://facedeep.me/api/v2/organizations/${selectedOrg}/api-keys \\
  -H "Authorization: Bearer TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"team_id": "TEAM_ID", "permissions": ["face:read", "face:write"]}'`}
                </pre>
              </div>
            </div>
          ) : (
            <div className="bg-white rounded-lg shadow p-6">
              <div className="text-center text-gray-500 py-12">
                <Building2 className="w-12 h-12 mx-auto mb-3 text-gray-300" />
                <p>Select an organization to view details</p>
              </div>
            </div>
          )}

          {selectedOrg && (
            <div className="bg-white rounded-lg shadow p-6 mt-6">
              <h2 className="font-semibold mb-4">Audit Log</h2>
              {auditLoading ? (
                <p className="text-sm text-gray-500">Loading...</p>
              ) : auditLog.length === 0 ? (
                <p className="text-sm text-gray-500">No audit entries yet</p>
              ) : (
                <div className="space-y-2">
                  {auditLog.map((entry) => (
                    <div key={entry.id} className="flex items-center gap-3 text-sm p-2 bg-gray-50 rounded-lg">
                      <span className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs font-medium">
                        {entry.action}
                      </span>
                      <span className="text-gray-500">{entry.resource_type}</span>
                      {entry.details && <span className="text-gray-400 truncate">{entry.details}</span>}
                      <span className="text-gray-400 ml-auto text-xs">
                        {new Date(entry.created_at).toLocaleString()}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
