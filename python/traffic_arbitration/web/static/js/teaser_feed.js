/*
  Глобальная логика для рендеринга "бесконечной" ленты тизеров + сайдбара.
  Выполняет единый запрос при инициализации.
  Ожидает, что JQuery ($) уже загружен.
  Ожидает, что в `window` определена переменная `currentCategory` (может быть null).
*/

// --- Управление состоянием (Cookie, Observer) ---
// 1. Управление Cookie для "долгосрочных" просмотров
const LONG_TERM_COOKIE_NAME = 'ta_seen_ids';
const MAX_COOKIE_IDS = 200; // Храним 200 последних ID

/**
 * Читает ID из cookie.
 * @returns {number[]} Массив ID.
 */
function getLongTermSeenIds() {
    try {
        const cookieValue = document.cookie
            .split('; ')
            .find(row => row.startsWith(LONG_TERM_COOKIE_NAME + '='));

        if (!cookieValue) return [];
        const jsonString = decodeURIComponent(cookieValue.split('=')[1]);
        return JSON.parse(jsonString) || [];
    } catch (e) {
        console.error("Error reading seen_ids cookie:", e);
        return [];
    }
}

/**
 * Добавляет новые ID в cookie, поддерживает лимит в 200.
 * @param {number[]} newIds - Массив ID, которые *только что* показал сервер.
 */
function updateLongTermSeenIds(newIds) {
    if (!newIds || newIds.length === 0) return;
    try {
        const currentIds = getLongTermSeenIds();
        const idSet = new Set(currentIds);
        newIds.forEach(id => idSet.add(id));
        let updatedIds = Array.from(idSet);
        if (updatedIds.length > MAX_COOKIE_IDS) {
            updatedIds = updatedIds.slice(updatedIds.length - MAX_COOKIE_IDS);
        }
        const jsonString = JSON.stringify(updatedIds);
        const expirationDate = new Date();
        expirationDate.setFullYear(expirationDate.getFullYear() + 1);
        document.cookie = `${LONG_TERM_COOKIE_NAME}=${encodeURIComponent(jsonString)}; expires=${expirationDate.toUTCString()}; path=/; SameSite=Lax`;
    } catch (e) {
        console.error("Error writing seen_ids cookie:", e);
    }
}

// 2. Краткосрочное состояние (ID, которые *реально* попали во вьюпорт *на этой странице*)
// Мы используем IntersectionObserver, чтобы заполнять этот Set.
const seenIdsOnPage = new Set();


// 3. Intersection Observer
const observerCallback = (entries, observer) => {
    entries.forEach(entry => {
        if (!entry.isIntersecting) return;

        const targetElement = entry.target;
        const teaserId = parseInt(targetElement.dataset.teaserId, 10);

        if (teaserId && !seenIdsOnPage.has(teaserId)) {
            seenIdsOnPage.add(teaserId);
            observer.unobserve(targetElement);
        }
    });
};

const intersectionObserver = new IntersectionObserver(observerCallback, {
    root: null, // (вьюпорт)
    threshold: 0.5 // 50% видимости для засчитывания просмотра
});

/**
 * Создает URL для тизера с параметрами трекинга.
 * @param {string} backendUrlString - /preview/{slug}?param=1
 * @param {string} widgetName - l00, l01, ...
 * @returns {string} - Полный URL для `href`
 */
