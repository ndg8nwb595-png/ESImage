import { App, Button, Card, Checkbox, Form, Input, Modal, Select, Space, Table, Tabs, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useState } from 'react'

import { useAuthStore } from '@/shared/store/authStore'
import { formatDateTime } from '@/shared/utils/time'
import * as api from '../accounts/api'
import type { AdminUser, RoleItem, RolesResponse } from '../accounts/api'

const ROLE_OPTIONS = [
  { value: 'user', label: '普通用户' },
  { value: 'admin', label: '管理员' },
  { value: 'super_admin', label: '超管' },
]

const STATUS_COLOR: Record<string, string> = {
  active: 'green',
  disabled: 'orange',
  deleted: 'red',
}
const STATUS_LABEL: Record<string, string> = { active: '正常', disabled: '禁用', deleted: '已删除' }

interface UserFormValues {
  username?: string
  display_name: string
  password?: string
  roles: string[]
  status: string
}

function UsersTab() {
  const { message, modal } = App.useApp()
  const currentRoles = useAuthStore((s) => s.roles)
  const isSuper = currentRoles.includes('super_admin')

  const [data, setData] = useState<api.AdminUserListResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [filters, setFilters] = useState({ keyword: '', role: '', status: 'all' })
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState<AdminUser | null>(null)
  const [creating, setCreating] = useState(false)
  const [resetting, setResetting] = useState<AdminUser | null>(null)
  const [form] = Form.useForm<UserFormValues>()
  const [pwdForm] = Form.useForm<{ new_password: string }>()

  const load = useCallback(
    async (p = 1) => {
      setLoading(true)
      try {
        setData(await api.listUsers({ ...filters, page: p, page_size: 20 }))
        setPage(p)
      } catch (err) {
        message.error(err instanceof Error ? err.message : '加载失败')
      } finally {
        setLoading(false)
      }
    },
    [filters, message],
  )

  useEffect(() => {
    void load(1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters])

  const roleOptions = isSuper ? ROLE_OPTIONS : ROLE_OPTIONS.filter((r) => r.value !== 'super_admin')

  const openCreate = () => {
    setCreating(true)
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ roles: ['user'], status: 'active' })
  }

  const openEdit = (user: AdminUser) => {
    setCreating(false)
    setEditing(user)
    form.resetFields()
    form.setFieldsValue({
      display_name: user.display_name,
      roles: user.roles.map((r) => r.code),
      status: user.status,
    })
  }

  const submitForm = async () => {
    const values = await form.validateFields()
    try {
      if (creating) {
        await api.createUser({
          username: values.username!,
          display_name: values.display_name,
          password: values.password!,
          roles: values.roles,
          status: values.status,
        })
        message.success('账号已创建')
      } else if (editing) {
        await api.updateUser(editing.user_id, {
          display_name: values.display_name,
          roles: values.roles,
          status: values.status,
        })
        message.success('账号已更新')
      }
      setCreating(false)
      setEditing(null)
      void load(page)
    } catch (err) {
      if (err instanceof Error) message.error(err.message)
    }
  }

  const submitPassword = async () => {
    const values = await pwdForm.validateFields()
    try {
      await api.resetPassword(resetting!.user_id, values.new_password)
      message.success('密码已重置')
      setResetting(null)
    } catch (err) {
      if (err instanceof Error) message.error(err.message)
    }
  }

  const toggleStatus = async (user: AdminUser) => {
    try {
      if (user.status === 'active') {
        modal.confirm({
          title: '禁用账号',
          content: `确定禁用「${user.username}」吗？禁用后该账号无法登录。`,
          onOk: async () => {
            await api.disableUser(user.user_id)
            message.success('已禁用')
            void load(page)
          },
        })
      } else if (user.status === 'disabled') {
        await api.enableUser(user.user_id)
        message.success('已启用')
        void load(page)
      }
    } catch (err) {
      if (err instanceof Error) message.error(err.message)
    }
  }

  const toggleDelete = async (user: AdminUser) => {
    try {
      if (user.status === 'deleted') {
        await api.restoreUser(user.user_id)
        message.success('已恢复')
        void load(page)
      } else {
        modal.confirm({
          title: '删除账号',
          content: `确定删除「${user.username}」吗？删除后无法登录，历史数据保留，可恢复。`,
          onOk: async () => {
            await api.deleteUser(user.user_id)
            message.success('已删除')
            void load(page)
          },
        })
      }
    } catch (err) {
      if (err instanceof Error) message.error(err.message)
    }
  }

  const columns: ColumnsType<AdminUser> = [
    { title: '用户名', dataIndex: 'username' },
    { title: '显示名', dataIndex: 'display_name' },
    {
      title: '角色',
      dataIndex: 'roles',
      render: (roles: api.RoleRef[]) =>
        roles.map((r) => <Tag key={r.code}>{r.name}</Tag>),
    },
    {
      title: '状态',
      dataIndex: 'status',
      render: (s: string) => <Tag color={STATUS_COLOR[s]}>{STATUS_LABEL[s]}</Tag>,
    },
    {
      title: '成功图/会话/Token',
      key: 'stats',
      render: (_, u) => `${u.stats.image_count}/${u.stats.session_count}/${u.stats.token_total}`,
    },
    { title: '最后登录', dataIndex: 'last_login_at', render: (v) => formatDateTime(v) || '—' },
    { title: '创建时间', dataIndex: 'created_at', render: (v) => formatDateTime(v) },
    {
      title: '操作',
      key: 'actions',
      width: 260,
      render: (_, u) => (
        <Space size="small">
          <Button size="small" onClick={() => openEdit(u)}>
            编辑
          </Button>
          <Button size="small" onClick={() => { setResetting(u); pwdForm.resetFields() }}>
            重置密码
          </Button>
          {u.status !== 'deleted' && (
            <Button size="small" onClick={() => void toggleStatus(u)}>
              {u.status === 'active' ? '禁用' : '启用'}
            </Button>
          )}
          <Button size="small" danger onClick={() => void toggleDelete(u)}>
            {u.status === 'deleted' ? '恢复' : '删除'}
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <Input.Search
          placeholder="用户名/显示名"
          allowClear
          style={{ width: 200 }}
          onSearch={(v) => setFilters((f) => ({ ...f, keyword: v }))}
        />
        <Select
          placeholder="角色"
          allowClear
          style={{ width: 120 }}
          value={filters.role || undefined}
          options={ROLE_OPTIONS}
          onChange={(v) => setFilters((f) => ({ ...f, role: v ?? '' }))}
        />
        <Select
          value={filters.status}
          style={{ width: 120 }}
          options={[
            { value: 'all', label: '全部状态' },
            { value: 'active', label: '正常' },
            { value: 'disabled', label: '禁用' },
            { value: 'deleted', label: '已删除' },
          ]}
          onChange={(v) => setFilters((f) => ({ ...f, status: v }))}
        />
        <Button type="primary" onClick={openCreate}>
          新建账号
        </Button>
      </Space>

      <Table
        rowKey="user_id"
        columns={columns}
        dataSource={data?.items ?? []}
        loading={loading}
        pagination={{
          current: page,
          pageSize: 20,
          total: data?.total ?? 0,
          onChange: (p) => void load(p),
          showSizeChanger: false,
        }}
      />

      <Modal
        title={creating ? '新建账号' : '编辑账号'}
        open={creating || editing !== null}
        onOk={() => void submitForm()}
        onCancel={() => { setCreating(false); setEditing(null) }}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            label="用户名"
            name="username"
            rules={creating ? [{ required: true, pattern: /^[A-Za-z0-9_]{4,20}$/, message: '4~20 位字母、数字或下划线' }] : []}
          >
            <Input disabled={!creating} />
          </Form.Item>
          <Form.Item label="显示名" name="display_name" rules={[{ required: true, message: '请输入显示名' }]}>
            <Input maxLength={30} />
          </Form.Item>
          {creating && (
            <Form.Item
              label="初始密码"
              name="password"
              rules={[{ required: true, min: 8, max: 32, message: '8~32 位' }]}
            >
              <Input.Password />
            </Form.Item>
          )}
          <Form.Item label="角色" name="roles" rules={[{ required: true, message: '请选择角色' }]}>
            <Select mode="multiple" options={roleOptions} />
          </Form.Item>
          <Form.Item label="状态" name="status">
            <Select
              options={[
                { value: 'active', label: '正常' },
                { value: 'disabled', label: '禁用' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`重置密码（${resetting?.username ?? ''}）`}
        open={resetting !== null}
        onOk={() => void submitPassword()}
        onCancel={() => setResetting(null)}
        destroyOnClose
      >
        <Form form={pwdForm} layout="vertical">
          <Form.Item
            label="新密码"
            name="new_password"
            rules={[{ required: true, min: 8, max: 32, message: '8~32 位' }]}
          >
            <Input.Password />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

function RolesTab() {
  const { message } = App.useApp()
  const [data, setData] = useState<RolesResponse | null>(null)
  const [selected, setSelected] = useState<Record<string, string[]>>({})
  const [saving, setSaving] = useState<string | null>(null)

  useEffect(() => {
    api
      .listRoles()
      .then((res) => {
        setData(res)
        setSelected(Object.fromEntries(res.roles.map((r) => [r.code, r.permissions])))
      })
      .catch((err) => message.error(err instanceof Error ? err.message : '加载失败'))
  }, [message])

  const save = async (role: RoleItem) => {
    setSaving(role.code)
    try {
      await api.updateRolePermissions(role.code, selected[role.code] ?? [])
      message.success('已保存')
    } catch (err) {
      if (err instanceof Error) message.error(err.message)
    } finally {
      setSaving(null)
    }
  }

  if (!data) return null

  return (
    <div>
      {data.roles.map((role) => (
        <Card
          key={role.code}
          title={role.name}
          style={{ marginBottom: 16 }}
          extra={
            role.editable ? (
              <Button type="primary" size="small" loading={saving === role.code} onClick={() => void save(role)}>
                保存
              </Button>
            ) : null
          }
        >
          <Checkbox.Group
            value={selected[role.code] ?? []}
            disabled={!role.editable}
            onChange={(v) => setSelected((s) => ({ ...s, [role.code]: v as string[] }))}
          >
            <Space direction="vertical">
              {data.permissions.map((p) => (
                <Checkbox key={p.code} value={p.code}>
                  {p.name} <span style={{ color: '#9ca3af' }}>({p.code})</span>
                </Checkbox>
              ))}
            </Space>
          </Checkbox.Group>
        </Card>
      ))}
    </div>
  )
}

export default function AccountsPage() {
  const currentRoles = useAuthStore((s) => s.roles)
  const isSuper = currentRoles.includes('super_admin')

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 24 }}>
      <Tabs
        items={[
          { key: 'users', label: '用户管理', children: <UsersTab /> },
          ...(isSuper ? [{ key: 'roles', label: '角色管理', children: <RolesTab /> }] : []),
        ]}
      />
    </div>
  )
}
