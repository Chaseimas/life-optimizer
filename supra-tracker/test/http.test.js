const test = require('node:test');
const assert = require('node:assert');
const http = require('node:http');
const { politeFetch, _resetThrottle } = require('../src/http');

test('politeFetch: sends browser UA and throttles same-host requests', async () => {
  let uas = [];
  let times = [];
  const srv = http.createServer((req, res) => {
    uas.push(req.headers['user-agent']);
    times.push(Date.now());
    res.end('ok');
  });
  await new Promise((r) => srv.listen(0, r));
  const url = `http://127.0.0.1:${srv.address().port}/`;
  _resetThrottle({ delayMs: 300, jitterMs: 0 }); // shrink delay for the test
  await politeFetch(url);
  await politeFetch(url);
  srv.close();
  assert.match(uas[0], /Mozilla/);
  // generous margin: Windows timers can fire a few ms early
  assert.ok(times[1] - times[0] >= 250, `gap was ${times[1] - times[0]}ms`);
});
