import { useState } from 'react'
import { signup, login } from '../api'
import './LoginScreen.css'

export default function LoginScreen({ onAuth }) {
  const [mode, setMode] = useState('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = mode === 'login'
        ? await login(username, password)
        : await signup(username, password)
      onAuth(res.user_id)
    } catch (err) {
      setError(mode === 'login' ? 'Invalid username or password.' : 'Could not create account — username may be taken.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-screen">
      <form className="login-screen__card" onSubmit={handleSubmit}>
        <span className="login-screen__label">Studio</span>
        <h2>{mode === 'login' ? 'Welcome back' : 'Create an account'}</h2>

        <input
          type="text"
          placeholder="Username"
          value={username}
          onChange={e => setUsername(e.target.value)}
          required
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          required
        />

        {error && <p className="login-screen__error">{error}</p>}

        <button className="btn" type="submit" disabled={loading}>
          {loading ? 'Please wait...' : mode === 'login' ? 'Log in' : 'Sign up'}
        </button>

        <button
          type="button"
          className="login-screen__switch"
          onClick={() => setMode(mode === 'login' ? 'signup' : 'login')}
        >
          {mode === 'login' ? "Don't have an account? Sign up" : 'Already have an account? Log in'}
        </button>
      </form>
    </div>
  )
}