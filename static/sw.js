/**
 * LogisFit Service Worker
 *
 * 네트워크 우선(Network First) 전략으로 동작합니다.
 * - 온라인: 항상 최신 데이터를 서버에서 가져옴
 * - 오프라인: 캐시된 정적 리소스로 기본 UI 제공
 */

const CACHE_NAME = 'logisfit-v1';

// 프리캐시할 정적 리소스 (앱 셸)
const PRECACHE_URLS = [
  '/',
  '/static/css/style.css',
  '/static/js/main.js',
  '/static/images/logo.png',
  '/static/images/favicon.ico',
];

// CDN 리소스 (캐시 허용)
const CDN_HOSTS = [
  'cdn.jsdelivr.net',
  'fonts.googleapis.com',
  'fonts.gstatic.com',
];

// ── Install ──────────────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_URLS).catch((err) => {
        console.warn('[SW] 프리캐시 일부 실패:', err);
      });
    })
  );
  // 새 서비스워커 즉시 활성화
  self.skipWaiting();
});

// ── Activate ─────────────────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    })
  );
  // 모든 클라이언트에 즉시 적용
  self.clients.claim();
});

// ── Fetch ────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // POST 등 비-GET 요청은 그냥 통과
  if (request.method !== 'GET') return;

  // API 요청은 캐시하지 않음
  if (url.pathname.startsWith('/api/')) return;

  // CDN 리소스: Cache First
  if (CDN_HOSTS.some((host) => url.hostname.includes(host))) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // 정적 파일: Cache First
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // HTML 페이지: Network First
  event.respondWith(networkFirst(request));
});

// ── 전략 함수 ────────────────────────────────────────

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response('', { status: 503 });
  }
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;

    return new Response(
      '<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
        '<title>오프라인 - LogisFit</title>' +
        '<style>body{font-family:"Noto Sans KR",sans-serif;display:flex;justify-content:center;align-items:center;' +
        'min-height:100vh;margin:0;background:#f8f9fa;color:#333}' +
        '.offline{text-align:center;padding:2rem}.offline h1{font-size:1.5rem;margin-bottom:1rem}' +
        '.offline p{color:#666}</style></head>' +
        '<body><div class="offline"><h1>오프라인 상태입니다</h1>' +
        '<p>인터넷 연결을 확인하고 다시 시도해주세요.</p>' +
        '<button onclick="location.reload()" style="margin-top:1rem;padding:0.5rem 1.5rem;border:none;' +
        'background:#0d6efd;color:#fff;border-radius:6px;cursor:pointer">새로고침</button></div></body></html>',
      { headers: { 'Content-Type': 'text/html; charset=UTF-8' } }
    );
  }
}
