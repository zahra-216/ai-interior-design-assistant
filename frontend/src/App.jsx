import { useState, useEffect } from 'react'
import LoginScreen from './components/LoginScreen'
import ChatPanel from './components/ChatPanel'
import FloorPlanPanel from './components/FloorPlanPanel'
import FurnitureSchedule from './components/FurnitureSchedule'
import CostSummary from './components/CostSummary'
import {
  generateDesign, reviseDesign, searchFurniture, estimateCost, optimizeBudget,
  getChatHistory, getDesignHistory, deleteConversation, deleteDesigns
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

// Accepted "Fit to my budget" swaps are remembered for the whole session (they survive a
// refresh and later layout changes; New chat clears them). A swap only applies while the
// item still gets the same original product.
const swapsKey = userId => `swaps:${userId}`

function loadSwaps(userId) {
  try {
    return JSON.parse(localStorage.getItem(swapsKey(userId))) || []
  } catch {
    return []
  }
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

export default function App() {
  const [userId, setUserId] = useState(() => localStorage.getItem('userId') || null)
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
    if (!userId) {
      setRestoring(false)
      return
    }
    localStorage.setItem('userId', userId)
    restoreSession()
  }, [userId, chatKey])

  async function restoreSession() {
    setRestoring(true)
    try {
      const res = await getChatHistory(userId)

      if (res.messages && res.messages.length > 0) {
        setInitialMessages(res.messages.map(m => ({ role: m.role, content: m.content, widget: m.widget })))
      } else {
        setInitialMessages(null)
      }

      const req = res.requirements
      const isComplete = res.requirements_complete ?? (req && Object.values(req).every(v => v !== null))

      if (isComplete) {
        setRequirements(req)

        const history = await getDesignHistory(userId)
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
          await fetchFurnitureAndCost(restoredDesign, req)
        }
      }
    } catch (err) {
      console.error('Could not restore session', err)
    } finally {
      setRestoring(false)
    }
  }

  function handleAuth(id) {
    setUserId(id)
  }

  async function handleNewChat() {
    try {
      await deleteConversation(userId)
      await deleteDesigns(userId)
      localStorage.removeItem(swapsKey(userId))
    } catch (err) {
      console.error('Could not clear previous session', err)
    }
    setInitialMessages(null)
    setRequirements(null)
    setDesign(null)
    setProducts(null)
    setCost(null)
    setProposal(null)
    setError(null)
    setChatKey(k => k + 1)
  }

  if (!userId) {
    return <LoginScreen onAuth={handleAuth} />
  }

  async function handleRequirementsComplete(reqs) {
    setRequirements(reqs)
    setDesignLoading(true)
    try {
      const designRes = await generateDesign({ user_id: userId, ...reqs })
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

  async function fetchFurnitureAndCost(designRes, reqs) {
    setProposal(null)
    setProductsLoading(true)
    try {
      const matched = await searchFurniture(designRes.layout_image_path, designRes.furniture_needed)
      const withSwaps = applySwaps(matched, loadSwaps(userId))
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
      const designRes = await reviseDesign(userId, { user_id: userId, ...requirements }, changeText)
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
    const swaps = [...loadSwaps(userId), ...proposal.optimized_items]
    try {
      localStorage.setItem(swapsKey(userId), JSON.stringify(swaps))
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
        <button className="btn-secondary app__new-chat" onClick={handleNewChat}>
          New chat
        </button>
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
