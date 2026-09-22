import { useState, useRef, useEffect } from 'react'
import { sendChatMessage } from '../api'
import OpeningsPicker from './OpeningsPicker'
import './ChatPanel.css'

export default function ChatPanel({ userId, projectId, initialMessages, onRequirementsComplete, locked = false }) {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: "Let's start. What room are you designing?",
      suggestions: {
        kind: 'room_type',
        mode: 'single',
        options: ['Bedroom', 'Living room', 'Dining room', 'Study / home office', 'Kids room']
      }
    }
  ])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const scrollRef = useRef(null)

  useEffect(() => {
    if (initialMessages && initialMessages.length > 0) {
      setMessages(initialMessages)
    }
  }, [initialMessages])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  function handleSend() {
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    send(text)
  }

  async function send(text, openings = null) {
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setSending(true)

    try {
      const res = await sendChatMessage(userId, text, openings, projectId)
      setMessages(prev => [...prev, {
        role: 'assistant', content: res.reply, widget: res.widget, suggestions: res.suggestions
      }])

      if (res.requirements_complete && res.requirements) {
        onRequirementsComplete(res.requirements)
      }
    } catch (err) {
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: 'Something went wrong reaching the assistant. Try again.' }
      ])
    } finally {
      setSending(false)
    }
  }

  // Single-choice chips (room, style, budget, size, colours) answer straight away;
  // furniture chips add to the message so several can be picked before sending.
  function handleChip(option, mode) {
    if (sending) return
    if (mode === 'single') {
      setInput('')
      send(option)
      return
    }
    setInput(current => {
      const parts = current.split(',').map(p => p.trim()).filter(Boolean)
      const exists = parts.some(p => p.toLowerCase() === option.toLowerCase())
      const next = exists ? parts.filter(p => p.toLowerCase() !== option.toLowerCase()) : [...parts, option]
      return next.join(', ')
    })
  }

  const chosen = input.toLowerCase().split(',').map(p => p.trim())
  const lastSuggestions = messages.at(-1)?.role === 'assistant' ? messages.at(-1).suggestions : null

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="chat-panel">
      <div className="chat-panel__header">
        <span className="chat-panel__label">Requirements</span>
        <h2>Tell us about your room</h2>
      </div>

      <div className="chat-panel__messages" ref={scrollRef}>
        {messages.map((m, i) => (
          <div key={i} className={`chat-bubble chat-bubble--${m.role}`}>
            <p>{m.content}</p>
          </div>
        ))}
        {!sending && !locked && lastSuggestions?.options?.length > 0 && (
          <div className="chat-chips" aria-label="Suggestions">
            {lastSuggestions.mode === 'multi' && (
              <span className="chat-chips__hint">Tap to add, then Send (or type your own):</span>
            )}
            {lastSuggestions.options.map(option => (
              <button
                key={option}
                type="button"
                className={`chat-chips__chip ${lastSuggestions.mode === 'multi' && chosen.includes(option.toLowerCase()) ? 'chat-chips__chip--on' : ''}`}
                onClick={() => handleChip(option, lastSuggestions.mode)}
              >
                {option}
              </button>
            ))}
          </div>
        )}
        {!sending && !locked && messages.at(-1)?.widget === 'openings' && (
          <OpeningsPicker onSubmit={send} disabled={sending} />
        )}
        {sending && (
          <div className="chat-bubble chat-bubble--assistant chat-bubble--typing">
            <p>...</p>
          </div>
        )}
      </div>

      {locked ? (
        <div className="chat-panel__locked">
          Requirements are final. To change the design, use <strong>Request a change</strong> under
          the layout. For a different room, start a <strong>New chat</strong>.
        </div>
      ) : (
      <div className="chat-panel__input">
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type your answer..."
          rows={2}
          disabled={sending}
        />
        <button className="btn" onClick={handleSend} disabled={sending || !input.trim()}>
          Send
        </button>
      </div>
      )}
    </div>
  )
}