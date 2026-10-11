'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { authAPI } from '@/lib/api'

type VerifyState = 'verifying' | 'success' | 'error'

export default function VerifyEmailPage() {
  const [state, setState] = useState<VerifyState>('verifying')
  const [message, setMessage] = useState('Verifying your email...')

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get('token')
    if (!token) {
      setState('error')
      setMessage('The verification link is missing its token.')
      return
    }

    authAPI
      .verifyEmail(token)
      .then((response) => {
        setState('success')
        setMessage(response.data.message || 'Email verified successfully.')
      })
      .catch((error) => {
        setState('error')
        setMessage(
          error.response?.data?.detail ||
            'This verification link is invalid or has expired.'
        )
      })
  }, [])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="max-w-md w-full rounded-lg bg-white p-8 shadow-lg text-center">
        <h1 className="text-3xl font-bold text-gray-900">FaceDeep</h1>
        <h2 className="mt-2 text-lg font-medium text-gray-700">Email verification</h2>

        <div
          className={`mt-6 rounded-md p-4 text-sm ${
            state === 'success'
              ? 'bg-green-50 text-green-700'
              : state === 'error'
                ? 'bg-red-50 text-red-700'
                : 'bg-blue-50 text-blue-700'
          }`}
        >
          {message}
        </div>

        {state !== 'verifying' && (
          <Link
            href="/login"
            className="mt-6 inline-flex rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Go to sign in
          </Link>
        )}
      </div>
    </div>
  )
}
