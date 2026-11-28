// Minimal Odoo JSON-RPC helper. Usage: const {kw, login} = require('./rpc'); await login(); await kw(model, method, args, kwargs)
const URL = 'https://palawi.rutekebangsaan.com';
let cookie = '';
async function post(path, params) {
  const r = await fetch(URL + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Cookie: cookie },
    body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params }),
  });
  const sc = r.headers.get('set-cookie');
  if (sc) cookie = sc.split(';')[0];
  const j = await r.json();
  if (j.error) {
    const e = new Error(j.error.data && j.error.data.message || j.error.message);
    e.debug = j.error.data && j.error.data.debug;
    throw e;
  }
  return j.result;
}
async function login() {
  return post('/web/session/authenticate', { db: 'odoo18_palawi', login: process.env.ODOO_LOGIN, password: process.env.ODOO_PASSWORD });
}
const CID = 13;
function ctx(extra) { return Object.assign({ allowed_company_ids: [CID], lang: 'en_US', tz: 'Asia/Jakarta' }, extra || {}); }
async function kw(model, method, args = [], kwargs = {}) {
  kwargs = Object.assign({}, kwargs);
  kwargs.context = Object.assign(ctx(), kwargs.context || {});
  return post('/web/dataset/call_kw', { model, method, args, kwargs });
}
module.exports = { login, kw, CID, post };
