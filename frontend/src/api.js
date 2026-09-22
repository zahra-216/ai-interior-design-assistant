const AGENT1_URL = 'http://127.0.0.1:8001'
const AGENT2_URL = 'http://127.0.0.1:8002'
const AGENT3_URL = 'http://127.0.0.1:8003'
const AGENT4_URL = 'http://127.0.0.1:8004'

// Login token from Agent 1. Agents 1 and 2 hold user data, so they need it.
let authToken = null
let onUnauthorized = () => {}

export function setAuth(token, handleUnauthorized) {
  authToken = token || null
  if (handleUnauthorized) onUnauthorized = handleUnauthorized
}

const needsAuth = url => url.startsWith(AGENT1_URL) || url.startsWith(AGENT2_URL)

async function request(url, { method = 'GET', body } = {}) {
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (authToken && needsAuth(url)) headers.Authorization = `Bearer ${authToken}`

  const res = await fetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined
  })
  if (!res.ok) {
    const detail = await res.text()
    if (res.status === 401 && authToken && needsAuth(url)) {
      onUnauthorized()  // expired or invalid session: back to the login screen
    }
    throw new Error(`Request failed (${res.status}): ${detail}`)
  }
  return res.json()
}

const postJSON = (url, body) => request(url, { method: 'POST', body })
const getJSON = url => request(url)

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
  return request(`${AGENT1_URL}/conversation/${userId}`, { method: 'DELETE' })
}

export function deleteDesigns(userId) {
  return request(`${AGENT2_URL}/design-history/${userId}`, { method: 'DELETE' })
}
