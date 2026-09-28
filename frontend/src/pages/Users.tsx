// Users & Roles (spec #34): create users with roles, per-user overrides, role permission editor.
import React, { useEffect, useState } from 'react';
import { api, type UserInfo } from '../api/client';
import { useStore } from '../store';
import { Modal, Field } from '../components/ui';

export default function Users() {
  const st = useStore();
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [roles, setRoles] = useState<any[]>([]);
  const [perms, setPerms] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);
  const [editRoles, setEditRoles] = useState(false);
  const load = () => {
    api.get<UserInfo[]>('/api/users').then(setUsers).catch(() => {});
    api.get<any[]>('/api/roles').then(setRoles).catch(() => {});
    api.get<string[]>('/api/permissions').then(setPerms).catch(() => {});
  };
  useEffect(() => { load(); }, []); // eslint-disable-line
  const toggleUser = async (u: UserInfo) => {
    try { await api.put(`/api/users/${u.id}`, { is_active: !u.is_active }); st.toast(u.is_active ? 'User deactivated' : 'User reactivated', 'ok'); load(); }
    catch (e: any) { st.toast(e.message, 'bad'); }
  };
  return <div>
    <div className="row spread" style={{ marginBottom: 12 }}>
      <h2 style={{ margin: 0 }}>Users & Roles</h2>
      <div className="row">
        <button onClick={() => setEditRoles(true)}>Role permissions</button>
        <button className="primary" onClick={() => setCreating(true)}>+ New user</button>
      </div>
    </div>
    <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
      <table><thead><tr><th>Username</th><th>Name</th><th>Role</th><th>Max discount</th><th>Status</th><th></th></tr></thead>
        <tbody>{users.map(u => (
          <tr key={u.id}><td>{u.username}</td><td>{u.full_name || '—'}</td><td><span className="badge info">{u.role}</span></td>
            <td>{u.max_discount_percent != null ? u.max_discount_percent + '%' : 'role default'}</td>
            <td>{u.is_active ? <span className="badge ok">active</span> : <span className="badge bad">inactive</span>}</td>
            <td><button className={u.is_active ? 'danger' : 'primary'} onClick={() => toggleUser(u)}>{u.is_active ? 'Deactivate' : 'Reactivate'}</button></td></tr>))}</tbody></table>
    </div>
    <div className="card" style={{ marginTop: 12 }}>
      <h3>Roles</h3>
      {roles.map(r => <div key={r.id} className="row" style={{ marginBottom: 6 }}>
        <b style={{ width: 140 }}>{r.name}</b>
        <span className="muted" style={{ fontSize: 12 }}>{(r.permissions || []).join(', ')}</span>
      </div>)}
    </div>
    {creating && <NewUser roles={roles} onClose={() => setCreating(false)} onDone={() => { setCreating(false); load(); }} />}
    {editRoles && <RoleEditor roles={roles} perms={perms} onClose={() => setEditRoles(false)} onDone={() => { setEditRoles(false); load(); }} />}
  </div>;
}

function NewUser({ roles, onClose, onDone }: { roles: any[]; onClose: () => void; onDone: () => void }) {
  const st = useStore();
  const [f, setF] = useState({ username: '', full_name: '', password: '', role_id: roles[1]?.id || roles[0]?.id, max_discount_percent: '' });
  const submit = async () => {
    try {
      await api.post('/api/users', { username: f.username, full_name: f.full_name, password: f.password, role_id: Number(f.role_id), max_discount_percent: f.max_discount_percent === '' ? null : Number(f.max_discount_percent) });
      st.toast('User created', 'ok'); onDone();
    } catch (e: any) { st.toast(e.message, 'bad'); }
  };
  return <Modal title="New staff user" onClose={onClose} width={400}>
    <Field label="Username *"><input autoFocus value={f.username} onChange={e => setF(p => ({ ...p, username: e.target.value }))} /></Field>
    <Field label="Full name"><input value={f.full_name} onChange={e => setF(p => ({ ...p, full_name: e.target.value }))} /></Field>
    <Field label="Password *"><input type="password" value={f.password} onChange={e => setF(p => ({ ...p, password: e.target.value }))} /></Field>
    <Field label="Role"><select value={f.role_id} onChange={e => setF(p => ({ ...p, role_id: Number(e.target.value) }))}>
      {roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}</select></Field>
    <Field label="Max discount % override (optional)"><input type="number" value={f.max_discount_percent} onChange={e => setF(p => ({ ...p, max_discount_percent: e.target.value }))} /></Field>
    <div className="row" style={{ justifyContent: 'flex-end' }}>
      <button onClick={onClose}>Cancel</button>
      <button className="primary" disabled={!f.username || f.password.length < 4} onClick={submit}>Create user</button>
    </div>
  </Modal>;
}

function RoleEditor({ roles, perms, onClose, onDone }: { roles: any[]; perms: string[]; onClose: () => void; onDone: () => void }) {
  const st = useStore();
  const [sel, setSel] = useState(roles.find(r => r.name !== 'Owner') || roles[0]);
  const [checked, setChecked] = useState<Set<string>>(new Set(sel?.permissions || []));
  if (!sel) return null;
  const save = async () => {
    try { await api.put(`/api/roles/${sel.id}/permissions`, { permissions: [...checked] }); st.toast('Role permissions updated', 'ok'); onDone(); }
    catch (e: any) { st.toast(e.message, 'bad'); }
  };
  return <Modal title="Role permissions" onClose={onClose} width={560}>
    <Field label="Role"><select value={sel.id} onChange={e => { const r = roles.find(x => x.id === Number(e.target.value))!; setSel(r); setChecked(new Set(r.permissions || [])); }}>
      {roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}</select></Field>
    <div style={{ maxHeight: 320, overflowY: 'auto', columns: 2 }}>
      {perms.map(p => <label key={p} style={{ display: 'block', fontSize: 13 }}>
        <input type="checkbox" checked={checked.has(p)} onChange={e => { const n = new Set(checked); e.target.checked ? n.add(p) : n.delete(p); setChecked(n); }} /> {p}
      </label>)}
    </div>
    <p className="muted" style={{ fontSize: 12 }}>Owner always has every permission (spec #66). Changes apply at next login.</p>
    <div className="row" style={{ justifyContent: 'flex-end' }}>
      <button onClick={onClose}>Cancel</button>
      <button className="primary" onClick={save}>Save permissions</button>
    </div>
  </Modal>;
}
