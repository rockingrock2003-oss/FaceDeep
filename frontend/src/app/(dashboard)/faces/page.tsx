'use client'

import { useState, useRef } from 'react'
import { faceAPI } from '@/lib/api'
import { Upload, Search, Trash2, Users } from 'lucide-react'

export default function FacesPage() {
  const [activeTab, setActiveTab] = useState<'enroll' | 'recognize' | 'ismatch' | 'list'>('enroll')
  const [personId, setPersonId] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [persons, setPersons] = useState<any[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleEnroll = async () => {
    if (!file || !personId) return
    setLoading(true)
    try {
      const response = await faceAPI.enroll(file, personId)
      setResult(response.data)
      loadPersons()
    } catch (error: any) {
      setResult({ error: error.response?.data?.detail || 'Enroll failed' })
    } finally {
      setLoading(false)
    }
  }

  const handleRecognize = async () => {
    if (!file) return
    setLoading(true)
    try {
      const response = await faceAPI.recognize(file)
      setResult(response.data)
    } catch (error: any) {
      setResult({ error: error.response?.data?.detail || 'Recognize failed' })
    } finally {
      setLoading(false)
    }
  }

  const handleIsMatch = async () => {
    if (!file) return
    setLoading(true)
    try {
      const response = await faceAPI.isMatch(file)
      setResult(response.data)
    } catch (error: any) {
      setResult({ error: error.response?.data?.detail || 'Match check failed' })
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (pid: string) => {
    if (!confirm(`Delete all faces for ${pid}?`)) return
    try {
      await faceAPI.delete(pid)
      loadPersons()
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Delete failed')
    }
  }

  const loadPersons = async () => {
    try {
      const response = await faceAPI.listPersons()
      setPersons(response.data.persons || [])
    } catch (error) {
      console.error('Failed to load persons:', error)
    }
  }

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-8">Face Management</h1>

      <div className="flex gap-4 mb-6">
        {(['enroll', 'recognize', 'ismatch', 'list'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => {
              setActiveTab(tab)
              setResult(null)
              if (tab === 'list') loadPersons()
            }}
            className={`px-4 py-2 rounded-lg font-medium ${
              activeTab === tab
                ? 'bg-blue-600 text-white'
                : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
            }`}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      <div className="bg-white rounded-lg shadow p-6">
        {activeTab === 'enroll' && (
          <div className="space-y-4">
            <h2 className="text-xl font-semibold">Enroll New Face</h2>
            <input
              type="text"
              placeholder="Person ID (e.g., emp_001)"
              value={personId}
              onChange={(e) => setPersonId(e.target.value)}
              className="w-full px-4 py-2 border rounded-lg"
            />
            <input
              type="file"
              ref={fileInputRef}
              accept="image/*"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="w-full p-4 border-2 border-dashed rounded-lg text-gray-600 hover:border-blue-500"
            >
              <Upload className="w-6 h-6 mx-auto mb-2" />
              {file ? file.name : 'Click to upload face image'}
            </button>
            <button
              onClick={handleEnroll}
              disabled={loading || !file || !personId}
              className="w-full py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {loading ? 'Enrolling...' : 'Enroll Face'}
            </button>
          </div>
        )}

        {activeTab === 'recognize' && (
          <div className="space-y-4">
            <h2 className="text-xl font-semibold">Recognize Face</h2>
            <input
              type="file"
              ref={fileInputRef}
              accept="image/*"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="w-full p-4 border-2 border-dashed rounded-lg text-gray-600 hover:border-blue-500"
            >
              <Search className="w-6 h-6 mx-auto mb-2" />
              {file ? file.name : 'Click to upload face image'}
            </button>
            <button
              onClick={handleRecognize}
              disabled={loading || !file}
              className="w-full py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
            >
              {loading ? 'Recognizing...' : 'Recognize Face'}
            </button>
          </div>
        )}

        {activeTab === 'ismatch' && (
          <div className="space-y-4">
            <h2 className="text-xl font-semibold">Check if Face Exists</h2>
            <input
              type="file"
              ref={fileInputRef}
              accept="image/*"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="w-full p-4 border-2 border-dashed rounded-lg text-gray-600 hover:border-blue-500"
            >
              <Search className="w-6 h-6 mx-auto mb-2" />
              {file ? file.name : 'Click to upload face image'}
            </button>
            <button
              onClick={handleIsMatch}
              disabled={loading || !file}
              className="w-full py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
            >
              {loading ? 'Checking...' : 'Check Match'}
            </button>
          </div>
        )}

        {activeTab === 'list' && (
          <div className="space-y-4">
            <h2 className="text-xl font-semibold">Enrolled Persons</h2>
            {persons.length === 0 ? (
              <p className="text-gray-500">No persons enrolled yet</p>
            ) : (
              <div className="space-y-2">
                {persons.map((person) => (
                  <div
                    key={person.person_id}
                    className="flex items-center justify-between p-4 bg-gray-50 rounded-lg"
                  >
                    <div className="flex items-center gap-3">
                      <Users className="w-5 h-5 text-gray-500" />
                      <div>
                        <p className="font-medium">{person.person_id}</p>
                        <p className="text-sm text-gray-500">{person.face_count} face(s)</p>
                      </div>
                    </div>
                    <button
                      onClick={() => handleDelete(person.person_id)}
                      className="p-2 text-red-600 hover:bg-red-50 rounded-lg"
                    >
                      <Trash2 className="w-5 h-5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {result && (
          <div className="mt-6 p-4 bg-gray-50 rounded-lg">
            <h3 className="font-semibold mb-2">Result:</h3>
            <pre className="text-sm overflow-auto">
              {JSON.stringify(result, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  )
}
