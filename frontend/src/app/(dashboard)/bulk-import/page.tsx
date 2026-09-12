'use client'

import { useState } from 'react'
import { faceAPI } from '@/lib/api'
import { Upload, CheckCircle, XCircle, Clock } from 'lucide-react'

export default function BulkImportPage() {
  const [personId, setPersonId] = useState('')
  const [urls, setUrls] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  const [jobStatus, setJobStatus] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const handleImport = async () => {
    if (!personId || !urls.trim()) return
    setLoading(true)
    try {
      const urlList = urls.split('\n').map((u) => u.trim()).filter(Boolean)
      const response = await faceAPI.bulkImport(personId, urlList)
      setJobId(response.data.job_id)
      pollStatus(response.data.job_id)
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Import failed')
    } finally {
      setLoading(false)
    }
  }

  const pollStatus = async (id: string) => {
    const interval = setInterval(async () => {
      try {
        const response = await faceAPI.getImportStatus(id)
        setJobStatus(response.data)
        if (response.data.status === 'completed' || response.data.status === 'failed') {
          clearInterval(interval)
        }
      } catch (error) {
        clearInterval(interval)
      }
    }, 2000)
  }

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-8">Bulk Import</h1>

      <div className="bg-white rounded-lg shadow p-6">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Person ID
            </label>
            <input
              type="text"
              placeholder="e.g., emp_001"
              value={personId}
              onChange={(e) => setPersonId(e.target.value)}
              className="w-full px-4 py-2 border rounded-lg"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Image URLs (one per line)
            </label>
            <textarea
              rows={8}
              placeholder="https://example.com/face1.jpg&#10;https://example.com/face2.jpg&#10;https://example.com/face3.jpg"
              value={urls}
              onChange={(e) => setUrls(e.target.value)}
              className="w-full px-4 py-2 border rounded-lg font-mono text-sm"
            />
          </div>

          <button
            onClick={handleImport}
            disabled={loading || !personId || !urls.trim()}
            className="w-full py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2"
          >
            <Upload className="w-5 h-5" />
            {loading ? 'Starting Import...' : 'Start Import'}
          </button>
        </div>

        {jobStatus && (
          <div className="mt-6 p-4 bg-gray-50 rounded-lg">
            <h3 className="font-semibold mb-4">Import Status</h3>
            
            <div className="grid grid-cols-4 gap-4 mb-4">
              <div className="text-center">
                <p className="text-2xl font-bold text-blue-600">{jobStatus.total}</p>
                <p className="text-sm text-gray-500">Total</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-green-600">{jobStatus.success}</p>
                <p className="text-sm text-gray-500">Success</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-red-600">{jobStatus.failed}</p>
                <p className="text-sm text-gray-500">Failed</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-gray-600">{jobStatus.progress_percent}%</p>
                <p className="text-sm text-gray-500">Progress</p>
              </div>
            </div>

            <div className="w-full bg-gray-200 rounded-full h-2">
              <div
                className="bg-blue-600 h-2 rounded-full transition-all"
                style={{ width: `${jobStatus.progress_percent}%` }}
              />
            </div>

            <div className="mt-4 flex items-center gap-2">
              {jobStatus.status === 'completed' && (
                <CheckCircle className="w-5 h-5 text-green-600" />
              )}
              {jobStatus.status === 'failed' && (
                <XCircle className="w-5 h-5 text-red-600" />
              )}
              {jobStatus.status === 'processing' && (
                <Clock className="w-5 h-5 text-yellow-600" />
              )}
              <span className="capitalize">{jobStatus.status}</span>
            </div>

            {jobStatus.errors && jobStatus.errors.length > 0 && (
              <div className="mt-4">
                <p className="text-sm font-medium text-red-600 mb-2">Errors:</p>
                <ul className="text-sm text-red-500 space-y-1">
                  {jobStatus.errors.slice(0, 5).map((error: string, i: number) => (
                    <li key={i}>{error}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
