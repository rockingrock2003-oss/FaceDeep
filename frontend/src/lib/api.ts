import axios from 'axios'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
})

api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
  }
  return config
})

let isRedirecting = false
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      if (typeof window !== 'undefined' && !isRedirecting) {
        isRedirecting = true
        localStorage.removeItem('access_token')
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export const authAPI = {
  register: (data: { username: string; email: string; password: string }) =>
    api.post('/auth/register', data),
  
  login: (data: { username: string; password: string }) =>
    api.post('/auth/login', data),
  
  getMe: () => api.get('/auth/me'),

  getApiKey: () => api.get('/auth/api-key'),

  regenerateApiKey: () => api.post('/auth/api-key/regenerate'),

  changePassword: (data: { current_password: string; new_password: string }) =>
    api.post('/auth/change-password', data),
  
  verifyEmail: (token: string) =>
    api.post('/auth/verify-email', { token }),
  
  resendVerification: (email: string) =>
    api.post('/auth/resend-verification', { email }),
}

export const faceAPI = {
  enroll: (file: File, personId: string) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('person_id', personId)
    return api.post('/face/enroll', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  recognize: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post('/face/recognize', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  isMatch: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post('/face/ismatch', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  update: (file: File, personId: string) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('person_id', personId)
    return api.put('/face/update', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  delete: (personId: string) =>
    api.delete('/face/delete', { data: { person_id: personId } }),

  listPersons: () => api.get('/face/persons'),

  bulkEnroll: (files: File[], personId: string) => {
    const formData = new FormData()
    files.forEach((file) => formData.append('files', file))
    formData.append('person_id', personId)
    return api.post('/face/bulk-enroll', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  bulkImport: (personId: string, imageUrls: string[]) =>
    api.post('/face/bulk-import', { person_id: personId, image_urls: imageUrls }),

  getImportStatus: (jobId: string) =>
    api.get(`/face/import-status/${jobId}`),

  listImportJobs: () => api.get('/face/import-jobs'),

  clearAll: () => api.delete('/face/clear'),
}

export const billingAPI = {
  getPlans: () => api.get('/billing/plans'),
  getUsage: () => api.get('/billing/usage'),
  activate: (plan: string, sessionId: string) =>
    api.post('/billing/activate', { plan, session_id: sessionId }),
  cancel: () => api.post('/billing/cancel'),
}

export default api
