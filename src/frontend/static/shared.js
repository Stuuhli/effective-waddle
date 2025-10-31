(function (global) {
  'use strict';

  function getCookie(name) {
    return document.cookie
      .split('; ')
      .map((entry) => entry.split('='))
      .find(([key]) => key === name)?.[1];
  }

  function setCookie(name, value, attributes = '') {
    const cleaned = attributes ? attributes.replace(/;+$/g, '') : '';
    const attr = cleaned ? `; ${cleaned}` : '';
    document.cookie = `${name}=${value}${attr}`;
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

  let refreshInFlight = null;

  async function refreshAccessToken() {
    if (refreshInFlight) {
      return refreshInFlight;
    }
    const refreshToken = getCookie('rag_refresh');
    if (!refreshToken) {
      return null;
    }
    refreshInFlight = (async () => {
      try {
        const response = await fetch('/auth/jwt/refresh', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
          },
          credentials: 'include',
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!response.ok) {
          return null;
        }
        const data = await response.json().catch(() => ({}));
        const accessToken = data?.access_token;
        const refreshValue = data?.refresh_token;
        const expiresIn = Number(data?.expires_in);
        if (accessToken) {
          setCookie('rag_token', '', 'Max-Age=0; Path=/; SameSite=Lax;');
          const maxAge = Number.isFinite(expiresIn) && expiresIn > 0 ? Math.floor(expiresIn) : 1800;
          setCookie('rag_token', accessToken, `Path=/; SameSite=Lax; Max-Age=${maxAge}`);
        }
        if (refreshValue) {
          setCookie('rag_refresh', '', 'Max-Age=0; Path=/; SameSite=Lax;');
          setCookie('rag_refresh', refreshValue, 'Path=/; SameSite=Lax;');
        }
        return accessToken || null;
      } catch (error) {
        console.warn('Failed to refresh access token', error);
        return null;
      } finally {
        refreshInFlight = null;
      }
    })();
    return refreshInFlight;
  }

  async function fetchWithAuth(resource, options = {}, retryOnAuth = true) {
    const execute = () => fetch(resource, withAuth(options));
    let response = await execute();
    if (response.status !== 401 || !retryOnAuth) {
      if (response.status === 401) {
        redirectToLogin();
      }
      return response;
    }

    const refreshed = await refreshAccessToken();
    if (!refreshed) {
      redirectToLogin();
      return response;
    }

    response = await execute();
    if (response.status === 401) {
      redirectToLogin();
    }
    return response;
  }

  function clearAuthCookies() {
    const cookies = ['rag_token', 'rag_refresh', 'rag_admin'];
    cookies.forEach((name) => {
      setCookie(name, '', 'Max-Age=0; Path=/; SameSite=Lax;');
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
    setCookie,
    isAdmin,
    withAuth,
    refreshAccessToken,
    fetchWithAuth,
    clearAuthCookies,
    redirectToLogin,
    currentUser,
    enableHoverPrefetch,
  });
})(window);
