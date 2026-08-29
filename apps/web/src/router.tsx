import { createRootRoute, createRoute, createRouter, Outlet } from '@tanstack/react-router'
import { SessionScreen } from '@/screens/session-screen'

const rootRoute = createRootRoute({ component: Outlet })

const sessionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: SessionScreen,
})

export const router = createRouter({
  routeTree: rootRoute.addChildren([sessionRoute]),
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
