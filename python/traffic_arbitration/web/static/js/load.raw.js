// Элемент, Тип, Количество, Дизайн, Подгрузка
var scrollSpace = 200;
var renderLock = false;
var renderScheme = [];
var scrollScheme = [];
var renderOffset = {};
var mediaWidth = 0;
var newsID = 0;
var catID = 0;
var htId = 0;
var tplSize = 0;
var resizeTimeout;
var gridRowGenerator;
var gridRow;

var hasWebP = false;

Render = {
    types: ['all', 'all4', 'aside', 'hotaside', 'incontent', 'noimgic', 'redic', 'mobic', 'topx2', 'inicx2', 'pcicno', 'mobicno', 'most_read'],
    wrappedTypes: ['noimgic', 'redic', 'mobic', 'topx2', 'inicx2'],
    imgSquareTypes: ['mobic', 'inicx2', 'topx2', 'incontent', 'mobicno', 'pcicno'],
    templates: {
        all: function (data, imgTag) {
            return '<a href="' + data.url + '" class="item-container item-size__l">' +
                       '<div class="item-img item-img__inline-l">' +
                           '<div class="item-category">' +
                              (data.hasOwnProperty('is_adv') && data.is_adv ? ADVERTISING :
                                ((typeof data.cat != "undefined") ? CATEGORIES[data.cat] : THE_BEST)) +
                           '</div>' +
                           imgTag +
                       '</div>' +
                       '<span class="item-link">' + data.title + '</span>' +
                   '</a>';
        },
        all4: function (data, imgTag) {
            return '<a href="' + data.url + '" class="item-container item-size__s">' +
                       '<div class="item-img item-img__inline-s">' + imgTag + '</div>' +
                       '<span class="item-link">' + data.title + '</span>' +
                   '</a>';
        },
        aside: function (data, imgTag) {
            return '<a href="' + data.url + '" class="item-container item-aside">' +
                       '<div class="item-img item-img__inline-l">' +
                           '<div class="item-category">' +
                              (data.hasOwnProperty('is_adv') && data.is_adv ? ADVERTISING :
                                ((typeof data.cat != "undefined") ? CATEGORIES[data.cat] : THE_BEST)) +
                           '</div>' +
                           imgTag +
                       '</div>' +
                       '<span class="item-link">' + data.title + '</span>' +
                   '</a>';
        },
        hotNewsAside: function (data, imgTag) {
            return '<a href="' + data.url + '" class="item-container">' +
                       '<div class="item-img item-img__inline-s">' + imgTag + '</div>' +
                       '<span class="item-link">' + data.title + '</span>' +
                   '</a>';
        },
        incontent: function (data, imgTag) {
            return '<div class="item">' +
                       '<a href="' + data.url + '" class="item-container__small">' +
                           '<div class="item-img item-img__inline-square">' + imgTag + '</div>' +
                           '<div class="item-container__text">' +
                               '<div class="item-title__small">' + data.title + '</div>' +
                               '<div class="item-stat">' +
                                 '<div class="stat__data__time"> <div class="icons-about-article icon__time"></div>' +
                                    Render.date() +
                                 '</div> ' +
                                 '<div class="stat__data__view"> <div class="icons-about-article icon__views"></div>' +
                                   (Math.floor(Math.random() * 2000000) + 1000000).toLocaleString('ru-RU') +
                                 '</div> ' +
                                 '<div class="stat__data__view">' + (data.hasOwnProperty('is_adv') && data.is_adv ? ADVERTISING : "") + '</div> ' +
                               '</div>' +
                           '</div>' +
                       '</a>' +
                   '</div>';
        },
        noImgIncontent: function (data) {
            return '<a href="' + data.url + '" class="item-container__small">' +
                       '<div class="item-title__small">' + data.title + '</div>' +
                       '<div class="item-stat">' +
                           '<div class="stat__data__time"> <div class="icons-about-article icon__time"></div>' +
                               Render.date() +
                           '</div>' +
                           '<div class="stat__data__view"> <div class="icons-about-article icon__views"></div>' +
                               Render.views() +
                           '</div>' +
                       '</div>' +
                   '</a>';
        },
        redBlockIncontent: function (data, imgTag) {
            return '<a href="' + data.url + '" class="item-container">' +
                       '<div class="item-img item-img__inline-s">' + imgTag + '</div>' +
                       '<div class="item-container__text">' +
                           '<p class="item-link item-link__bold">' + data.title + '</p>' +
                           // '<p class="item-link">Связаны ли они как-то с ростом заболеваемости в дальних регионаха и что за это будет?</p>' +
                       '</div>' +
                   '</a>';
        },
        groupIncontent: function (data, imgTag) {
            return '<a href="' + data.url + '" class="item-container__small">' +
                       '<div class="item-img item-img__inline-square">' + imgTag + '</div>' +
                       '<div class="item-container__text">' +
                           '<div class="item-title__small">' + data.title + '</div>' +
                           '<div class="item-stat">' +
                               '<div class="stat__data__time"> <div class="icons-about-article icon__time"></div>' +
                                   Render.date() +
                               '</div> ' +
                               '<div class="stat__data__view"> <div class="icons-about-article icon__views"></div>' +
                                   Render.views() +
                               '</div> ' +
                           '</div>' +
                       '</div>' +
                    '</a>';
        },
        mostRead: function(index, data) {
            return '<div class="mostReadItem">' +
                        '<span class="mostReadNum">' + index + '</span>' +
                        '<a class="mostReadLink" href="' + data.url + '">' + data.title + '</a>' +
                   '</div>';
        }
    },
    wrapTemplates: {
        noImgIncontent: function(html) {
            return '<div class="item item__no-image item__left-border">' + html + '</div>';
        },
        redBlockIncontent: function(html) {
            return '<div class="item__red-block">' +
                       '<p class="item-title__small">Материалы по теме</p>' +
                       html +
                   '</div>';
        },
        groupIncontent: function(html) {
            return '<div class="item">' + html + '</div>';
        }
    },
    buildTpl: function(type, data, index) {
        var img = Render.imgSquareTypes.includes(type) ? data.img : data.img_wide;
        // var img = type === 'hotaside' ? img.replace('500.300', '300.180').replace('500x300', '200') : img;
        var imgTag = '<img src="' + img + '">';

        if ((data.hasOwnProperty('teas') && data['teas'] == true) || (data.hasOwnProperty('n_teas') && data['n_teas'] == true)) {
            if (img.search('.webp') !== -1) {
                imgTag = '<picture>' +
                    '<source srcset="' + img + '" type="image/webp">' +
                    '<img class="imgwebp" src="' + img + '">' +
                    '</picture>';
            } else if (data.is_dynamic) {
                imgTag = '<picture>' +
                        '<source srcset="' + img + '" type="image/jpeg">' +
                        '<img src="' + img + '">' +
                    '</picture>';
            } else {
                var img_webp = replaceLast(img, '.jpg', '.webp');
                imgTag = '<picture>' +
                        '<source srcset="' + img_webp + '" type="image/webp">' +
                        '<source srcset="' + img + '" type="image/jpeg">' +
                        '<img src="' + img + '">' +
                    '</picture>';
            }
        }

        switch (type) {
            case 'all':
                return Render.templates.all(data, imgTag);
            case 'all4':
                return Render.templates.all4(data, imgTag);
            case 'incontent':
            case 'pcicno':
            case 'mobicno':
                return Render.templates.incontent(data, imgTag);
            case 'noimgic':
                return Render.templates.noImgIncontent(data);
            case 'redic':
                return Render.templates.redBlockIncontent(data, imgTag);
            case 'mobic':
            case 'topx2':
            case 'inicx2':
                return Render.templates.groupIncontent(data, imgTag);
            case 'aside':
                return Render.templates.aside(data, imgTag);
            case 'hotaside':
                return Render.templates.hotNewsAside(data, imgTag);
            case 'most_read':
                return Render.templates.mostRead(index + 1, data);
        }
    },
    wrap: function(type, html) {
        switch (type) {
            case 'noimgic':
                return Render.wrapTemplates.noImgIncontent(html);
            case 'redic':
                return Render.wrapTemplates.redBlockIncontent(html);
            case 'mobic':
            case 'topx2':
            case 'inicx2':
                return Render.wrapTemplates.groupIncontent(html);
        }
    },
    date: function() {
        var date = new Date();
        date.setDate(date.getDate() - Math.floor(Math.random() * 3 + 0.5));
        return date.getDate() + ' ' + DAYS[date.getMonth()];
    },
    views: function() {
        return (Math.floor(Math.random() * 2000000) + 1000000).toLocaleString('ru-RU');
    }
};

