(function (global) {
  'use strict';

  function init() {
    const utils = global.FrontendUtils;
    if (!utils) {
      console.warn('FrontendUtils is unavailable; chat interactions are disabled.');
      return;
    }

    const layout = document.getElementById('chat-layout');
    const sidebarToggleButton = document.getElementById('sidebar-open');
    const adminLinks = document.getElementById('admin-links');
    const chatWindow = document.getElementById('chat-window');
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const streamStatus = document.getElementById('stream-status');
    const stopStreamButton = document.getElementById('stop-stream');
    const sendButton = document.getElementById('send-button');
    const conversationList = document.getElementById('conversation-list');
    const newConversationButton = document.getElementById('new-conversation');
    const logoutButton = document.getElementById('logout-button');

    const fullscreenToggle = document.getElementById('fullscreen-toggle');
    const fullscreenEnterIcon = fullscreenToggle?.querySelector('.fullscreen-toggle__icon--enter');
    const fullscreenExitIcon = fullscreenToggle?.querySelector('.fullscreen-toggle__icon--exit');
    const sidebarToggleIcon = document.getElementById('sidebar-toggle-icon');

    if (!layout || !chatForm || !chatWindow || !chatInput || !streamStatus) {
      console.error('Chat workspace markup is incomplete; aborting initialisation.');
      return;
    }

    const { isAdmin } = utils;
    if (!isAdmin() && adminLinks) {
      adminLinks.hidden = true;
    }

    const SIDEBAR_OPEN_SVG =
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" width="24" height="24" fill="#eeeeef"><path d="m256-200-56-56 224-224-224-224 56-56 224 224 224-224 56 56-224 224 224 224-56 56-224-224-224 224Z"/></svg>';
    const SIDEBAR_CLOSED_SVG =
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" width="24" height="24" fill="#eeeeef"><path d="M120-240v-80h720v80H120Zm0-200v-80h720v80H120Zm0-200v-80h720v80H120Z"/></svg>';

    let isFullscreen = layout.classList.contains('chat-layout--fullscreen');
    let sidebarWasOpen = !layout.classList.contains('chat-layout--sidebar-hidden');
    let activeConversationId = null;

    function setSidebarToggleState(isOpen) {
      sidebarToggleButton?.setAttribute('aria-pressed', String(isOpen));
      if (sidebarToggleIcon) {
        sidebarToggleIcon.innerHTML = isOpen ? SIDEBAR_OPEN_SVG : SIDEBAR_CLOSED_SVG;
      }
    }

    function ensureConversationPlaceholder() {
      if (!conversationList) {
        return;
      }
      const items = conversationList.querySelectorAll('.conversation-list__item');
      let emptyState = conversationList.querySelector('.conversation-list__empty');
      if (items.length === 0) {
        if (!emptyState) {
          emptyState = document.createElement('li');
          emptyState.className = 'conversation-list__empty';
          emptyState.textContent = 'No conversations yet. Create your first one to begin.';
          conversationList.appendChild(emptyState);
        }
      } else if (emptyState) {
        emptyState.remove();
      }
    }

    async function deleteConversation(conversationId, listItem) {
      if (!conversationId || !listItem) {
        return;
      }
      const confirmed = global.confirm('Delete this conversation and its messages?');
      if (!confirmed) {
        return;
      }
      try {
        const response = await global.fetch(
          `/chat/sessions/${conversationId}`,
          utils.withAuth({ method: 'DELETE' }),
        );
        if (!response.ok) {
          throw new Error(`Failed with status ${response.status}`);
        }
        listItem.remove();
        ensureConversationPlaceholder();
        if (activeConversationId === conversationId) {
          activeConversationId = null;
          appendMessage('system', 'Conversation deleted.');
        }
      } catch (error) {
        console.error('Failed to delete conversation', error);
        appendMessage('system', 'Deleting the conversation failed. Please try again.');
      }
    }

    function updateFullscreenToggle(enabled) {
      if (!fullscreenToggle) {
        return;
      }
      fullscreenToggle.setAttribute('aria-pressed', String(enabled));
      fullscreenToggle.setAttribute('aria-label', enabled ? 'Exit fullscreen' : 'Enter fullscreen');
      if (fullscreenEnterIcon) {
        fullscreenEnterIcon.hidden = enabled;
      }
      if (fullscreenExitIcon) {
        fullscreenExitIcon.hidden = !enabled;
      }
    }

    function openSidebar() {
      layout.classList.add('chat-layout--sidebar-open');
      layout.classList.remove('chat-layout--sidebar-hidden');
      sidebarWasOpen = true;
      setSidebarToggleState(true);
    }

    function closeSidebar() {
      layout.classList.add('chat-layout--sidebar-hidden');
      layout.classList.remove('chat-layout--sidebar-open');
      sidebarWasOpen = false;
      setSidebarToggleState(false);
    }

    function enterFullscreen() {
      isFullscreen = true;
      sidebarWasOpen = !layout.classList.contains('chat-layout--sidebar-hidden');
      document.body.classList.add('chat-fullscreen');
      layout.classList.add('chat-layout--fullscreen');
      if (sidebarWasOpen) {
        openSidebar();
      } else {
        closeSidebar();
      }
      updateFullscreenToggle(true);
    }

    function exitFullscreen() {
      isFullscreen = false;
      document.body.classList.remove('chat-fullscreen');
      layout.classList.remove('chat-layout--fullscreen');
      if (sidebarWasOpen) {
        openSidebar();
      } else {
        closeSidebar();
      }
      updateFullscreenToggle(false);
    }

    sidebarToggleButton?.addEventListener('click', () => {
      const isHidden = layout.classList.contains('chat-layout--sidebar-hidden');
      if (isHidden) {
        openSidebar();
      } else {
        closeSidebar();
      }
    });

    logoutButton?.addEventListener('click', () => {
      utils.redirectToLogin();
    });

    fullscreenToggle?.addEventListener('click', () => {
      if (isFullscreen) {
        exitFullscreen();
      } else {
        enterFullscreen();
      }
    });

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
      const deleteButton =
        target instanceof HTMLElement ? target.closest('.conversation-list__delete') : null;
      if (deleteButton) {
        event.preventDefault();
        event.stopPropagation();
        const listItem = deleteButton.closest('.conversation-list__item');
        const conversationId = deleteButton.dataset.deleteId || null;
        deleteConversation(conversationId, listItem);
        return;
      }
      const button = target instanceof HTMLElement ? target.closest('button[data-id]') : null;
      if (!button) {
        return;
      }

      conversationList
        .querySelectorAll('.conversation-list__button--active')
        .forEach((active) => active.classList.remove('conversation-list__button--active'));

      button.classList.add('conversation-list__button--active');
      activeConversationId = button.dataset.id || null;
      const title = button.querySelector('.conversation-list__title');
      const label = title ? title.textContent : 'conversation';
      appendMessage('system', `Loaded conversation "${label}".`);
      closeSidebar();
    });

    newConversationButton?.addEventListener('click', () => {
      appendMessage('system', 'New conversation started. Streaming responses will appear here.');
    });

    setSidebarToggleState(!layout.classList.contains('chat-layout--sidebar-hidden'));
    isFullscreen = layout.classList.contains('chat-layout--fullscreen');
    updateFullscreenToggle(isFullscreen);
    setStreamingState('idle');
    ensureConversationPlaceholder();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})(window);
