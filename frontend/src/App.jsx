import { useState } from 'react'
import LoginPage from './pages/LoginPage'
import ChatPage from './pages/ChatPage'
import './App.css'

export default function App() {
  const [user, setUser] = useState(null)

  const handleLogout = () => {
    setUser(null)
  }

  if (!user) {
    return <LoginPage onLogin={setUser} />
  }

  return <ChatPage user={user} onLogout={handleLogout} />
}