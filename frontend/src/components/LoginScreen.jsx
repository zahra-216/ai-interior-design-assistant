import { useState } from 'react'
import { signup, login } from '../api'
import './LoginScreen.css'

export default function LoginScreen({ onAuth, notice }) {
  const [mode, setMode] = useState('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const isLogin = mode === 'login'

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = isLogin
        ? await login(username, password)
        : await signup(username, password)
      onAuth(res)
    } catch (err) {
      setError(isLogin ? 'Invalid username or password.' : 'Could not create account — username may be taken.')
    } finally {
      setLoading(false)
    }
  }

  function switchMode() {
    setMode(isLogin ? 'signup' : 'login')
    setError(null)
  }

  return (
    <div className="login-screen">
      {/* Styled like a sheet from an architect's drawing set */}
      <form className="login-sheet" onSubmit={handleSubmit}>
        <div className="login-sheet__head">
          <span className="login-sheet__wordmark">Studio</span>
          <span className="login-sheet__tagline">AI interior design, made for Sri Lankan homes</span>
        </div>

        <h2>{isLogin ? 'Welcome back' : 'Create an account'}</h2>

        <label className="login-sheet__field">
          <span>Username</span>
          <input
            type="text"
            autoComplete="username"
            value={username}
            onChange={e => setUsername(e.target.value)}
            required
          />
        </label>

        <label className="login-sheet__field">
          <span>Password</span>
          <input
            type="password"
            autoComplete={isLogin ? 'current-password' : 'new-password'}
            value={password}
            onChange={e => setPassword(e.target.value)}
            minLength={isLogin ? undefined : 6}
            required
          />
          {!isLogin && <small>At least 6 characters</small>}
        </label>

        {notice && !error && <p className="login-screen__notice">{notice}</p>}
        {error && <p className="login-screen__error">{error}</p>}

        <button className="btn login-sheet__submit" type="submit" disabled={loading}>
          {loading ? 'Please wait...' : isLogin ? 'Log in' : 'Sign up'}
        </button>

        <button type="button" className="login-screen__switch" onClick={switchMode}>
          {isLogin ? "Don't have an account? " : 'Already have an account? '}
          <span className="login-screen__switch-action">{isLogin ? 'Sign up' : 'Log in'}</span>
        </button>

        <div className="login-sheet__titleblock" aria-hidden="true">
          <span>Sheet 01</span>
          <span>{isLogin ? 'Sign in' : 'New account'}</span>
          <span>Colombo, Sri Lanka</span>
        </div>
      </form>
    </div>
  )
}
