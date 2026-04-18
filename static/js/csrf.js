(function () {
    const meta = document.querySelector('meta[name="csrf-token"]');
    const token = meta ? meta.getAttribute('content') : '';
    if (!token) return;

    function isUnsafeMethod(method) {
        return !['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes((method || 'GET').toUpperCase());
    }

    function isSameOrigin(input) {
        const url = typeof input === 'string' ? input : input && input.url;
        if (!url) return true;
        try {
            return new URL(url, window.location.href).origin === window.location.origin;
        } catch (_) {
            return false;
        }
    }

    function attachHiddenTokens() {
        document.querySelectorAll('form[method]').forEach(function (form) {
            if ((form.getAttribute('method') || '').toUpperCase() !== 'POST') return;
            if (form.querySelector('input[name="csrf_token"]')) return;

            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'csrf_token';
            input.value = token;
            form.appendChild(input);
        });
    }

    attachHiddenTokens();
    document.addEventListener('DOMContentLoaded', attachHiddenTokens);

    if (window.fetch) {
        const originalFetch = window.fetch.bind(window);
        window.fetch = function (input, init) {
            const options = init ? Object.assign({}, init) : {};
            const method = options.method || (input && input.method) || 'GET';

            if (isUnsafeMethod(method) && isSameOrigin(input)) {
                const headers = new Headers(options.headers || (input && input.headers) || {});
                if (!headers.has('X-CSRFToken')) {
                    headers.set('X-CSRFToken', token);
                }
                options.headers = headers;
            }

            return originalFetch(input, options);
        };
    }
})();
