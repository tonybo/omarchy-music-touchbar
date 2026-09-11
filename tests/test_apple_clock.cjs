const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const patch = fs.readFileSync(path.join(__dirname, '../patches/apple-music-clock.js'), 'utf8');
function publish(snapshot, session) {
  const context = { instance: {}, model: { serializePlayer: () => snapshot }, navigator: { mediaSession: session } };
  vm.runInNewContext(patch, context);
}
test('exports the song clock and clamps its position to the duration', () => {
  let position;
  const session = { setPositionState(value) { position = value; } };
  publish({ ready: true, nowPlaying: {}, duration: 274, time: 80, playing: true }, session);
  assert.equal(position.duration, 274); assert.equal(position.position, 80);
  assert.equal(session.playbackState, 'playing');
  publish({ ready: true, nowPlaying: {}, duration: 274, time: 280, playing: true }, session);
  assert.equal(position.position, 274);
});
test('pauses the exported clock during buffering and clears invalid timing', () => {
  let position;
  const session = { setPositionState(value) { position = value; } };
  publish({ ready: true, nowPlaying: {}, duration: 274, time: 80, playing: true, loading: true }, session);
  assert.equal(session.playbackState, 'paused');
  publish({ ready: true, nowPlaying: {}, duration: Infinity, time: 80 }, session);
  assert.equal(Object.keys(position).length, 0);
});
test('unsupported media-session APIs cannot stop the player bridge', () => {
  assert.doesNotThrow(() => publish({ ready: true, nowPlaying: {}, duration: 274, time: 80 }, {
    setPositionState() { throw new Error('unsupported'); }
  }));
});
