(function () {
  "use strict"
  const attribute = "data-touchbar-apple-lyrics"
  const event = "touchbar-apple-lyrics"
  let key = "", ttml = "", status = "unavailable", retryAt = 0, generation = 0
  let busy = false
  function current() {
    const instance = globalThis.MusicKit && MusicKit.getInstance()
    const model = globalThis.OmarchyAppleMusicPlayer
    if (!instance || !model) return null
    const snapshot = model.serializePlayer(instance)
    if (!snapshot.ready || !snapshot.nowPlaying) return null
    return { instance, snapshot }
  }
  function extract(response) {
    const body = response && response.data
    const rows = Array.isArray(body) ? body : body && body.data
    for (const row of rows || []) {
      const value = row && row.attributes && row.attributes.ttml
      if (typeof value === "string" && value.length < 524288 && /<tt[\s>]/.test(value)) return value
    }
    return ""
  }
  async function load(instance, id, storefront, epoch) {
    let result = "", failed = false
    try {
      for (const relation of ["syllable-lyrics", "lyrics"]) {
        if (epoch !== generation) return
        try {
          // The signed-in player's API manages authorization inside the page.
          // Never read, copy or send its developer/user tokens to the native host.
          const request = instance.api.music(`/v1/catalog/${storefront}/songs/${id}/${relation}`)
          const response = await Promise.race([request, new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), 12000))])
          result = extract(response)
          if (result) break
        } catch (_) { failed = true }
      }
    } finally {
      if (epoch === generation) {
        ttml = result
        status = result ? "ready" : failed ? "error" : "unavailable"
        retryAt = Date.now() + 60000
        busy = false
      }
    }
  }
  function tick() {
    try {
      const live = current()
      if (!live || !document.documentElement) return
      const { instance, snapshot } = live
      const track = snapshot.nowPlaying
      const next = JSON.stringify([track.id, track.title, track.artist, track.album])
      if (next !== key) {
        key = next; ttml = ""; status = "unavailable"; retryAt = 0; busy = false; generation++
      }
      const raw = instance.nowPlayingItem || {}
      const attributes = raw.attributes || raw.item && raw.item.attributes || {}
      const params = raw.playParams || attributes.playParams || {}
      const id = String(params.catalogId || params.id || track.id || "")
      const storefront = String(instance.storefrontId || "")
      if (!ttml && !busy && Date.now() >= retryAt && /^\d+$/.test(id) && /^[a-z]{2}$/.test(storefront)
          && instance.api && typeof instance.api.music === "function") {
        busy = true; status = "loading"
        load(instance, id, storefront, generation).catch(() => {})
      }
      const packet = { schema: 1, track: { id: track.id, title: track.title, artist: track.artist, album: track.album },
        position: snapshot.time, duration: snapshot.duration, paused: !snapshot.playing || snapshot.loading,
        status, ttml }
      document.documentElement.setAttribute(attribute, JSON.stringify(packet))
      document.dispatchEvent(new Event(event))
    } catch (_) { /* A changing player must never interrupt music. */ }
  }
  const timer = setInterval(tick, 500)
  tick()
  window.addEventListener("pagehide", () => clearInterval(timer), { once: true })
})()
