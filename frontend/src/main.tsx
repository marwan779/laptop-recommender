import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { UserSessionProvider } from './context/UserSessionContext'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <UserSessionProvider>
      <App />
    </UserSessionProvider>
  </StrictMode>,
)
