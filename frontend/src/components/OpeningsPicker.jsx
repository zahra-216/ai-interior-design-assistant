import { useState } from 'react'
import './OpeningsPicker.css'

// Room seen from above. The wall you walk in through is always drawn at the bottom,
// so users describe walls relative to the door ("opposite the door", "on my left")
// instead of compass directions. Wall/position names match what Agent 2 expects.
const ROOM = { x: 40, y: 34, w: 180, h: 150 }
const BOTTOM = ROOM.y + ROOM.h
const RIGHT = ROOM.x + ROOM.w

const WALL_WORDS = {
  bottom: 'the wall I walk in through',
  top: 'the wall opposite the door',
  left: 'the left wall as I walk in',
  right: 'the right wall as I walk in'
}
const POSITION_WORDS = {
  left: 'on the left', center: 'in the middle', right: 'on the right',
  start: 'near the entrance', end: 'at the far end'
}

function buildSegments() {
  const segs = []
  const thirdW = ROOM.w / 3
  const thirdH = ROOM.h / 3
  ;['left', 'center', 'right'].forEach((position, i) => {
    const x1 = ROOM.x + i * thirdW
    segs.push({ wall: 'bottom', position, x1, y1: BOTTOM, x2: x1 + thirdW, y2: BOTTOM })
    segs.push({ wall: 'top', position, x1, y1: ROOM.y, x2: x1 + thirdW, y2: ROOM.y })
  })
  // Side walls run from the entrance (bottom of the drawing) to the far end
  ;['start', 'center', 'end'].forEach((position, i) => {
    const y1 = BOTTOM - i * thirdH
    segs.push({ wall: 'left', position, x1: ROOM.x, y1, x2: ROOM.x, y2: y1 - thirdH })
    segs.push({ wall: 'right', position, x1: RIGHT, y1, x2: RIGHT, y2: y1 - thirdH })
  })
  return segs
}

const SEGMENTS = buildSegments()
const keyOf = s => `${s.wall}:${s.position}`

function Door({ seg }) {
  const cx = (seg.x1 + seg.x2) / 2
  const r = 34
  const hinge = cx - r / 2
  return (
    <g className="openings-picker__door">
      <line x1={hinge} y1={BOTTOM} x2={hinge + r} y2={BOTTOM} className="openings-picker__gap" />
      <line x1={hinge} y1={BOTTOM} x2={hinge} y2={BOTTOM - r} />
      <path d={`M ${hinge + r} ${BOTTOM} A ${r} ${r} 0 0 0 ${hinge} ${BOTTOM - r}`} fill="none" strokeDasharray="3 3" />
    </g>
  )
}

function Window({ seg }) {
  const horizontal = seg.y1 === seg.y2
  const inset = 10
  const lines = [-3, 0, 3].map(off => horizontal
    ? { x1: Math.min(seg.x1, seg.x2) + inset, x2: Math.max(seg.x1, seg.x2) - inset, y1: seg.y1 + off, y2: seg.y1 + off }
    : { x1: seg.x1 + off, x2: seg.x1 + off, y1: Math.max(seg.y1, seg.y2) - inset, y2: Math.min(seg.y1, seg.y2) + inset })
  return (
    <g className="openings-picker__window">
      <line {...lines[1]} className="openings-picker__gap" />
      {lines.map((l, i) => <line key={i} {...l} />)}
    </g>
  )
}

export default function OpeningsPicker({ onSubmit, disabled }) {
  const [step, setStep] = useState('door')
  const [door, setDoor] = useState(null)
  const [windows, setWindows] = useState([])

  function handleSegment(seg) {
    if (disabled) return
    if (step === 'door') {
      if (seg.wall !== 'bottom') return
      setDoor(seg)
      setWindows(ws => ws.filter(w => keyOf(w) !== keyOf(seg)))
      setStep('windows')
    } else {
      if (door && keyOf(seg) === keyOf(door)) return
      setWindows(ws => ws.some(w => keyOf(w) === keyOf(seg))
        ? ws.filter(w => keyOf(w) !== keyOf(seg))
        : [...ws, seg])
    }
  }

  function handleDone() {
    const openings = [
      { type: 'door', wall: 'bottom', position: door.position },
      ...windows.map(w => ({ type: 'window', wall: w.wall, position: w.position }))
    ]
    const windowText = windows.length
      ? windows.map(w => `${WALL_WORDS[w.wall]} (${POSITION_WORDS[w.position]})`).join('; ')
      : 'none'
    onSubmit(`Door: ${POSITION_WORDS[door.position]} of the wall I walk in through. Windows: ${windowText}.`, openings)
  }

  function isClickable(seg) {
    if (step === 'door') return seg.wall === 'bottom'
    return !(door && keyOf(seg) === keyOf(door))
  }

  return (
    <div className="openings-picker">
      <p className="openings-picker__prompt">
        {step === 'door'
          ? 'Imagine standing in the doorway. Tap where the door is on the entrance wall.'
          : 'Now tap every wall section that has a window, then press Done.'}
      </p>

      <svg viewBox="0 0 260 226" className="openings-picker__room" role="img"
           aria-label="Room seen from above. The entrance wall is at the bottom.">
        <rect x={ROOM.x} y={ROOM.y} width={ROOM.w} height={ROOM.h} className="openings-picker__floor" />

        <text x={130} y={20} className="openings-picker__label">Wall opposite the door</text>
        <text x={130} y={BOTTOM + 30} className="openings-picker__label openings-picker__label--strong">
          Entrance wall · you walk in here ↑
        </text>
        <text x={22} y={ROOM.y + ROOM.h / 2} className="openings-picker__label"
              transform={`rotate(-90 22 ${ROOM.y + ROOM.h / 2})`}>Left wall</text>
        <text x={238} y={ROOM.y + ROOM.h / 2} className="openings-picker__label"
              transform={`rotate(90 238 ${ROOM.y + ROOM.h / 2})`}>Right wall</text>

        {SEGMENTS.map(seg => (
          <line key={`wall-${keyOf(seg)}`} x1={seg.x1} y1={seg.y1} x2={seg.x2} y2={seg.y2}
                className="openings-picker__wall" />
        ))}

        {door && <Door seg={door} />}
        {windows.map(w => <Window key={`win-${keyOf(w)}`} seg={w} />)}

        {SEGMENTS.filter(isClickable).map(seg => (
          <line key={`hit-${keyOf(seg)}`} x1={seg.x1} y1={seg.y1} x2={seg.x2} y2={seg.y2}
                className={`openings-picker__hit${windows.some(w => keyOf(w) === keyOf(seg)) ? ' openings-picker__hit--selected' : ''}`}
                onClick={() => handleSegment(seg)}>
            <title>{`${WALL_WORDS[seg.wall]}, ${POSITION_WORDS[seg.position]}`}</title>
          </line>
        ))}
      </svg>

      <div className="openings-picker__actions">
        {step === 'windows' && (
          <>
            <button className="btn" onClick={handleDone} disabled={disabled}>
              Done{windows.length === 0 ? ' (no windows)' : ''}
            </button>
            <button className="btn-secondary openings-picker__small" onClick={() => setStep('door')} disabled={disabled}>
              Move door
            </button>
          </>
        )}
        <button className="btn-secondary openings-picker__small" disabled={disabled}
                onClick={() => onSubmit("I'm not sure where the door and windows are.", [])}>
          I'm not sure
        </button>
      </div>
    </div>
  )
}
