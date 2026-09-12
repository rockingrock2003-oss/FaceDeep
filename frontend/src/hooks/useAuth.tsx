'use client'

import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { authAPI } from '@/lib/api'

interface User {
  id: string
  username: string
  email: string
  plan: string
  entry_in_chroma_db: number
  number_of_api_use_for_service: number
}

interface AuthContextType {
  user: User | null
  apiKey: string | null
  login: (username: string, password: string) => Promise<void>
  register: (username: string, email: string, password: string) => Promise<{ api_key: string }>
  logout: () => void
  isLoading: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [apiKey, setApiKey] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const storedApiKey = localStorage.getItem('api_key')
    if (storedApiKey) {
      setApiKey(storedApiKey)
      fetchUser()
    } else {
      setIsLoading(false)
    }
  }, [])

  const fetchUser = async () => {
    try {
      const response = await authAPI.getMe()
      setUser(response.data)
    } catch (error) {
      localStorage.removeItem('api_key')
      setApiKey(null)
    } finally {
      setIsLoading(false)
    }
  }

  const login = async (username: string, password: string) => {
    const response = await authAPI.login({ username, password })
    const { api_key } = response.data
    localStorage.setItem('api_key', api_key)
    setApiKey(api_key)
    await fetchUser()
  }

  const register = async (username: string, email: string, password: string) => {
    const response = await authAPI.register({ username, email, password })
    return response.data
  }

  const logout = () => {
    localStorage.removeItem('api_key')
    setApiKey(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, apiKey, login, register, logout, isLoading }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
