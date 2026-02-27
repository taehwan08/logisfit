/**
 * LogisFit - 3PL 물류 관리 시스템
 * 메인 JavaScript 파일
 */

document.addEventListener('DOMContentLoaded', function() {
    // 사이드바 토글 (모바일)
    initSidebarToggle();

    // 사이드바 스와이프 제스처 (모바일)
    initSidebarSwipe();

    // 메시지 자동 닫기
    initAutoCloseMessages();

    // 폼 유효성 검사
    initFormValidation();

    // 확인 다이얼로그
    initConfirmDialogs();

    // 툴팁 초기화
    initTooltips();
});

/**
 * 사이드바 토글 초기화 (모바일)
 */
function initSidebarToggle() {
    const sidebar = document.getElementById('sidebar');
    const toggleBtns = document.querySelectorAll('.sidebar-toggle, .sidebar-toggle-btn');

    if (!sidebar) return;

    // 오버레이 생성
    let overlay = document.querySelector('.sidebar-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.className = 'sidebar-overlay';
        document.body.appendChild(overlay);
    }

    // 토글 버튼 클릭 이벤트
    toggleBtns.forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            sidebar.classList.toggle('show');
            overlay.classList.toggle('show');
        });
    });

    // 오버레이 클릭 시 사이드바 닫기
    overlay.addEventListener('click', function() {
        sidebar.classList.remove('show');
        overlay.classList.remove('show');
    });

    // ESC 키로 사이드바 닫기
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && sidebar.classList.contains('show')) {
            sidebar.classList.remove('show');
            overlay.classList.remove('show');
        }
    });
}

/**
 * 사이드바 스와이프 제스처 (모바일)
 * - 왼쪽 가장자리에서 오른쪽 스와이프: 사이드바 열기
 * - 사이드바 위에서 왼쪽 스와이프: 사이드바 닫기
 */
function initSidebarSwipe() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.querySelector('.sidebar-overlay');
    if (!sidebar) return;

    let touchStartX = 0;
    let touchStartY = 0;
    let swiping = false;

    const EDGE_WIDTH = 30;       // 가장자리 감지 영역 (px)
    const SWIPE_THRESHOLD = 60;  // 스와이프 인식 최소 거리 (px)

    // 스와이프 시작
    document.addEventListener('touchstart', function(e) {
        const touch = e.touches[0];
        touchStartX = touch.clientX;
        touchStartY = touch.clientY;

        // 사이드바 닫혀있을 때: 왼쪽 가장자리에서만 시작
        if (!sidebar.classList.contains('show') && touchStartX <= EDGE_WIDTH) {
            swiping = true;
        }
        // 사이드바 열려있을 때: 사이드바/오버레이 위에서 시작
        else if (sidebar.classList.contains('show')) {
            swiping = true;
        }
    }, { passive: true });

    // 스와이프 종료
    document.addEventListener('touchend', function(e) {
        if (!swiping) return;
        swiping = false;

        const touch = e.changedTouches[0];
        const diffX = touch.clientX - touchStartX;
        const diffY = Math.abs(touch.clientY - touchStartY);

        // 수직 스크롤이 더 크면 무시
        if (diffY > Math.abs(diffX)) return;

        const isOpen = sidebar.classList.contains('show');

        // 오른쪽 스와이프 → 열기
        if (!isOpen && diffX > SWIPE_THRESHOLD) {
            sidebar.classList.add('show');
            if (overlay) overlay.classList.add('show');
        }
        // 왼쪽 스와이프 → 닫기
        else if (isOpen && diffX < -SWIPE_THRESHOLD) {
            sidebar.classList.remove('show');
            if (overlay) overlay.classList.remove('show');
        }
    }, { passive: true });
}

/**
 * 메시지 자동 닫기 (5초 후)
 */
function initAutoCloseMessages() {
    const alerts = document.querySelectorAll('.messages-container .alert');

    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            if (bsAlert) {
                bsAlert.close();
            }
        }, 5000);
    });
}

