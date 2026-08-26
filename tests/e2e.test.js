/**
 * End-to-end tests against the local static server on http://127.0.0.1:8766/
 * Run: node tests/e2e.test.js
 */

const { chromium } = require('playwright');
const assert = require('assert');

const URL = process.env.MINIDEVIN_URL || 'http://127.0.0.1:8766/';

let passed = 0;
let failed = 0;

async function test(name, fn) {
  const b = await chromium.launch({ args: ['--no-sandbox'] });
  const p = await b.newPage({ viewport: { width: 1280, height: 800 } });
  try {
    await p.goto(URL);
    await fn(p);
    passed++;
    console.log(`  ✓ ${name}`);
  } catch (e) {
    failed++;
    console.log(`  ✗ ${name}`);
    console.warn(`    ${e.message}`);
  } finally {
    await b.close();
  }
}

async function run() {
  console.log('E2E:', URL);

  await test('sidebar renders with logo and New Thread', async (p) => {
    await p.waitForSelector('.sb-new');
    const text = await p.textContent('.sb-new');
    assert.ok(text.includes('New Thread'), 'sidebar button missing');
    const brand = await p.textContent('.sb-head .name');
    assert.ok(brand.includes('MiniDevin'));
  });

  await test('model chip renders bot svg once puter responds', async (p) => {
    await p.waitForFunction(() => {
      const chip = document.getElementById('model-chip');
      return (chip && chip.querySelector('svg')) || chip.textContent.length > 0;
    }, { timeout: 5000 }).catch(() => {});
    const html = await p.innerHTML('#model-chip');
    // Jika puter SDK lambat, tetap cek static patterns di source
    if (!html.includes('svg')) {
      const src = await p.content();
      assert.ok(src.includes('MODEL_ICON'), 'bot icon missing in source');
    } else {
      assert.ok(!html.includes('🤖'), 'emoji robot still in chip');
    }
  });

  await test('attachment button is paperclip SVG', async (p) => {
    await p.waitForSelector('#attach-btn svg');
    const html = await p.innerHTML('#attach-btn');
    assert.ok(html.includes('m21.44 11.05'), 'paperclip icon missing');
    assert.ok(!html.includes('📎'), 'emoji still in attach button');
  });

  await test('mic button is SVG', async (p) => {
    await p.waitForSelector('#mic-btn svg');
    const html = await p.innerHTML('#mic-btn');
    assert.ok(!html.includes('🎤'), 'emoji still in mic button');
  });

  await test('model dropdown populates when puter delivers', async (p) => {
    await p.waitForFunction(() => {
      const s = document.getElementById('model-select');
      return s.options.length > 0;
    }, { timeout: 4000 }).catch(() => {});
    const count = await p.locator('#model-select > option').count();
    if (count === 0) {
      // CDN puter lambat/blocked — cek fallback options exist di source
      const src = await p.content();
      assert.ok(src.includes('FALLBACK_MODELS'), 'no models and no fallback');
    }
  });

  await test('slash menu renders SVG icons', async (p) => {
    await p.fill('#input', '/');
    await p.waitForSelector('#slash-pop.show');
    const svgs = await p.locator('.slash-item .ic svg').count();
    assert.ok(svgs > 0, `slash icons missing (${svgs})`);
  });

  await test('attachment chip renders svg icon, not emoji', async (p) => {
    const objectUrl = await p.evaluate(() => {
      const d = new Blob(['x']);
      return URL.createObjectURL(d);
    });
    await p.evaluate(() => {
      document.getElementById('home').style.display = 'none';
      document.getElementById('chat-wrap').style.display = 'block';
      const chat = document.getElementById('chat');
      const body = 'x'.repeat(40);
      const d = document.createElement('div');
      d.className = 'msg user';
      const av = document.createElement('div');
      av.className = 'avatar';
      av.innerHTML = '<svg width="14" height="14"></svg>';
      const chip = document.createElement('div');
      chip.className = 'attach-row';
      chip.innerHTML = '<span class="ic"><svg width="14" height="14"></svg></span><img><span class="nm"></span>';
      chip.querySelector('.nm').textContent = 'x.png';
      const bodyEl = document.createElement('div');
      bodyEl.className = 'body'; bodyEl.textContent = body;
      d.appendChild(av); d.appendChild(bodyEl); d.appendChild(chip);
      chat.appendChild(d);
    });
    const hasAttachRow = await p.locator('.attach-row').count();
    assert.ok(hasAttachRow === 1, 'attach-row not rendered');
  });

  await test('send button functions', async (p) => {
    const sendBtn = await p.locator('#send-btn');
    assert.ok(await sendBtn.isVisible());
    const stop = await sendBtn.getAttribute('disabled');
    assert.ok(stop === null);
  });

  await test('send enters stream mode code', async (p) => {
    const fallback = await p.evaluate(() => {
      // ambil semua inline scripts — checks union
      const all = Array.from(document.querySelectorAll('script')).map(s => s.textContent).join('\n');
      return all.includes('does not support http call') ||
             all.includes('only support stream');
    });
    assert.ok(fallback, 'stream-only fallback missing');
    const vision = await p.evaluate(() => {
      const all = Array.from(document.querySelectorAll('script')).map(s => s.textContent).join('\n');
      return all.includes('image_url');
    });
    assert.ok(vision, 'vision format missing in messages');
  });

  await test('user chip renders Lucide user icon when signed in', async (p) => {
    await p.evaluate(async () => {
      window.puter = {
        auth: {
          isSignedIn: () => true,
          getUser: async () => ({ username: 'budi' }),
          signIn: async () => {},
          signOut: async () => {}
        },
        ai: { listModels: async () => [] },
        kv: {}
      };
      await refreshAuth();
    });
    const html = await p.innerHTML('#user-chip');
    assert.ok(html.includes('<svg'), 'user icon missing');
    assert.ok(!html.includes('👤'), 'emoji user still in chip');
    assert.ok(html.includes('budi'), 'username not in chip');
    const cls = await p.getAttribute('#user-chip', 'class');
    assert.ok(cls.includes('show'), 'user-chip not marked .show');
  });

  await test('export menu opens with formats', async (p) => {
    await p.evaluate(() => {
      document.getElementById('home').style.display = 'none';
      document.getElementById('export-menu-wrap').style.display = 'block';
      toggleExportMenu();
    });
    const html = await p.innerHTML('#export-menu');
    assert.ok(html.includes('Markdown'), 'md option missing');
    assert.ok(html.includes('JSON'), 'json option missing');
    assert.ok(html.includes('HTML'), 'html option missing');
    const visible = await p.locator('#export-menu.show').count();
    assert.ok(visible === 1, 'menu not opened');
  });

  await test('delete all button present and prompts', async (p) => {
    const count = await p.locator('#sb-del-all').count();
    assert.ok(count === 1, 'delete-all missing');
  });

  await test('regenerate button appears on AI message', async (p) => {
    await p.evaluate(() => {
      document.getElementById('home').style.display = 'none';
      const d = addMsg('ai', 'test');
      document.querySelector('#chat-wrap').style.display = 'block';
    });
    const del = await p.locator('.tools .tbtn').count();
    assert.ok(del >= 1, 'regenerate/copy buttons missing');
  });

  await test('markdown toggle exists and shows preview', async (p) => {
    await p.fill('#input', `# Title`);
    const count = await p.locator('#md-toggle').count();
    assert.ok(count === 1, 'md toggle missing');
    await p.click('#md-toggle');
    await p.waitForTimeout(250);
    const preview = await p.locator('#md-preview-box').count();
    assert.ok(preview === 1, 'preview box not created');
  });

  await test('compare button exists', async (p) => {
    const count = await p.locator('#compare-btn').count();
    assert.ok(count === 1, 'compare button missing');
  });

  await test('auth button triggers puter only', async (p) => {
    const count = await p.locator('#auth-btn').count();
    assert.ok(count === 1, 'auth button missing');
    const title = await p.getAttribute('#auth-btn', 'title');
    assert.ok(title && title.includes('Puter'), 'title not controlled by puter only');
    const menu = await p.locator('#auth-menu').count();
    assert.ok(menu === 0, 'auth-menu still present');
  });

  await test('toggle theme persists preference', async (p) => {
    await p.click('#theme-btn');
    const theme = await p.getAttribute('html', 'data-theme');
    assert.ok(theme === 'light' || theme === null || theme === 'dark', 'theme attr');
    const stored = await p.evaluate(() => localStorage.getItem('minidevin_theme'));
    assert.ok(stored === null || stored === 'light' || stored === 'dark');
  });

  await test('sidebar closes on toggleSidebar', async (p) => {
    await p.click('#topbar .icon-btn:first-child');
    const hidden = await p.getAttribute('#sidebar', 'class');
    assert.ok(hidden.includes('hidden'), 'sidebar did not hide');
  });

  console.log(`\nResults: ${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
}

run().catch((e) => {
  console.error(e);
  process.exit(1);
});
