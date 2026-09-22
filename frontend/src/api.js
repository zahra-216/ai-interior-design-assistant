const AGENT1_URL = 'http://127.0.0.1:8001'
const AGENT2_URL = 'http://127.0.0.1:8002'
const AGENT3_URL = 'http://127.0.0.1:8003'
const AGENT4_URL = 'http://127.0.0.1:8004'

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(`Request failed (${res.status}): ${detail}`)
  }
  return res.json()
}

async function getJSON(url) {
  const res = await fetch(url)
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(`Request failed (${res.status}): ${detail}`)
  }
  return res.json()
}

export function signup(username, password) {
  return postJSON(`${AGENT1_URL}/signup`, { username, password })
}

export function login(username, password) {
  return postJSON(`${AGENT1_URL}/login`, { username, password })
}

export function getChatHistory(userId) {
  return getJSON(`${AGENT1_URL}/chat-history/${userId}`)
}

// Agent 1 — Requirement Gathering
// openings: exact door/window picks from the room picker (optional)
export function sendChatMessage(userId, message, openings = null) {
  const body = { user_id: userId, message }
  if (openings) body.openings = openings
  return postJSON(`${AGENT1_URL}/chat`, body)
}

export function getRequirements(userId) {
  return getJSON(`${AGENT1_URL}/requirements/${userId}`)
}

// Agent 2 — Design Generation
export function generateDesign(requirements) {
  return postJSON(`${AGENT2_URL}/generate-design`, requirements)
}

export function reviseDesign(userId, originalRequirements, changeText) {
  return postJSON(`${AGENT2_URL}/revise-design`, {
    user_id: userId,
    original_requirements: originalRequirements,
    change_text: changeText
  })
}

export function getDesignHistory(userId) {
  return getJSON(`${AGENT2_URL}/design-history/${userId}`)
}

// Agent 3 — Furniture Search
export function searchFurniture(layoutImagePath, furnitureNeeded) {
  return postJSON(`${AGENT3_URL}/search-furniture`, {
    layout_image_path: layoutImagePath,
    furniture_needed: furnitureNeeded,
    include_missing: true
  })
}

// Agent 4 — Cost Estimation
export function estimateCost(products, budget) {
  return postJSON(`${AGENT4_URL}/estimate-cost`, { products, budget })
}

export function optimizeBudget(products, budget, preferences) {
  return postJSON(`${AGENT4_URL}/optimize-budget`, { products, budget, preferences })
}

export function deleteConversation(userId) {
  return fetch(`${AGENT1_URL}/conversation/${userId}`, { method: 'DELETE' }).then(r => r.json())
}

export function deleteDesigns(userId) {
  return fetch(`${AGENT2_URL}/design-history/${userId}`, { method: 'DELETE' }).then(r => r.json())
}
