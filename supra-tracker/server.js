const config = require('./src/config');
const { getDb } = require('./src/db');
const { makeStore } = require('./src/store');
const { loadGeo } = require('./src/geo');
const { makeApp } = require('./src/api');
const scheduler = require('./src/scheduler');

const places = loadGeo();
console.log(`[geo] ${places} places loaded`);
const store = makeStore(getDb());
const app = makeApp(store);

app.listen(config.PORT, '127.0.0.1', () => {
  console.log(`Supra Tracker dashboard: http://localhost:${config.PORT}`);
  scheduler.start(store);
});
