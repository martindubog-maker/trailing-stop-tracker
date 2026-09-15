// Service worker mínimo: solo habilita la instalación como app.
// No cachea nada — la app siempre necesita internet para hablar con GitHub y Yahoo Finance.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', () => self.clients.claim());
self.addEventListener('fetch', () => {});
