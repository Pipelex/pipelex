/* docs/js/pipelex-shiki.js */
const SHIKI_VER = '3.14.0';
const TIMEOUT_MS = 2000; // 2 second timeout per block

const currentTheme = () =>
  document.documentElement.getAttribute('data-md-color-scheme') === 'slate'
    ? 'github-dark'
    : 'github-light';

let highlighterPromise;

async function getHighlighterOnce() {
  if (highlighterPromise) return highlighterPromise;

  highlighterPromise = (async () => {
    try {
      console.log('[Pipelex Shiki] Loading...');

      const { createHighlighterCore } = await import(
        `https://esm.sh/shiki@${SHIKI_VER}/core`
      );
      const { createJavaScriptRegexEngine } = await import(
        `https://esm.sh/@shikijs/engine-javascript@${SHIKI_VER}`
      );
      const { default: githubLight } = await import(
        `https://esm.sh/shiki@${SHIKI_VER}/themes/github-light.mjs`
      );
      const { default: githubDark } = await import(
        `https://esm.sh/shiki@${SHIKI_VER}/themes/github-dark.mjs`
      );

      const resp = await fetch('/grammars/plx.tmLanguage.json');
      if (!resp.ok) throw new Error(`Failed to load grammar: ${resp.status}`);
      
      const grammarJson = await resp.json();
      console.log('[Pipelex Shiki] ✓ Grammar loaded');

      const highlighter = await createHighlighterCore({
        engine: createJavaScriptRegexEngine(),
        themes: [githubLight, githubDark],
        langs: [],
      });

      await highlighter.loadLanguage({
        name: 'plx',
        scopeName: grammarJson.scopeName,
        ...grammarJson
      });

      console.log('[Pipelex Shiki] ✅ Ready!');
      return highlighter;
    } catch (err) {
      console.error('[Pipelex Shiki] ❌ Error:', err);
      throw err;
    }
  })();

  return highlighterPromise;
}

// Helper: Run with timeout
function withTimeout(promise, ms) {
  return Promise.race([
    promise,
    new Promise((_, reject) => 
      setTimeout(() => reject(new Error('Timeout')), ms)
    )
  ]);
}

async function highlightPLXBlocks() {
  try {
    const highlighter = await getHighlighterOnce();
    const theme = currentTheme();

    const allBlocks = document.querySelectorAll('pre code, div.highlight code');
    
    const plxBlocks = Array.from(allBlocks).filter(code => {
      if (code.dataset.shikiDone === '1') return false;
      const content = code.textContent || '';
      return content.match(/^\s*\[(pipe|concept)\b/m) || 
             content.match(/^\s*domain\s*=/m);
    });

    console.log(`[Pipelex Shiki] Highlighting ${plxBlocks.length} block(s)...`);

    let successCount = 0;
    let failCount = 0;

    for (const code of plxBlocks) {
      const raw = code.textContent || '';
      const preview = raw.substring(0, 50).replace(/\n/g, ' ');
      
      console.log(`[Pipelex Shiki] ⏳ Processing: "${preview}..."`);

      try {
        // ⚡ Add timeout protection
        const html = await withTimeout(
          Promise.resolve(highlighter.codeToHtml(raw, { lang: 'plx', theme })),
          TIMEOUT_MS
        );

        const pre = code.closest('pre');
        if (!pre) continue;

        const temp = document.createElement('div');
        temp.innerHTML = html;
        const newPre = temp.firstElementChild;

        newPre.querySelector('code')?.setAttribute('data-shiki-done', '1');

        const wrapper = pre.closest('div.highlight') || pre;
        wrapper.replaceWith(newPre);
        
        successCount++;
        console.log(`[Pipelex Shiki] ✅ Block ${successCount} done`);
      } catch (err) {
        failCount++;
        console.error(`[Pipelex Shiki] ⚠️ Block ${failCount} failed (${err.message}):`, preview);
        
        // Mark as processed to avoid retry loops
        code.setAttribute('data-shiki-done', '1');
        
        // Add visual indicator that highlighting failed
        const pre = code.closest('pre');
        if (pre) {
          pre.style.borderLeft = '3px solid orange';
          pre.title = 'Syntax highlighting failed for this block';
        }
      }
    }

    console.log(`[Pipelex Shiki] 🏁 Done: ${successCount} success, ${failCount} failed`);
  } catch (err) {
    console.error('[Pipelex Shiki] Fatal error:', err);
  }
}

// Start
(function() {
  function init() {
    console.log('[Pipelex Shiki] Starting...');

    const doc$ = window.document$;
    if (doc$ && doc$.subscribe) {
      doc$.subscribe(() => setTimeout(highlightPLXBlocks, 50));
    }

    new MutationObserver((mutations) => {
      if (mutations.some(m => m.attributeName === 'data-md-color-scheme')) {
        highlightPLXBlocks();
      }
    }).observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-md-color-scheme']
    });

    setTimeout(highlightPLXBlocks, 50);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();