// Run with: node tests/keyboard_controls.cjs (from the project directory).
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(path.join(__dirname, '../web/templates/game/index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1]
  .replace('setInterval(poll, 80); poll(); draw();', '');
let now = 0;
const handlers = {}, nodes = {}, intervals = [], requests = [];
function node(id) {
  return nodes[id] ||= {style: {}, value: '80', events: {}, getContext: () => ({}),
    addEventListener(name, fn) { this.events[name] = fn; }};
}
const context = vm.createContext({
  performance: {now: () => now},
  window: {addEventListener: (name, fn) => handlers[name] = fn},
  document: {getElementById: node, addEventListener() {}},
  setInterval: fn => intervals.push(fn),
  fetch: async (url, options) => {
    requests.push({url, ...JSON.parse(options?.body || '{}')});
    return {ok: true, json: async () => ({ok: true})};
  },
});
vm.runInContext(script, context);
const read = code => vm.runInContext(code, context);
const event = (key, repeat = false) => ({key, repeat, preventDefault() {}});
const flush = () => new Promise(setImmediate);
(async () => {
  for (const [ms, speed] of [[100, 60], [150, 40], [300, 20], [600, 10], [2000, 3], [0, 250]]) {
    assert.equal(read(`speedForDuration(${ms})`), speed);
  }
  handlers.keydown(event('a'));
  await flush();
  now = 50;
  handlers.keydown(event('a', true));
  assert.equal(read("sensorSpeed('a')"), 0, 'holding must not fire');
  now = 100;
  handlers.keyup(event('A'));
  await flush();
  assert.equal(read("sensorSpeed('a')"), 60, '100ms press uses original keydown');
  assert.equal(requests.filter(r => r.sensor === 0).at(-1).speed, 60);
  now = 301;
  intervals[0]();
  await flush();
  assert.equal(read("sensorSpeed('a')"), 0);
  assert.equal(requests.filter(r => r.sensor === 0).at(-1).speed, 0, 'pulse resets');
  const count = requests.length;
  handlers.keyup(event('a'));
  await flush();
  assert.equal(requests.length, count, 'unmatched release must not swing');
  now = 1000;
  handlers.keydown(event('a'));
  now = 1500;
  handlers.keydown(event('ArrowRight'));
  now = 1600;
  handlers.keyup(event('a'));
  handlers.keyup(event('ArrowRight'));
  assert.equal(read("sensorSpeed('a')"), 10);
  assert.equal(read("sensorSpeed('ArrowRight')"), 60, 'independent player timers');
  handlers.blur();
  await flush();
  assert.equal(read('heldSince.size'), 0);
  assert.equal(read("sensorSpeed('ArrowRight')"), 0);
  assert.equal(requests.filter(r => r.sensor === 3).at(-1).speed, 0);
  now = 2000;
  handlers.keydown(event('d'));
  handlers.blur();
  now = 2100;
  handlers.keyup(event('d'));
  assert.equal(read("sensorSpeed('d')"), 0, 'blur cancels unfinished press');
  const slider = node('distance-2');
  slider.events.pointerdown();
  now = 2200;
  slider.value = '70';
  slider.events.input();
  assert.ok(Math.abs(read('inputSpeed(2)') - 100) < 0.001, 'slider still uses distance/time');
  await flush();
  console.log('PASS: inverse duration, repeat suppression, release-only swing, pulse reset, independent keys, blur, sliders');
})().catch(error => { console.error(error); process.exitCode = 1; });
