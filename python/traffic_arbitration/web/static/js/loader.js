/*
  Traffic Arbitration Loader v2.3
  - FIX: Исправлена ошибка 404 в article.html (через корректное подключение этого файла)
  - FIX: Гарантированно убран текст из тизеров ленты (l)
  - Единый запрос (/etc)
*/

// --- КОНСТАНТЫ И СОСТОЯНИЕ ---
const LONG_TERM_COOKIE_NAME = 'ta_seen_ids';
const MAX_COOKIE_IDS = 300;
const SEEN_IDS_ON_PAGE = new Set(); // Краткосрочная память
let isFeedLoading = false;
let currentFeedPage = -1;
const MAX_FEED_ROWS = 100;

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
            const tid = parseInt(entry.target.dataset.teaserId);
            if (tid && !SEEN_IDS_ON_PAGE.has(tid)) {
                SEEN_IDS_ON_PAGE.add(tid);
                viewObserver.unobserve(entry.target);
            }
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

// --- API REQUEST ---
async function requestTeasers(widgetsMap) {
    const longTerm = getLongTermSeenIds();
    const pageSeen = Array.from(SEEN_IDS_ON_PAGE);
    const uid = localStorage.getItem('ta_uid') || 'anon';

    let cat = null;
    if (typeof window.currentCategory !== 'undefined') {
        cat = window.currentCategory;
    }

    try {
        const resp = await fetch('/etc', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                uid: uid,
                ip: '',
                ua: navigator.userAgent,
                url: window.location.href,
                w: window.innerWidth,
                h: window.innerHeight,
                widgets: widgetsMap,
                seen_ids_page: pageSeen,
                seen_ids_long_term: longTerm,
                category: cat
            })
        });

        if (!resp.ok) {
            const errText = await resp.text();
            console.error('API Error:', resp.status, errText);
            throw new Error(`API Error: ${resp.status}`);
        }

        const data = await resp.json();

        if (data.newly_served_ids && data.newly_served_ids.length > 0) {
            data.newly_served_ids.forEach(id => SEEN_IDS_ON_PAGE.add(id));
        }
        // Save the *entire* seen_ids_long_term from the backend response directly to the cookie.
        // No client-side truncation or uniqueness checks are performed as per user's instruction.
        if (data.seen_ids_long_term) {
            const exp = new Date();
            exp.setFullYear(exp.getFullYear() + 1);
            document.cookie = `${LONG_TERM_COOKIE_NAME}=${encodeURIComponent(JSON.stringify(data.seen_ids_long_term))}; expires=${exp.toUTCString()}; path=/; SameSite=Lax`;
        }
        return data.widgets;
    } catch (e) {
        console.error("Ошибка запроса тизеров:", e);
        return {};
    }
}

// --- RENDERER ---
function renderWidget(wName, teaser) {
    const $placeholder = $(`#widget-${wName}`);
    if (!$placeholder.length) return;

    if (!teaser) {
        $placeholder.remove();
        return;
    }

    const url = buildTrackingUrl(teaser.url, wName);
    let html = '';

    const type = wName.charAt(0);

    if (type === 's') { // Sidebar Preview
        html = `
            <a href="${url}" class="sidebar-widget" data-teaser-id="${teaser.id}">
                <img src="${teaser.image}" class="sidebar-image" loading="lazy">
                <div class="sidebar-content">
                    <h4 class="sidebar-title">${teaser.title}</h4>
                </div>
            </a>`;
    }
    else if (type === 'r') { // Sidebar Article
        html = `
            <div class="teaser-widget" data-teaser-id="${teaser.id}" style="margin-bottom: 20px;">
                <a href="${url}" class="teaser-link">
                    <div class="teaser-image-wrapper">
                        <img src="${teaser.image}" class="teaser-image" loading="lazy">
                    </div>
                    <div class="teaser-content">
                        <h3 class="teaser-title">${teaser.title}</h3>
                    </div>
                </a>
            </div>`;
    }
    else if (type === 'i') { // In-Article
        html = `
            <a href="${url}" class="in-article-widget" data-teaser-id="${teaser.id}">
                <img src="${teaser.image}" class="in-article-image" loading="lazy">
                <div class="in-article-content">
                    <h4 class="in-article-title">${teaser.title}</h4>
                    <div class="in-article-text">${teaser.text || ''}</div>
                </div>
            </a>`;
    }
    else { // 'l' - Feed
         // Текст убран по требованию
         html = `
            <div class="teaser-widget" data-teaser-id="${teaser.id}">
                <a href="${url}" class="teaser-link">
                    <div class="teaser-image-wrapper">
                        <img src="${teaser.image}" class="teaser-image" loading="lazy">
                    </div>
                    <div class="teaser-content">
                        <h3 class="teaser-title">${teaser.title}</h3>
                    </div>
                </a>
            </div>`;
    }

    const $el = $(html);
    $placeholder.replaceWith($el);
    viewObserver.observe($el[0]);
}

// --- FEED LOGIC ---
function getColumns() {
    const cols = $('#teaser-feed').css('--feed-columns');
    return parseInt(cols) || 1;
}

function generatePlaceholders(row, cols) {
    const map = {};
    for (let c = 0; c < cols; c++) {
        const name = `l${c.toString(16)}${row.toString(16).padStart(2, '0')}`;
        const id = `widget-${name}`;
        if (!$(`#${id}`).length) {
            $('<div/>', {
                id: id,
                class: 'teaser-widget-placeholder'
            }).insertBefore('#feed-load-trigger');
        }
        map[name] = 1;
    }
    return map;
}

// --- INIT ---
$(document).ready(function() {
    const widgetsToRequest = {};
    const $feed = $('#teaser-feed');
    const isMobile = window.innerWidth < 994;

    // 1. In-Article (i)
    $('[id^="widget-i"]').each(function() {
        let name = $(this).data('widget-name');
        if (!name && this.id) {
            name = this.id.replace('widget-', '');
        }
        if (name) {
            widgetsToRequest[name] = 1;
        }
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
        let count = Math.floor(articleH / 300);
        count = Math.max(2, Math.min(count, 15));

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
        const rowsToLoad = 2;
        for(let r=0; r<rowsToLoad; r++) {
            Object.assign(widgetsToRequest, generatePlaceholders(r, cols));
        }
        currentFeedPage = rowsToLoad - 1;
    }

    // 5. ЕДИНЫЙ ЗАПРОС
    if (Object.keys(widgetsToRequest).length > 0) {
        requestTeasers(widgetsToRequest).then(widgets => {
            for (const [name, data] of Object.entries(widgets)) {
                renderWidget(name, data);
            }
        });
    }

    // --- INFINITE SCROLL ---
    const scrollObserver = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting && !isFeedLoading && currentFeedPage < MAX_FEED_ROWS) {
            isFeedLoading = true;
            const cols = getColumns();
            const nextRow = currentFeedPage + 1;
            const req = generatePlaceholders(nextRow, cols);

            requestTeasers(req).then(widgets => {
                for (const [name, data] of Object.entries(widgets)) {
                    renderWidget(name, data);
                }
                currentFeedPage = nextRow;
                isFeedLoading = false;
            });
        }
    }, { rootMargin: '200px' });

    if ($('#feed-load-trigger').length) {
        scrollObserver.observe(document.getElementById('feed-load-trigger'));
    }
});