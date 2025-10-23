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

  global.FrontendUtils = Object.freeze({
    getCookie,
    isAdmin,
    withAuth,
    clearAuthCookies,
    redirectToLogin,
    currentUser,
  });
})(window);
