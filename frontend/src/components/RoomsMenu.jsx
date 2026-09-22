import { useEffect, useRef, useState } from 'react'
import './RoomsMenu.css'

function formatDate(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

// "My rooms": every room the user has designed (or started), newest first
export default function RoomsMenu({ projects, currentId, onOpen, onDelete, onRefresh }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    onRefresh()
    const close = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  function handleDelete(e, project) {
    e.stopPropagation()
    if (window.confirm(`Delete "${project.title}"? Its chat and layouts will be removed.`)) {
      onDelete(project.id)
    }
  }

  return (
    <div className="rooms-menu" ref={ref}>
      <button className="app__action rooms-menu__toggle" onClick={() => setOpen(o => !o)} aria-expanded={open}>
        My rooms{projects.length ? ` (${projects.length})` : ''}
      </button>

      {open && (
        <div className="rooms-menu__panel" role="menu">
          {projects.length === 0 && (
            <p className="rooms-menu__empty">No designed rooms yet. A room appears here once its layout is generated.</p>
          )}
          {projects.map(p => (
            <div
              key={p.id}
              role="menuitem"
              tabIndex={0}
              className={`rooms-menu__item ${p.id === currentId ? 'rooms-menu__item--current' : ''}`}
              onClick={() => { setOpen(false); if (p.id !== currentId) onOpen(p.id) }}
              onKeyDown={e => { if (e.key === 'Enter') { setOpen(false); onOpen(p.id) } }}
            >
              <div className="rooms-menu__text">
                <span className="rooms-menu__title">{p.title}</span>
                <span className="rooms-menu__meta">
                  {p.status === 'complete' ? 'Designed' : 'In progress'} · {formatDate(p.updated_at)}
                  {p.budget ? ` · LKR ${Math.round(p.budget).toLocaleString()}` : ''}
                </span>
              </div>
              <button className="rooms-menu__delete" onClick={e => handleDelete(e, p)} aria-label={`Delete ${p.title}`}>
                Delete
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