/**
 * Bootstrap 폼 유효성 검사
 */
function initFormValidation() {
    const forms = document.querySelectorAll('.needs-validation');

    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!form.checkValidity()) {
                e.preventDefault();
                e.stopPropagation();
            }
            form.classList.add('was-validated');
        });
    });
}

/**
 * 확인 다이얼로그 (data-confirm 속성 사용)
 */
function initConfirmDialogs() {
    const confirmElements = document.querySelectorAll('[data-confirm]');

    confirmElements.forEach(element => {
        element.addEventListener('click', function(e) {
            const message = this.dataset.confirm || '정말 진행하시겠습니까?';
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });
}

/**
 * Bootstrap 툴팁 초기화
 */
function initTooltips() {
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltipTriggerList.forEach(el => {
        new bootstrap.Tooltip(el);
    });
}

/**
 * AJAX 요청 헬퍼 함수
 * @param {string} url - 요청 URL
 * @param {Object} options - fetch 옵션
 * @returns {Promise}
 */
async function fetchAPI(url, options = {}) {
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken'),
        },
    };

    const mergedOptions = {
        ...defaultOptions,
        ...options,
        headers: {
            ...defaultOptions.headers,
            ...options.headers,
        },
    };

    try {
        const response = await fetch(url, mergedOptions);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error('API 요청 오류:', error);
        throw error;
    }
}

/**
 * 쿠키 값 가져오기
 * @param {string} name - 쿠키 이름
 * @returns {string|null}
 */
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

/**
 * 숫자 포맷팅 (천 단위 콤마)
 * @param {number} num - 숫자
 * @returns {string}
 */
function formatNumber(num) {
    return new Intl.NumberFormat('ko-KR').format(num);
}

/**
 * 날짜 포맷팅
 * @param {string|Date} date - 날짜
 * @param {string} format - 포맷 (기본: 'YYYY-MM-DD')
 * @returns {string}
 */
function formatDate(date, format = 'YYYY-MM-DD') {
    const d = new Date(date);
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');

    return format
        .replace('YYYY', year)
        .replace('MM', month)
        .replace('DD', day)
        .replace('HH', hours)
        .replace('mm', minutes);
}

/**
 * 로딩 스피너 표시/숨김
 * @param {boolean} show - 표시 여부
 */
function toggleLoading(show) {
    let spinner = document.getElementById('loading-spinner');

    if (!spinner && show) {
        spinner = document.createElement('div');
        spinner.id = 'loading-spinner';
        spinner.innerHTML = `
            <div style="position: fixed; top: 0; left: 0; right: 0; bottom: 0;
                        background: rgba(255,255,255,0.8); z-index: 9999;
                        display: flex; align-items: center; justify-content: center;">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">로딩 중...</span>
                </div>
            </div>
        `;
        document.body.appendChild(spinner);
    } else if (spinner && !show) {
        spinner.remove();
    }
}

/**
 * 토스트 메시지 표시
 * @param {string} message - 메시지
 * @param {string} type - 타입 (success, error, warning, info)
 */
function showToast(message, type = 'info') {
    const toastContainer = document.querySelector('.toast-container') || createToastContainer();

    const toastId = 'toast-' + Date.now();
    const bgClass = {
        success: 'bg-success',
        error: 'bg-danger',
        warning: 'bg-warning',
        info: 'bg-info',
    }[type] || 'bg-info';

    const toastHtml = `
        <div id="${toastId}" class="toast ${bgClass} text-white" role="alert">
            <div class="toast-body d-flex justify-content-between align-items-center">
                ${message}
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `;

    toastContainer.insertAdjacentHTML('beforeend', toastHtml);

    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement, { delay: 5000 });
    toast.show();

    toastElement.addEventListener('hidden.bs.toast', () => {
        toastElement.remove();
    });
}

function createToastContainer() {
    const container = document.createElement('div');
    container.className = 'toast-container position-fixed top-0 end-0 p-3';
    container.style.zIndex = '1100';
    document.body.appendChild(container);
    return container;
}
