'use client'

import { useEffect, useState } from 'react'
import { slaAPI } from '@/lib/api'
import { ExternalLink, Shield, Clock, Server, FileText, AlertTriangle } from 'lucide-react'

export default function ApiDocsPage() {
  const [status, setStatus] = useState<any>(null)
  const [sla, setSla] = useState<any>(null)
  const [compliance, setCompliance] = useState<any>(null)
  const [retention, setRetention] = useState<any>(null)

  useEffect(() => {
    Promise.all([
      slaAPI.getStatus().then((r) => setStatus(r.data)).catch(() => {}),
      slaAPI.getSla().then((r) => setSla(r.data)).catch(() => {}),
      slaAPI.getCompliance().then((r) => setCompliance(r.data)).catch(() => {}),
      slaAPI.getDataRetention().then((r) => setRetention(r.data)).catch(() => {}),
    ])
  }, [])

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-8">API Documentation</h1>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        <a
          href="/docs"
          target="_blank"
          className="bg-white rounded-lg shadow p-6 hover:shadow-lg transition-shadow flex items-center gap-4"
        >
          <div className="p-3 bg-green-100 rounded-lg">
            <FileText className="w-6 h-6 text-green-600" />
          </div>
          <div>
            <h3 className="font-semibold">Swagger UI</h3>
            <p className="text-sm text-gray-500">Interactive API explorer with live testing</p>
          </div>
          <ExternalLink className="w-4 h-4 text-gray-400 ml-auto" />
        </a>

        <a
          href="/redoc"
          target="_blank"
          className="bg-white rounded-lg shadow p-6 hover:shadow-lg transition-shadow flex items-center gap-4"
        >
          <div className="p-3 bg-blue-100 rounded-lg">
            <FileText className="w-6 h-6 text-blue-600" />
          </div>
          <div>
            <h3 className="font-semibold">ReDoc</h3>
            <p className="text-sm text-gray-500">Clean, responsive API documentation</p>
          </div>
          <ExternalLink className="w-4 h-4 text-gray-400 ml-auto" />
        </a>
      </div>

      {status && (
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="font-semibold mb-4 flex items-center gap-2">
            <Server className="w-5 h-5" />
            Service Status
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="p-3 bg-green-50 rounded-lg">
              <div className="text-sm text-gray-500">Status</div>
              <div className="font-bold text-green-600 capitalize">{status.status}</div>
            </div>
            <div className="p-3 bg-blue-50 rounded-lg">
              <div className="text-sm text-gray-500">Version</div>
              <div className="font-bold text-blue-600">{status.current_version}</div>
            </div>
            <div className="p-3 bg-purple-50 rounded-lg">
              <div className="text-sm text-gray-500">API Versions</div>
              <div className="font-bold text-purple-600">{status.supported_versions?.join(', ')}</div>
            </div>
            <div className="p-3 bg-gray-50 rounded-lg">
              <div className="text-sm text-gray-500">Uptime</div>
              <div className="font-bold">{Math.floor((status.uptime_seconds || 0) / 3600)}h {Math.floor(((status.uptime_seconds || 0) % 3600) / 60)}m</div>
            </div>
          </div>
        </div>
      )}

      {sla && (
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="font-semibold mb-4 flex items-center gap-2">
            <Clock className="w-5 h-5" />
            SLA Guarantees
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-4 bg-gray-50 rounded-lg">
              <div className="text-sm text-gray-500">Uptime SLA</div>
              <div className="text-2xl font-bold">{sla.uptime_sla}</div>
              <div className="text-xs text-gray-400">Max {sla.max_downtime_per_year} downtime/year</div>
            </div>
            <div className="p-4 bg-gray-50 rounded-lg">
              <div className="text-sm text-gray-500">Response Time (p99)</div>
              <div className="space-y-1 mt-2">
                {sla.response_time_sla && Object.entries(sla.response_time_sla).map(([k, v]) => (
                  <div key={k} className="flex justify-between text-sm">
                    <span className="text-gray-600">{k}</span>
                    <span className="font-medium">{v as string}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="p-4 bg-gray-50 rounded-lg">
              <div className="text-sm text-gray-500">Incident Response</div>
              <div className="space-y-1 mt-2">
                {sla.incident_response && Object.entries(sla.incident_response).map(([k, v]) => (
                  <div key={k} className="flex justify-between text-sm">
                    <span className="text-gray-600">{k}</span>
                    <span className="font-medium">{v as string}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="p-4 bg-gray-50 rounded-lg">
              <div className="text-sm text-gray-500">Support</div>
              <div className="space-y-1 mt-2">
                {sla.support && Object.entries(sla.support).map(([k, v]) => (
                  <div key={k} className="flex justify-between text-sm">
                    <span className="text-gray-600 capitalize">{k}</span>
                    <span className="font-medium">{v as string}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {retention && (
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="font-semibold mb-4 flex items-center gap-2">
            <Shield className="w-5 h-5" />
            Data Retention Policies
          </h2>
          <div className="space-y-2">
            {retention.policies?.map((p: any) => (
              <div key={p.data_type} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div>
                  <div className="font-medium text-sm">{p.data_type}</div>
                  <div className="text-xs text-gray-500">{p.description}</div>
                </div>
                <span className="text-sm font-medium px-3 py-1 bg-gray-200 rounded-full">
                  {p.retention_days === -1 ? 'Indefinite' : `${p.retention_days} days`}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {compliance && (
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="font-semibold mb-4 flex items-center gap-2">
            <Shield className="w-5 h-5" />
            Compliance
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
            {compliance.frameworks?.map((f: any) => (
              <div key={f.name} className="p-4 bg-gray-50 rounded-lg">
                <div className="font-medium">{f.name}</div>
                <div className={`text-sm font-medium ${f.status === 'Compliant' ? 'text-green-600' : 'text-yellow-600'}`}>
                  {f.status}
                </div>
                <div className="text-xs text-gray-500 mt-1">{f.description}</div>
              </div>
            ))}
          </div>
          {compliance.data_processing && (
            <div className="p-4 bg-gray-50 rounded-lg">
              <h3 className="font-medium mb-2">Data Processing</h3>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div><span className="text-gray-500">DPA Available:</span> {compliance.data_processing.dpa_available ? 'Yes' : 'No'}</div>
                <div><span className="text-gray-500">Right to Deletion:</span> {compliance.data_processing.right_to_deletion}</div>
                <div className="col-span-2">
                  <span className="text-gray-500">Subprocessors:</span> {compliance.data_processing.subprocessors?.join(', ')}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="font-semibold mb-4">Quick Start</h2>
        <div className="space-y-4">
          <div>
            <h3 className="text-sm font-medium text-gray-700 mb-2">1. Get your API key</h3>
            <pre className="bg-gray-900 text-green-400 p-3 rounded-lg text-xs overflow-auto">
{`# Register and get your API key
curl -X POST https://facedeep.me/api/v2/auth/register \\
  -H "Content-Type: application/json" \\
  -d '{"username": "your_user", "email": "you@example.com", "password": "secure_pass"}'`}
            </pre>
          </div>
          <div>
            <h3 className="text-sm font-medium text-gray-700 mb-2">2. Enroll a face</h3>
            <pre className="bg-gray-900 text-green-400 p-3 rounded-lg text-xs overflow-auto">
{`curl -X POST https://facedeep.me/api/v2/face/enroll \\
  -H "X-API-Key: fd_your_key_here" \\
  -F "file=@photo.jpg" \\
  -F "person_id=employee_001"`}
            </pre>
          </div>
          <div>
            <h3 className="text-sm font-medium text-gray-700 mb-2">3. Recognize a face</h3>
            <pre className="bg-gray-900 text-green-400 p-3 rounded-lg text-xs overflow-auto">
{`curl -X POST https://facedeep.me/api/v2/face/recognize \\
  -H "X-API-Key: fd_your_key_here" \\
  -F "file=@photo.jpg"`}
            </pre>
          </div>
        </div>
      </div>
    </div>
  )
}
