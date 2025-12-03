/*
  Traffic Arbitration Loader v2.5
  - FIX: Исправлена логика бесконечной прокрутки в системе очередей.
  - ADD: Внедрена последовательная очередь запросов с таймаутом и повторными попытками.
*/

// --- КОНСТАНТЫ И СОСТОЯНИЕ ---
const LONG_TERM_COOKIE_NAME = 'ta_seen_ids';
const MAX_COOKIE_IDS = 300;
const SEEN_IDS_ON_PAGE = new Set(); // Краткосрочная память
let currentFeedPage = -1;
const MAX_FEED_ROWS = 100;
const REQUEST_TIMEOUT_MS = 500;

// --- ОЧЕРЕДЬ ЗАПРОСОВ ---
const teaserRequestQueue = [];
let isRequestInFlight = false;
let isFeedLoading = false; // Отдельный флаг для состояния загрузки ленты

// --- COOKIE HELPERS ---
function getLongTermSeenIds() {
    try {
        const match = document.cookie.match(new RegExp('(^| )' + LONG_TERM_COOKIE_NAME + '=([^;]+)'));
        return match ? JSON.parse(decodeURIComponent(match[2])) : [];
    } catch (e) { return []; }
}

function updateLongTermSeenIds(newIds) {
    if (!newIds || !newIds.length) return;
    try {
        let currentIds = getLongTermSeenIds();
        const uniqueSet = new Set([...currentIds, ...newIds]);
        let updatedIds = Array.from(uniqueSet);
        if (updatedIds.length > MAX_COOKIE_IDS) {
            updatedIds = updatedIds.slice(-MAX_COOKIE_IDS);
        }

        const exp = new Date();
        exp.setFullYear(exp.getFullYear() + 1);
        document.cookie = `${LONG_TERM_COOKIE_NAME}=${encodeURIComponent(JSON.stringify(updatedIds))}; expires=${exp.toUTCString()}; path=/; SameSite=Lax`;
    } catch (e) { console.error(e); }
}

// --- TRACKING & OBSERVER ---
const viewObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            viewObserver.unobserve(entry.target);
        }
    });
}, { threshold: 0.5 });

function buildTrackingUrl(baseUrl, widgetName) {
    try {
        const url = new URL(baseUrl, window.location.origin);
        url.searchParams.set('w', window.innerWidth);
        url.searchParams.set('ws', widgetName);
        return url.href;
    } catch(e) { return baseUrl; }
}

// --- CORE API LOGIC ---
async function _fetchTeasers(widgetsMap, signal) {
    const longTerm = getLongTermSeenIds();
    const pageSeen = Array.from(SEEN_IDS_ON_PAGE);
    const uid = localStorage.getItem('ta_uid') || 'anon';
    let cat = window.currentCategory || null;

    const resp = await fetch('/etc', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: signal,
        body: JSON.stringify({
            uid: uid, ua: navigator.userAgent, url: window.location.href,
            w: window.innerWidth, h: window.innerHeight,
            widgets: widgetsMap,
            seen_ids_page: pageSeen, seen_ids_long_term: longTerm,
            category: cat
        })
    });

    if (!resp.ok) {
        throw new Error(`API Error: ${resp.status}`);
    }

    const data = await resp.json();
    
    if (data.newly_served_ids && data.newly_served_ids.length > 0) {
        data.newly_served_ids.forEach(id => SEEN_IDS_ON_PAGE.add(id));
    }
    if (data.seen_ids_long_term) {
        const exp = new Date();
        exp.setFullYear(exp.getFullYear() + 1);
        document.cookie = `${LONG_TERM_COOKIE_NAME}=${encodeURIComponent(JSON.stringify(data.seen_ids_long_term))}; expires=${exp.toUTCString()}; path=/; SameSite=Lax`;
    }
    return data.widgets;
}

async function executeRequestWithRetry(widgetsMap, attempts = 2) {
    for (let i = 0; i < attempts; i++) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
            
            const widgets = await _fetchTeasers(widgetsMap, controller.signal);
            
            clearTimeout(timeoutId);
            return widgets; // Успех
        } catch (e) {
            if (e.name === 'AbortError') {
                console.warn(`Запрос по таймауту для виджетов:`, widgetsMap, `Попытка ${i + 1}`);
            } else {
                console.error(`Ошибка запроса для виджетов:`, widgetsMap, e, `Попытка ${i + 1}`);
            }
            if (i === attempts - 1) {
                throw e; // Провалены все попытки
            }
        }
    }
}

// --- QUEUE PROCESSOR ---
async function processRequestQueue() {
    if (isRequestInFlight || teaserRequestQueue.length === 0) {
        return;
    }
    isRequestInFlight = true;

    const requestItem = teaserRequestQueue.shift();
    
    try {
        const widgets = await executeRequestWithRetry(requestItem.widgetsMap);
        for (const [name, data] of Object.entries(widgets)) {
            renderWidget(name, data);
        }
    } catch (error) {
        console.error("Не удалось загрузить тизеры (все попытки провалены):", requestItem.widgetsMap, error);
    } finally {
        isRequestInFlight = false;
        if (requestItem.onComplete) {
            requestItem.onComplete();
        }
        setTimeout(processRequestQueue, 0);
    }
}

function enqueueTeaserRequest(widgetsMap, onComplete) {
    if (Object.keys(widgetsMap).length === 0) {
        if (onComplete) onComplete();
        return;
    }
    teaserRequestQueue.push({ widgetsMap, onComplete });
    processRequestQueue();
}


