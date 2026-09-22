import { useState } from 'react'
import './FloorPlanPanel.css'

export default function FloorPlanPanel({ design, loading, onRevise }) {
  const [changeText, setChangeText] = useState('')
  const [revising, setRevising] = useState(false)

  async function handleRevise() {
    if (!changeText.trim()) return
    setRevising(true)
    await onRevise(changeText.trim())
    setChangeText('')
    setRevising(false)
  }

  if (loading) {
    return (
      <div className="floor-plan floor-plan--empty">
        <p className="floor-plan__status">Drawing up your layout...</p>
      </div>
    )
  }

  if (!design) {
    return (
      <div className="floor-plan floor-plan--empty">
        <span className="floor-plan__label">Floor plan</span>
        <p className="floor-plan__status">
          Your layout will appear here once requirements are complete.
        </p>
      </div>
    )
  }

  return (
    <div className="floor-plan">
      <div className="floor-plan__header">
        <span className="floor-plan__label">Floor plan</span>
        <h2>Your layout</h2>
      </div>

      <div className="floor-plan__sheet">
        <img
          src={`http://127.0.0.1:8002/${design.layout_image_path}`}
          alt="Generated room layout"
        />
      </div>

      {design.warnings?.length > 0 && (
        <ul className="floor-plan__notes">
          {design.warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )}

      <div className="floor-plan__revise">
        <input
          type="text"
          value={changeText}
          onChange={e => setChangeText(e.target.value)}
          placeholder="Request a change — e.g. remove the TV unit"
          disabled={revising}
        />
        <button className="btn btn-secondary" onClick={handleRevise} disabled={revising || !changeText.trim()}>
          {revising ? 'Updating...' : 'Update layout'}
        </button>
      </div>
    </div>
  )
}
