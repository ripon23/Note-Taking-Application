import { productionApi } from './config.js'

const local = ['localhost', '127.0.0.1'].includes(location.hostname)
const apiBase = local ? `http://${location.hostname}:3000/api` : productionApi.replace(/\/$/, '') + '/api'
const $ = id => document.getElementById(id)
const sessionKey = 'secure-notes-token'
const titles = { notes: 'My notes', posts: 'Public posts', 'all-notes': 'All notes', users: 'Users', interests: 'Users by interest' }
let session
let registering = false
let view = 'notes'
let page = 1
let authorId = ''
let visitorPage = 1
let visitorAuthorId = ''
let revision = 0

function node(tag, value, attributes = {}) {
  const element = document.createElement(tag)
  if (value !== undefined) element.textContent = value
  for (const [key, attribute] of Object.entries(attributes)) element.setAttribute(key, attribute)
  return element
}

function status(message = '', error = false) {
  $('status').textContent = message
  $('status').hidden = !message
  $('status').dataset.error = error
}

async function api(path, method = 'GET', body, token = session?.token) {
  if (!local && !productionApi) throw new Error('The frontend needs its backend URL configured.')
  const headers = {}
  if (token) headers.Authorization = 'Bearer ' + token
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const response = await fetch(apiBase + path, { method, headers, body: JSON.stringify(body) })
  if (response.status === 204) return
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    if (response.status === 401 && session && session.token === token) signOut()
    const error = new Error(data.error || `Request failed (${response.status})`)
    error.status = response.status
    throw error
  }
  return data
}

function action(element, handler) {
  element.addEventListener(element.tagName === 'FORM' ? 'submit' : 'click', async event => {
    event.preventDefault()
    const button = event.submitter ?? (element.tagName === 'BUTTON' ? element : null)
    if (button?.disabled) return
    if (button) button.disabled = true
    status()
    try {
      await handler()
    } catch (error) {
      status(error.message, true)
    } finally {
      if (button) button.disabled = false
    }
  })
}

function data(form) {
  return Object.fromEntries(new FormData(form))
}

function interests(value) {
  return value.split(',').map(item => item.trim()).filter(Boolean)
}

function toggleAuth() {
  registering = !registering
  $('auth-title').textContent = $('auth-submit').textContent = registering ? 'Create account' : 'Sign in'
  $('auth-toggle').textContent = registering ? 'Back to sign in' : 'Create an account'
  for (const label of document.querySelectorAll('[data-register]')) {
    label.hidden = !registering
    label.querySelector('input').disabled = !registering
  }
  const form = $('auth-form')
  form.elements.name.required = registering
  form.elements.password.minLength = registering ? 12 : 1
  form.elements.password.autocomplete = registering ? 'new-password' : 'current-password'
}

function showSession() {
  $('auth').hidden = $('visitor').hidden = Boolean(session)
  $('workspace').hidden = $('identity').hidden = !session
  if (!session) return
  const { user } = session
  $('account').textContent = `${user.name} (${user.role})`
  $('own-id').textContent = 'Your author ID: ' + user._id
  for (const button of document.querySelectorAll('[data-admin]')) button.hidden = user.role !== 'admin'
}

function signOut() {
  session = undefined
  sessionStorage.removeItem(sessionKey)
  authorId = ''
  revision++
  $('items').replaceChildren()
  $('editor').replaceChildren()
  $('editor').onsubmit = null
  showSession()
}

action($('auth-toggle'), toggleAuth)
action($('logout'), signOut)
action($('auth-form'), async () => {
  const values = data($('auth-form'))
  if (registering) values.interests = interests(values.interests)
  session = await api('/auth/' + (registering ? 'register' : 'login'), 'POST', values)
  sessionStorage.setItem(sessionKey, session.token)
  $('auth-form').reset()
  showSession()
  await switchView('notes')
})

function field(label, name, value = '', attributes = {}) {
  const wrapper = node('label', label)
  const input = node(name === 'body' ? 'textarea' : 'input', undefined, { name, ...attributes })
  input.value = value
  wrapper.append(input)
  return wrapper
}

function configureEditor(item) {
  const form = $('editor')
  form.replaceChildren()
  form.onsubmit = null
  form.hidden = !['notes', 'posts', 'users'].includes(view)
  if (form.hidden) return
  const editingView = view
  const users = editingView === 'users'
  form.append(node('h3', item ? 'Edit ' + (users ? 'user' : 'note') :
    ({ notes: 'New note', posts: 'New post', users: 'Add user' })[editingView]))
  if (users) {
    form.append(
      field('Name', 'name', item?.name, { required: '', maxlength: 80 }),
      field('Email', 'email', item?.email, { required: '', type: 'email', maxlength: 254 }),
      field(item ? 'New password (optional)' : 'Password', 'password', '', { type: 'password', minlength: 12, maxlength: 128, autocomplete: 'new-password', ...(!item && { required: '' }) }),
      field('Interests, comma separated', 'interests', item?.interests.join(', ')),
    )
    const label = node('label', 'Role')
    const select = node('select', undefined, { name: 'role' })
    select.append(node('option', 'User', { value: 'user' }), node('option', 'Admin', { value: 'admin' }))
    select.value = item?.role ?? 'user'
    label.append(select)
    form.append(label)
  } else {
    form.append(field('Title', 'title', item?.title, { required: '', maxlength: 120 }),
      field('Body', 'body', item?.body, { maxlength: 10000 }))
  }

  const submit = node('button', item ? 'Save changes' : 'Create', { type: 'submit' })
  const controls = node('div', undefined, { class: 'actions' })
  controls.append(submit)
  if (item) {
    const cancel = node('button', 'Cancel', { type: 'button', class: 'secondary' })
    action(cancel, () => configureEditor())
    controls.append(cancel)
  }
  form.append(controls)
  form.onsubmit = async event => {
    event.preventDefault()
    if (submit.disabled) return
    submit.disabled = true
    status()
    try {
      const values = data(form)
      if (users) {
        values.interests = interests(values.interests)
        if (!values.password) delete values.password
        if (item?.role === values.role) delete values.role
        if (item?.email === values.email) delete values.email
      }
      const base = users ? '/admin/users' : '/' + editingView
      const saved = await api(item ? base + '/' + item._id : base, item ? 'PATCH' : 'POST', values)
      if (!session || view !== editingView) return
      if (users && item?._id === session.user._id) {
        session.user = saved
        showSession()
      }
      if (editingView === 'posts') {
        authorId = session.user._id
        $('lookup').elements.author.value = authorId
      }
      page = 1
      configureEditor()
      await load()
      status(item ? 'Changes saved.' : 'Created.')
    } catch (error) {
      status(error.message, true)
    } finally {
      submit.disabled = false
    }
  }
}

