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
        conversationMeta.delete(conversationId);
        listItem.remove();
        ensureConversationPlaceholder();
        if (activeConversationId === conversationId) {
          activeConversationId = null;
          stopStreaming('idle');
          chatWindow.innerHTML = '';
          appendMessage('system', 'Conversation deleted. Select or create a new session.');
        }
        await refreshConversations();
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

    const userRoles = (document.body.dataset.userRoles || '')
      .split(',')
      .map((role) => role.trim().toLowerCase())
      .filter(Boolean);
    const conversationMeta = new Map();
    let activeStream = null;

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

    function appendMessage(type, text, options = {}) {
      const message = document.createElement('div');
      message.className = `message message--${type}`;

      const author = document.createElement('span');
      author.className = 'message__author';
      author.textContent = type === 'user' ? 'You' : type === 'assistant' ? 'Assistant' : 'System';

      const body = document.createElement('p');
      body.className = 'message__content';
      const content = text ?? '';
      if (type === 'assistant' && content) {
        body.innerHTML = renderMarkdown(content);
      } else {
        body.textContent = content;
      }

      message.append(author, body);

      if (
        type === 'assistant' &&
        (Array.isArray(options.contextSources) || Array.isArray(options.citations))
      ) {
        const contextSources = Array.isArray(options.contextSources) ? options.contextSources : [];
        const citationItems = Array.isArray(options.citations) ? options.citations : [];
        renderContextSources(message, contextSources, citationItems);
      }

      chatWindow.appendChild(message);
      chatWindow.scrollTop = chatWindow.scrollHeight;
      return message;
    }

    function stopStreaming(nextState) {
      if (activeStream?.cancelRender && typeof activeStream.cancelRender === 'function') {
        try {
          activeStream.cancelRender();
        } catch (error) {
          console.warn('Failed to cancel pending render', error);
        }
      }
      if (activeStream?.controller) {
        activeStream.controller.abort();
      }
      activeStream = null;
      setStreamingState(nextState ?? 'stopped');
    }

    function setActiveConversationHighlight(conversationId) {
      if (!conversationList) {
        return;
      }
      conversationList
        .querySelectorAll('.conversation-list__button--active')
        .forEach((active) => active.classList.remove('conversation-list__button--active'));
      if (conversationId) {
        const button = conversationList.querySelector(`button[data-id="${conversationId}"]`);
        if (button) {
          button.classList.add('conversation-list__button--active');
        }
      }
    }

    function populateConversationMetaFromDom() {
      if (!conversationList) {
        return;
      }
      conversationList.querySelectorAll('button[data-id]').forEach((button) => {
        const id = button.dataset.id || '';
        if (!id) {
          return;
        }
        conversationMeta.set(id, {
          id,
          title:
            button.dataset.title ||
            button.querySelector('.conversation-list__title')?.textContent ||
            '',
          created_at: button.dataset.createdAt || null,
        });
      });
      ensureConversationPlaceholder();
    }

    function determineChatMode() {
      if (userRoles.includes('graphrag')) {
        return 'graphrag';
      }
      return 'rag';
    }

    function escapeHtml(value) {
      return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    function formatInlineMarkdown(text) {
      let html = escapeHtml(text);
      html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
      html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
      html = html.replace(/(^|\s)\*(.+?)\*(?=\s|$)/g, '$1<em>$2</em>');
      html = html.replace(/\[(.+?)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
      return html;
    }

    function renderMarkdown(text) {
      const lines = String(text ?? '')
        .replace(/\r\n/g, '\n')
        .split('\n');
      const html = [];
      let paragraph = [];
      let listType = null;
      let listItems = [];

      function flushParagraph() {
        if (!paragraph.length) {
          return;
        }
        const paragraphText = paragraph.join(' ').trim();
        if (paragraphText) {
          html.push(`<p>${formatInlineMarkdown(paragraphText)}</p>`);
        }
        paragraph = [];
      }

      function flushList() {
        if (!listType || !listItems.length) {
          listType = null;
          listItems = [];
          return;
        }
        const items = listItems
          .map((content) => `<li>${formatInlineMarkdown(content)}</li>`)
          .join('');
        html.push(`<${listType}>${items}</${listType}>`);
        listType = null;
        listItems = [];
      }

      lines.forEach((rawLine) => {
        const line = rawLine.replace(/\s+$/g, '');
        const trimmed = line.trim();
        if (!trimmed) {
          flushParagraph();
          flushList();
          return;
        }

        if (/^---+$/.test(trimmed)) {
          flushParagraph();
          flushList();
          html.push('<hr />');
          return;
        }

        const headingMatch = trimmed.match(/^(#{1,6})\s+(.*)$/);
        if (headingMatch) {
          flushParagraph();
          flushList();
          const level = Math.min(headingMatch[1].length, 6);
          html.push(`<h${level}>${formatInlineMarkdown(headingMatch[2])}</h${level}>`);
          return;
        }

        const bulletMatch = trimmed.match(/^[-*]\s+(.*)$/);
        if (bulletMatch) {
          flushParagraph();
          const content = bulletMatch[1];
          if (listType && listType !== 'ul') {
            flushList();
          }
          listType = 'ul';
          listItems.push(content);
          return;
        }

        const orderedMatch = trimmed.match(/^\d+\.\s+(.*)$/);
        if (orderedMatch) {
          flushParagraph();
          const content = orderedMatch[1];
          if (listType && listType !== 'ol') {
            flushList();
          }
          listType = 'ol';
          listItems.push(content);
          return;
        }

        if (listType) {
          flushList();
        }
        paragraph.push(trimmed);
      });

      flushParagraph();
      flushList();
      return html.join('');
    }

    function renderConversationList(conversations, selectId) {
      if (!conversationList) {
        return;
      }
      conversationList.innerHTML = '';
      conversationMeta.clear();
      const formatter = (iso) => {
        if (!iso) {
          return '';
        }
        const date = new Date(iso);
        if (Number.isNaN(date.getTime())) {
          return '';
        }
        return date.toLocaleString(undefined, {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
        });
      };
      conversations.forEach((conversation) => {
        conversationMeta.set(conversation.id, conversation);
        const item = document.createElement('li');
        item.className = 'conversation-list__item';

        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'conversation-list__button';
        button.dataset.id = conversation.id;
        button.dataset.title = conversation.title || '';

        const titleSpan = document.createElement('span');
        titleSpan.className = 'conversation-list__title';
        titleSpan.textContent = conversation.title || 'New session';

        const metaSpan = document.createElement('span');
        metaSpan.className = 'conversation-list__meta';
        metaSpan.textContent = formatter(conversation.created_at);

        button.append(titleSpan, metaSpan);

        const deleteButton = document.createElement('button');
        deleteButton.type = 'button';
        deleteButton.className = 'conversation-list__delete';
        deleteButton.dataset.deleteId = conversation.id;
        deleteButton.setAttribute('aria-label', 'Delete conversation');
        deleteButton.innerHTML = '<span class="icon icon--close" aria-hidden="true"></span>';

        item.append(button, deleteButton);
        conversationList.appendChild(item);
      });
      ensureConversationPlaceholder();
      const targetId =
        selectId && conversationMeta.has(selectId) ? selectId : activeConversationId;
      if (targetId) {
        setActiveConversationHighlight(targetId);
      }
    }

    async function refreshConversations(selectId) {
      try {
        const response = await global.fetch('/chat/sessions', utils.withAuth());
        if (!response.ok) {
          throw new Error(`Failed with status ${response.status}`);
        }
        const conversations = await response.json();
        renderConversationList(conversations, selectId);
      } catch (error) {
        console.error('Failed to refresh conversations', error);
      }
    }

    function renderMessages(messages) {
      chatWindow.innerHTML = '';
      if (!Array.isArray(messages) || !messages.length) {
        const placeholder = appendMessage('system', 'No messages yet. Ask something to begin.');
        placeholder.dataset.placeholder = 'true';
        return;
      }
      messages.forEach((message) => {
        const role = message.role === 'assistant' ? 'assistant' : message.role === 'user' ? 'user' : 'system';
        appendMessage(role, message.content || '', {
          contextSources: message.context,
          citations: message.citations,
        });
      });
    }

    async function loadMessages(conversationId) {
      if (!conversationId) {
        return;
      }
      try {
        const response = await global.fetch(
          `/chat/${conversationId}/messages`,
          utils.withAuth(),
        );
        if (!response.ok) {
          throw new Error(`Failed with status ${response.status}`);
        }
        const messages = await response.json();
        renderMessages(messages);
      } catch (error) {
        console.error('Failed to load messages', error);
        chatWindow.innerHTML = '';
        appendMessage('system', 'Unable to load conversation history.');
      }
    }

    async function activateConversation(conversationId, options = {}) {
      if (!conversationId) {
        return;
      }
      if (!conversationMeta.has(conversationId)) {
        await refreshConversations(conversationId);
      }
      stopStreaming('idle');
      activeConversationId = conversationId;
      setActiveConversationHighlight(conversationId);
      if (options.initialMessages) {
        renderMessages(options.initialMessages);
      } else if (!options.skipMessages) {
        await loadMessages(conversationId);
      }
      if (!options.skipSidebarClose) {
        closeSidebar();
      }
    }

    function deriveTitleFromQuery(query) {
      if (!query) {
        return null;
      }
      const cleaned = query.trim().split(/\s+/).slice(0, 12).join(' ');
      const clipped = cleaned.slice(0, 80).trim();
      return clipped || null;
    }

    async function createConversation(title) {
      const payload = title ? { title } : {};
      const response = await global.fetch(
        '/chat/sessions',
        utils.withAuth({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        }),
      );
      if (!response.ok) {
        throw new Error(`Failed with status ${response.status}`);
      }
      return response.json();
    }

    async function ensureConversation(query) {
      if (activeConversationId && conversationMeta.has(activeConversationId)) {
        return activeConversationId;
      }
      const session = await createConversation(deriveTitleFromQuery(query));
      await refreshConversations(session.id);
      await activateConversation(session.id, { initialMessages: [] });
      return session.id;
    }

    function renderContextSources(messageElement, sources, citations) {
      const hasSources = Array.isArray(sources) && sources.length > 0;
      const wrapperSelector = '.message__context-wrapper';
      let wrapper = messageElement.querySelector(wrapperSelector);
      if (!hasSources) {
        wrapper?.remove();
        return;
      }

      const citationMap = new Map();
      if (Array.isArray(citations)) {
        citations.forEach((item) => {
          if (item?.label) {
            citationMap.set(String(item.label), item);
          }
        });
      }

      const previousDetails = wrapper?.querySelector('.message__context');
      const wasOpen = Boolean(previousDetails?.open);

      if (!wrapper) {
        wrapper = document.createElement('div');
        wrapper.className = 'message__context-wrapper';
        messageElement.appendChild(wrapper);
      }
      wrapper.innerHTML = '';

      const details = document.createElement('details');
      details.className = 'message__context';
      details.open = wasOpen;

      const summary = document.createElement('summary');
      summary.textContent = `Context sources (${sources.length})`;
      details.appendChild(summary);

      const list = document.createElement('ul');
      list.className = 'context-source-list';

      sources.forEach((source, index) => {
        const listItem = document.createElement('li');
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'context-source';

        const labelSpan = document.createElement('span');
        labelSpan.className = 'context-source__label';
        labelSpan.textContent = source.label || `Source ${index + 1}`;

        const titleSpan = document.createElement('span');
        titleSpan.className = 'context-source__title';
        const titleText =
          source.document_title ||
          source.metadata?.document_title ||
          source.metadata?.docling_chunk?.origin?.filename ||
          `Source ${index + 1}`;
        titleSpan.textContent = titleText;

        const citationData = citationMap.get(source.label || '');
        const page =
          citationData?.page ??
          source.metadata?.page_number ??
          (Array.isArray(source.metadata?.page_numbers) ? source.metadata?.page_numbers[0] : null);
        const metaSpan = document.createElement('span');
        metaSpan.className = 'context-source__meta';
        const metaParts = [];
        if (page != null) {
          metaParts.push(`Page ${page}`);
        }
        if (source.metadata?.collection) {
          metaParts.push(String(source.metadata.collection));
        }
        metaSpan.textContent = metaParts.join(' • ');

        const snippetSpan = document.createElement('span');
        snippetSpan.className = 'context-source__snippet';
        if (source.snippet) {
          const trimmed = source.snippet.length > 200 ? `${source.snippet.slice(0, 197)}…` : source.snippet;
          snippetSpan.textContent = trimmed;
        } else {
          snippetSpan.textContent = 'Snippet not available.';
        }

        const previewUrl =
          source.metadata?.citation?.image_url ||
          source.metadata?.page_preview ||
          citationData?.preview ||
          citationData?.image_url ||
          null;
        const fallbackUrl = citationData?.source || source.metadata?.source_path || null;
        const resolvedPreview = previewUrl || fallbackUrl;
        if (resolvedPreview) {
          button.dataset.previewUrl = resolvedPreview;
          button.addEventListener('click', (event) => {
            event.preventDefault();
            openPreviewResource(resolvedPreview);
          });
        } else {
          button.classList.add('context-source--disabled');
        }

        button.append(labelSpan, titleSpan, metaSpan, snippetSpan);
        listItem.appendChild(button);
        list.appendChild(listItem);
      });

      details.appendChild(list);
      wrapper.appendChild(details);
    }

    async function openPreviewResource(previewTarget) {
      if (!previewTarget) {
        return;
      }

      let previewWindow = null;
      try {
        const previewUrl = new URL(previewTarget, global.location.origin);
        const sameOrigin = previewUrl.origin === global.location.origin;

        if (!sameOrigin) {
          global.open(previewUrl.toString(), '_blank', 'noopener');
          return;
        }

        previewWindow = global.open('about:blank', '_blank');
        if (!previewWindow) {
          throw new Error('Browser blocked the preview window.');
        }
        try {
          previewWindow.opener = null;
        } catch (openerError) {
          console.debug('Unable to clear preview window opener', openerError);
        }
        previewWindow.document.title = 'Loading preview…';

        const response = await global.fetch(
          previewUrl.toString(),
          utils.withAuth({ method: 'GET' }),
        );
        if (!response.ok) {
          throw new Error(`Preview request failed with status ${response.status}`);
        }

        const blob = await response.blob();
        const objectUrl = global.URL.createObjectURL(blob);
        previewWindow.location.replace(objectUrl);

        const cleanup = () => {
          global.URL.revokeObjectURL(objectUrl);
        };
        previewWindow.addEventListener('beforeunload', cleanup, { once: true });
        global.setTimeout(cleanup, 60_000);
      } catch (error) {
        if (previewWindow && !previewWindow.closed) {
          previewWindow.close();
        }
        console.error('Failed to open preview', error);
        global.alert('Unable to open the cited document preview. Please check your permissions.');
      }
    }

    async function streamChatResponse(conversationId, query, assistantMessage) {
      const contentElement = assistantMessage.querySelector('.message__content');
      if (!contentElement) {
        return;
      }
      const controller = new AbortController();
      const mode = determineChatMode();
      let assistantText = '';
      let contextChunks = [];
      let citationItems = [];
      let streamState = 'idle';
      const raf = global.requestAnimationFrame?.bind(global) ?? null;
      const caf = global.cancelAnimationFrame?.bind(global) ?? null;
      let pendingRender = null;
      let pendingRenderUsesTimeout = false;
      let streamingActive = true;

      const commitStreamingRender = () => {
        pendingRender = null;
        if (!streamingActive) {
          return;
        }
        contentElement.textContent = assistantText;
        chatWindow.scrollTop = chatWindow.scrollHeight;
      };

      const cancelScheduledRender = () => {
        if (pendingRender == null) {
          return;
        }
        if (pendingRenderUsesTimeout) {
          global.clearTimeout(pendingRender);
        } else if (caf) {
          caf(pendingRender);
        }
        pendingRender = null;
      };

      const scheduleStreamingRender = (immediate = false) => {
        if (!streamingActive) {
          return;
        }
        if (immediate) {
          commitStreamingRender();
          return;
        }
        if (pendingRender != null) {
          return;
        }
        if (raf) {
          pendingRenderUsesTimeout = false;
          pendingRender = raf(commitStreamingRender);
        } else {
          pendingRenderUsesTimeout = true;
          pendingRender = global.setTimeout(commitStreamingRender, 16);
        }
      };

      const stopStreamingRender = () => {
        streamingActive = false;
        cancelScheduledRender();
      };

      activeStream = { controller, message: assistantMessage, cancelRender: stopStreamingRender };
      setStreamingState('streaming');
      contentElement.innerHTML = '<p class="message__placeholder">Generating response…</p>';

      const handleEvent = (event) => {
        const type = event.type;
        if (type === 'token') {
          const text = typeof event.text === 'string' ? event.text : '';
          assistantText += text;
          streamState = 'streaming';
          streamingActive = true;
          scheduleStreamingRender(assistantText.length === text.length);
        } else if (type === 'status' && typeof event.message === 'string') {
          streamStatus.textContent = event.message;
        } else if (type === 'context' && Array.isArray(event.chunks)) {
          contextChunks = event.chunks;
        } else if (type === 'citations' && Array.isArray(event.citations)) {
          citationItems = event.citations;
          renderContextSources(assistantMessage, contextChunks, citationItems);
        } else if (type === 'error') {
          const message =
            typeof event.message === 'string'
              ? event.message
              : 'The assistant encountered an error.';
          stopStreamingRender();
          contentElement.textContent = message;
          streamState = 'stopped';
          controller.abort();
        } else if (type === 'done') {
          stopStreamingRender();
          streamState = 'idle';
          const finalText = assistantText.trim();
          contentElement.innerHTML = finalText
            ? renderMarkdown(finalText)
            : '<p>No response generated.</p>';
          chatWindow.scrollTop = chatWindow.scrollHeight;
          renderContextSources(assistantMessage, contextChunks, citationItems);
        }
      };

      try {
        const response = await global.fetch(
          `/chat/${conversationId}/messages`,
          utils.withAuth({
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, mode }),
            signal: controller.signal,
          }),
        );
        if (!response.ok || !response.body) {
          throw new Error(`Streaming failed with status ${response.status}`);
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
          const { value, done } = await reader.read();
          if (done) {
            break;
          }
          buffer += decoder.decode(value, { stream: true });
          let newlineIndex;
          while ((newlineIndex = buffer.indexOf('\n')) >= 0) {
            const line = buffer.slice(0, newlineIndex).trim();
            buffer = buffer.slice(newlineIndex + 1);
            if (!line) {
              continue;
            }
            try {
              const event = JSON.parse(line);
              handleEvent(event);
            } catch (error) {
              console.warn('Failed to parse chat stream event', line, error);
            }
          }
        }
        buffer += decoder.decode();
        const finalChunk = buffer.trim();
        if (finalChunk) {
          try {
            const event = JSON.parse(finalChunk);
            handleEvent(event);
          } catch (error) {
            console.warn('Failed to parse trailing chat event', finalChunk, error);
          }
        }
      } catch (error) {
        stopStreamingRender();
        if (controller.signal.aborted) {
          streamState = 'stopped';
          const current = contentElement.textContent?.trim();
          contentElement.textContent = current
            ? `${current} (stream stopped)`
            : 'Streaming stopped.';
        } else {
          streamState = 'stopped';
          console.error('Chat streaming failed', error);
          const message =
            error instanceof Error ? error.message : 'Unable to complete the request.';
          contentElement.textContent = message;
        }
      } finally {
        if (activeStream && activeStream.controller === controller) {
          activeStream = null;
        }
        stopStreamingRender();
        setStreamingState(streamState);
        await refreshConversations(conversationId);
      }
    }

    populateConversationMetaFromDom();
    refreshConversations().catch((error) => {
      console.warn('Initial conversation refresh failed', error);
    });

    chatForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const value = chatInput.value.trim();
      if (!value || sendButton?.disabled) {
        return;
      }
      try {
        const conversationId = await ensureConversation(value);
        chatWindow.querySelectorAll('.message[data-placeholder="true"]').forEach((node) =>
          node.remove(),
        );
        appendMessage('user', value);
        chatInput.value = '';
        const assistant = appendMessage('assistant', '');
        await streamChatResponse(conversationId, value, assistant);
      } catch (error) {
        console.error('Failed to send message', error);
        appendMessage('system', 'Unable to send message. Please try again.');
        setStreamingState('idle');
      }
    });

    stopStreamButton?.addEventListener('click', () => {
      if (!activeStream) {
        return;
      }
      const messageElement = activeStream.message;
      stopStreaming('stopped');
      const content = messageElement?.querySelector('.message__content');
      if (content) {
        const existing = content.textContent?.trim();
        content.textContent = existing ? `${existing} (stream stopped)` : 'Streaming stopped.';
      }
    });

    conversationList?.addEventListener('click', async (event) => {
      const target = event.target;
      const deleteButton =
        target instanceof HTMLElement ? target.closest('.conversation-list__delete') : null;
      if (deleteButton) {
        event.preventDefault();
        event.stopPropagation();
        const listItem = deleteButton.closest('.conversation-list__item');
        const conversationId = deleteButton.dataset.deleteId || null;
        await deleteConversation(conversationId, listItem);
        return;
      }
      const button = target instanceof HTMLElement ? target.closest('button[data-id]') : null;
      if (!button) {
        return;
      }
      const conversationId = button.dataset.id || '';
      if (!conversationId) {
        return;
      }
      await activateConversation(conversationId);
    });

    newConversationButton?.addEventListener('click', async () => {
      stopStreaming('idle');
      try {
        const session = await createConversation(null);
        await refreshConversations(session.id);
        await activateConversation(session.id, {
          initialMessages: [],
          skipSidebarClose: true,
        });
        chatWindow.querySelectorAll('.message[data-placeholder="true"]').forEach((node) =>
          node.remove(),
        );
        const placeholder = appendMessage(
          'system',
          'New conversation started. Ask a question to begin.',
        );
        placeholder.dataset.placeholder = 'true';
      } catch (error) {
        console.error('Failed to create conversation', error);
        appendMessage('system', 'Unable to create a new conversation. Please try again.');
      }
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
