(function() {
  'use strict';

  const content = document.getElementById('deals-content');
  const search = document.getElementById('search');

  async function init() {
    try {
      const response = await fetch('deals.md');
      if (!response.ok) throw new Error('Failed to load deals');
      const markdown = await response.text();
      content.innerHTML = parseMarkdown(markdown);
      bindSearch();
    } catch (error) {
      content.innerHTML = '<p class="text-center text-red">Error loading deals. Please try again later.</p>';
      console.error(error);
    }
  }

  function parseMarkdown(md) {
    let html = '';
    const lines = md.split('\n');
    let inList = false;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      // Store header (# Store Name)
      if (line.startsWith('# ') && !line.startsWith('## ')) {
        if (inList) { html += '</ul>'; inList = false; }
        const storeName = line.slice(2).trim();
        html += `<h1 class="deals-store" data-store="${storeName}">${storeName}</h1>`;
        continue;
      }

      // Category header (## Category)
      if (line.startsWith('## ')) {
        if (inList) { html += '</ul>'; inList = false; }
        const category = line.slice(3).trim();
        html += `<h2 class="deals-category" data-category="${category}">${category}</h2>`;
        continue;
      }

      // Valid dates (*Valid...*)
      if (line.startsWith('*') && line.endsWith('*') && line.includes('Valid')) {
        const date = line.slice(1, -1);
        html += `<p class="deals-date">${date}</p>`;
        continue;
      }

      // Deal item (- Item — $X.XX)
      if (line.startsWith('- ')) {
        if (!inList) { html += '<ul class="deals-list">'; inList = true; }
        html += parseDealItem(line.slice(2));
        continue;
      }

      // Horizontal rule
      if (line.startsWith('---')) {
        if (inList) { html += '</ul>'; inList = false; }
        html += '<hr class="deals-divider">';
        continue;
      }
    }

    if (inList) html += '</ul>';
    return html;
  }

  function parseDealItem(text) {
    // Check for featured (bold) items
    const isFeatured = text.includes('⭐');
    const isRepeat = text.includes('🔁');

    // Remove emoji markers for cleaner display but keep the info
    let cleanText = text
      .replace(/\s*⭐\s*/g, '')
      .replace(/\s*🔁\s*/g, '')
      .replace(/\(REPEAT\)\s*/gi, '')
      .trim();

    // Handle bold markers
    cleanText = cleanText.replace(/\*\*/g, '');

    // Bold item name (everything before the em dash)
    cleanText = cleanText.replace(
      /^([^—]+)\s*—/,
      '<span class="deals-name">$1</span> —'
    );

    // Highlight price
    cleanText = cleanText.replace(
      /(\$[\d.]+(?:\/lb)?)/g,
      '<span class="deals-price">$1</span>'
    );

    // Handle BOGO
    cleanText = cleanText.replace(
      /(BOGO)/gi,
      '<span class="deals-bogo">$1</span>'
    );

    const classes = ['deals-item'];
    if (isFeatured) classes.push('deals-featured');

    let badges = '';
    if (isFeatured) badges += '<span class="deals-badge deals-badge-star">⭐</span>';
    if (isRepeat) badges += '<span class="deals-badge deals-badge-repeat">🔁</span>';

    return `<li class="${classes.join(' ')}" data-text="${text.toLowerCase()}">${badges}${cleanText}</li>`;
  }

  function bindSearch() {
    if (!search) return;

    search.addEventListener('input', function() {
      const query = this.value.toLowerCase().trim();
      const items = content.querySelectorAll('.deals-item');
      const categories = content.querySelectorAll('.deals-category');
      const stores = content.querySelectorAll('.deals-store');
      const lists = content.querySelectorAll('.deals-list');

      if (!query) {
        // Show everything
        items.forEach(item => item.style.display = '');
        categories.forEach(cat => cat.style.display = '');
        stores.forEach(store => store.style.display = '');
        lists.forEach(list => list.style.display = '');
        content.querySelectorAll('.deals-date').forEach(d => d.style.display = '');
        return;
      }

      // Filter items
      items.forEach(item => {
        const text = item.getAttribute('data-text') || '';
        item.style.display = text.includes(query) ? '' : 'none';
      });

      // Hide empty lists
      lists.forEach(list => {
        const visibleItems = list.querySelectorAll('.deals-item:not([style*="display: none"])');
        list.style.display = visibleItems.length > 0 ? '' : 'none';
      });

      // Hide categories with no visible lists after them
      categories.forEach(cat => {
        const nextList = cat.nextElementSibling;
        if (nextList && nextList.classList.contains('deals-list')) {
          cat.style.display = nextList.style.display;
        }
      });

      // Hide stores with no visible content
      stores.forEach(store => {
        let hasVisible = false;
        let el = store.nextElementSibling;
        while (el && !el.classList.contains('deals-store')) {
          if (el.classList.contains('deals-item') && el.style.display !== 'none') {
            hasVisible = true;
            break;
          }
          if (el.classList.contains('deals-list') && el.style.display !== 'none') {
            hasVisible = true;
            break;
          }
          el = el.nextElementSibling;
        }
        store.style.display = hasVisible ? '' : 'none';
        // Hide date after store
        const nextEl = store.nextElementSibling;
        if (nextEl && nextEl.classList.contains('deals-date')) {
          nextEl.style.display = store.style.display;
        }
      });
    });
  }

  document.addEventListener('DOMContentLoaded', init);
})();
