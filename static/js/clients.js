/**
 * 거래처 관련 JavaScript 기능
 */
document.addEventListener('DOMContentLoaded', function() {

    // 사업자번호 자동 하이픈 (123-45-67890)
    document.querySelectorAll('[data-format="business-number"]').forEach(function(input) {
        input.addEventListener('input', function(e) {
            let value = e.target.value.replace(/[^0-9]/g, '');
            if (value.length > 10) value = value.slice(0, 10);
            if (value.length > 5) {
                value = value.slice(0, 3) + '-' + value.slice(3, 5) + '-' + value.slice(5);
            } else if (value.length > 3) {
                value = value.slice(0, 3) + '-' + value.slice(3);
            }
            e.target.value = value;
        });
    });

    // 전화번호 자동 하이픈 (010-1234-5678)
    document.querySelectorAll('[data-format="phone"]').forEach(function(input) {
        input.addEventListener('input', function(e) {
            let value = e.target.value.replace(/[^0-9]/g, '');
            if (value.length > 11) value = value.slice(0, 11);
            if (value.length > 7) {
                value = value.slice(0, 3) + '-' + value.slice(3, 7) + '-' + value.slice(7);
            } else if (value.length > 3) {
                value = value.slice(0, 3) + '-' + value.slice(3);
            }
            e.target.value = value;
        });
    });

});