(function (context) {
    var img = new Image();
    img.onload = function () {
        context.hasWebP = !!(img.height > 0 && img.width > 0);
    };
    img.onerror = function () {
        context.hasWebP = false;
    };
    img.src = 'data:image/webp;base64,UklGRiIAAABXRUJQVlA4IBYAAAAwAQCdASoBAAEADsD+JaQAA3AAAAAA';
})(this);


// Старт, проверяем задачу
var loadInit = function(rules){
    //
    if(mW(0,599)) tplSize = "0-599";
    if(mW(600,767)) tplSize = "600-767";
    if(mW(768,1023)) tplSize = "768-1023";
    if(mW(1024,1440)) tplSize = "1024-1440";
    if(mW(1441,1600)) tplSize = "1441-1600";
    if(mW(1601,1920)) tplSize = "1601-1920";
    if(mW(1921,3840)) tplSize = "1921-3840";
    // Массив под запрос
    var request = {};
    var blockData = {};
    window.template = {};
    gridRowGenerator = getGridRow();
    gridRow = gridRowGenerator.next().value;
    // Перебираем правила блоков
    for(block in rules){

        if (!rules.hasOwnProperty(block)) continue;
        // Нет необходимого количества параметров - пропуск
        if (!(4<rules[block].length<6)) continue;
        // Нет целевого элемента для подгрузки - пропуск
        var rule = rules[block]; elem = $(rule[0]); if(elem.length!=1) continue;

        var targetElement = rule[0];
        var teaserType = rule[1];
        var amount = rule[2];
        var template = rule[3];
        // 4 - количество для подгрузки при скролле

        // Не нашли функцию рендера дизайна - пропуск
        if(!Render.types.includes(template)) continue;
        // Если все ок - пушим в схему настройку
        renderScheme.push([targetElement, teaserType, amount, template, (typeof rule[4] != "undefined" && rule[4] == parseInt(rule[4]) && rule[4] >0 )?rule[4]:false]);

        if (!window.template.hasOwnProperty(template)) {
            window.template[template] = 0;
        } else {
            window.template[template]++;
        }

        blockData[template + ':' + window.template[template]] = amount;

        // Пишем количество элементов в запрос этого типа
        if (!request.hasOwnProperty(teaserType)) {
            request[teaserType] = amount;
        } else {
            request[teaserType] += amount;
        }
    }
    // Отсылаем запрос
    corePost(request, blockData, function(json){renderStart(json);}, true);
    //
    $('#load_more').click(function(){ startScroll(true); });
};