// --- RENDERER ---
function renderWidget(wName, teaser) {
    const $placeholder = $(`#widget-${wName}`);
    if (!$placeholder.length) return;

    if (!teaser) {
        return;
    }

    const url = buildTrackingUrl(teaser.url, wName);
    let html = '';
    const type = wName.charAt(0);

    if (type === 's') { // Sidebar Preview
        html = `<a href="${url}" class="sidebar-widget" data-teaser-id="${teaser.id}"><img src="${teaser.image}" class="sidebar-image" loading="lazy"><div class="sidebar-content"><h4 class="sidebar-title">${teaser.title}</h4></div></a>`;
    } else if (type === 'r') { // Sidebar Article
        html = `<div class="teaser-widget" data-teaser-id="${teaser.id}" style="margin-bottom: 20px;"><a href="${url}" class="teaser-link"><div class="teaser-image-wrapper"><img src="${teaser.image}" class="teaser-image" loading="lazy"></div><div class="teaser-content"><h3 class="teaser-title">${teaser.title}</h3></div></a></div>`;
    } else if (type === 'i') { // In-Article
        html = `<a href="${url}" class="in-article-widget" data-teaser-id="${teaser.id}"><img src="${teaser.image}" class="in-article-image" loading="lazy"><div class="in-article-content"><h4 class="in-article-title">${teaser.title}</h4><div class="in-article-text">${teaser.text || ''}</div></div></a>`;
    } else { // 'l' - Feed
        html = `<div class="teaser-widget" data-teaser-id="${teaser.id}"><a href="${url}" class="teaser-link"><div class="teaser-image-wrapper"><img src="${teaser.image}" class="teaser-image" loading="lazy"></div><div class="teaser-content"><h3 class="teaser-title">${teaser.title}</h3></div></a></div>`;
    }

    const $el = $(html);
    $placeholder.replaceWith($el);
    viewObserver.observe($el[0]);
}

// --- FEED LOGIC ---
function getColumns() {
    const cols = $('.teaser-feed').css('--feed-columns');
    return parseInt(cols) || 1;
}

function generatePlaceholders(row, cols) {
    const map = {};
    for (let c = 0; c < cols; c++) {
        const name = `l${c.toString(16)}${row.toString(16).padStart(2, '0')}`;
        const id = `widget-${name}`;
        if (!$(`#${id}`).length) {
            $('<div/>', { id: id, class: 'teaser-widget-placeholder' }).insertBefore('#feed-load-trigger');
        }
        map[name] = 1;
    }
    return map;
}

// --- INIT ---
$(document).ready(function() {
    const widgetsToRequest = {};
    const $feed = $('.teaser-feed');
    const isMobile = window.innerWidth < 994;

    // 1. In-Article (i)
    $('[id^="widget-i"]').each(function() {
        let name = $(this).data('widget-name') || this.id.replace('widget-', '');
        if (name) widgetsToRequest[name] = 1;
    });

    // 2. Sidebar Preview (s)
    const $sideS = $('#preview-sidebar-content, .preview-sidebar-content').first();
    if ($sideS.length && !isMobile) {
        for(let i=0; i<5; i++) {
            const name = `s0${i.toString(16).padStart(2,'0')}`;
            if (!$(`#widget-${name}`).length) {
                $sideS.append(`<div id="widget-${name}" class="sidebar-widget-placeholder"></div>`);
            }
            widgetsToRequest[name] = 1;
        }
    }

    // 3. Sidebar Article (r)
    const $sideR = $('#article-sidebar-content, .article-sidebar-content').first();
    if ($sideR.length && !isMobile) {
        const articleH = $('.article-content-wrapper, article').height() || 800;
        let count = Math.min(15, Math.max(2, Math.floor(articleH / 300)));
        for(let i=0; i<count; i++) {
            const name = `r0${i.toString(16).padStart(2,'0')}`;
            if (!$(`#widget-${name}`).length) {
                $sideR.append(`<div id="widget-${name}" class="teaser-widget-placeholder" style="margin-bottom:20px"></div>`);
            }
            widgetsToRequest[name] = 1;
        }
    }

    // 4. Feed (l)
    if ($feed.length) {
        $feed.append('<div id="feed-load-trigger" style="height:1px; width:100%"></div>');
        const cols = getColumns();
        // const rowsToLoad = 2;
        const rowsToLoad = Math.max(2, Math.ceil(window.innerHeight / 300));
        for(let r=0; r<rowsToLoad; r++) {
            Object.assign(widgetsToRequest, generatePlaceholders(r, cols));
        }
        currentFeedPage = rowsToLoad - 1;
    }

    // 5. Постановка первоначального запроса в очередь
    enqueueTeaserRequest(widgetsToRequest);

    // --- INFINITE SCROLL ---
    const scrollObserver = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting && !isFeedLoading && currentFeedPage < MAX_FEED_ROWS) {
            isFeedLoading = true;
            const cols = getColumns();
            const nextRow = currentFeedPage + 1;
            const req = generatePlaceholders(nextRow, cols);
            
            enqueueTeaserRequest(req, () => {
                isFeedLoading = false;
            });
            currentFeedPage = nextRow;
        }
    }, { rootMargin: '200px' });

    if ($('#feed-load-trigger').length) {
        scrollObserver.observe(document.getElementById('feed-load-trigger'));
    }
});