function buildTrackingUrl(backendUrlString, widgetName) {
    try {
        // 1. URL, который пришел от бэка (может иметь query-params)
        const backendUrl = new URL(backendUrlString, window.location.origin);
        const backendParams = new URLSearchParams(backendUrl.search);

        // 2. URL текущей страницы (откуда кликнули)
        const currentPageUrl = new URL(window.location.href);
        const finalParams = new URLSearchParams(currentPageUrl.search);

        // 3. Добавляем/перезаписываем параметры текущей страницы
        finalParams.set('w', $(window).width());
        finalParams.set('ws', widgetName);

        // 4. Параметры бэкенда (из teaser.url) имеют наивысший приоритет
        backendParams.forEach((value, key) => {
            finalParams.set(key, value);
        });

        // 5. Собираем итоговую ссылку
        // (Используем pathname от бэка, а query - собранный)
        const finalUrl = new URL(backendUrl.pathname, window.location.origin);
        finalUrl.search = finalParams.toString();
        return finalUrl.href;
    } catch (e) {
        console.error("Ошибка при построении URL:", e);
        // Фолбэк на оригинальный URL, если что-то пошло не так
        return backendUrlString;
    }
}

// --- УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ЗАПРОСА ---
function requestTeasersAPI(widgetsMap, category) {
    const longTermIds = getLongTermSeenIds();
    const pageIds = Array.from(seenIdsOnPage);
    const uid = 'placeholder-uid-' + (localStorage.getItem('my_uid') || 'new');

    return fetch('/etc', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        },
        body: JSON.stringify({
            uid: uid,
            ip: '1.1.1.1',
            ua: navigator.userAgent,
            url: window.location.href,
            loc: navigator.language || 'ru',
            w: $(window).width(),
            h: $(window).height(),
            widgets: widgetsMap,
            seen_ids_page: pageIds,
            seen_ids_long_term: longTermIds,
            category: category
        })
    })
        .then(response => {
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            return response.json();
        })
        .then(data => {
            if (data.newly_served_ids) {
                updateLongTermSeenIds(data.newly_served_ids);
            }
            return data.widgets || {};
        });
}

// --- УТИЛИТА РЕНДЕРИНГА ---
function renderWidget(widgetName, teaser, htmlBuilder) {
    const $placeholder = $(`#widget-${widgetName}`);

    if ($placeholder.length && teaser) {
        const trackUrl = buildTrackingUrl(teaser.url, widgetName);
        const html = htmlBuilder(teaser, trackUrl);
        const $element = $(html);

        $placeholder.replaceWith($element);

        // Наблюдение
        const teaserId = $element.attr('data-teaser-id');
        if (teaserId) {
            intersectionObserver.observe($element[0]);
        } else {
            const inner = $element.find(`[data-teaser-id="${teaser.id}"]`)[0];
            if (inner) intersectionObserver.observe(inner);
        }

    } else if ($placeholder.length) {
        $placeholder.text('Нет данных').addClass('empty');
    }
}

// --- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ И ХЕЛПЕРЫ ЛЕНТЫ ---
const $feed = $('#teaser-feed');
const $trigger = $('<div id="feed-load-trigger-dynamic"></div>');
$trigger.css({height: '1px', width: '100%'});

let isFeedLoading = false;
// currentFeedPage теперь указывает на ПОСЛЕДНИЙ загруженный ряд.
// При старте -1, т.к. еще ничего не загружено.
let currentFeedPage = -1;
const MAX_FEED_ROWS = 100;

function getGridColumns() {
    if (!$feed.length) return 1;
    const columns = $feed.css('--feed-columns');
    return parseInt(columns, 10) || 1;
}

// --- НОВОЕ: Расчет количества рядов для заполнения экрана ---
function estimateRowsToFillScreen() {
    const cols = getGridColumns();
    const containerWidth = $feed.width() || $(window).width();
    const gap = 20;
    // Примерная ширина карточки
    const cardWidth = (containerWidth - (gap * (cols - 1))) / cols;
    // Примерная высота: картинка (16:9) + текст (~160px с отступами)
    const estimatedCardHeight = (cardWidth * 0.5625) + 160;

    const screenHeight = $(window).height();

    // Сколько рядов влезет + 1 запасной
    const rows = Math.ceil(screenHeight / estimatedCardHeight) + 1;

    // Ограничим разумным минимумом (1) и максимумом (например, 5),
    // чтобы не грузить слишком много при ошибке расчета.
    return Math.max(1, Math.min(rows, 5));
}

