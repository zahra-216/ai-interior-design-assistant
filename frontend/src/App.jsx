import { useState, useEffect, useRef } from 'react'
import LoginScreen from './components/LoginScreen'
import ChatPanel from './components/ChatPanel'
import FloorPlanPanel from './components/FloorPlanPanel'
import FurnitureSchedule from './components/FurnitureSchedule'
import CostSummary from './components/CostSummary'
import RoomsMenu from './components/RoomsMenu'
import {
  generateDesign, reviseDesign, searchFurniture, estimateCost, optimizeBudget,
  getChatHistory, getDesignHistory, deleteDesigns, setAuth,
  getProjects, createProject, deleteProject
} from './api'
import './App.css'

// "Request failed (503): {"detail":"The AI is busy..."}" -> "The AI is busy..."
function errorDetail(err, fallback) {
  const match = /\{.*\}/s.exec(err?.message || '')
  if (match) {
    try {
      const detail = JSON.parse(match[0]).detail
      if (typeof detail === 'string') return detail
    } catch { /* not JSON */ }
  }
  return fallback
}

// Accepted "Fit to my budget" swaps are remembered per room (they survive a refresh and
// later layout changes). A swap only applies while the item still gets the same original product.
const swapsKey = (userId, projectId) => `swaps:${userId}:${projectId}`

function loadSwaps(userId, projectId) {
  try {
    return JSON.parse(localStorage.getItem(swapsKey(userId, projectId))) || []
  } catch {
    return []
  }
}

// The room that was open last, so a refresh reopens it
const projectKey = userId => `project:${userId}`

function storedProject(userId) {
  try {
    return Number(localStorage.getItem(projectKey(userId))) || null
  } catch {
    return null
  }
}

function rememberProject(userId, projectId) {
  try {
    localStorage.setItem(projectKey(userId), String(projectId))
  } catch { /* ignore */ }
}

function applySwaps(products, swaps) {
  return products.map(p => {
    // Follow chains (A -> B accepted earlier, then B -> C)
    for (let hops = 0; hops < 5; hops++) {
      const swap = swaps.find(s => s.item === p.item && s.original_product === p.product_name)
      if (!swap) break
      p = {
        ...p,
        product_name: swap.optimized_product,
        price: swap.optimized_price,
        retailer: swap.retailer,
        product_url: swap.product_url,
        note: swap.note,
        match_score: swap.match_score,
        swapped_from: p.swapped_from || swap.original_product
      }
    }
    return p
  })
}

// Logged-in session: { userId, username, token, expiresAt }. Expired sessions are dropped,
// and so is the old format (a bare 'userId' with no token), which forces a proper login.
const SESSION_KEY = 'session'

function loadSession() {
  try {
    const saved = JSON.parse(localStorage.getItem(SESSION_KEY))
    if (saved?.token && saved.expiresAt * 1000 > Date.now()) return saved
  } catch { /* corrupt or unavailable storage */ }
  try {
    localStorage.removeItem(SESSION_KEY)
    localStorage.removeItem('userId')
  } catch { /* ignore */ }
  return null
}

