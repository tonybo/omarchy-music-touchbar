(function () {
  "use strict"
  let sending = false, last = 0
  document.addEventListener("touchbar-apple-lyrics", function () {
    if (sending || Date.now() - last < 400) return
    const raw = document.documentElement.getAttribute("data-touchbar-apple-lyrics")
    if (!raw || raw.length > 540000) return
    try {
      const packet = JSON.parse(raw)
      sending = true; last = Date.now()
      chrome.runtime.sendMessage({ type: "touchbar-apple-lyrics", packet }, function () {
        void chrome.runtime.lastError
        sending = false
      })
    } catch (_) { sending = false }
  })
})()
