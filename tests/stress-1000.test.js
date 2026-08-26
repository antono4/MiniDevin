// Stress test: 1000 pertanyaan melalui pipeline send() aplikasi.
// puter.ai.chat di-stub karena 1000 panggilan API nyata tidak feasible
// (rate limit + waktu). Yang diuji: rendering DOM, storage, memori, error.
const { chromium } = require('playwright');
const assert = require('assert');

const TOTAL = 1000;

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  await page.goto('http://localhost:12000/index.html', { waitUntil: 'networkidle' });

  // Stub hanya lapisan jaringan AI; seluruh logika aplikasi tetap nyata
  await page.evaluate(() => {
    window.puter = window.puter || {};
    window.puter.ai = window.puter.ai || {};
    window.puter.ai.chat = async function* (messages) {
      const q = messages[messages.length - 1].content;
      yield { text: 'Jawaban untuk: ' + String(q).slice(0, 60) };
    };
    window.puter.ai.listModels = async () => ['test-model'];
    window.puter.auth = { isSignedIn: () => false, getUser: async () => null };
    window.puter.kv = { get: async () => null, set: async () => true };
  });

  const t0 = Date.now();
  let failed = 0;

  for (let i = 1; i <= TOTAL; i++) {
    const ok = await page.evaluate(async (n) => {
      try {
        const input = document.getElementById('input');
        input.value = 'Pertanyaan uji nomor ' + n;
        await send();
        // tunggu hingga tidak busy (stream selesai)
        for (let w = 0; w < 100 && document.getElementById('send-btn').classList.contains('stop'); w++) {
          await new Promise(r => setTimeout(r, 10));
        }
        return true;
      } catch (e) { return String(e); }
    }, i);
    if (ok !== true) { failed++; if (failed <= 3) console.log('GAGAL #' + i + ':', ok); }
    if (i % 100 === 0) console.log('progress:', i + '/' + TOTAL);
  }

  const elapsed = ((Date.now() - t0) / 1000).toFixed(1);

  const stats = await page.evaluate(() => {
    const chat = document.getElementById('chat');
    const msgs = chat.querySelectorAll('.msg').length;
    const userMsgs = chat.querySelectorAll('.msg.user').length;
    const aiMsgs = chat.querySelectorAll('.msg.ai').length;
    const convoCount = document.querySelectorAll('#convo-list .convo').length;
    const stored = (localStorage.getItem('minidevin_convos') || '').length;
    return { msgs, userMsgs, aiMsgs, convoCount, storedKB: (stored / 1024).toFixed(0) };
  });

  const mem = await page.evaluate(() =>
    performance.memory ? (performance.memory.usedJSHeapSize / 1048576).toFixed(1) : 'n/a');

  console.log('\n===== HASIL =====');
  console.log('Total dikirim :', TOTAL);
  console.log('Gagal         :', failed);
  console.log('Waktu         :', elapsed + 's');
  console.log('DOM .msg      :', stats.msgs, '(user:', stats.userMsgs + ', ai:', stats.aiMsgs + ')');
  console.log('Daftar convo  :', stats.convoCount);
  console.log('localStorage  :', stats.storedKB + ' KB');
  console.log('JS heap       :', mem, 'MB');
  console.log('JS errors     :', errors.length ? errors.slice(0, 5) : 'tidak ada');

  assert.strictEqual(failed, 0, failed + ' pesan gagal');
  assert.strictEqual(errors.length, 0, 'ada JS error: ' + errors[0]);
  assert.strictEqual(stats.userMsgs, TOTAL, 'pesan user tidak lengkap');
  assert.strictEqual(stats.aiMsgs, TOTAL, 'pesan AI tidak lengkap');

  console.log('\n✅ STRESS TEST 1000 PERTANYAAN LULUS');
  await browser.close();
})().catch(e => { console.error('❌ FATAL:', e.message); process.exit(1); });
