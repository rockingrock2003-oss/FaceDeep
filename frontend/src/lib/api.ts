import axios from 'axios'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: `${API_URL}/api/v2`,
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

  getApiStats: () => api.get('/auth/api-stats'),

  getUsage: () => api.get('/billing/usage'),

  getRealtimeUsage: () => api.get('/billing/realtime-usage'),

  getMonthlyCost: () => api.get('/billing/monthly-cost'),

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

  listPersons: (limit = 100, offset = 0) =>
    api.get(`/face/persons?limit=${limit}&offset=${offset}`),

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
  getRealtimeUsage: () => api.get('/billing/realtime-usage'),
  getMonthlyCost: () => api.get('/billing/monthly-cost'),
  activate: (plan: string, sessionId: string) =>
    api.post('/billing/activate', { plan, session_id: sessionId }),
  cancel: () => api.post('/billing/cancel'),
}

export const webhookAPI = {
  list: () => api.get('/webhooks'),
  get: (id: string) => api.get(`/webhooks/${id}`),
  create: (data: { url: string; events: string[] }) =>
    api.post('/webhooks', data),
  update: (id: string, data: { url?: string; events?: string[]; is_active?: boolean }) =>
    api.put(`/webhooks/${id}`, data),
  delete: (id: string) => api.delete(`/webhooks/${id}`),
  test: (id: string) => api.post(`/webhooks/${id}/test`),
  getDeliveries: (id: string) => api.get(`/webhooks/${id}/deliveries`),
}

export const organizationAPI = {
  list: () => api.get('/organizations'),
  get: (id: string) => api.get(`/organizations/${id}`),
  create: (data: { name: string; slug: string }) =>
    api.post('/organizations', data),
  addMember: (orgId: string, data: { user_id: string; role: string }) =>
    api.post(`/organizations/${orgId}/members`, data),
  createApiKey: (orgId: string, data: { team_id: string; permissions?: string[] }) =>
    api.post(`/organizations/${orgId}/api-keys`, data),
  getAuditLog: (orgId: string, limit = 50) =>
    api.get(`/organizations/${orgId}/audit-log?limit=${limit}`),
}

export const slaAPI = {
  getStatus: () => api.get('/status'),
  getSla: () => api.get('/sla'),
  getDataRetention: () => api.get('/data-retention'),
  getCompliance: () => api.get('/compliance'),
  getIncidents: () => api.get('/incidents'),
}

export const uploadAPI = {
  createSession: (filename: string, contentType: string, fileSize: number) =>
    api.post('/upload/presigned-url', null, {
      params: { filename, content_type: contentType, file_size: fileSize },
    }),
  uploadPart: (uploadId: string, partNumber: number, file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post(`/upload/${uploadId}/part?part_number=${partNumber}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  complete: (uploadId: string) => api.post(`/upload/${uploadId}/complete`),
  abort: (uploadId: string) => api.delete(`/upload/${uploadId}`),
  process: (file: File, targetFormat = 'webp', quality = 85) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('target_format', targetFormat)
    formData.append('quality', String(quality))
    return api.post('/upload/process', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      responseType: 'blob',
    })
  },
}

export default api
