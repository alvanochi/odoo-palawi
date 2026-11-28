// Headless Edge screenshot of an Odoo backend URL, logged in via session cookie. Usage: node shot.js <path> <out.png> [waitMs] [height]
const { spawn } = require('child_process');
const path = require('path');
const U = 'https://palawi.rutekebangsaan.com';
const [, , urlPath, out, waitMs = '9000', height = '1800'] = process.argv;
const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const sleep = ms => new Promise(r => setTimeout(r, ms));
setTimeout(() => { console.log('global timeout'); process.exit(2); }, (+process.argv[4] || 9000) + 90000);
(async () => {
  const a = await fetch(U + '/web/session/authenticate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params: { db: 'odoo18_palawi', login: process.env.ODOO_LOGIN, password: process.env.ODOO_PASSWORD } }) });
  const sid = a.headers.get('set-cookie').match(/session_id=([^;]+)/)[1];
  const port = 9333 + Math.floor(Math.random() * 500);
  const prof = path.join(__dirname, 'edgeprof' + port);
  const p = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${prof}`, '--window-size=1440,' + height, '--hide-scrollbars', '--lang=id-ID', 'about:blank'], { stdio: 'ignore' });
  let ver;
  for (let i = 0; i < 40; i++) { try { ver = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json(); if (ver.length) break; } catch (e) { } await sleep(300); }
  const page = ver.find(t => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise(r => ws.onopen = r);
  let id = 0; const pending = {}; const errors = [];
  ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pending[m.id]) { pending[m.id](m); delete pending[m.id]; } if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text); if (m.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(m.params.type)) errors.push(m.params.type + ': ' + m.params.args.map(x => x.value || x.description).join(' ').slice(0, 400)); };
  const send = (method, params = {}) => new Promise(r => { const i = ++id; pending[i] = r; ws.send(JSON.stringify({ id: i, method, params })); setTimeout(() => { if (pending[i]) { delete pending[i]; r({ result: { result: { value: 'timeout' }, data: '' } }); } }, 20000); });
  await send('Runtime.enable'); await send('Network.enable'); await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: +height, deviceScaleFactor: 1, mobile: false });
  const host = new URL(U).hostname;
  await send('Network.setCookie', { name: 'session_id', value: sid, domain: host, path: '/', secure: true, httpOnly: true });
  await send('Network.setCookie', { name: 'cids', value: '13', domain: host, path: '/' });
  await send('Page.navigate', { url: U + urlPath });
  await sleep(+waitMs);
  const ev = await send('Runtime.evaluate', { expression: "(()=>{try{const e=odoo.loader.findErrors();return JSON.stringify(Object.fromEntries(Object.entries(e).map(([k,v])=>[k,v&&v.size!==undefined?[...v]:v])))}catch(x){return 'n/a '+x}})()", returnByValue: true });
  console.log('loader:', ev.result && ev.result.result && ev.result.result.value);
  if (process.env.SCROLL) { const sc = await send('Runtime.evaluate', { expression: "(()=>{const e=document.querySelector('.ss_dash');if(!e)return 'no .ss_dash';e.scrollTop=99999;return JSON.stringify({scrollHeight:e.scrollHeight,clientHeight:e.clientHeight,scrollTop:e.scrollTop})})()", returnByValue: true }); console.log('scroll:', sc.result.result.value); await sleep(800); }
  const shot = await send('Page.captureScreenshot', { format: 'png' });
  require('fs').writeFileSync(out, Buffer.from(shot.result.data, 'base64'));
  console.log('saved', out); if (errors.length) console.log('PAGE ERRORS:\n' + errors.join('\n')); else console.log('no page errors');
  ws.close(); p.kill();
  setTimeout(() => { try { require('fs').rmSync(prof, { recursive: true, force: true }); } catch (e) { } process.exit(0); }, 800);
})().catch(e => { console.error(e); process.exit(1); });
