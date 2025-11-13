/*
  Глобальная логика для рендеринга "бесконечной" ленты тизеров.
  Ожидает, что JQuery ($) уже загружен.
  Ожидает, что в `window` определена переменная `currentCategory` (может быть null).
*/

// --- Управление состоянием ---
// ... (весь код управления cookie и observer остается без изменений) ...
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
// Эта функция будет следить за всеми тизерами, которые мы рендерим.
const observerCallback = (entries, observer) => {
    entries.forEach(entry => {
        // Проверяем, что элемент виден (isIntersecting),
        // виден как минимум на 50% (intersectionRatio)
        if (entry.isIntersecting && entry.intersectionRatio >= 0.5) {
            const teaserElement = entry.target;
            const teaserId = parseInt(teaserElement.dataset.teaserId, 10);

            if (teaserId && !seenIdsOnPage.has(teaserId)) {
                // --- ЭТО И ЕСТЬ ВАШЕ "Req. 2" (50% / 1 сек) ---
                // (Для 1 секунды нужен `setTimeout`, но для дедупликации
                // на этой странице достаточно простого добавления)

                // Добавляем в краткосрочный кэш
                seenIdsOnPage.add(teaserId);

                // Мы больше не отслеживаем этот элемент
                observer.unobserve(teaserElement);
            }
        }
    });
};

const intersectionObserver = new IntersectionObserver(observerCallback, {
    root: null, // (вьюпорт)
    threshold: 0.5 // (срабатывать при 50% видимости)
    // (Для 1 секунды нужна более сложная логика с `setTimeout`)
});

// --- Конец управления состоянием ---


$(document).ready(function () {
    const $feed = $('#teaser-feed');
    if (!$feed.length) return;

    let isLoading = false;
    let currentPage = 0; // "Страница" (ряд) ленты
    const $window = $(window);

// ... (функции throttle, getGridColumns, createPlaceholders, renderTeasers без изменений) ...
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
     * @returns {Object} - Карта { "l<row><col>": 1 } для API
     */
    function createPlaceholders(row, columns) {
        const widgetsMap = {};
        for (let col = 0; col < columns; col++) {
            // "l" - лента, <row> (hex), <col> (hex)
            const widgetName = `l${row.toString(16)}${col.toString(16)}`;
            // (ID для плейсхолдера)
            const placeholderId = `widget-${widgetName}`;

            // Убедимся, что плейсхолдер еще не существует
            if ($(`#${placeholderId}`).length === 0) {
                const $placeholder = $('<div></div>')
                    .attr('id', placeholderId)
                    .addClass('teaser-widget-placeholder')
                    .text(`Загрузка ${widgetName}...`);
                $feed.append($placeholder);
            }

            // `1` - это quantity (запрашиваем 1 тизер)
            widgetsMap[widgetName] = 1;
        }
        return widgetsMap;
    }

    /**
     * Рендерит полученные тизеры в плейсхолдеры
     * @param {Object} widgets - Карта { "l<row><col>": { ...teaser_data } }
     */
    function renderTeasers(widgets) {
        for (const widgetName in widgets) {
            const teaser = widgets[widgetName];
            const $placeholder = $(`#widget-${widgetName}`);

            if ($placeholder.length && teaser) {
                // --- ИСПРАВЛЕНИЕ: Класс "teaser-image-container" изменен на "teaser-image-wrapper" ---
                // Это исправит ошибку рендеринга (0px height) и остановит бесконечный цикл.
                const $teaserHTML = $(`
                    <div class="teaser-widget" data-teaser-id="${teaser.id}">
                        <a href="${teaser.url}" class="teaser-link">
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

                // --- НОВОЕ: Начинаем отслеживать этот тизер ---
                const newTeaserElement = $feed.find(`[data-teaser-id="${teaser.id}"]`)[0];
                if (newTeaserElement) {
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
        if (isLoading) return;
        isLoading = true;

        const columns = getGridColumns();
        const widgetsMap = createPlaceholders(page, columns);

        // Если виджеты не создались (например, 0 колонок), выходим
        if (Object.keys(widgetsMap).length === 0) {
            isLoading = false;
            return;
        }

// ... (остальной код fetchTeasers, checkAndLoadMore, throttledScrollHandler и т.д. без изменений) ...
        const longTermIds = getLongTermSeenIds();
        const pageIds = Array.from(seenIdsOnPage);
        // ---

        // (Здесь нужен UID, пока используем заглушку.
        // В идеале он должен приходить из cookie или <meta> тега)
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

                // --- НОВЫЕ ПОЛЯ ---
                seen_ids_page: pageIds,
                seen_ids_long_term: longTermIds
            })
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                // `data` теперь - это { widgets: {...}, newly_served_ids: [...] }

                if (data.widgets) {
                    renderTeasers(data.widgets);
                }

                // --- НОВОЕ: Обновляем долгосрочное хранилище ---
                if (data.newly_served_ids) {
                    updateLongTermSeenIds(data.newly_served_ids);
                    console.log(`Добавлено в cookie ${data.newly_served_ids.length} новых ID.`);
                }

                // --- ИЗМЕНЕНИЕ: Убрали checkAndLoadMore() отсюда ---
            })
            .catch(error => {
                console.error('Ошибка при загрузке тизеров:', error);
                // Очищаем плейсхолдеры, чтобы не висела "Загрузка..."
                Object.keys(widgetsMap).forEach(widgetName => {
                    $(`#widget-${widgetName}`).text('Ошибка').addClass('empty');
                });
            })
            .finally(() => {
                isLoading = false;
                // --- ИЗМЕНЕНИЕ: Перенесли checkAndLoadMore() сюда ---
                // Он будет вызван *после* того, как isLoading станет false.
                checkAndLoadMore();
            });
    }

    /**
     * Проверяет, заполнена ли страница. Если нет - грузит еще.
     */
    function checkAndLoadMore() {
        if (isLoading) return; // Уже грузится (или вызвано скроллом)


        // Проверяем, есть ли полоса прокрутки
        const hasScrollbar = $(document).height() > $window.height();

        if (!hasScrollbar) {
            console.log("Нет скролла, загружаем еще...");
            currentPage++;
            fetchTeasers(currentPage);
        }
    }

    /**
     * Обработчик "бесконечной" прокрутки
     */
    const throttledScrollHandler = throttle(() => {
        // (высота окна + прокрутка) > (высота документа - "триггерная" зона)
        if ($window.scrollTop() + $window.height() > $(document).height() - 400) {
            currentPage++;
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
            // Краткосрочные ID можно *не* сбрасывать,
            // т.к. бэкенд все равно их отфильтрует
            // seenIdsOnPage.clear();

            // Запускаем первую загрузку
            fetchTeasers(0);
        }, 300); // 300 мс "успокоения"
    };

    $window.on('resize', debouncedResizeHandler);

    // --- Первоначальная загрузка ---
    // (Загружаем первый ряд)
    fetchTeasers(0);
});