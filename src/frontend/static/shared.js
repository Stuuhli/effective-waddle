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

  global.FrontendUtils = Object.freeze({ getCookie, isAdmin, withAuth });
})(window);