// Механизм отсылки запроса к серверу
var corePost = function(request, blockData, callback, isFirstCall = false){
    // Если другая загрузка не в процессе - ставим флаг
    if(renderLock) return false; renderLock = true;
    //
    $('#load_more').css('display', 'none');
    $('#load_gif').css('display', 'flex');
    // Если не задан коллбек - заменяем пустым
    if(typeof callback != "function") callback = function(){};

    var db = [];
    var da = ['ZGV2X2dlbw==', 'ZGV2X2Rldg=='];
    if (typeof (window.URLSearchParams) != "undefined") {
        var up = new URLSearchParams(window.location.search);
        da.forEach(function(e) {
            e = atob(e); up.has(e) ? db.push(e + '=' + up.get(e)) : void(0);
        });
    }

    if (isFirstCall) {
        db.push('fc=1');
    }
    if (window.hasOwnProperty('DISABLE_OPTIONS') && window.DISABLE_OPTIONS) {
        db.push('do=1');
    }

    // Посылаем запрос с указанием отступов и ID новости
    $.post('/qaz.html' + '?' + db.join('&'), {
        request: request,
        b: blockData,
        after: renderOffset,
        id: newsID,
        catId: catID,
        htid: htId
        }, function (data) {
        if (data){
            // Пытаемся декодировать, нужно для обратной совместимости
            var decoded;
            if (typeof data == 'string') {
                decoded = JSON.parse(data);
            } else {
                decoded = data;
            }
            //
            $('#load_more').css('display', 'block');
            $('#load_gif').css('display', 'none');
            // Снимаем блокировку
            renderLock = false;
            // Запускаем коллбек
            if (decoded[Object.getOwnPropertyNames(request)[0]].length === 0) {
                renderLock = true;
                window.haveNotTeasers = true;
                console.log(window.haveNotTeasers);
            }
            if(!renderLock) callback(decoded);
        }}
    );
};

