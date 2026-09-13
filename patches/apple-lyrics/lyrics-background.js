"use strict"
let nativePort = null
let reconnectAt = 0
chrome.runtime.onMessage.addListener(function (message, sender, respond) {
  if (sender.id !== chrome.runtime.id || !sender.tab || sender.frameId !== 0
      || !/^https:\/\/music\.apple\.com\//.test(sender.url || "")
      || !message || message.type !== "touchbar-apple-lyrics") return
  const packet = message.packet
  if (!packet || packet.schema !== 1 || JSON.stringify(packet).length > 540000) return
  try {
    if (!nativePort) {
      if (Date.now() < reconnectAt) { respond({ ok: false }); return }
      nativePort = chrome.runtime.connectNative("com.omarchy.touchbar_apple_lyrics")
      nativePort.onDisconnect.addListener(function () {
        void chrome.runtime.lastError
        nativePort = null; reconnectAt = Date.now() + 5000
      })
    }
    nativePort.postMessage(packet)
    respond({ ok: true })
  } catch (_) {
    nativePort = null; reconnectAt = Date.now() + 5000
    respond({ ok: false })
  }
})
