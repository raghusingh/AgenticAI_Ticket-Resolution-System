import { useState } from 'react'
import { loginUser } from '../api/chatApi'
import '../App.css'

export default function LoginPage({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleLogin = async () => {
    try {
      setLoading(true)
      setError('')

      const data = await loginUser({
        username,
        password,
      })

      onLogin(data)
    } catch (err) {
      setError(err?.response?.data?.detail || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <h2>Login</h2>

        <input
          type="text"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />

        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <button
          type="button"
          onClick={handleLogin}
          disabled={!username.trim() || !password.trim() || loading}
        >
          {loading ? 'Logging in...' : 'Login'}
        </button>

        {error ? <div className="error-text">{error}</div> : null}
      </div>
    </div>
  )
}