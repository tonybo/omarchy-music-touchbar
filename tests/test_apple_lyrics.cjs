const test = require('node:test'); const assert = require('node:assert/strict'); const vm = require('node:vm'); const fs = require('node:fs'); const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'../patches/apple-lyrics/lyrics-main.js'),'utf8');
function harness(api) {
  const attributes = new Map(); let tick; let track = {id:'123',title:'Song',artist:'Artist',album:'Album'};
  const instance = {storefrontId:'fr', nowPlayingItem:{}, api:{music:api}};
  const context = {MusicKit:{getInstance:()=>instance},OmarchyAppleMusicPlayer:{serializePlayer:()=>({ready:true,nowPlaying:track,time:12,duration:200,playing:true,loading:false})},document:{documentElement:{setAttribute:(key,value)=>attributes.set(key,value)},dispatchEvent(){}},Event:class{},Date,setInterval:f=>(tick=f,1),clearInterval(){},setTimeout(){},window:{addEventListener(){}}};
  vm.runInNewContext(source,context);
  return {tick:()=>tick(), track:t=>track=t, packet:()=>JSON.parse(attributes.get('data-touchbar-apple-lyrics'))};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
test('fetches lyrics using existing player API and sends no credentials',async()=>{
  const urls=[]; const h=harness(async url=>{urls.push(url);return {data:{data:[{attributes:{ttml:'<tt xmlns="test"><body/></tt>'}}]}}});
  await settle();h.tick();assert.equal(h.packet().status,'ready');assert.equal(h.packet().position,12);
  assert.deepEqual(urls,['/v1/catalog/fr/songs/123/syllable-lyrics']);
  assert.deepEqual(Object.keys(h.packet()).sort(),['duration','paused','position','schema','status','track','ttml']);
});
test('falls back to line lyrics and avoids repeated requests on heartbeat',async()=>{
  const urls=[];const h=harness(async url=>{urls.push(url);return url.endsWith('/lyrics')?{data:{data:[{attributes:{ttml:'<tt><body/></tt>'}}]}}:{data:{data:[]}}});
  await settle();h.tick();h.tick();assert.equal(h.packet().status,'ready');assert.equal(urls.length,2);
});
test('discards lyrics belonging to the previous song',async()=>{
  const pending=[];const h=harness(()=>new Promise(resolve=>pending.push(resolve)));
  h.track({id:'456',title:'Next',artist:'Artist',album:'Album'});h.tick();
  pending[0]({data:{data:[{attributes:{ttml:'<tt><body>old</body></tt>'}}]}});await settle();h.tick();
  assert.equal(h.packet().track.id,'456');assert.equal(h.packet().ttml,'');
  pending[1]({data:{data:[{attributes:{ttml:'<tt><body>new</body></tt>'}}]}});await settle();h.tick();assert.match(h.packet().ttml,/new/);
});
test('API failures leave a retriable fallback, not stale lyrics',async()=>{
  const h=harness(async()=>{throw new Error('not available')});await settle();h.tick();assert.equal(h.packet().status,'error');assert.equal(h.packet().ttml,'');
});
