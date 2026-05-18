/**
 * WebSocket wrapper for chat module.
 * - Exponential backoff reconnection
 * - Heartbeat (ping/pong)
 * - _intentionalClose flag prevents reconnect on manual disconnect
 * - Close code 4001 (auth failure) stops retry
 */
class ChatWebSocket {
  constructor() {
    this.ws = null
    this.reconnectAttempts = 0
    this.maxRetries = 20
    this.handlers = {}
    this.heartbeatTimer = null
    this._intentionalClose = false
  }

  connect(token) {
    this._intentionalClose = false
    this._stopHeartbeat()

    // 清理旧连接，防止旧 onclose 异步触发幽灵重连
    if (this.ws) {
      this.ws.onopen = null
      this.ws.onmessage = null
      this.ws.onclose = null
      this.ws.onerror = null
      if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) {
        this.ws.close(1000)
      }
    }

    const baseUrl = import.meta.env.VITE_APP_BASE_API
    // Build WebSocket URL: handle both absolute (http://...) and relative (/dev-api) base URLs
    let wsUrl
    if (baseUrl.startsWith('http://') || baseUrl.startsWith('https://')) {
      wsUrl = baseUrl.replace(/^http/, 'ws')
    } else {
      // Relative path like /dev-api — use current page host
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      wsUrl = `${proto}//${window.location.host}${baseUrl}`
    }
    this.ws = new WebSocket(`${wsUrl}/entrust/chat/ws?token=Bearer ${token}`)

    this.ws.onopen = () => {
      this.reconnectAttempts = 0
      this._startHeartbeat()
      this._emit('connected', {})
    }

    this.ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        this._emit(msg.type, msg.data)
      } catch (err) { /* ignore invalid JSON */ }
    }

    this.ws.onclose = (event) => {
      this._stopHeartbeat()
      if (this._intentionalClose) return
      // Auth failure (4001) -> do not retry
      if (event.code === 4001) {
        this._emit('auth_failed', {})
        return
      }
      this._reconnect(token)
    }

    this.ws.onerror = () => {} // onclose will handle cleanup
  }

  _emit(type, data) {
    const cbs = this.handlers[type]
    if (cbs) cbs.forEach(cb => cb(data))
  }

  on(type, callback) {
    if (!this.handlers[type]) this.handlers[type] = []
    this.handlers[type].push(callback)
  }

  off(type, callback) {
    if (!this.handlers[type]) return
    if (callback) {
      this.handlers[type] = this.handlers[type].filter(cb => cb !== callback)
    } else {
      delete this.handlers[type]
    }
  }

  sendMessage(data) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'send_message', data }))
    }
  }

  /**
   * Exponential backoff: 1s -> 2s -> 5s -> 10s -> 30s, max maxRetries times.
   */
  _reconnect(token) {
    if (this.reconnectAttempts >= this.maxRetries) {
      this._emit('reconnect_failed', {})
      return
    }
    const delays = [1000, 2000, 5000, 10000, 30000]
    const delay = delays[Math.min(this.reconnectAttempts, delays.length - 1)]
    this.reconnectAttempts++
    setTimeout(() => this.connect(token), delay)
  }

  _startHeartbeat() {
    this._stopHeartbeat()
    this.heartbeatTimer = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'ping' }))
      }
    }, 30000)
  }

  _stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }

  disconnect() {
    this._intentionalClose = true
    this._stopHeartbeat()
    this.ws?.close(1000)
  }
}

export default new ChatWebSocket()
