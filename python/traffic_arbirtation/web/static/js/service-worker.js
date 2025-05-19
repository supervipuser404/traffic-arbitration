self.addEventListener("push", function (event) {
    console.log("Push received (заглушка):", event);

    const title = "ETC News";
    const options = {
        body: "Это тестовое push-уведомление",
        icon: "/icons/icon-192x192.png",
        badge: "/icons/icon-192x192.png"
    };

    event.waitUntil(self.registration.showNotification(title, options));
});