function createFeedPlaceholders(row, columns) {
    const widgetsMap = {};
    if (!$feed.length) return widgetsMap;

    for (let col = 0; col < columns; col++) {
        // Формат: l[1-char COL][2-char ROW]
        // Пример: l000, l100, l001
        const widgetName = `l${col.toString(16)}${row.toString(16).padStart(2, '0')}`;
        const placeholderId = `widget-${widgetName}`;

        if ($(`#${placeholderId}`).length === 0) {
            const $placeholder = $('<div></div>')
                .attr('id', placeholderId)
                .addClass('teaser-widget-placeholder')
                .text(`...`);

            $placeholder.insertBefore($trigger);
        }
        widgetsMap[widgetName] = 1;
    }
    return widgetsMap;
}

// Функция для догрузки ленты (скролл или инициализация пачки)
// count - сколько линий загрузить (по умолчанию 1)
function fetchFeedNextPage(count = 1) {
    if (isFeedLoading || currentFeedPage >= MAX_FEED_ROWS - 1) {
        if (currentFeedPage >= MAX_FEED_ROWS - 1) $trigger.hide();
        return;
    }

    isFeedLoading = true;
    const columns = getGridColumns();
    const widgetsMap = {};

    // Генерируем плейсхолдеры для `count` следующих рядов
    for (let i = 1; i <= count; i++) {
        const targetRow = currentFeedPage + i;
        if (targetRow < MAX_FEED_ROWS) {
            Object.assign(widgetsMap, createFeedPlaceholders(targetRow, columns));
        }
    }

    // Обновляем счетчик страниц
    currentFeedPage += count;

    if (Object.keys(widgetsMap).length === 0) {
        isFeedLoading = false;
        return;
    }

    requestTeasersAPI(widgetsMap, window.currentCategory)
        .then(widgets => {
            for (const wName in widgetsMap) {
                renderWidget(wName, widgets[wName], (t, url) => `
                    <div class="teaser-widget" data-teaser-id="${t.id}">
                        <a href="${url}" class="teaser-link">
                            <div class="teaser-image-wrapper">
                                <img src="${t.image}" alt="${t.title}" class="teaser-image" onerror="this.style.display='none'">
                            </div>
                            <div class="teaser-content">
                                <h3 class="teaser-title">${t.title}</h3>
                            </div>
                        </a>
                    </div>
                `);
            }
        })
        .catch(e => {
            console.error('Feed scroll load error:', e);
            Object.keys(widgetsMap).forEach(w => $(`#widget-${w}`).text('Error').addClass('empty'));
        })
        .finally(() => {
            isFeedLoading = false;
            checkAndLoadMore();
        });
}

function checkAndLoadMore() {
    if (isFeedLoading || !$feed.length) return;
    if ($trigger[0].getBoundingClientRect().top <= $(window).height() && currentFeedPage < MAX_FEED_ROWS) {
        fetchFeedNextPage(1);
    }
}