function contentCard(item, mode) {
  const article = node('article')
  if (mode === 'interests') {
    article.append(node('h3', item._id), node('small', `${item.count} member(s)`))
    const list = node('ul')
    for (const user of item.users ?? []) list.append(node('li', user.name))
    article.append(list)
  } else if (mode === 'users') {
    article.append(node('h3', item.name), node('p', `${item.email} · ${item.role}`),
      node('small', `ID: ${item._id} · Interests: ${item.interests.join(', ') || 'None'}`))
  } else {
    article.append(node('h3', item.title), node('p', item.body),
      node('small', mode === 'all-notes' ? 'Owner ID: ' + item.owner : new Date(item.createdAt).toLocaleString()))
  }
  if (mode !== 'notes' && mode !== 'users') return article
  const controls = node('div', undefined, { class: 'actions' })
  const edit = node('button', 'Edit', { class: 'secondary' })
  action(edit, () => {
    configureEditor(item)
    $('editor').querySelector('input').focus()
  })
  controls.append(edit)
  if (mode === 'notes' || item._id !== session.user._id) {
    const remove = node('button', 'Delete', { class: 'secondary' })
    action(remove, async () => {
      if (!confirm(`Delete this ${mode === 'notes' ? 'note' : 'account'}?`)) return
      await api((mode === 'notes' ? '/notes/' : '/admin/users/') + item._id, 'DELETE')
      if (!session || view !== mode) return
      configureEditor()
      await load()
      status('Deleted.')
    })
    controls.append(remove)
  }
  article.append(controls)
  return article
}

function renderList(result, mode, prefix = '') {
  const cards = result.items.map(item => contentCard(item, mode))
  $(prefix + 'items').replaceChildren(...(cards.length ? cards : [node('p', 'No results.')]))
  $(prefix + 'pagination').hidden = result.page === 1 && !result.hasNext
  $(prefix + 'page').textContent = 'Page ' + result.page
  $(prefix + 'previous').disabled = result.page <= 1
  $(prefix + 'next').disabled = !result.hasNext
}

async function load() {
  const ticket = ++revision
  const mode = view
  const path = ({
    notes: '/notes', posts: authorId && '/users/' + authorId + '/posts',
    'all-notes': '/admin/notes', users: '/admin/users', interests: '/admin/interests',
  })[mode]
  if (!path) return
  const result = await api(path + '?page=' + page)
  if (ticket !== revision) return
  if (!result.items.length && page > 1) {
    page--
    return load()
  }
  renderList(result, mode)
}

async function switchView(next) {
  view = next
  page = 1
  $('items').replaceChildren()
  $('pagination').hidden = true
  $('view-title').textContent = titles[view]
  $('lookup').hidden = view !== 'posts'
  $('lookup').elements.author.value = authorId
  for (const button of document.querySelectorAll('[data-view]')) {
    button.setAttribute('aria-current', button.dataset.view === view)
  }
  configureEditor()
  await load()
}

for (const button of document.querySelectorAll('[data-view]')) {
  action(button, () => switchView(button.dataset.view))
}
$('previous').addEventListener('click', () => movePage(-1))
$('next').addEventListener('click', () => movePage(1))
async function movePage(offset) {
  const previous = page
  page += offset
  status()
  try {
    await load()
  } catch (error) {
    page = previous
    status(error.message, true)
  }
}

action($('lookup'), async () => {
  authorId = data($('lookup')).author
  page = 1
  $('items').replaceChildren()
  $('pagination').hidden = true
  await load()
})

async function loadVisitorPosts() {
  const result = await api('/users/' + visitorAuthorId + '/posts?page=' + visitorPage)
  renderList(result, 'posts', 'visitor-')
}

action($('visitor-lookup'), async () => {
  visitorAuthorId = data($('visitor-lookup')).author
  visitorPage = 1
  $('visitor-items').replaceChildren()
  $('visitor-pagination').hidden = true
  await loadVisitorPosts()
})
for (const [id, offset] of [['visitor-previous', -1], ['visitor-next', 1]]) {
  $(id).addEventListener('click', async () => {
    const previous = visitorPage
    visitorPage += offset
    status()
    try {
      await loadVisitorPosts()
    } catch (error) {
      visitorPage = previous
      status(error.message, true)
    }
  })
}

async function restoreSession() {
  const token = sessionStorage.getItem(sessionKey)
  if (!token) {
    showSession()
    return
  }

  $('auth').hidden = true
  $('visitor').hidden = true
  try {
    const user = await api('/auth/me', 'GET', undefined, token)
    session = { token, user }
    showSession()
    await switchView('notes')
  } catch (error) {
    if (error.status === 401) signOut()
    showSession()
    status(error.message, true)
  }
}

restoreSession()
