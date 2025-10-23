(function (global) {
  'use strict';

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
    }

    function renderRoleCheckboxes(container, selectedNames, prefix) {
      if (!container) {
        return;
      }
      container.innerHTML = '';
      if (!state.roles.length) {
        const empty = document.createElement('p');
        empty.className = 'role-checkboxes__empty';
        empty.textContent = 'No roles available. Create one first.';
        container.appendChild(empty);
        return;
      }
      state.roles.forEach((role) => {
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
        container.appendChild(wrapper);
      });
    }

    function renderUsers() {
      const tbody = elements.userTableBody;
      if (!tbody) {
        return;
      }
      tbody.innerHTML = '';
      if (!state.users.length) {
        const row = document.createElement('tr');
        row.innerHTML = '<td colspan="3" class="admin-table__empty">No users found.</td>';
        tbody.appendChild(row);
        return;
      }
      state.users.forEach((user) => {
        const row = document.createElement('tr');

        const emailCell = document.createElement('td');
        emailCell.textContent = user.email;
        row.appendChild(emailCell);

        const rolesCell = document.createElement('td');
        if (user.roles.length) {
          user.roles.forEach((roleName) => {
            const pill = document.createElement('span');
            pill.className = 'role-pill';
            pill.textContent = roleName;
            rolesCell.appendChild(pill);
          });
        } else {
          const hint = document.createElement('span');
          hint.className = 'admin-table__hint';
          hint.textContent = 'No roles assigned';
          rolesCell.appendChild(hint);
        }
        row.appendChild(rolesCell);

        const statusCell = document.createElement('td');
        const statusPill = document.createElement('span');
        statusPill.className = 'status-pill';
        statusPill.textContent = user.is_active ? 'Active' : 'Inactive';
        if (!user.is_active) {
          statusPill.classList.add('status-pill--inactive');
        }
        statusCell.appendChild(statusPill);
        row.appendChild(statusCell);

        tbody.appendChild(row);
      });
    }

    function renderCollections() {
      const tbody = elements.collectionTableBody;
      if (!tbody) {
        return;
      }
      tbody.innerHTML = '';
      if (!state.collections.length) {
        const row = document.createElement('tr');
        row.innerHTML = '<td colspan="3" class="admin-table__empty">No collections found.</td>';
        tbody.appendChild(row);
        return;
      }
      state.collections.forEach((collection) => {
        const row = document.createElement('tr');

        const nameCell = document.createElement('td');
        nameCell.textContent = collection.name;
        row.appendChild(nameCell);

        const rolesCell = document.createElement('td');
        if (collection.roles.length) {
          collection.roles.forEach((roleName) => {
            const pill = document.createElement('span');
            pill.className = 'role-pill';
            pill.textContent = roleName;
            rolesCell.appendChild(pill);
          });
        } else {
          const hint = document.createElement('span');
          hint.className = 'admin-table__hint';
          hint.textContent = 'No roles assigned';
          rolesCell.appendChild(hint);
        }
        row.appendChild(rolesCell);

        const countCell = document.createElement('td');
        countCell.textContent = String(collection.document_count ?? 0);
        row.appendChild(countCell);

        tbody.appendChild(row);
      });
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
      renderRoleCheckboxes(elements.userRoleOptions, selectedRoles, 'user-role');
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
      renderRoleCheckboxes(elements.collectionRoleOptions, selectedRoles, 'collection-role');
    }

    function updateCollectionCreateRoleOptions() {
      renderRoleCheckboxes(elements.collectionCreateRoleOptions, new Set(), 'collection-create-role');
    }

    function collectCheckedRoles(container) {
      if (!container) {
        return [];
      }
      return Array.from(container.querySelectorAll('input[type="checkbox"]:checked')).map((input) => input.value);
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
