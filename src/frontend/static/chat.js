(function (global) {
  'use strict';

  function init() {
    const utils = global.FrontendUtils;
    if (!utils) {
      console.warn('FrontendUtils is unavailable; chat interactions are disabled.');
      return;
    }

    const layout = document.getElementById('chat-layout');
    const sidebarOpen = document.getElementById('sidebar-open');
    const sidebarClose = document.getElementById('sidebar-close');
    const adminLinks = document.getElementById('admin-links');
    const chatWindow = document.getElementById('chat-window');
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const streamStatus = document.getElementById('stream-status');
    const stopStreamButton = document.getElementById('stop-stream');
    const sendButton = document.getElementById('send-button');
    const conversationList = document.getElementById('conversation-list');
    const newConversationButton = document.getElementById('new-conversation');

    if (!layout || !chatForm || !chatWindow || !chatInput || !streamStatus) {
      console.error('Chat workspace markup is incomplete; aborting initialisation.');
      return;
    }

    const { isAdmin } = utils;
    if (!isAdmin() && adminLinks) {
      adminLinks.hidden = true;
    }

    function openSidebar() {
      layout.classList.add('chat-layout--sidebar-open');
      layout.classList.remove('chat-layout--sidebar-hidden');
    }

    function closeSidebar() {
      layout.classList.add('chat-layout--sidebar-hidden');
      layout.classList.remove('chat-layout--sidebar-open');
    }

    sidebarOpen?.addEventListener('click', () => {
      const isHidden = layout.classList.contains('chat-layout--sidebar-hidden');
      if (isHidden) {
        openSidebar();
      } else {
        closeSidebar();
      }
    });

    sidebarClose?.addEventListener('click', closeSidebar);

    let streamingInterval = null;
    let streamBuffer = [];

    function setStreamingState(state) {
      const label = state === 'streaming' ? 'Streaming…' : state === 'stopped' ? 'Stopped' : 'Idle';
      streamStatus.textContent = label;
      streamStatus.classList.toggle('status-pill--streaming', state === 'streaming');
      streamStatus.classList.toggle('status-pill--idle', state !== 'streaming');
      if (stopStreamButton) {
        stopStreamButton.disabled = state !== 'streaming';
      }
      if (sendButton) {
        sendButton.disabled = state === 'streaming';
      }
    }

    function appendMessage(type, text) {
      const message = document.createElement('div');
      message.className = `message message--${type}`;

      const author = document.createElement('span');
      author.className = 'message__author';
      author.textContent = type === 'user' ? 'You' : type === 'assistant' ? 'Assistant' : 'System';

      const body = document.createElement('p');
      body.className = 'message__content';
      body.textContent = text;

      message.append(author, body);
      chatWindow.appendChild(message);
      chatWindow.scrollTop = chatWindow.scrollHeight;
      return message;
    }

    function stopStreaming(nextState) {
      if (streamingInterval) {
        global.clearInterval(streamingInterval);
        streamingInterval = null;
      }
      setStreamingState(nextState ?? 'stopped');
    }

    function startMockStreaming(container) {
      const placeholderTokens = [
        'Generating response',
        'Streaming chunk 1',
        'Streaming chunk 2',
        'Finalizing output',
      ];
      streamBuffer = [...placeholderTokens];
      setStreamingState('streaming');

      streamingInterval = global.setInterval(() => {
        const token = streamBuffer.shift();
        const messageContent = container.querySelector('.message__content');
        if (!messageContent) {
          stopStreaming('idle');
          return;
        }
        if (!token) {
          stopStreaming('idle');
          messageContent.textContent = 'Streaming skeleton complete. Integrate LLM output here.';
          return;
        }
        messageContent.textContent = token;
      }, 1200);
    }

    chatForm.addEventListener('submit', (event) => {
      event.preventDefault();
      const value = chatInput.value.trim();
      if (!value) {
        return;
      }
      appendMessage('user', value);
      chatInput.value = '';
      const assistant = appendMessage('assistant', 'Preparing to stream…');
      startMockStreaming(assistant);
    });

    stopStreamButton?.addEventListener('click', () => {
      stopStreaming();
      const lastAssistant = [...chatWindow.querySelectorAll('.message--assistant')].pop();
      const messageContent = lastAssistant?.querySelector('.message__content');
      if (messageContent) {
        messageContent.textContent += ' (stream stopped)';
      }
    });

    conversationList?.addEventListener('click', (event) => {
      const target = event.target;
      const button = target instanceof HTMLElement ? target.closest('button[data-id]') : null;
      if (!button) {
        return;
      }

      conversationList
        .querySelectorAll('.conversation-list__button--active')
        .forEach((active) => active.classList.remove('conversation-list__button--active'));

      button.classList.add('conversation-list__button--active');
      const title = button.querySelector('.conversation-list__title');
      const label = title ? title.textContent : 'conversation';
      appendMessage('system', `Loaded conversation "${label}".`);
      closeSidebar();
    });

    newConversationButton?.addEventListener('click', () => {
      appendMessage('system', 'New conversation started. Streaming responses will appear here.');
    });

    setStreamingState('idle');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})(window);
