// Этот файл ожидает, что jQuery ($) уже загружен
// и что 'window.currentCategory' (e.g., "sport" or null)
// была определена в inline-скрипте в HTML.

$(document).ready(function () {

    // --- Глобальные переменные ---
    // Ищем feed только если он есть на странице
    const feed = $('#teaser-feed');
    if (feed.length === 0) {
        // Если контейнера нет, ничего не делаем
        return;
    }

    let currentPage = 0; // Отслеживаем текущую "страницу" (ряд) ленты
    let isLoading = false; // Флаг, чтобы не загружать данные дважды

    // Используем глобальную переменную, определенную в HTML
    const currentCategory = window.currentCategory || null;

    // --- 1. Определение сетки ---

    function getGridColumns() {
        const width = window.innerWidth;
        if (width > 1200) return 4;
        if (width > 900) return 3;
        if (width > 600) return 2;
        return 1;
    }

    function generateWidgetNames(pageIndex, columns) {
        const widgets = {};
        for (let i = 0; i < columns; i++) {
            const widgetName = `l${i.toString(16)}${pageIndex.toString(16).padStart(2, '0')}`;
            widgets[widgetName] = 1;
        }
        return widgets;
    }

    // --- 2. Запрос и Рендеринг Данных ---

    function placeholderImage(text) {
        return `https://placehold.co/400x225/E8E8E8/999?text=${encodeURIComponent(text)}`;
    }

    function renderTeasers(widgetsData, pageIndex) {
        const columns = getGridColumns();

        for (let i = 0; i < columns; i++) {
            const widgetName = `l${i.toString(16)}${pageIndex.toString(16).padStart(2, '0')}`;

            if (widgetsData[widgetName] && widgetsData[widgetName].length > 0) {
                const teaser = widgetsData[widgetName][0];
                const imageUrl = teaser.image ? teaser.image : placeholderImage(widgetName);

                const teaserHtml = `
                    <a class="teaser-widget" id="${widgetName}" href="${teaser.url}" target="_blank">
                        <div class="teaser-image-wrapper">
                            <img class="teaser-image" 
                                 src="${imageUrl}" 
                                 alt="${teaser.title || 'Teaser'}"
                                 onerror="this.src='${placeholderImage('Error')}'">
                        </div>
                        <div class="teaser-content">
                            <h3 class="teaser-title">${teaser.title || 'Заголовок тизера'}</h3>
                            <p class="teaser-text">${teaser.text || 'Описание тизера...'}</p>
                        </div>
                    </a>
                `;
                feed.append(teaserHtml);
            } else {
                const placeholderHtml = `
                    <div class="teaser-widget loading-placeholder" id="${widgetName}">
                        <span>(empty: ${widgetName})</span>
                    </div>
                `;
                feed.append(placeholderHtml);
            }
        }
    }

    function checkAndLoadMore() {
        if (isLoading) return;

        const scrollHeight = document.documentElement.scrollHeight;
        const windowHeight = $(window).height();

        if (scrollHeight <= windowHeight) {
            console.log("Контент не заполняет экран, загружаем еще...", currentPage);
            fetchTeasers(currentPage);
        }
    }


    function fetchTeasers(pageIndex) {
        if (isLoading) return;
        isLoading = true;

        console.log(`Запрос ряда ${pageIndex}`);

        const columns = getGridColumns();
        const widgetsToLoad = generateWidgetNames(pageIndex, columns);

        const placeholderIds = [];
        for (let i = 0; i < columns; i++) {
            const id = `placeholder-${pageIndex}-${i}`;
            placeholderIds.push(id);
            feed.append(`<div class="loading-placeholder" id="${id}">...</div>`);
        }

        const requestBody = {
            uid: "user-123", // Заглушка
            ip: "127.0.0.1", // Заглушка
            ua: navigator.userAgent,
            url: window.location.href,
            loc: "ru",
            w: window.innerWidth,
            h: window.innerHeight,
            widgets: widgetsToLoad,
            category: currentCategory // Передаем категорию
        };

        $.ajax({
            url: "/etc",
            type: "POST",
            contentType: "application/json",
            data: JSON.stringify(requestBody),
            success: function (response) {
                placeholderIds.forEach(id => $(`#${id}`).remove());

                if (response.widgets) {
                    renderTeasers(response.widgets, pageIndex);
                    currentPage = pageIndex + 1;
                }
            },
            error: function (xhr, status, error) {
                console.error("Ошибка при загрузке тизеров:", error);
                placeholderIds.forEach(id => $(`#${id}`).remove());
            },
            complete: function () {
                isLoading = false;
                checkAndLoadMore();
            }
        });
    }

    // --- 3. Инициализация и Обработчики ---

    function updateGrid() {
        const cols = getGridColumns();
        console.log(`Обновление сетки: ${cols} колонок (ширина ${window.innerWidth}px)`);
        document.documentElement.style.setProperty('--feed-columns', cols.toString());

        feed.empty();
        currentPage = 0;

        fetchTeasers(0);
    }

    $(window).on('scroll', function () {
        const scrollHeight = document.documentElement.scrollHeight;
        const scrollTop = $(window).scrollTop();
        const windowHeight = $(window).height();

        if (scrollTop + windowHeight >= scrollHeight - 500) {
            if (!isLoading) {
                console.log("Загрузка (скролл) следующего ряда...", currentPage);
                fetchTeasers(currentPage);
            }
        }
    });

    let resizeTimer;
    $(window).on('resize', function () {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(updateGrid, 300);
    });

    // --- Первый запуск ---
    updateGrid();

});