// Запускаем отрисовку блоков
var renderStart = function(info){
    var templateCount = [];
    // Для каждого правила
    for(b in renderScheme)
        if(renderScheme.hasOwnProperty(b)){
            var targetElem = renderScheme[b][0];
            var teaserType = renderScheme[b][1];
            var template = renderScheme[b][3];
            var scrollAmount = renderScheme[b][4];

            if (!templateCount.hasOwnProperty(template)) {
                templateCount[template] = 0;
            }

            var key = template;
            if (teaserType !== 'most_read' && teaserType !== 'featured') {
                key = template + ':' + templateCount[template];
            }


            templateCount[template]++;

            // Если есть что вывести
            if(info.hasOwnProperty(teaserType) && info[teaserType].hasOwnProperty(key) && info[teaserType][key].length){
                // Добавляем элементы
                $(targetElem).append(renderCore(template, info[teaserType][key]));

                // Записываем отступ для данного типа
                if(!renderOffset.hasOwnProperty(teaserType)) {
                    renderOffset[teaserType] = renderScheme[b][2];
                } else {
                    renderOffset[teaserType] = renderOffset[teaserType] + renderScheme[b][2];
                }
            }
            // Если для правила задана подгрузка при скролле
            if(scrollAmount) {
                scrollScheme.push([targetElem, teaserType, scrollAmount, template]);
            }
        }
    // На событие скролла
    if(scrollScheme.length>0) $(window).scroll( function() { startScroll(); } );
    // На событие ресайза
    window.addEventListener('resize', function(event) {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(function(){
            var lastWidth = mediaWidth;
            var currWidth = mW();
            if(lastWidth!=currWidth){
                var min = Math.min(lastWidth,currWidth);
                var max = Math.max(lastWidth,currWidth);
                if((min<=599 && 600<=max) || (min<=767 && 768<=max) || (min<=1023 && 1024<=max) || (min<=1439 && 1440<=max))
                    window.location.reload();
            }
        }, 1000);
    });
    // Вешаем эвент на клики
    onClick();
};

startScroll = function (click) {
    // Если загрузка в процессе - игнорируем
    if (renderLock) return false;
    // Если не передан параметр "проверка"
    click = (typeof click != "undefined");
    // Массив под запрос
    var request = {};
    var blockData = {};
    var plan = [];
    var templateCount = [];
    // Для каждого отслеживаемого

    for (s in scrollScheme) {
        if (scrollScheme.hasOwnProperty(s)) {
            // Находим блок
            var elem = $(scrollScheme[s][0]);
            var amount = scrollScheme[s][2];
            var template = scrollScheme[s][3];
            // Проверяем необходимость подгрузки
            if (click || $(window).scrollTop() + $(window).height() + scrollSpace + 1 > elem.offset().top + elem.height()) {
                // Пишем количество элементов в запрос этого типа
                if (!request.hasOwnProperty(scrollScheme[s][1])) request[scrollScheme[s][1]] = scrollScheme[s][2];
                else request[scrollScheme[s][1]] = request[scrollScheme[s][1]] + scrollScheme[s][2];
                // Пишем план подгрузки
                plan.push(scrollScheme[s]);
            }

            if (!templateCount.hasOwnProperty(template)) {
                templateCount[template] = window.template[template] !== undefined ? window.template[template] + 1 : 0;
            } else {
                templateCount[template]++;
            }

            blockData[template + ':' + templateCount[template]] = amount;
        }
    }

    // Если нет активной загрузки - отсылаем запрос
    if (!renderLock && !jQuery.isEmptyObject(request)) {

        for (var t in templateCount) {
            window.template[t] = templateCount[t];
        }

        corePost(request, blockData, function (info) {
            for (p in plan) {
                if (plan.hasOwnProperty(p)) {
                    var key = plan[p][3] + ':' + (window.template.hasOwnProperty(plan[p][3]) ? window.template[plan[p][3]] : 0);

                    // Выводим элементы
                    $(plan[p][0]).append(renderCore(plan[p][3], info[plan[p][1]][key]));

                    // Записываем отступ для данного типа
                    if (!renderOffset.hasOwnProperty(plan[p][1])) renderOffset[plan[p][1]] = plan[p][2];
                    else renderOffset[plan[p][1]] = renderOffset[plan[p][1]] + plan[p][2];
                }
            }
            // Обновляем эвент на клики
            onClick();
        });
    }
};


