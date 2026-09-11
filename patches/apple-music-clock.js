    const snapshot = model.serializePlayer(instance)
    // HLS's underlying media element can expose an infinite duration or a
    // segment clock. Publish MusicKit's song clock for desktop/MPRIS clients.
    if (globalThis.navigator && navigator.mediaSession && navigator.mediaSession.setPositionState) {
      try {
        if (snapshot.ready && snapshot.nowPlaying && Number.isFinite(snapshot.duration) && snapshot.duration > 0
            && Number.isFinite(snapshot.time)) {
          navigator.mediaSession.setPositionState({
            duration: snapshot.duration,
            position: Math.min(snapshot.duration, Math.max(0, snapshot.time)),
            playbackRate: 1
          })
          navigator.mediaSession.playbackState = snapshot.playing && !snapshot.loading ? "playing" : "paused"
        } else {
          navigator.mediaSession.setPositionState({})
        }
      } catch (_) {
        // Keep playback and the in-app UI available if a browser rejects it.
      }
    }
    const state = JSON.stringify(snapshot)
