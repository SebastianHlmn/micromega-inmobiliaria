
const state = { view: 'dashboard', conversations: [], categories: [], stages: [] };

async function api(path, options) {
  const response = await fetch(path, Object.assign({
    headers: { 'Content-Type': 'application/json' }
  }, options || {}));
  if (!response.ok) {
    let detail = 'Error ' + response.status;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}

function esc(value) {
  return String(value == null ? '' : value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function fmtDate(value) {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString('es-AR', { dateStyle: 'short', timeStyle: 'short' });
  } catch (_) {
    return value;
  }
}

function fmtMoney(value, currency) {
  if (value == null) return '—';
  try {
    return new Intl.NumberFormat('es-AR', {
      style: 'currency',
      currency: currency || 'ARS',
      maximumFractionDigits: 0
    }).format(value);
  } catch (_) {
    return String(value);
  }
}

function toast(message) {
  const el = document.getElementById('toast');
  el.textContent = message;
  el.classList.add('show');
  setTimeout(function () { el.classList.remove('show'); }, 2400);
}

function setView(view) {
  state.view = view;
  document.querySelectorAll('.view').forEach(function (el) { el.classList.remove('active'); });
  document.querySelectorAll('.nav-item').forEach(function (el) { el.classList.remove('active'); });
  document.getElementById('view-' + view).classList.add('active');
  document.querySelector('.nav-item[data-view="' + view + '"]').classList.add('active');
  const titles = {
    dashboard: 'Resumen',
    conversations: 'Conversaciones',
    properties: 'Propiedades',
    categories: 'Categorías',
    visits: 'Visitas'
  };
  document.getElementById('page-title').textContent = titles[view] || view;
  refreshCurrent();
}

function renderBars(items, labelKey, valueKey) {
  if (!items || !items.length) return '<div class="empty">Sin datos todavía.</div>';
  const max = Math.max.apply(null, items.map(function (x) { return x[valueKey] || 0; }).concat([1]));
  return items.map(function (item) {
    const width = Math.round(((item[valueKey] || 0) / max) * 100);
    return '<div class="bar-row">' +
      '<span>' + esc(item[labelKey]) + '</span>' +
      '<div class="bar-track"><div class="bar-fill" style="width:' + width + '%"></div></div>' +
      '<strong>' + esc(item[valueKey]) + '</strong>' +
    '</div>';
  }).join('');
}

async function loadDashboard() {
  const view = document.getElementById('view-dashboard');
  view.innerHTML = '<div class="section-card">Cargando…</div>';
  const data = await api('/api/management/dashboard');
  const t = data.totals || {};
  view.innerHTML =
    '<div class="cards">' +
      metric('Consultas', t.conversations || 0, 'conversaciones registradas') +
      metric('Personas', t.contacts || 0, 'contactos únicos') +
      metric('Mensajes recibidos', t.inbound_messages || 0, 'mensajes de clientes') +
      metric('Intereses', t.interests || 0, 'propiedades marcadas') +
      metric('Pedidos de visita', t.visit_requests || 0, 'detectados en conversación') +
      metric('Visitas concertadas', t.scheduled_visits || 0, 'confirmadas manualmente') +
      metric('Derivaciones', t.handoffs || 0, 'requieren atención humana') +
    '</div>' +
    '<div class="section-card">' +
      '<div class="section-head"><h2>Embudo comercial</h2><span class="muted tiny">Estado actual de las conversaciones</span></div>' +
      '<div class="funnel">' +
        (data.funnel || []).map(function (x) {
          return '<div class="funnel-step"><span class="muted tiny">' + esc(x.name) + '</span><strong>' + esc(x.count) + '</strong></div>';
        }).join('') +
      '</div>' +
    '</div>' +
    '<div class="grid-2">' +
      '<div class="section-card"><div class="section-head"><h2>Qué preguntan</h2></div>' +
        renderBars(data.categories, 'name', 'count') +
      '</div>' +
      '<div class="section-card"><div class="section-head"><h2>Barrios buscados</h2></div>' +
        renderBars(data.neighborhoods, 'name', 'count') +
      '</div>' +
    '</div>' +
    '<div class="section-card"><div class="section-head"><h2>Propiedades con interés</h2></div>' +
      renderBars((data.properties || []).map(function (x) {
        return { name: x.code + ' · ' + x.address, count: x.interests };
      }), 'name', 'count') +
    '</div>';
}

function metric(label, value, note) {
  return '<div class="card"><div class="metric-label">' + esc(label) + '</div><div class="metric-value">' +
    esc(value) + '</div><div class="muted tiny">' + esc(note) + '</div></div>';
}

async function loadConversations() {
  const view = document.getElementById('view-conversations');
  view.innerHTML = '<div class="section-card">Cargando…</div>';
  const rows = await api('/api/management/conversations');
  state.conversations = rows;
  view.innerHTML =
    '<div class="section-card">' +
      '<div class="section-head"><h2>Bandeja</h2><div><span class="muted tiny">' + rows.length + ' conversaciones</span> <a class="small-btn" href="/api/management/export/conversations.csv">Exportar CSV</a></div></div>' +
      '<div class="filters"><input id="conversation-search" placeholder="Buscar por nombre, teléfono, barrio o texto…"></div>' +
      '<div id="conversation-table"></div>' +
    '</div>';
  renderConversationTable(rows);
  document.getElementById('conversation-search').addEventListener('input', function (event) {
    const q = event.target.value.toLowerCase().trim();
    const filtered = state.conversations.filter(function (row) {
      const haystack = JSON.stringify(row).toLowerCase();
      return !q || haystack.includes(q);
    });
    renderConversationTable(filtered);
  });
}

function renderConversationTable(rows) {
  const host = document.getElementById('conversation-table');
  if (!rows.length) {
    host.innerHTML = '<div class="empty">Todavía no hay conversaciones.</div>';
    return;
  }
  host.innerHTML =
    '<table><thead><tr><th>Contacto</th><th>Último mensaje</th><th>Búsqueda</th><th>Categorías</th><th>Estado</th></tr></thead><tbody>' +
    rows.map(function (row) {
      const profile = row.profile || {};
      const search = [
        profile.operation,
        (profile.neighborhoods || []).join(', '),
        profile.rooms_min ? profile.rooms_min + ' amb.' : null,
        profile.budget_max ? fmtMoney(profile.budget_max, profile.currency) : null
      ].filter(Boolean).join(' · ') || 'Sin perfil';
      const cats = (row.categories || []).slice(0, 3).map(function (c) {
        return '<span class="pill">' + esc(c.name) + '</span>';
      }).join('');
      const contact = row.contact || {};
      return '<tr class="clickable" data-conversation-id="' + row.id + '">' +
        '<td><strong>' + esc(contact.name || 'Sin nombre') + '</strong><br><span class="muted tiny">' + esc(contact.phone || '') + '</span></td>' +
        '<td>' + esc((row.last_message || '').slice(0, 110)) + '<br><span class="muted tiny">' + fmtDate(row.last_message_at) + '</span></td>' +
        '<td>' + esc(search) + '</td>' +
        '<td>' + (cats || '<span class="muted">—</span>') + '</td>' +
        '<td><span class="pill green">' + esc((row.stage && row.stage.name) || 'Nuevo') + '</span>' +
          (row.needs_human ? '<span class="pill warn">humano</span>' : '') + '</td>' +
      '</tr>';
    }).join('') +
    '</tbody></table>';
  host.querySelectorAll('[data-conversation-id]').forEach(function (row) {
    row.addEventListener('click', function () { openConversation(row.dataset.conversationId); });
  });
}

async function openConversation(id) {
  const drawer = document.getElementById('drawer');
  const content = document.getElementById('drawer-content');
  drawer.classList.add('open');
  content.innerHTML = '<p>Cargando conversación…</p>';
  const results = await Promise.all([
    api('/api/management/conversations/' + id),
    state.stages.length ? Promise.resolve(state.stages) : api('/api/management/stages')
  ]);
  const data = results[0];
  state.stages = results[1];
  const contact = data.contact || {};
  const profile = data.profile || {};
  const search = [
    profile.operation,
    (profile.neighborhoods || []).join(', '),
    profile.rooms_min ? profile.rooms_min + (profile.rooms_max && profile.rooms_max !== profile.rooms_min ? '–' + profile.rooms_max : '') + ' amb.' : null,
    profile.budget_max ? fmtMoney(profile.budget_max, profile.currency) : null,
    profile.pets === true ? 'con mascota' : null
  ].filter(Boolean).join(' · ') || 'Sin búsqueda estructurada';

  content.innerHTML =
    '<p class="eyebrow">Conversación #' + data.id + '</p>' +
    '<h2>' + esc(contact.name || contact.phone || 'Contacto') + '</h2>' +
    '<p class="muted">' + esc(search) + '</p>' +
    '<div class="section-card">' +
      '<div class="section-head"><h3>Estado comercial</h3></div>' +
      '<select id="stage-select">' +
        state.stages.map(function (stage) {
          const selected = data.stage && data.stage.slug === stage.slug ? ' selected' : '';
          return '<option value="' + esc(stage.slug) + '"' + selected + '>' + esc(stage.name) + '</option>';
        }).join('') +
      '</select>' +
    '</div>' +
    '<div class="section-card">' +
      '<div class="section-head"><h3>Resumen</h3><button class="small-btn" id="summary-btn">Generar con GPT</button></div>' +
      '<div id="summary-box" class="summary-box">' + esc(data.summary || 'Todavía no se generó un resumen.') + '</div>' +
    '</div>' +
    '<div class="section-card">' +
      '<div class="section-head"><h3>Categorías detectadas</h3></div>' +
      ((data.categories || []).map(function (c) { return '<span class="pill">' + esc(c.name) + '</span>'; }).join('') || '<span class="muted">Sin categorías</span>') +
    '</div>' +
    '<div class="section-card">' +
      '<div class="section-head"><h3>Conversación</h3></div>' +
      '<div class="chat">' +
        (data.messages || []).map(function (m) {
          return '<div class="bubble ' + esc(m.direction) + '">' + esc(m.text || '') +
            '<span class="bubble-time">' + fmtDate(m.created_at) + '</span></div>';
        }).join('') +
      '</div>' +
    '</div>' +
    '<div class="section-card">' +
      '<div class="section-head"><h3>Notas internas</h3></div>' +
      '<textarea id="owner-notes" placeholder="Seguimiento, observaciones…">' + esc(data.owner_notes || '') + '</textarea>' +
      '<div style="margin-top:8px"><button class="small-btn" id="save-notes">Guardar notas</button></div>' +
    '</div>' +
    '<div class="grid-2">' +
      '<div class="section-card"><h3>Intereses</h3>' +
        ((data.interests || []).map(function (x) {
          return '<p><strong>' + esc(x.property.code) + '</strong><br><span class="muted tiny">' + esc(x.property.address) + '</span></p>';
        }).join('') || '<p class="muted tiny">Sin intereses registrados.</p>') +
      '</div>' +
      '<div class="section-card"><h3>Visitas</h3>' +
        ((data.visits || []).map(function (x) {
          return '<p><strong>' + esc(x.property.code) + '</strong> · ' + esc(x.status) + '<br><span class="muted tiny">' + esc(x.visit_date || '') + '</span></p>';
        }).join('') || '<p class="muted tiny">Sin visitas registradas.</p>') +
      '</div>' +
    '</div>' +
    '<div class="section-card"><h3>Eventos</h3><div class="timeline">' +
      ((data.events || []).map(function (e) {
        return '<div class="timeline-item"><strong>' + esc(e.event_type) + '</strong><br><span class="muted">' + fmtDate(e.created_at) + '</span></div>';
      }).join('') || '<span class="muted tiny">Sin eventos todavía.</span>') +
    '</div></div>';

  document.getElementById('stage-select').addEventListener('change', async function (event) {
    await api('/api/management/conversations/' + id + '/stage', {
      method: 'PATCH',
      body: JSON.stringify({ stage_slug: event.target.value })
    });
    toast('Estado actualizado');
    loadConversations();
  });
  document.getElementById('summary-btn').addEventListener('click', async function () {
    const button = this;
    button.disabled = true;
    button.textContent = 'Generando…';
    try {
      const result = await api('/api/management/conversations/' + id + '/summary', { method: 'POST' });
      document.getElementById('summary-box').textContent = result.summary;
      toast('Resumen actualizado');
    } finally {
      button.disabled = false;
      button.textContent = 'Generar con GPT';
    }
  });
  document.getElementById('save-notes').addEventListener('click', async function () {
    await api('/api/management/conversations/' + id + '/notes', {
      method: 'PATCH',
      body: JSON.stringify({ owner_notes: document.getElementById('owner-notes').value })
    });
    toast('Notas guardadas');
  });
}

async function loadProperties() {
  const view = document.getElementById('view-properties');
  const rows = await api('/api/properties');
  view.innerHTML =
    '<div class="section-card">' +
      '<div class="section-head"><h2>Stock</h2><span class="muted tiny">' + rows.length + ' propiedades</span></div>' +
      '<table><thead><tr><th>Código</th><th>Operación</th><th>Ubicación</th><th>Amb.</th><th>Precio</th><th>Estado</th></tr></thead><tbody>' +
        rows.map(function (p) {
          return '<tr><td><strong>' + esc(p.code) + '</strong></td><td>' + esc(p.operation) + '</td>' +
            '<td>' + esc(p.neighborhood) + '<br><span class="muted tiny">' + esc(p.address) + '</span></td>' +
            '<td>' + esc(p.rooms) + '</td><td>' + esc(fmtMoney(p.price, p.currency)) + '</td>' +
            '<td><span class="pill ' + (p.available ? 'green' : 'danger') + '">' + (p.available ? 'Disponible' : 'No disponible') + '</span> <button class="small-btn" data-toggle-property="' + p.id + '" data-next="' + (!p.available) + '">' + (p.available ? 'Pausar' : 'Activar') + '</button></td></tr>';
        }).join('') +
      '</tbody></table>' +
    '</div>' +
    '<div class="section-card">' +
      '<div class="section-head"><h2>Cargar propiedad</h2><span class="muted tiny">Fuente demo/manual</span></div>' +
      '<form id="property-form" class="form-grid">' +
        field('Código', 'code', 'MM-016') +
        selectField('Operación', 'operation', [['alquiler','Alquiler'],['venta','Venta']]) +
        field('Barrio', 'neighborhood', 'Palermo') +
        field('Dirección', 'address', 'Soler 4500') +
        numberField('Ambientes', 'rooms', '2') +
        numberField('Precio', 'price', '800000') +
        selectField('Moneda', 'currency', [['ARS','ARS'],['USD','USD']]) +
        numberField('Expensas', 'expenses', '120000') +
        '<label>Mascotas<select name="pets_allowed"><option value="">Sin dato</option><option value="true">Sí</option><option value="false">No</option></select></label>' +
        '<label class="full">Descripción<textarea name="description" placeholder="Descripción breve"></textarea></label>' +
        '<div class="full"><button class="primary" type="submit">Agregar propiedad</button></div>' +
      '</form>' +
    '</div>';
  document.querySelectorAll('[data-toggle-property]').forEach(function (button) {\n    button.addEventListener('click', async function () {\n      await api('/api/properties/' + this.dataset.toggleProperty, {\n        method: 'PATCH',\n        body: JSON.stringify({ available: this.dataset.next === 'true' })\n      });\n      toast('Disponibilidad actualizada');\n      loadProperties();\n    });\n  });\n  document.getElementById('property-form').addEventListener('submit', async function (event) {
    event.preventDefault();
    const form = new FormData(event.target);
    const pet = form.get('pets_allowed');
    const payload = {
      code: form.get('code'),
      operation: form.get('operation'),
      neighborhood: form.get('neighborhood'),
      address: form.get('address'),
      rooms: Number(form.get('rooms')),
      price: Number(form.get('price')),
      currency: form.get('currency'),
      expenses: form.get('expenses') ? Number(form.get('expenses')) : null,
      pets_allowed: pet === '' ? null : pet === 'true',
      available: true,
      description: form.get('description') || null
    };
    await api('/api/properties', { method: 'POST', body: JSON.stringify(payload) });
    toast('Propiedad agregada');
    loadProperties();
  });
}

function field(label, name, placeholder) {
  return '<label>' + esc(label) + '<input name="' + esc(name) + '" placeholder="' + esc(placeholder || '') + '" required></label>';
}
function numberField(label, name, placeholder) {
  return '<label>' + esc(label) + '<input type="number" name="' + esc(name) + '" placeholder="' + esc(placeholder || '') + '" required></label>';
}
function selectField(label, name, options) {
  return '<label>' + esc(label) + '<select name="' + esc(name) + '">' +
    options.map(function (x) { return '<option value="' + esc(x[0]) + '">' + esc(x[1]) + '</option>'; }).join('') +
    '</select></label>';
}

async function loadCategories() {
  const view = document.getElementById('view-categories');
  const rows = await api('/api/management/categories');
  state.categories = rows;
  view.innerHTML =
    '<div class="section-card">' +
      '<div class="section-head"><div><h2>Taxonomía de consultas</h2><p class="muted tiny">Estas categorías alimentan la clasificación automática de GPT. La lógica y los prompts siguen configurados por Micromega.</p></div></div>' +
      '<div id="category-list">' +
        rows.map(function (c) {
          return '<div class="category-row" data-category-id="' + c.id + '">' +
            '<div><strong>' + esc(c.name) + '</strong><br><span class="muted tiny">' + esc(c.slug) + '</span></div>' +
            '<div class="muted tiny">' + esc(c.description || '') + '</div>' +
            '<label class="switch"><input type="checkbox" data-category-active ' + (c.active ? 'checked' : '') + '> activa</label>' +
            '<button class="small-btn" data-edit-category>Editar</button>' +
          '</div>';
        }).join('') +
      '</div>' +
    '</div>' +
    '<div class="section-card">' +
      '<div class="section-head"><h2>Nueva categoría</h2></div>' +
      '<form id="category-form" class="form-grid">' +
        field('Nombre', 'name', 'Apto profesional') +
        '<label class="full">Descripción<textarea name="description" placeholder="Qué tipo de consulta incluye"></textarea></label>' +
        '<label class="full">Ejemplos<textarea name="examples" placeholder="Un ejemplo por línea"></textarea></label>' +
        '<label class="full">Pista para GPT<textarea name="prompt_hint" placeholder="Criterio de clasificación"></textarea></label>' +
        '<div class="full"><button class="primary" type="submit">Crear categoría</button></div>' +
      '</form>' +
    '</div>';

  document.querySelectorAll('[data-category-active]').forEach(function (checkbox) {
    checkbox.addEventListener('change', async function () {
      const id = this.closest('[data-category-id]').dataset.categoryId;
      await api('/api/management/categories/' + id, {
        method: 'PATCH',
        body: JSON.stringify({ active: this.checked })
      });
      toast('Categoría actualizada');
    });
  });
  document.querySelectorAll('[data-edit-category]').forEach(function (button) {
    button.addEventListener('click', function () {
      const id = Number(this.closest('[data-category-id]').dataset.categoryId);
      editCategory(id);
    });
  });
  document.getElementById('category-form').addEventListener('submit', async function (event) {
    event.preventDefault();
    const form = new FormData(event.target);
    await api('/api/management/categories', {
      method: 'POST',
      body: JSON.stringify({
        name: form.get('name'),
        description: form.get('description') || null,
        examples: String(form.get('examples') || '').split('\n').map(function (x) { return x.trim(); }).filter(Boolean),
        prompt_hint: form.get('prompt_hint') || null,
        active: true,
        display_order: state.categories.length * 10 + 10
      })
    });
    toast('Categoría creada');
    loadCategories();
  });
}

function editCategory(id) {
  const category = state.categories.find(function (c) { return c.id === id; });
  if (!category) return;
  const name = prompt('Nombre de la categoría', category.name);
  if (name == null || !name.trim()) return;
  const description = prompt('Descripción', category.description || '');
  api('/api/management/categories/' + id, {
    method: 'PATCH',
    body: JSON.stringify({ name: name.trim(), description: description })
  }).then(function () {
    toast('Categoría guardada');
    loadCategories();
  }).catch(function (err) { toast(err.message); });
}

async function loadVisits() {
  const view = document.getElementById('view-visits');
  const rows = await api('/api/management/visits');
  view.innerHTML =
    '<div class="section-card">' +
      '<div class="section-head"><h2>Visitas</h2><span class="muted tiny">' + rows.length + ' registros</span></div>' +
      (rows.length ? '<table><thead><tr><th>Contacto</th><th>Propiedad</th><th>Fecha</th><th>Estado</th><th></th></tr></thead><tbody>' +
        rows.map(function (v) {
          return '<tr data-visit-id="' + v.id + '">' +
            '<td>' + esc(v.contact.name || v.contact.phone) + '</td>' +
            '<td><strong>' + esc(v.property.code) + '</strong><br><span class="muted tiny">' + esc(v.property.address) + '</span></td>' +
            '<td><input type="date" data-visit-date value="' + esc(v.visit_date || '') + '"></td>' +
            '<td><select data-visit-status>' +
              ['requested','proposed','scheduled','completed','cancelled'].map(function (s) {
                return '<option value="' + s + '"' + (v.status === s ? ' selected' : '') + '>' + s + '</option>';
              }).join('') +
            '</select></td>' +
            '<td><button class="small-btn" data-save-visit>Guardar</button></td>' +
          '</tr>';
        }).join('') +
      '</tbody></table>' : '<div class="empty">Todavía no hay pedidos de visita.</div>') +
    '</div>';
  document.querySelectorAll('[data-save-visit]').forEach(function (button) {
    button.addEventListener('click', async function () {
      const row = this.closest('[data-visit-id]');
      await api('/api/management/visits/' + row.dataset.visitId, {
        method: 'PATCH',
        body: JSON.stringify({
          status: row.querySelector('[data-visit-status]').value,
          visit_date: row.querySelector('[data-visit-date]').value || null,
          notes: null
        })
      });
      toast('Visita actualizada');
      loadVisits();
    });
  });
}

async function refreshCurrent() {
  try {
    if (state.view === 'dashboard') await loadDashboard();
    if (state.view === 'conversations') await loadConversations();
    if (state.view === 'properties') await loadProperties();
    if (state.view === 'categories') await loadCategories();
    if (state.view === 'visits') await loadVisits();
  } catch (err) {
    const view = document.getElementById('view-' + state.view);
    view.innerHTML = '<div class="section-card"><strong>No se pudo cargar.</strong><p class="muted">' + esc(err.message) + '</p></div>';
  }
}

document.querySelectorAll('.nav-item').forEach(function (button) {
  button.addEventListener('click', function () { setView(button.dataset.view); });
});
document.getElementById('refresh-btn').addEventListener('click', refreshCurrent);
document.querySelectorAll('[data-close-drawer]').forEach(function (el) {
  el.addEventListener('click', function () { document.getElementById('drawer').classList.remove('open'); });
});

refreshCurrent();
