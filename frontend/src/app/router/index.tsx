import { Navigate, createBrowserRouter } from 'react-router-dom'

import AccountsPage from '@/modules/admin/pages/AccountsPage'
import AdminDashboardPage from '@/modules/admin/pages/DashboardPage'
import AgentConfigPage from '@/modules/admin/pages/AgentConfigPage'
import AssetsPage from '@/modules/admin/pages/AssetsPage'
import AuditLogsPage from '@/modules/admin/pages/AuditLogsPage'
import ChatPage from '@/modules/admin/pages/ChatPage'
import ContentPage from '@/modules/admin/pages/ContentPage'
import ForbiddenPage from '@/modules/errors/pages/ForbiddenPage'
import NotFoundPage from '@/modules/errors/pages/NotFoundPage'
import HistoryDetailPage from '@/modules/history/pages/HistoryDetailPage'
import HistoryPage from '@/modules/history/pages/HistoryPage'
import ProfilePage from '@/modules/profile/pages/ProfilePage'
import LoginPage from '@/modules/auth/pages/LoginPage'
import WorkspacePage from '@/modules/workspace/pages/WorkspacePage'
import AppLayout from '@/shared/layouts/AppLayout'
import { RequireAuth, RequirePermission } from './guard'

export const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/workspace" replace /> },
  { path: '/login', element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppLayout />,
        children: [
          {
            path: '/workspace',
            element: (
              <RequirePermission permission="user.workspace">
                <WorkspacePage />
              </RequirePermission>
            ),
          },
          {
            path: '/history',
            element: (
              <RequirePermission permission="user.history">
                <HistoryPage />
              </RequirePermission>
            ),
          },
          {
            path: '/history/:batchId',
            element: (
              <RequirePermission permission="user.history">
                <HistoryDetailPage />
              </RequirePermission>
            ),
          },
          {
            path: '/profile',
            element: (
              <RequirePermission permission="user.profile">
                <ProfilePage />
              </RequirePermission>
            ),
          },
          {
            path: '/admin/dashboard',
            element: (
              <RequirePermission permission="admin.dashboard.view">
                <AdminDashboardPage />
              </RequirePermission>
            ),
          },
          {
            path: '/admin/accounts',
            element: (
              <RequirePermission permission="admin.accounts.view">
                <AccountsPage />
              </RequirePermission>
            ),
          },
          {
            path: '/admin/content',
            element: (
              <RequirePermission permission="admin.content.view">
                <ContentPage />
              </RequirePermission>
            ),
          },
          {
            path: '/admin/chat',
            element: (
              <RequirePermission permission="admin.content.view">
                <ChatPage />
              </RequirePermission>
            ),
          },
          {
            path: '/admin/assets',
            element: (
              <RequirePermission permission="admin.assets.view">
                <AssetsPage />
              </RequirePermission>
            ),
          },
          {
            path: '/admin/agent-config',
            element: (
              <RequirePermission permission="admin.prompts.view">
                <AgentConfigPage />
              </RequirePermission>
            ),
          },
          {
            path: '/admin/audit-logs',
            element: (
              <RequirePermission permission="admin.audit.view">
                <AuditLogsPage />
              </RequirePermission>
            ),
          },
        ],
      },
    ],
  },
  { path: '/403', element: <ForbiddenPage /> },
  { path: '*', element: <NotFoundPage /> },
])
