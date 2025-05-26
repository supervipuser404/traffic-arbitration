if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/static/js/service-worker.js")
        .then(reg => {
            console.log("Сервис-воркер зарегистрирован:", reg);
        })
        .catch(err => {
            console.error("Ошибка регистрации сервис-воркера:", err);
        });
}
