/*
  Глобальная логика для рендеринга "бесконечной" ленты тизеров.
  Ожидает, что JQuery ($) уже загружен.
  Ожидает, что в `window` определена переменная `currentCategory` (может быть null).
*/

// --- Управление состоянием ---
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

        if (!cookieValue) {
            return [];
        }
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
    if (!newIds || newIds.length === 0) {
        return;
    }

    try {
        const currentIds = getLongTermSeenIds();
        // Используем Set для автоматической дедупликации
        const idSet = new Set(currentIds);
        newIds.forEach(id => idSet.add(id));

        // Превращаем обратно в массив и обрезаем "старые"
        let updatedIds = Array.from(idSet);
        if (updatedIds.length > MAX_COOKIE_IDS) {
            // Убираем самые старые ID, которые были в начале
            updatedIds = updatedIds.slice(updatedIds.length - MAX_COOKIE_IDS);
        }

        const jsonString = JSON.stringify(updatedIds);
        const expirationDate = new Date();
        expirationDate.setFullYear(expirationDate.getFullYear() + 1); // Храним 1 год

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
        // Элемент не виден, ничего не делаем
        if (!entry.isIntersecting) {
            return;
        }

        const targetElement = entry.target;
        const teaserId = parseInt(targetElement.dataset.teaserId, 10);

        // --- Задача 1: Это ТИЗЕР (у него есть data-teaser-id) ---
        // Отслеживаем просмотр для дедупликации
        if (teaserId && !seenIdsOnPage.has(teaserId)) {
            // Добавляем в краткосрочный кэш
            seenIdsOnPage.add(teaserId);
            // Мы отписываемся от этого элемента,
            // так как его просмотр засчитан
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

// --- Конец новой функции ---


$(document).ready(function () {
    const $feed = $('#teaser-feed');
    if (!$feed.length) return;

    const $trigger = $('<div id="feed-load-trigger-dynamic"></div>');
    $trigger.css({height: '1px', width: '100%'});
    $feed.append($trigger);

    let isLoading = false;
    let currentPage = 0; // "Страница" (ряд) ленты
    const $window = $(window);

    // Лимит рядов в "бесконечной" ленте
    const MAX_FEED_ROWS = 100;

    function throttle(func, limit) {
        let inThrottle;
        return function () {
            const args = arguments;
            const context = this;
            if (!inThrottle) {
                func.apply(context, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        }
    }

    /**
     * Определяет, сколько колонок сейчас на экране
     * @returns {number}
     */
    function getGridColumns() {
        const columns = $feed.css('--feed-columns');
        return parseInt(columns, 10) || 1;
    }

    /**
     * Создает плейсхолдеры для тизеров в DOM
     * @param {number} row - Номер ряда
     * @param {number} columns - Количество колонок
     * @returns {{widgetsMap: Object, lastPlaceholderId: string|null}}
     */
    function createPlaceholders(row, columns) {
        const widgetsMap = {};
        let lastPlaceholderId = null;

        for (let col = 0; col < columns; col++) {
            const widgetName = `l${row.toString(16)}${col.toString(16)}`;
            const placeholderId = `widget-${widgetName}`;

            if ($(`#${placeholderId}`).length === 0) {
                const $placeholder = $('<div></div>')
                    .attr('id', placeholderId)
                    .addClass('teaser-widget-placeholder')
                    .text(`Загрузка ${widgetName}...`);

                $placeholder.insertBefore($trigger);
            }

            lastPlaceholderId = placeholderId; // Запоминаем ID *последнего*
            widgetsMap[widgetName] = 1;
        }
        return {widgetsMap, lastPlaceholderId};
    }

    /**
     * Рендерит полученные тизеры в плейсхолдеры
     * @param {Object} widgets - Карта { "l<row><col>": { ...teaser_data } }
     * @param {string|null} lastPlaceholderId - ID элемента, который будет триггером
     */
    function renderTeasers(widgets, lastPlaceholderId) {
        for (const widgetName in widgets) {
            const teaser = widgets[widgetName];
            const placeholderId = `widget-${widgetName}`;
            const $placeholder = $(`#${placeholderId}`);

            if ($placeholder.length && teaser) {
                const finalTrackingUrl = buildTrackingUrl(teaser.url, widgetName);
                const $teaserHTML = $(`
                    <div class="teaser-widget" data-teaser-id="${teaser.id}">
                        <a href="${finalTrackingUrl}" class="teaser-link">
                            <div class="teaser-image-wrapper">
                                <img src="${teaser.image}" alt="${teaser.title}" class="teaser-image" onerror="this.style.display='none'">
                            </div>
                            <div class="teaser-content">
                                <h3 class="teaser-title">${teaser.title}</h3>
                            </div>
                        </a>
                    </div>
                `);

                // Заменяем плейсхолдер
                $placeholder.replaceWith($teaserHTML);

                const newTeaserElement = $teaserHTML[0];
                if (newTeaserElement) {
                    // Наблюдаем за тизером (только для seenIds)
                    intersectionObserver.observe(newTeaserElement);
                }

            } else if ($placeholder.length) {
                $placeholder.text('Нет данных');
                $placeholder.addClass('empty');
            }
        }
    }

    /**
     * Главная функция: запрашивает тизеры для N-го ряда
     * @param {number} page - Номер ряда (начиная с 0)
     */
    function fetchTeasers(page) {
        if (isLoading || page >= MAX_FEED_ROWS) {
            if (page >= MAX_FEED_ROWS) {
                console.log(`Достигнут лимит ленты (${MAX_FEED_ROWS} рядов).`);
                $trigger.hide();
            }
            return;
        }

        isLoading = true;
        currentPage++;

        const columns = getGridColumns();
        const {widgetsMap, lastPlaceholderId} = createPlaceholders(page, columns);

        if (Object.keys(widgetsMap).length === 0) {
            isLoading = false;
            return;
        }

        const longTermIds = getLongTermSeenIds();
        const pageIds = Array.from(seenIdsOnPage);

        const uid = 'placeholder-uid-' + (localStorage.getItem('my_uid') || 'new');

        console.log(`Запрос для ряда ${page}. Колонки: ${columns}.`);
        console.log(`Отправка seen_ids_page: [${pageIds.join(', ')}]`);
        console.log(`Отправка seen_ids_long_term: [${longTermIds.join(', ')}]`);

        fetch('/etc', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({
                uid: uid,
                ip: '1.1.1.1', // Заглушка, сервер должен сам определять
                ua: navigator.userAgent,
                url: window.location.href,
                loc: navigator.language || 'ru',
                w: $window.width(),
                h: $window.height(),
                widgets: widgetsMap,

                seen_ids_page: pageIds,
                seen_ids_long_term: longTermIds,

                category: window.currentCategory
            })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.widgets) {
                renderTeasers(data.widgets, lastPlaceholderId);
            }

            if (data.newly_served_ids) {
                updateLongTermSeenIds(data.newly_served_ids);
                console.log(`Добавлено в cookie ${data.newly_served_ids.length} новых ID.`);
            }
        })
        .catch(error => {
            console.error('Ошибка при загрузке тизеров:', error);
            Object.keys(widgetsMap).forEach(widgetName => {
                $(`#widget-${widgetName}`).text('Ошибка').addClass('empty');
            });
        })
        .finally(() => {
            isLoading = false;
            checkAndLoadMore();
        });
    }

    /**
     * Проверяет, заполнена ли страница. Если нет - грузит еще.
     */
    function checkAndLoadMore() {
        if (isLoading) return;

        const triggerTop = $trigger[0].getBoundingClientRect().top;
        const windowHeight = $window.height();

        if (triggerTop <= windowHeight && currentPage < MAX_FEED_ROWS) {
            console.log("Триггер виден, загружаем еще...");
            // `fetchTeasers` сам УВЕЛИЧИТ `currentPage`
            fetchTeasers(currentPage);
        }
    }

    /**
     * Обработчик "бесконечной" прокрутки
     */
    const throttledScrollHandler = throttle(() => {
        if ($window.scrollTop() + $window.height() > $(document).height() - 400) {
            fetchTeasers(currentPage);
        }
    }, 200); // Проверять не чаще, чем раз в 200 мс

    $window.on('scroll', throttledScrollHandler);

    /**
     * Обработчик изменения размера окна (для адаптивности)
     */
    let resizeTimer;
    const debouncedResizeHandler = () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            console.log("Изменение размера, перезагрузка...");
            // Сбрасываем все
            $feed.empty();
            currentPage = 0;

            $feed.append($trigger);
            $trigger.show();

            // Запускаем первую загрузку
            fetchTeasers(0);
        }, 300); // 300 мс "успокоения"
    };

    $window.on('resize', debouncedResizeHandler);

    // --- Первоначальная загрузка ---
    // (Загружаем первый ряд)
    fetchTeasers(0);
});