// --- ИНИЦИАЛИЗАЦИЯ ---
$(document).ready(function () {

    // 1. Сбор виджетов для ЕДИНОГО запроса
    const initialWidgetsMap = {};

    // --- Сайдбар (если есть) ---
    const $sidebarContainer = $('#preview-sidebar-content');
    if ($sidebarContainer.length && $sidebarContainer.is(':visible')) {
        for (let i = 0; i < 5; i++) {
            // --- ИЗМЕНЕНИЕ: Нейминг сайдбара приведен к стандарту 4 символа ---
            // Формат: s[1-char COL][2-char ROW]
            // Для сайдбара колонка всегда 0.
            // Было: s00, s01... (3 chars)
            // Стало: s000, s001... (4 chars)
            const rowHex = i.toString(16).padStart(2, '0');
            const wName = `s0${rowHex}`;
            // --- Конец изменения ---

            initialWidgetsMap[wName] = 1;
            $sidebarContainer.append(`
                <div id="widget-${wName}" class="sidebar-widget-placeholder" style="height: 80px; background: #f9f9f9; margin-bottom:10px; border-radius:6px;"></div>
            `);
        }
    }

    // --- Лента (Первый экран) ---
    if ($feed.length) {
        $feed.append($trigger);

        // Расчет количества рядов для первого экрана
        const initialRows = estimateRowsToFillScreen();
        console.log(`Расчет: нужно ${initialRows} рядов для заполнения экрана.`);

        const columns = getGridColumns();

        // Генерируем плейсхолдеры для всех начальных рядов
        for (let r = 0; r < initialRows; r++) {
            Object.assign(initialWidgetsMap, createFeedPlaceholders(r, columns));
        }

        // Устанавливаем индекс последнего загруженного ряда
        currentFeedPage = initialRows - 1;
    }

    // 2. Выполняем ЕДИНЫЙ запрос (если есть что запрашивать)
    if (Object.keys(initialWidgetsMap).length > 0) {
        requestTeasersAPI(initialWidgetsMap, window.currentCategory)
            .then(widgets => {
                // Рендеринг всего, что пришло
                for (const wName in widgets) {
                    const t = widgets[wName];

                    if (wName.startsWith('s')) {
                        // Сайдбар
                        renderWidget(wName, t, (teaser, url) => `
                            <a href="${url}" class="sidebar-widget" data-teaser-id="${teaser.id}">
                                <img src="${teaser.image}" class="sidebar-image" alt="">
                                <div class="sidebar-content">
                                    <h4 class="sidebar-title">${teaser.title}</h4>
                                </div>
                            </a>
                        `);
                    } else if (wName.startsWith('l')) {
                        // Лента
                        renderWidget(wName, t, (teaser, url) => `
                            <div class="teaser-widget" data-teaser-id="${teaser.id}">
                                <a href="${url}" class="teaser-link">
                                    <div class="teaser-image-wrapper">
                                        <img src="${teaser.image}" alt="${teaser.title}" class="teaser-image" onerror="this.style.display='none'">
                                    </div>
                                    <div class="teaser-content">
                                        <h3 class="teaser-title">${teaser.title}</h3>
                                    </div>
                                </a>
                            </div>
                        `);
                    }
                }
            })
            .catch(e => console.error("Initial load error:", e))
            .finally(() => {
                // После инициализации запускаем проверку скролла для ленты
                checkAndLoadMore();
            });
    }

    // --- Обработчики событий ---

    let inThrottle;
    $(window).on('scroll', () => {
        if (!inThrottle) {
            // Триггерим только догрузку ленты
            if ($feed.length && $(window).scrollTop() + $(window).height() > $(document).height() - 400) {
                fetchFeedNextPage(1);
            }
            inThrottle = true;
            setTimeout(() => inThrottle = false, 200);
        }
    });

    /**
     * Обработчик изменения размера окна (для адаптивности)
     */
    let resizeTimer;
    $(window).on('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            if ($feed.length) {
                $feed.empty();
                $feed.append($trigger);
                $trigger.show();

                // Пересчитываем для новой высоты/ширины
                const rows = estimateRowsToFillScreen();
                currentFeedPage = rows - 1; // Устанавливаем базу

                // Тут делаем отдельный запрос на перезагрузку ленты
                currentFeedPage = -1;
                fetchFeedNextPage(rows);

                if ($('#preview-sidebar-content').is(':visible') && $('#preview-sidebar-content').children().length === 0) {
                    // Перезагрузка сайдбара, если он был скрыт, а стал виден
                    // (Внимание: это создаст повторную логику, если не вынести loadSidebarTeasers)
                    // Но для простоты пока так, или лучше перезагрузить страницу полностью.
                }
            }
        }, 300);
    });
});