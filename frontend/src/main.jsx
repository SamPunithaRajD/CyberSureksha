import React, { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ErrorBoundary } from 'react-error-boundary'
import App from './App.jsx'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 1000 * 30, // 30 seconds
    },
  },
})

function ErrorFallback({ error, resetErrorBoundary }) {
  return (
    <div style={{ padding: '40px', background: '#09090b', height: '100vh', color: '#e4e4e7', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ background: 'rgba(244,63,94,0.1)', padding: '24px', borderRadius: '8px', border: '1px solid rgba(244,63,94,0.3)', maxWidth: '600px' }}>
        <h2 style={{ color: '#f43f5e', margin: '0 0 16px 0' }}>Something went wrong</h2>
        <p style={{ color: '#a1a1aa', marginBottom: '16px' }}>The application encountered an unexpected error during rendering.</p>
        <pre style={{ color: '#ffc1c1', background: 'rgba(0,0,0,0.3)', padding: '12px', borderRadius: '4px', overflowX: 'auto', fontSize: '13px' }}>
          {error.message}
        </pre>
        <button 
          onClick={resetErrorBoundary}
          style={{ background: '#3b82f6', color: '#fff', border: 'none', padding: '8px 16px', borderRadius: '4px', marginTop: '16px', cursor: 'pointer', fontWeight: 500 }}
        >
          Restart Application
        </button>
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary FallbackComponent={ErrorFallback} onReset={() => window.location.href = '/'}>
        <App />
      </ErrorBoundary>
    </QueryClientProvider>
  </StrictMode>,
)
