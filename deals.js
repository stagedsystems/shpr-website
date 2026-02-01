(function() {
  'use strict';

  const content = document.getElementById('deals-content');
  const search = document.getElementById('search');
  const groupToggle = document.getElementById('group-toggle');

  let allDeals = [];
  let groupBy = 'store'; // 'store' or 'category'

  async function init() {
    try {
      const response = await fetch('deals.md');
      if (!response.ok) throw new Error('Failed to load deals');
      const markdown = await response.text();
      allDeals = parseMarkdown(markdown);
      render();
      bindEvents();
    } catch (error) {
      content.innerHTML = '<p class="text-center text-red">Error loading deals. Please try again later.</p>';
      console.error(error);
    }
  }

  function parseMarkdown(md) {
    const deals = [];
    const lines = md.split('\n');
    let currentStore = '';
    let currentCategory = '';

    for (const line of lines) {
      // Store header (# Store Name)
      if (line.startsWith('# ') && !line.startsWith('## ')) {
        currentStore = line.slice(2).trim();
        continue;
      }

      // Category header (## Category)
      if (line.startsWith('## ')) {
        currentCategory = line.slice(3).trim();
        continue;
      }

      // Deal item (- Item — $X.XX)
      if (line.startsWith('- ')) {
        deals.push({
          store: currentStore,
          category: currentCategory,
          text: line.slice(2),
          isFeatured: line.includes('⭐'),
          isRepeat: line.includes('🔁')
        });
      }
    }

    return deals;
  }

  function render() {
    const query = search ? search.value.toLowerCase().trim() : '';

    // Filter deals
    let filtered = allDeals;
    if (query) {
      filtered = allDeals.filter(d => d.text.toLowerCase().includes(query));
    }

    if (filtered.length === 0) {
      content.innerHTML = '<p class="text-center text-gray-600">No deals found.</p>';
      return;
    }

    let html = '';

    if (groupBy === 'store') {
      html = renderByStore(filtered);
    } else {
      html = renderByCategory(filtered);
    }

    content.innerHTML = html;
  }

  function renderByStore(deals) {
    const grouped = {};
    for (const deal of deals) {
      if (!grouped[deal.store]) grouped[deal.store] = {};
      if (!grouped[deal.store][deal.category]) grouped[deal.store][deal.category] = [];
      grouped[deal.store][deal.category].push(deal);
    }

    let html = '';
    for (const store of Object.keys(grouped).sort()) {
      html += `<h1 class="deals-store">${store}</h1>`;
      for (const category of Object.keys(grouped[store]).sort()) {
        html += `<h2 class="deals-category">${category}</h2>`;
        html += '<ul class="deals-list">';
        for (const deal of grouped[store][category]) {
          html += renderDealItem(deal);
        }
        html += '</ul>';
      }
    }
    return html;
  }

  function renderByCategory(deals) {
    const grouped = {};
    for (const deal of deals) {
      if (!grouped[deal.category]) grouped[deal.category] = {};
      if (!grouped[deal.category][deal.store]) grouped[deal.category][deal.store] = [];
      grouped[deal.category][deal.store].push(deal);
    }

    let html = '';
    for (const category of Object.keys(grouped).sort()) {
      html += `<h1 class="deals-store">${category}</h1>`;
      for (const store of Object.keys(grouped[category]).sort()) {
        html += `<h2 class="deals-category">${store}</h2>`;
        html += '<ul class="deals-list">';
        for (const deal of grouped[category][store]) {
          html += renderDealItem(deal);
        }
        html += '</ul>';
      }
    }
    return html;
  }

  function renderDealItem(deal) {
    let cleanText = deal.text
      .replace(/\s*⭐\s*/g, '')
      .replace(/\s*🔁\s*/g, '')
      .replace(/\(REPEAT\)\s*/gi, '')
      .replace(/\*\*/g, '')
      .trim();

    // Item name
    cleanText = cleanText.replace(
      /^([^—]+)\s*—/,
      '<span class="deals-name">$1</span> —'
    );

    // Price
    cleanText = cleanText.replace(
      /(\$[\d.]+(?:\/lb)?)/g,
      '<span class="deals-price">$1</span>'
    );

    // BOGO
    cleanText = cleanText.replace(
      /(BOGO)/gi,
      '<span class="deals-bogo">$1</span>'
    );

    const classes = ['deals-item'];
    if (deal.isFeatured) classes.push('deals-featured');

    let badges = '';
    if (deal.isFeatured) badges += '<span class="deals-badge">⭐</span>';
    if (deal.isRepeat) badges += '<span class="deals-badge">🔁</span>';

    return `<li class="${classes.join(' ')}">${badges}${cleanText}</li>`;
  }

  function bindEvents() {
    if (search) {
      search.addEventListener('input', debounce(render, 150));
    }

    if (groupToggle) {
      groupToggle.addEventListener('click', function(e) {
        if (e.target.tagName === 'BUTTON') {
          const mode = e.target.getAttribute('data-group');
          if (mode && mode !== groupBy) {
            groupBy = mode;
            groupToggle.querySelectorAll('button').forEach(btn => {
              btn.classList.toggle('active', btn.getAttribute('data-group') === groupBy);
            });
            render();
          }
        }
      });
    }
  }

  function debounce(fn, delay) {
    let timeout;
    return function(...args) {
      clearTimeout(timeout);
      timeout = setTimeout(() => fn.apply(this, args), delay);
    };
  }

  document.addEventListener('DOMContentLoaded', init);
})();
