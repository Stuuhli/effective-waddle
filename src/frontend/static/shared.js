(function (global) {
  'use strict';

  function getCookie(name) {
    return document.cookie
      .split('; ')
      .map((entry) => entry.split('='))
      .find(([key]) => key === name)?.[1];
  }

  function isAdmin() {
    const body = document.body;
    if (!body) {
      return false;
    }
    const attr = body.dataset.admin;
    if (attr === 'true' || attr === 'false') {
      return attr === 'true';
    }
    return getCookie('rag_admin') === '1';
  }

  function withAuth(options = {}) {
    const token = getCookie('rag_token');
    const headers = new Headers(options.headers || {});
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }
    return {
      ...options,
      headers,
      credentials: 'include',
    };
  }

  function clearAuthCookies() {
    const cookies = ['rag_token', 'rag_refresh', 'rag_admin'];
    cookies.forEach((name) => {
      document.cookie = `${name}=; Max-Age=0; Path=/; SameSite=Lax;`;
    });
  }

  function redirectToLogin() {
    clearAuthCookies();
    window.location.assign('/frontend/login');
  }

  function currentUser() {
    const body = document.body;
    if (!body) {
      return { id: '', email: '' };
    }
    return {
      id: body.dataset.userId || '',
      email: body.dataset.userEmail || '',
    };
  }

  const PREFETCH_ATTR = 'data-prefetch';
  const PREFETCH_MODE = 'hover';
  const prefetchRegistry = new Set();

  function prefetchLink(url) {
    if (!url || prefetchRegistry.has(url)) {
      return;
    }
    prefetchRegistry.add(url);
    const link = document.createElement('link');
    link.rel = 'prefetch';
    link.href = url;
    link.as = 'document';
    document.head.appendChild(link);
  }

  function enableHoverPrefetch(root = document) {
    if (!root || !root.querySelectorAll) {
      return;
    }
    const candidates = root.querySelectorAll(`[${PREFETCH_ATTR}="${PREFETCH_MODE}"]`);
    candidates.forEach((element) => {
      if (!(element instanceof HTMLAnchorElement) || element.dataset.prefetchBound === 'true') {
        return;
      }
      const { href } = element;
      const handlePrefetch = () => prefetchLink(href);
      element.addEventListener('mouseenter', handlePrefetch, { once: true });
      element.addEventListener('focus', handlePrefetch, { once: true });
      element.dataset.prefetchBound = 'true';
    });
  }

  function initSharedEnhancements() {
    enableHoverPrefetch(document);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSharedEnhancements, { once: true });
  } else {
    initSharedEnhancements();
  }

  global.FrontendUtils = Object.freeze({
    getCookie,
    isAdmin,
    withAuth,
    clearAuthCookies,
    redirectToLogin,
    currentUser,
    enableHoverPrefetch,
  });
})(window);
