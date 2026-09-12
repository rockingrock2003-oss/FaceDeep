'use client'

import { AuthProvider } from '@/hooks/useAuth'
import Sidebar from '@/components/Sidebar'

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <AuthProvider>
      <div className="flex min-h-screen bg-gray-100">
        <Sidebar />
        <main className="flex-1 ml-64 p-8">
          {children}
        </main>
      </div>
    </AuthProvider>
  )
}
