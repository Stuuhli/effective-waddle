(function (global) {
  'use strict';

  const EQUAL_ROW_SELECTOR = '[data-equal-row]';
  const DESKTOP_BREAKPOINT = '(min-width: 1081px)';
  let scheduleEqualRowHeights = () => {};

  function createEqualHeightSynchronizer() {
    const mediaQuery = window.matchMedia(DESKTOP_BREAKPOINT);
    const requestFrame =
      typeof window.requestAnimationFrame === 'function'
        ? window.requestAnimationFrame.bind(window)
        : (callback) => setTimeout(callback, 16);
    const cancelFrame =
      typeof window.cancelAnimationFrame === 'function'
        ? window.cancelAnimationFrame.bind(window)
        : clearTimeout;

    let frameId = 0;

    function collectGroups() {
      const groups = new Map();
      document.querySelectorAll(EQUAL_ROW_SELECTOR).forEach((element) => {
        const key = element.dataset.equalRow;
        if (!key) {
          return;
        }
        if (!groups.has(key)) {
          groups.set(key, []);
        }
        groups.get(key).push(element);
      });
      return groups;
    }

    function resetGroupHeights(group) {
      group.forEach((element) => {
        element.style.minHeight = '';
      });
    }

    function apply() {
      frameId = 0;
      const groups = collectGroups();
      if (!groups.size) {
        return;
      }

      groups.forEach((group) => {
        resetGroupHeights(group);
      });

      if (!mediaQuery.matches) {
        return;
      }

      groups.forEach((group) => {
        if (!Array.isArray(group) || group.length < 2) {
          return;
        }
        let tallest = 0;
        group.forEach((element) => {
          const { height } = element.getBoundingClientRect();
          tallest = Math.max(tallest, height);
        });
        const targetHeight = `${Math.ceil(tallest)}px`;
        group.forEach((element) => {
          element.style.minHeight = targetHeight;
        });
      });
    }

    function schedule() {
      if (frameId) {
        cancelFrame(frameId);
      }
      frameId = requestFrame(apply);
    }

    const handleChange = () => schedule();

    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', handleChange);
    } else if (typeof mediaQuery.addListener === 'function') {
      mediaQuery.addListener(handleChange);
    }
    window.addEventListener('resize', handleChange, { passive: true });

    return {
      schedule,
      apply: () => {
        if (frameId) {
          cancelFrame(frameId);
          frameId = 0;
        }
        apply();
      },
    };
  }

  function init() {
    const utils = global.FrontendUtils;
    if (!utils) {
      console.warn('Frontend utilities unavailable; admin console disabled.');
      return;
    }

    const elements = {
      userTableBody: document.getElementById('user-table-body'),
      collectionTableBody: document.getElementById('collection-table-body'),
      userSelect: document.getElementById('user-select'),
      collectionSelect: document.getElementById('collection-select'),
      userRoleOptions: document.getElementById('user-role-options'),
      collectionRoleOptions: document.getElementById('collection-role-options'),
      collectionCreateRoleOptions: document.getElementById('collection-create-role-options'),
      userRoleStatus: document.getElementById('user-role-status'),
      collectionRoleStatus: document.getElementById('collection-role-status'),
      createRoleStatus: document.getElementById('create-role-status'),
      createCollectionStatus: document.getElementById('create-collection-status'),
      userRoleForm: document.getElementById('user-role-form'),
      createRoleForm: document.getElementById('create-role-form'),
      collectionRoleForm: document.getElementById('collection-role-form'),
      createCollectionForm: document.getElementById('create-collection-form'),
      refreshUsers: document.getElementById('refresh-users'),
      refreshCollections: document.getElementById('refresh-collections'),
      resetUserForm: document.getElementById('reset-user-form'),
      resetCollectionForm: document.getElementById('reset-collection-form'),
    };

    const equalHeightSync = createEqualHeightSynchronizer();
    scheduleEqualRowHeights = equalHeightSync.apply;
    scheduleEqualRowHeights();

    const ROLE_CATEGORIES = Object.freeze({
      PERMISSION: 'permission',
      WORKSPACE: 'workspace',
    });
    const ROLE_LABELS = {
      [ROLE_CATEGORIES.PERMISSION]: 'Permissions',
      [ROLE_CATEGORIES.WORKSPACE]: 'Workspaces',
    };
    const ICONS = Object.freeze({
      toggle:
        '<svg xmlns="http://www.w3.org/2000/svg" height="24" viewBox="0 -960 960 960" width="24" fill="currentColor"><path d="M538-538ZM424-424Zm56 264q51 0 98-15.5t88-44.5q-41-29-88-44.5T480-280q-51 0-98 15.5T294-220q41 29 88 44.5t98 15.5Zm106-328-57-57q5-8 8-17t3-18q0-25-17.5-42.5T480-640q-9 0-18 3t-17 8l-57-57q19-17 42.5-25.5T480-720q58 0 99 41t41 99q0 26-8.5 49.5T586-488Zm228 228-58-58q22-37 33-78t11-84q0-134-93-227t-227-93q-43 0-84 11t-78 33l-58-58q49-32 105-49t115-17q83 0 156 31.5T763-763q54 54 85.5 127T880-480q0 59-17 115t-49 105ZM480-80q-83 0-156-31.5T197-197q-54-54-85.5-127T80-480q0-59 16.5-115T145-701L27-820l57-57L876-85l-57 57-615-614q-22 37-33 78t-11 84q0 57 19 109t55 95q54-41 116.5-62.5T480-360q38 0 76 8t74 22l133 133q-57 57-130 87T480-80Z"/></svg>',
      delete:
        '<svg xmlns="http://www.w3.org/2000/svg" height="24" viewBox="0 -960 960 960" width="24" fill="currentColor"><path d="M280-120q-33 0-56.5-23.5T200-200v-520h-40v-80h200v-40h240v40h200v80h-40v520q0 33-23.5 56.5T680-120H280Zm400-600H280v520h400v-520ZM360-280h80v-360h-80v360Zm160 0h80v-360h-80v360ZM280-720v520-520Z"/></svg>',
    });
    const currentUser = typeof utils.currentUser === 'function' ? utils.currentUser() : { id: '', email: '' };

    const state = {
      users: [],
      roles: [],
      collections: [],
    };

    function setStatus(element, message, variant) {
      if (!element) {
        return;
      }
      element.textContent = message || '';
      element.classList.remove('form-status--error', 'form-status--success');
      if (variant === 'error') {
        element.classList.add('form-status--error');
      } else if (variant === 'success') {
        element.classList.add('form-status--success');
      }
      scheduleEqualRowHeights();
    }

    function renderRoleCheckboxes(container, selectedNames, prefix, options = {}) {
      if (!container) {
        return;
      }
      container.innerHTML = '';
      const categories = options.categories || [ROLE_CATEGORIES.PERMISSION, ROLE_CATEGORIES.WORKSPACE];
      const showEmptyGroups = options.showEmptyGroups !== false;
      let rendered = false;

      categories.forEach((category) => {
        const roles = state.roles.filter((role) => role.category === category);
        if (!roles.length && !showEmptyGroups) {
          return;
        }

        const group = document.createElement('div');
        group.className = 'role-group';

        const label = document.createElement('p');
        label.className = 'role-group__label';
        label.textContent = options.labels?.[category] || ROLE_LABELS[category] || category;
        group.appendChild(label);

        if (!roles.length) {
          const empty = document.createElement('p');
          empty.className = 'role-checkboxes__empty';
          if (category === ROLE_CATEGORIES.WORKSPACE) {
            empty.textContent =
              options.workspaceHint || 'No workspaces available. Create one below to manage access.';
          } else {
            empty.textContent = options.permissionHint || 'No permissions available.';
          }
          group.appendChild(empty);
          container.appendChild(group);
          rendered = true;
          return;
        }

        const optionGrid = document.createElement('div');
        optionGrid.className = 'role-group__options';
        roles.forEach((role) => {
          const wrapper = document.createElement('label');
          wrapper.className = 'role-option';
          const input = document.createElement('input');
          input.type = 'checkbox';
          input.name = `${prefix || 'role'}-${role.id}`;
          input.value = role.name;
          input.checked = selectedNames.has(role.name);
          const span = document.createElement('span');
          span.textContent = role.name;
          wrapper.appendChild(input);
          wrapper.appendChild(span);
          optionGrid.appendChild(wrapper);
        });
        group.appendChild(optionGrid);
        container.appendChild(group);
        rendered = true;
      });

      if (!rendered) {
        const empty = document.createElement('p');
        empty.className = 'role-checkboxes__empty';
        empty.textContent = options.emptyMessage || 'No roles available. Create one first.';
        container.appendChild(empty);
      }
      scheduleEqualRowHeights();
    }

    function renderUsers() {
      const tbody = elements.userTableBody;
      if (!tbody) {
        return;
      }
      tbody.innerHTML = '';
      if (!state.users.length) {
        const row = document.createElement('tr');
        row.innerHTML = '<td colspan="4" class="admin-table__empty">No users found.</td>';
        tbody.appendChild(row);
        scheduleEqualRowHeights();
        return;
      }
      state.users.forEach((user) => {
        const row = document.createElement('tr');
        row.dataset.userId = user.id;

        const emailCell = document.createElement('td');
        emailCell.textContent = user.email;
        row.appendChild(emailCell);

        const rolesCell = document.createElement('td');
        const rolesWrapper = document.createElement('div');
        rolesWrapper.className = 'table-cell table-cell--wrap';
        if (user.roles.length) {
          user.roles.forEach((roleName) => {
            const pill = document.createElement('span');
            pill.className = 'role-pill';
            pill.textContent = roleName;
            rolesWrapper.appendChild(pill);
          });
        } else {
          const hint = document.createElement('span');
          hint.className = 'admin-table__hint';
          hint.textContent = 'No roles assigned';
          rolesWrapper.appendChild(hint);
        }
        rolesCell.appendChild(rolesWrapper);
        row.appendChild(rolesCell);

        const statusCell = document.createElement('td');
        const statusWrapper = document.createElement('div');
        statusWrapper.className = 'table-cell';
        const statusPill = document.createElement('span');
        statusPill.className = 'status-pill';
        statusPill.textContent = user.is_active ? 'Active' : 'Inactive';
        if (!user.is_active) {
          statusPill.classList.add('status-pill--inactive');
        }
        statusWrapper.appendChild(statusPill);
        const toggleButton = document.createElement('button');
        toggleButton.type = 'button';
        toggleButton.className = 'icon-button';
        toggleButton.dataset.userAction = 'toggle-status';
        toggleButton.dataset.userId = user.id;
        toggleButton.setAttribute(
          'aria-label',
          user.is_active ? `Deactivate ${user.email}` : `Activate ${user.email}`,
        );
        toggleButton.title = user.is_active ? 'Deactivate user' : 'Activate user';
        toggleButton.innerHTML = ICONS.toggle;
        statusWrapper.appendChild(toggleButton);
        statusCell.appendChild(statusWrapper);
        row.appendChild(statusCell);

        const actionsCell = document.createElement('td');
        actionsCell.className = 'table-actions';
        const actionsWrapper = document.createElement('div');
        actionsWrapper.className = 'table-cell table-cell--end';

        const deleteButton = document.createElement('button');
        deleteButton.type = 'button';
        deleteButton.className = 'icon-button icon-button--danger';
        deleteButton.dataset.userAction = 'delete';
        deleteButton.dataset.userId = user.id;
        deleteButton.setAttribute('aria-label', `Delete ${user.email}`);
        deleteButton.title = `Delete ${user.email}`;
        deleteButton.innerHTML = ICONS.delete;
        actionsWrapper.appendChild(deleteButton);
        actionsCell.appendChild(actionsWrapper);
        row.appendChild(actionsCell);

        tbody.appendChild(row);
      });
      scheduleEqualRowHeights();
    }

    function renderCollections() {
      const tbody = elements.collectionTableBody;
      if (!tbody) {
        return;
      }
      tbody.innerHTML = '';
      if (!state.collections.length) {
        const row = document.createElement('tr');
        row.innerHTML = '<td colspan="4" class="admin-table__empty">No collections found.</td>';
        tbody.appendChild(row);
        scheduleEqualRowHeights();
        return;
      }
      state.collections.forEach((collection) => {
        const row = document.createElement('tr');
        row.dataset.collectionId = collection.id;

        const nameCell = document.createElement('td');
        nameCell.textContent = collection.name;
        row.appendChild(nameCell);

        const rolesCell = document.createElement('td');
        const rolesWrapper = document.createElement('div');
        rolesWrapper.className = 'table-cell table-cell--wrap';
        if (collection.roles.length) {
          collection.roles.forEach((roleName) => {
            const pill = document.createElement('span');
            pill.className = 'role-pill';
            pill.textContent = roleName;
            rolesWrapper.appendChild(pill);
          });
        } else {
          const hint = document.createElement('span');
          hint.className = 'admin-table__hint';
          hint.textContent = 'No roles assigned';
          rolesWrapper.appendChild(hint);
        }
        rolesCell.appendChild(rolesWrapper);
        row.appendChild(rolesCell);

        const countCell = document.createElement('td');
        countCell.textContent = String(collection.document_count ?? 0);
        row.appendChild(countCell);

        const actionsCell = document.createElement('td');
        actionsCell.className = 'table-actions';
        const actionsWrapper = document.createElement('div');
        actionsWrapper.className = 'table-cell table-cell--end';

        const deleteButton = document.createElement('button');
        deleteButton.type = 'button';
        deleteButton.className = 'icon-button icon-button--danger';
        deleteButton.dataset.collectionAction = 'delete';
        deleteButton.dataset.collectionId = collection.id;
        deleteButton.setAttribute('aria-label', `Delete ${collection.name}`);
        deleteButton.title = `Delete ${collection.name}`;
        deleteButton.innerHTML = ICONS.delete;
        actionsWrapper.appendChild(deleteButton);
        actionsCell.appendChild(actionsWrapper);
        row.appendChild(actionsCell);

        tbody.appendChild(row);
      });
      scheduleEqualRowHeights();
    }

    function renderUserSelect() {
      const select = elements.userSelect;
      if (!select) {
        return;
      }
      const currentValue = select.value;
      select.innerHTML = '<option value="">Select a user…</option>';
      state.users.forEach((user) => {
        const option = document.createElement('option');
        option.value = user.id;
        option.textContent = user.email;
        select.appendChild(option);
      });
      if (currentValue && state.users.some((user) => user.id === currentValue)) {
        select.value = currentValue;
      } else {
        select.value = '';
      }
      updateUserRoleOptions();
    }

    function renderCollectionSelect() {
      const select = elements.collectionSelect;
      if (!select) {
        return;
      }
      const currentValue = select.value;
      select.innerHTML = '<option value="">Select a collection…</option>';
      state.collections.forEach((collection) => {
        const option = document.createElement('option');
        option.value = collection.id;
        option.textContent = collection.name;
        select.appendChild(option);
      });
      if (currentValue && state.collections.some((collection) => collection.id === currentValue)) {
        select.value = currentValue;
      } else {
        select.value = '';
      }
      updateCollectionRoleOptions();
    }

    function updateUserRoleOptions() {
      const userId = elements.userSelect?.value;
      const selectedRoles = new Set();
      if (userId) {
        const user = state.users.find((item) => item.id === userId);
        if (user) {
          user.roles.forEach((role) => selectedRoles.add(role));
        }
      }
      renderRoleCheckboxes(elements.userRoleOptions, selectedRoles, 'user-role', {
        showEmptyGroups: true,
        workspaceHint: 'Create a workspace role below to assign documents.',
      });
    }

    function updateCollectionRoleOptions() {
      const collectionId = elements.collectionSelect?.value;
      const selectedRoles = new Set();
      if (collectionId) {
        const collection = state.collections.find((item) => item.id === collectionId);
        if (collection) {
          collection.roles.forEach((role) => selectedRoles.add(role));
        }
      }
      renderRoleCheckboxes(elements.collectionRoleOptions, selectedRoles, 'collection-role', {
        categories: [ROLE_CATEGORIES.WORKSPACE],
        showEmptyGroups: true,
        workspaceHint: 'Workspaces control document access. Create one to continue.',
      });
    }

    function updateCollectionCreateRoleOptions() {
      renderRoleCheckboxes(elements.collectionCreateRoleOptions, new Set(), 'collection-create-role', {
        categories: [ROLE_CATEGORIES.WORKSPACE],
        showEmptyGroups: true,
        workspaceHint: 'Please first create a workspace to assign the collection to.',
      });
    }

    function collectCheckedRoles(container) {
      if (!container) {
        return [];
      }
      return Array.from(container.querySelectorAll('input[type="checkbox"]:checked')).map((input) => input.value);
    }

    function findUser(userId) {
      return state.users.find((item) => item.id === userId);
    }

    function findCollection(collectionId) {
      return state.collections.find((item) => item.id === collectionId);
    }

    async function handleUserStatusToggle(user) {
      const nextStatus = !user.is_active;
      let confirmMessage = nextStatus
        ? `Activate ${user.email}?`
        : `Deactivate ${user.email}?`;
      if (user.id === currentUser.id && !nextStatus) {
        confirmMessage = 'Deactivating your own account will immediately log you out. Continue?';
      }
      if (!global.confirm(confirmMessage)) {
        return;
      }
      try {
        const response = await fetch(`/admin/users/${user.id}/status`, utils.withAuth({
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ is_active: nextStatus }),
        }));
        if (!response.ok) {
          throw new Error('Request failed');
        }
        const updated = await response.json();
        const index = state.users.findIndex((item) => item.id === updated.id);
        if (index >= 0) {
          state.users[index] = updated;
        }
        renderUsers();
        renderUserSelect();
        setStatus(
          elements.userRoleStatus,
          nextStatus ? `Activated ${updated.email}.` : `Deactivated ${updated.email}.`,
          'success',
        );
        if (updated.id === currentUser.id && !updated.is_active) {
          utils.redirectToLogin();
        }
      } catch (error) {
        console.error(error);
        setStatus(elements.userRoleStatus, 'Unable to update user status.', 'error');
      }
    }

    async function handleUserDeletion(user) {
      const confirmMessage =
        user.id === currentUser.id
          ? 'Deleting your own account will remove access and redirect you to the login screen. Continue?'
          : `Delete ${user.email}? This action cannot be undone.`;
      if (!global.confirm(confirmMessage)) {
        return;
      }
      try {
        const response = await fetch(`/admin/users/${user.id}`, utils.withAuth({ method: 'DELETE' }));
        if (!response.ok) {
          throw new Error('Request failed');
        }
        state.users = state.users.filter((item) => item.id !== user.id);
        renderUsers();
        renderUserSelect();
        if (elements.userSelect && elements.userSelect.value === user.id) {
          elements.userSelect.value = '';
          updateUserRoleOptions();
        }
        setStatus(elements.userRoleStatus, `Deleted ${user.email}.`, 'success');
        if (user.id === currentUser.id) {
          utils.redirectToLogin();
        }
      } catch (error) {
        console.error(error);
        setStatus(elements.userRoleStatus, 'Unable to delete user.', 'error');
      }
    }

    async function handleCollectionDeletion(collection) {
      const message = `Delete collection "${collection.name}"? This will remove access for all workspaces.`;
      if (!global.confirm(message)) {
        return;
      }
      try {
        const response = await fetch(
          `/admin/collections/${collection.id}`,
          utils.withAuth({ method: 'DELETE' }),
        );
        if (!response.ok) {
          throw new Error('Request failed');
        }
        state.collections = state.collections.filter((item) => item.id !== collection.id);
        renderCollections();
        renderCollectionSelect();
        if (elements.collectionSelect && elements.collectionSelect.value === collection.id) {
          elements.collectionSelect.value = '';
        }
        updateCollectionRoleOptions();
        updateCollectionCreateRoleOptions();
        setStatus(
          elements.collectionRoleStatus,
          `Collection "${collection.name}" deleted.`,
          'success',
        );
      } catch (error) {
        console.error(error);
        setStatus(elements.collectionRoleStatus, 'Unable to delete collection.', 'error');
      }
    }

    function onUserTableClick(event) {
      const target = event.target;
      if (!(target instanceof Element)) {
        return;
      }
      const trigger = target.closest('[data-user-action]');
      if (!trigger) {
        return;
      }
      const userId = trigger.dataset.userId || '';
      const action = trigger.dataset.userAction;
      if (!userId || !action) {
        return;
      }
      const user = findUser(userId);
      if (!user) {
        return;
      }
      if (action === 'toggle-status') {
        handleUserStatusToggle(user);
      } else if (action === 'delete') {
        handleUserDeletion(user);
      }
    }

    function onCollectionTableClick(event) {
      const target = event.target;
      if (!(target instanceof Element)) {
        return;
      }
      const trigger = target.closest('[data-collection-action]');
      if (!trigger) {
        return;
      }
      const collectionId = trigger.dataset.collectionId || '';
      if (!collectionId) {
        return;
      }
      const collection = findCollection(collectionId);
      if (!collection) {
        return;
      }
      if (trigger.dataset.collectionAction === 'delete') {
        handleCollectionDeletion(collection);
      }
    }

    async function loadRoles() {
      try {
        const response = await fetch('/admin/roles', utils.withAuth());
        if (!response.ok) {
          throw new Error('Failed to load roles');
        }
        state.roles = await response.json();
        updateUserRoleOptions();
        updateCollectionRoleOptions();
        updateCollectionCreateRoleOptions();
      } catch (error) {
        console.error(error);
      }
    }

    async function loadUsers(showStatus) {
      try {
        const response = await fetch('/admin/users', utils.withAuth());
        if (!response.ok) {
          throw new Error('Failed to load users');
        }
        state.users = await response.json();
        renderUsers();
        renderUserSelect();
        if (showStatus) {
          setStatus(elements.userRoleStatus, 'Users refreshed.', 'success');
        }
      } catch (error) {
        console.error(error);
        if (showStatus) {
          setStatus(elements.userRoleStatus, 'Unable to refresh users.', 'error');
        }
      }
    }

    async function loadCollections(showStatus) {
      try {
        const response = await fetch('/admin/collections', utils.withAuth());
        if (!response.ok) {
          throw new Error('Failed to load collections');
        }
        state.collections = await response.json();
        renderCollections();
        renderCollectionSelect();
        if (showStatus) {
          setStatus(elements.collectionRoleStatus, 'Collections refreshed.', 'success');
        }
      } catch (error) {
        console.error(error);
        if (showStatus) {
          setStatus(elements.collectionRoleStatus, 'Unable to refresh collections.', 'error');
        }
      }
    }

    elements.userTableBody?.addEventListener('click', onUserTableClick);
    elements.collectionTableBody?.addEventListener('click', onCollectionTableClick);

    elements.userSelect?.addEventListener('change', () => {
      updateUserRoleOptions();
      setStatus(elements.userRoleStatus, '', null);
    });

    elements.collectionSelect?.addEventListener('change', () => {
      updateCollectionRoleOptions();
      setStatus(elements.collectionRoleStatus, '', null);
    });

    elements.resetUserForm?.addEventListener('click', () => {
      if (elements.userSelect) {
        elements.userSelect.value = '';
      }
      updateUserRoleOptions();
      setStatus(elements.userRoleStatus, 'Selection cleared.', 'success');
    });

    elements.resetCollectionForm?.addEventListener('click', () => {
      if (elements.collectionSelect) {
        elements.collectionSelect.value = '';
      }
      updateCollectionRoleOptions();
      setStatus(elements.collectionRoleStatus, 'Selection cleared.', 'success');
    });

    elements.refreshUsers?.addEventListener('click', () => {
      loadUsers(true);
    });

    elements.refreshCollections?.addEventListener('click', () => {
      loadCollections(true);
    });

    elements.userRoleForm?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const userId = elements.userSelect?.value;
      if (!userId) {
        setStatus(elements.userRoleStatus, 'Choose a user before saving.', 'error');
        return;
      }
      const roles = collectCheckedRoles(elements.userRoleOptions);
      try {
        const response = await fetch(`/admin/users/${userId}/roles`, utils.withAuth({
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ role_names: roles }),
        }));
        if (!response.ok) {
          throw new Error('Failed to update roles');
        }
        const updated = await response.json();
        const index = state.users.findIndex((user) => user.id === updated.id);
        if (index >= 0) {
          state.users[index] = updated;
        }
        renderUsers();
        renderUserSelect();
        setStatus(elements.userRoleStatus, 'Roles updated successfully.', 'success');
      } catch (error) {
        console.error(error);
        setStatus(elements.userRoleStatus, 'Unable to update roles.', 'error');
      }
    });

    elements.createRoleForm?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      if (!(form instanceof HTMLFormElement)) {
        return;
      }
      const formData = new FormData(form);
      const name = String(formData.get('role-name') || '').trim();
      const descriptionRaw = formData.get('role-description');
      const description = descriptionRaw ? String(descriptionRaw).trim() : '';
      if (!name) {
        setStatus(elements.createRoleStatus, 'Role name is required.', 'error');
        return;
      }
      try {
        const response = await fetch('/admin/roles', utils.withAuth({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, description: description || null }),
        }));
        if (!response.ok) {
          throw new Error('Failed to create role');
        }
        form.reset();
        setStatus(elements.createRoleStatus, 'Role created.', 'success');
        await loadRoles();
      } catch (error) {
        console.error(error);
        setStatus(elements.createRoleStatus, 'Unable to create role.', 'error');
      }
    });

    elements.createCollectionForm?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      if (!(form instanceof HTMLFormElement)) {
        return;
      }
      const formData = new FormData(form);
      const name = String(formData.get('collection-name') || '').trim();
      const descriptionRaw = formData.get('collection-description');
      const description = descriptionRaw ? String(descriptionRaw).trim() : '';
      if (!name) {
        setStatus(elements.createCollectionStatus, 'Collection name is required.', 'error');
        return;
      }
      const roles = collectCheckedRoles(elements.collectionCreateRoleOptions);
      try {
        const response = await fetch('/admin/collections', utils.withAuth({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, description: description || null, role_names: roles }),
        }));
        if (response.status === 409) {
          setStatus(elements.createCollectionStatus, 'A collection with that name already exists.', 'error');
          return;
        }
        if (!response.ok) {
          throw new Error('Failed to create collection');
        }
        const created = await response.json();
        state.collections.push(created);
        renderCollections();
        renderCollectionSelect();
        form.reset();
        updateCollectionCreateRoleOptions();
        setStatus(elements.createCollectionStatus, 'Collection created.', 'success');
      } catch (error) {
        console.error(error);
        setStatus(elements.createCollectionStatus, 'Unable to create collection.', 'error');
      }
    });

    elements.collectionRoleForm?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const collectionId = elements.collectionSelect?.value;
      if (!collectionId) {
        setStatus(elements.collectionRoleStatus, 'Choose a collection before saving.', 'error');
        return;
      }
      const roles = collectCheckedRoles(elements.collectionRoleOptions);
      try {
        const response = await fetch(`/admin/collections/${collectionId}/roles`, utils.withAuth({
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ role_names: roles }),
        }));
        if (response.status === 404) {
          setStatus(elements.collectionRoleStatus, 'Collection not found.', 'error');
          return;
        }
        if (!response.ok) {
          throw new Error('Failed to update collection roles');
        }
        const updated = await response.json();
        const index = state.collections.findIndex((collection) => collection.id === updated.id);
        if (index >= 0) {
          state.collections[index] = updated;
        }
        renderCollections();
        renderCollectionSelect();
        setStatus(elements.collectionRoleStatus, 'Collection roles updated.', 'success');
      } catch (error) {
        console.error(error);
        setStatus(elements.collectionRoleStatus, 'Unable to update collection.', 'error');
      }
    });

    (async () => {
      await loadRoles();
      await Promise.all([loadUsers(false), loadCollections(false)]);
      updateCollectionCreateRoleOptions();
    })();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window);