export default function App() {
  const [session, setSession] = useState(() => {
    const saved = loadSession()
    setAuth(saved?.token)
    return saved
  })
  const [loginNotice, setLoginNotice] = useState(null)
  const userId = session?.userId || null
  const [projectId, setProjectId] = useState(null)
  // Set by a real login/signup: open a fresh room. A page refresh reopens the last room instead.
  const startFresh = useRef(false)
  const [projects, setProjects] = useState([])
  const [chatKey, setChatKey] = useState(0)
  const [initialMessages, setInitialMessages] = useState(null)
  const [requirements, setRequirements] = useState(null)
  const [design, setDesign] = useState(null)
  const [products, setProducts] = useState(null)
  const [cost, setCost] = useState(null)
  const [proposal, setProposal] = useState(null)

  const [restoring, setRestoring] = useState(true)
  const [designLoading, setDesignLoading] = useState(false)
  const [productsLoading, setProductsLoading] = useState(false)
  const [costLoading, setCostLoading] = useState(false)
  const [optimizing, setOptimizing] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!session) {
      setRestoring(false)
      return
    }
    setAuth(session.token, () => handleLogout('Your session has expired. Please log in again.'))
    restoreSession()
    // Log out when the token expires, even if the tab stays open
    const timer = setTimeout(() => handleLogout('Your session has expired. Please log in again.'),
      Math.max(0, session.expiresAt * 1000 - Date.now()))
    return () => clearTimeout(timer)
  }, [session, chatKey])

  async function refreshProjects() {
    try {
      const list = (await getProjects(userId)).projects || []
      setProjects(list)
      return list
    } catch (err) {
      console.error('Could not load rooms', err)
      return null
    }
  }

  // Open the remembered room (or the latest one, or a brand new one) and restore it
  async function restoreSession() {
    setRestoring(true)
    try {
      const list = await refreshProjects() || []
      let current = storedProject(userId)
      if (!list.some(p => p.id === current)) current = list[0]?.id ?? null
      if (startFresh.current) {
        // New chat after logging in (the backend re-uses an empty room instead of adding another)
        startFresh.current = false
        current = (await createProject(userId)).project_id
        await refreshProjects()
      } else if (current === null) {
        current = (await createProject(userId)).project_id
        await refreshProjects()
      }
      rememberProject(userId, current)
      setProjectId(current)

      const res = await getChatHistory(userId, current)

      if (res.messages && res.messages.length > 0) {
        setInitialMessages(res.messages.map(m => ({
          role: m.role, content: m.content, widget: m.widget, suggestions: m.suggestions
        })))
      } else {
        setInitialMessages(null)
      }

      const req = res.requirements
      const isComplete = res.requirements_complete ?? (req && Object.values(req).every(v => v !== null))

      if (isComplete) {
        setRequirements(req)

        const history = await getDesignHistory(userId, current)
        if (history.designs && history.designs.length > 0) {
          const latest = history.designs[0]
          const restoredDesign = {
            layout_image_path: latest.image_path,
            furniture_needed: latest.layout_data.furniture_needed || latest.layout_data.furniture.map(f => ({
              item: f.item,
              style: req.style,
              qty: 1,
              color: req.color_preference,
              audience: req.occupant
            })),
            warnings: latest.layout_data.warnings || []
          }
          setDesign(restoredDesign)
          await fetchFurnitureAndCost(restoredDesign, req, current)
        }
      }
    } catch (err) {
      console.error('Could not restore session', err)
    } finally {
      setRestoring(false)
    }
  }

  function handleAuth(res) {
    const next = { userId: res.user_id, username: res.username, token: res.token, expiresAt: res.expires_at }
    try {
      localStorage.setItem(SESSION_KEY, JSON.stringify(next))
    } catch { /* storage unavailable: login lasts until the tab closes */ }
    setAuth(next.token)
    setLoginNotice(null)
    startFresh.current = true
    setSession(next)
  }

  function resetWorkspace() {
    setInitialMessages(null)
    setRequirements(null)
    setDesign(null)
    setProducts(null)
    setCost(null)
    setProposal(null)
    setError(null)
  }

  function handleLogout(notice = null) {
    try {
      localStorage.removeItem(SESSION_KEY)
    } catch { /* ignore */ }
    setAuth(null)
    resetWorkspace()
    setLoginNotice(notice)
    setSession(null)
  }

  // Switch rooms: remember the choice and let restoreSession load it
  function openProject(id) {
    rememberProject(userId, id)
    resetWorkspace()
    setChatKey(k => k + 1)
  }

  // New chat = a new room. Earlier rooms stay in "My rooms".
  async function handleNewChat() {
    try {
      const { project_id } = await createProject(userId)
      openProject(project_id)
    } catch (err) {
      console.error(err)
      setError(errorDetail(err, 'Could not start a new room. Please try again.'))
    }
  }

  async function handleDeleteProject(id) {
    try {
      await deleteDesigns(userId, id)
      await deleteProject(id)
      try { localStorage.removeItem(swapsKey(userId, id)) } catch { /* ignore */ }
      if (id === projectId) {
        try { localStorage.removeItem(projectKey(userId)) } catch { /* ignore */ }
        resetWorkspace()
        setChatKey(k => k + 1)  // reopens the latest remaining room (or a new one)
      } else {
        await refreshProjects()
      }
    } catch (err) {
      console.error(err)
      setError(errorDetail(err, 'Could not delete that room.'))
    }
  }

  if (!session) {
    return <LoginScreen onAuth={handleAuth} notice={loginNotice} />
  }

  async function handleRequirementsComplete(reqs) {
    setRequirements(reqs)
    setDesignLoading(true)
    try {
      refreshProjects()  // the room now has a title and is "Designed"
      const designRes = await generateDesign({ user_id: userId, ...reqs, project_id: projectId })
      setDesign(designRes)
      await fetchFurnitureAndCost(designRes, reqs)
    } catch (err) {
      console.error(err)
      setError(errorDetail(err, 'Could not generate your design. Check that all servers are running.'))
    } finally {
      setDesignLoading(false)
    }
  }

  // Context for each item (colour theme, size, who the room is for, priority) from Agent 2
  function itemContext(designRes, item) {
    return (designRes?.furniture_needed || []).find(f => f.item === item) || {}
  }

  async function fetchFurnitureAndCost(designRes, reqs, room = projectId) {
    setProposal(null)
    setProductsLoading(true)
    try {
      const matched = await searchFurniture(designRes.layout_image_path, designRes.furniture_needed)
      const withSwaps = applySwaps(matched, loadSwaps(userId, room))
      setProducts(withSwaps)
      setProductsLoading(false)
      await updateCost(withSwaps, designRes, reqs.budget)
    } catch (err) {
      console.error(err)
      setError('Could not find matching furniture or estimate cost.')
    } finally {
      setProductsLoading(false)
    }
  }

  // Only products we actually found can be costed; missing items are listed separately
  function costableProducts(list, designRes) {
    return list.filter(p => p.found !== false).map(p => {
      const ctx = itemContext(designRes, p.item)
      return {
        item: p.item,
        product_name: p.product_name,
        price: p.price,
        quantity: p.quantity || 1,
        priority: ctx.priority || 'flexible',
        style: ctx.style || undefined,
        retailer: p.retailer,
        match_score: p.match_score,
        product_url: p.product_url,
        color: ctx.color || undefined,
        size: ctx.size || undefined,
        audience: ctx.audience || undefined
      }
    })
  }

  async function updateCost(list, designRes, budget) {
    const costable = costableProducts(list, designRes)
    if (costable.length === 0) {
      setCost(null)
      return
    }
    setCostLoading(true)
    try {
      setCost(await estimateCost(costable, budget))
    } finally {
      setCostLoading(false)
    }
  }

  async function handleRevise(changeText) {
    if (!requirements) return
    setDesignLoading(true)
    try {
      const designRes = await reviseDesign(userId, { user_id: userId, ...requirements }, changeText, projectId)
      // A revision can change the budget, colours or style; keep them in sync here too
      const updatedReqs = { ...requirements, ...(designRes.requirement_updates || {}) }
      setRequirements(updatedReqs)
      setDesign(designRes)
      await fetchFurnitureAndCost(designRes, updatedReqs)
    } catch (err) {
      console.error(err)
      setError(errorDetail(err, 'Could not update the layout. Please try again.'))
    } finally {
      setDesignLoading(false)
    }
  }

  async function handleOptimize() {
    if (!products || !requirements) return
    setOptimizing(true)
    try {
      setProposal(await optimizeBudget(costableProducts(products, design), requirements.budget))
    } catch (err) {
      console.error(err)
      setError(errorDetail(err, 'Could not look for cheaper options right now.'))
    } finally {
      setOptimizing(false)
    }
  }

  async function handleApplyProposal() {
    if (!proposal) return
    const swaps = [...loadSwaps(userId, projectId), ...proposal.optimized_items]
    try {
      localStorage.setItem(swapsKey(userId, projectId), JSON.stringify(swaps))
    } catch { /* storage unavailable: swaps just won't survive a refresh */ }
    const swapped = applySwaps(products, proposal.optimized_items)
    setProducts(swapped)
    setProposal(null)
    await updateCost(swapped, design, requirements.budget)
  }

  return (
    <div className="app">
      <header className="app__header">
        <span className="app__wordmark">Studio</span>
        <span className="app__tagline">AI interior design, made for Sri Lankan homes</span>

        <div className="app__controls">
          <div className="app__account">
            <span className="app__user-label">Signed in as</span>
            <span className="app__user">{session.username}</span>
            <button className="app__logout" onClick={() => handleLogout()}>Log out</button>
          </div>
          <div className="app__actions">
            {/* Only rooms that were fully designed count as history */}
            <RoomsMenu
              projects={projects.filter(p => p.status === 'complete')}
              currentId={projectId}
              onOpen={openProject}
              onDelete={handleDeleteProject}
              onRefresh={refreshProjects}
            />
            <button className="app__action app__action--primary" onClick={handleNewChat}>
              New chat
            </button>
          </div>
        </div>
      </header>

      {error && (
        <div className="app__error" onClick={() => setError(null)}>
          {error}
        </div>
      )}

      {restoring ? (
        <div className="app__restoring">Loading your session...</div>
      ) : (
        <main className="app__body">
          <div className="app__chat">
            <ChatPanel
              key={chatKey}
              userId={userId}
              projectId={projectId}
              initialMessages={initialMessages}
              onRequirementsComplete={handleRequirementsComplete}
              locked={!!requirements}
            />
          </div>

          <div className="app__workspace">
            <div className="app__plan">
              <FloorPlanPanel design={design} loading={designLoading} onRevise={handleRevise} />
            </div>
            <FurnitureSchedule products={products} loading={productsLoading} />
            <CostSummary
              cost={cost}
              loading={costLoading}
              proposal={proposal}
              optimizing={optimizing}
              onOptimize={handleOptimize}
              onApply={handleApplyProposal}
              onDismiss={() => setProposal(null)}
            />
          </div>
        </main>
      )}
    </div>
  )
}