// Обертка над дизайнами элементов
var renderCore = function (type, data) {
    var i = 0, j = 0;
    // Фикс для бокового блока
    if (type === 'side') {
        if (mW(1024, 1439) + mW(1440) > 0) {
            var rebuild = [];
            var x = (mW(1024, 1439) == 1) ? 2 : 3, y = 3;
            for (j = 0; j < y; j++) {
                for (i = 0; i < x; i++) {
                    if (typeof data[(i * y) + j] != "undefined") {
                        rebuild.push(data[(i * y) + j]);
                    }
                }
            }
            data = rebuild;
        }
    }
    // Выполняем основную задачу+
    var html = '';
    var gridIndex = 0;

    for (i = 0; i < data.length; i++) {
        if (gridIndex > gridRow.length - 1) {
            gridRow = gridRowGenerator.next().value;
            gridIndex = 0;
        }
        // var preload = new Image();
        // if (hasWebP && ((data[i].hasOwnProperty('teas') && data[i]['teas'] == true) || (data[i].hasOwnProperty('n_teas') && data[i]['n_teas'] == true))) {
        //     preload.src = replaceLast(data[i].img, '.jpg', '.webp');
        // } else {
        //     preload.src = data[i].img;
        // }
        if ((data[i].hasOwnProperty('teas') && data[i]['teas'] == true) || (data[i].hasOwnProperty('n_teas') && data[i]['n_teas'] == true)) {
            data[i].url = data[i].url + "&size=" + tplSize + "&zone=" + type + "&pos=" + (i + 1);
        }

        html += Render.buildTpl(type, data[i], i);
        gridIndex++;
    }

    if (Render.wrappedTypes.includes(type)) {
        html = Render.wrap(type, html);
    }

    return html;
};

var mW = function(min,max){
    if(typeof min == "undefined" || mediaWidth==0){
        var e = window, a = 'inner';
        if (!('innerWidth' in window )) { a = 'client'; e = document.documentElement || document.body; }
        mediaWidth = e[a+'Width']; }
    if(typeof min == "undefined") return mediaWidth;
    else return (typeof max == "undefined") ? ((min<=mediaWidth)?1:0) : ((min <= mediaWidth && mediaWidth <= max)?1:0);
};


function getGridRow() {
    var currentIndex = -1;
    var grid = {
        mobile: [['m', 'm'], ['l']],
        tablet: [['m', 'm'], ['l', 's'], ['s', 'l']],
        desktop: [['s', 's', 's'], ['m', 'm'], ['s', 's', 's']],
        desktopWide: [['xs', 'xs', 'xs', 'xs'], ['m', 'xs', 'xs'], ['xs', 'xs', 'm'], ['m', 'm']],
    };
    var screenType = 'desktopWide';

    if (mW(0, 767)) {
        screenType = 'mobile';
    } else if (mW(768, 1023)) {
        screenType = 'tablet';
    } else if (mW(1024, 1439)) {
        screenType = 'desktop';
    }

    return makeIterable({
        next: function () {
            currentIndex++;
            if (currentIndex > grid[screenType].length - 1) {
                currentIndex = 0;
            }
            return {
                done: false,
                value: grid[screenType][currentIndex],
            };
        },
    });
};

var makeIterable = typeof Symbol !== 'undefined'
  ?
    function makeIterable(iterator) { iterator[Symbol.iterator] = returnThis; return iterator; }
  :
    function makeIterable(iterator) { return iterator; };

function returnThis() {
  return this;
}

replaceLast = function (str, what, replacement) {
    var pcs = str.split(what);
    var lastPc = pcs.pop();
    return pcs.join(what) + replacement + lastPc;
};

if (mW(0, 979)) {
    $(window).scroll(function() {
        if (window.hasOwnProperty('SHOW_OVERLAY') && window.SHOW_OVERLAY === false) {
            return;
        }
        var targetElement = $('.focusable');
        var article = $('.row-article');
        var overlayAppearsAt = 250;
        var overlayDisappearsAt = -100;
        if (targetElement.length) {
            var distance = targetElement.offset().top - $(this).scrollTop();
            if ((distance <= overlayDisappearsAt || distance > overlayAppearsAt) && article.hasClass('focusOverlay')) {
                article.removeClass('focusOverlay');
            } else if (distance <= overlayAppearsAt && distance > overlayDisappearsAt && !article.hasClass('focusOverlay'))  {
                article.addClass('focusOverlay');
            }
        }
    });
}
