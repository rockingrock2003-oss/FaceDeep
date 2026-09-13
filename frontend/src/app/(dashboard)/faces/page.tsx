'use client'

import { useState, useRef, useEffect } from 'react'
import { faceAPI } from '@/lib/api'
import {
  Upload,
  Search,
  Trash2,
  Users,
  Eraser,
  Plus,
  RefreshCw,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'

interface Person {
  person_id: string
  face_count: number
  faces?: { face_id: string; uploaded_time: string }[]
  expanded?: boolean
}

export default function FacesPage() {
  const [activeTab, setActiveTab] = useState<
    'enroll' | 'recognize' | 'ismatch' | 'list'
  >('enroll')
  const [personId, setPersonId] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [persons, setPersons] = useState<Person[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [sortBy, setSortBy] = useState<'person_id' | 'face_count'>('person_id')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const bulkFileInputRef = useRef<HTMLInputElement>(null)
  const addFileInputRef = useRef<HTMLInputElement>(null)
  const [addTargetPerson, setAddTargetPerson] = useState<string | null>(null)

  const handleEnroll = async () => {
    if (!file || !personId) return
    setLoading(true)
    try {
      const response = await faceAPI.enroll(file, personId)
      setResult(response.data)
      loadPersons()
      setFile(null)
      setPersonId('')
      if (fileInputRef.current) fileInputRef.current.value = ''
    } catch (error: any) {
      setResult({ error: error.response?.data?.detail || 'Enroll failed' })
    } finally {
      setLoading(false)
    }
  }

  const handleBulkEnroll = async () => {
    const input = bulkFileInputRef.current
    if (!input?.files?.length || !personId) return
    const files = Array.from(input.files)
    setLoading(true)
    try {
      const response = await faceAPI.bulkEnroll(files, personId)
      setResult(response.data)
      loadPersons()
      setPersonId('')
      input.value = ''
    } catch (error: any) {
      setResult({ error: error.response?.data?.detail || 'Bulk enroll failed' })
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
      setResult({
        error: error.response?.data?.detail || 'Match check failed',
      })
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (pid: string) => {
    if (!confirm(`Delete ALL faces for "${pid}"? This cannot be undone.`)) return
    setLoading(true)
    try {
      await faceAPI.delete(pid)
      loadPersons()
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Delete failed')
    } finally {
      setLoading(false)
    }
  }

  const handleClearAll = async () => {
    if (
      !confirm(
        'Delete ALL face embeddings for your account? This cannot be undone.'
      )
    )
      return
    setLoading(true)
    try {
      const response = await faceAPI.clearAll()
      setResult({ message: response.data.message })
      loadPersons()
    } catch (error: any) {
      setResult({ error: error.response?.data?.detail || 'Clear failed' })
    } finally {
      setLoading(false)
    }
  }

  const handleAddFace = async (pid: string) => {
    setAddTargetPerson(pid)
    addFileInputRef.current?.click()
  }

  const processAddFace = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0]
    if (!selectedFile || !addTargetPerson) return
    setLoading(true)
    try {
      const response = await faceAPI.enroll(selectedFile, addTargetPerson)
      setResult(response.data)
      loadPersons()
    } catch (error: any) {
      setResult({
        error: error.response?.data?.detail || 'Add face failed',
      })
    } finally {
      setLoading(false)
      setAddTargetPerson(null)
      if (addFileInputRef.current) addFileInputRef.current.value = ''
    }
  }

  const toggleExpand = (pid: string) => {
    setPersons((prev) =>
      prev.map((p) =>
        p.person_id === pid ? { ...p, expanded: !p.expanded } : p
      )
    )
  }

  const loadPersons = async () => {
    try {
      const response = await faceAPI.listPersons()
      setPersons(
        (response.data.persons || []).map((p: Person) => ({
          ...p,
          expanded: false,
        }))
      )
    } catch (error) {
      console.error('Failed to load persons:', error)
    }
  }

  useEffect(() => {
    if (activeTab === 'list') loadPersons()
  }, [activeTab])

  const filteredPersons = persons
    .filter((p) =>
      p.person_id.toLowerCase().includes(searchQuery.toLowerCase())
    )
    .sort((a, b) => {
      const val = sortBy === 'person_id' ? a.person_id : a.face_count
      const cmp =
        typeof val === 'string'
          ? val.localeCompare(
              sortBy === 'person_id' ? b.person_id : String(b.face_count)
            )
          : val - (sortBy === 'face_count' ? b.face_count : 0)
      return sortDir === 'asc' ? cmp : -cmp
    })

  const totalFaces = persons.reduce((sum, p) => sum + p.face_count, 0)

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-8">
        Face Management
      </h1>

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
            {tab === 'list'
              ? `List (${persons.length})`
              : tab.charAt(0).toUpperCase() + tab.slice(1)}
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

            <hr className="my-4" />
            <h2 className="text-xl font-semibold">Bulk Enroll</h2>
            <input
              type="text"
              placeholder="Person ID"
              value={personId}
              onChange={(e) => setPersonId(e.target.value)}
              className="w-full px-4 py-2 border rounded-lg"
            />
            <input
              type="file"
              ref={bulkFileInputRef}
              accept="image/*"
              multiple
              className="hidden"
            />
            <button
              onClick={() => bulkFileInputRef.current?.click()}
              className="w-full p-4 border-2 border-dashed rounded-lg text-gray-600 hover:border-green-500"
            >
              <Upload className="w-6 h-6 mx-auto mb-2" />
              Select multiple images
            </button>
            <button
              onClick={handleBulkEnroll}
              disabled={loading || !personId}
              className="w-full py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
            >
              {loading ? 'Uploading...' : 'Bulk Enroll'}
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
            <input
              type="file"
              ref={addFileInputRef}
              accept="image/*"
              onChange={processAddFace}
              className="hidden"
            />

            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold">Enrolled Persons</h2>
              <div className="flex gap-2">
                <button
                  onClick={loadPersons}
                  disabled={loading}
                  className="flex items-center gap-2 px-3 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300"
                >
                  <RefreshCw className="w-4 h-4" />
                  Refresh
                </button>
                {persons.length > 0 && (
                  <button
                    onClick={handleClearAll}
                    disabled={loading}
                    className="flex items-center gap-2 px-3 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
                  >
                    <Eraser className="w-4 h-4" />
                    Clear All
                  </button>
                )}
              </div>
            </div>

            <div className="flex items-center gap-4 text-sm text-gray-500">
              <span>
                {persons.length} person(s), {totalFaces} total face(s)
              </span>
              <input
                type="text"
                placeholder="Search person_id..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="px-3 py-1 border rounded-lg text-sm"
              />
            </div>

            {filteredPersons.length === 0 ? (
              <p className="text-gray-500 py-8 text-center">
                {persons.length === 0
                  ? 'No persons enrolled yet'
                  : 'No matching persons'}
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr className="border-b bg-gray-50">
                      <th className="px-4 py-3">
                        <button
                          onClick={() => {
                            setSortBy('person_id')
                            setSortDir(
                              sortBy === 'person_id' && sortDir === 'asc'
                                ? 'desc'
                                : 'asc'
                            )
                          }}
                          className="flex items-center gap-1 font-semibold text-gray-700 hover:text-gray-900"
                        >
                          Person ID
                          {sortBy === 'person_id' &&
                            (sortDir === 'asc' ? (
                              <ChevronUp className="w-4 h-4" />
                            ) : (
                              <ChevronDown className="w-4 h-4" />
                            ))}
                        </button>
                      </th>
                      <th className="px-4 py-3">
                        <button
                          onClick={() => {
                            setSortBy('face_count')
                            setSortDir(
                              sortBy === 'face_count' && sortDir === 'asc'
                                ? 'desc'
                                : 'asc'
                            )
                          }}
                          className="flex items-center gap-1 font-semibold text-gray-700 hover:text-gray-900"
                        >
                          Faces
                          {sortBy === 'face_count' &&
                            (sortDir === 'asc' ? (
                              <ChevronUp className="w-4 h-4" />
                            ) : (
                              <ChevronDown className="w-4 h-4" />
                            ))}
                        </button>
                      </th>
                      <th className="px-4 py-3 font-semibold text-gray-700">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredPersons.map((person) => (
                      <>
                        <tr
                          key={person.person_id}
                          className="border-b hover:bg-gray-50"
                        >
                          <td className="px-4 py-3">
                            <button
                              onClick={() => toggleExpand(person.person_id)}
                              className="flex items-center gap-2 font-medium text-gray-900 hover:text-blue-600"
                            >
                              <Users className="w-4 h-4 text-gray-400" />
                              {person.person_id}
                              {person.expanded ? (
                                <ChevronUp className="w-4 h-4 text-gray-400" />
                              ) : (
                                <ChevronDown className="w-4 h-4 text-gray-400" />
                              )}
                            </button>
                          </td>
                          <td className="px-4 py-3">
                            <span
                              className={`px-2 py-1 rounded-full text-xs font-medium ${
                                person.face_count >= 10
                                  ? 'bg-green-100 text-green-700'
                                  : person.face_count >= 5
                                    ? 'bg-yellow-100 text-yellow-700'
                                    : 'bg-red-100 text-red-700'
                              }`}
                            >
                              {person.face_count} face(s)
                            </span>
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() =>
                                  handleAddFace(person.person_id)
                                }
                                disabled={loading}
                                className="flex items-center gap-1 px-3 py-1 bg-blue-100 text-blue-700 rounded-lg hover:bg-blue-200 text-sm"
                              >
                                <Plus className="w-3 h-3" />
                                Add
                              </button>
                              <button
                                onClick={() =>
                                  handleDelete(person.person_id)
                                }
                                disabled={loading}
                                className="flex items-center gap-1 px-3 py-1 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 text-sm"
                              >
                                <Trash2 className="w-3 h-3" />
                                Delete
                              </button>
                            </div>
                          </td>
                        </tr>
                        {person.expanded && (
                          <tr key={`${person.person_id}-details`}>
                            <td
                              colSpan={3}
                              className="px-4 py-3 bg-gray-50"
                            >
                              <p className="text-sm text-gray-500 mb-2">
                                {person.face_count} embedding(s) stored.
                                Max 50 per person (oldest auto-removed).
                              </p>
                            </td>
                          </tr>
                        )}
                      </>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {result && (
          <div className="mt-6 p-4 bg-gray-50 rounded-lg">
            <h3 className="font-semibold mb-2">Result:</h3>
            <pre className="text-sm overflow-auto max-h-60">
              {JSON.stringify(result, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  )
}
