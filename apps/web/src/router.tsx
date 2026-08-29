import { createRootRoute, createRoute, createRouter, Outlet } from '@tanstack/react-router'

const rootRoute = createRootRoute({ component: Outlet })

const landingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: () => null,
})

export const router = createRouter({
  routeTree: rootRoute.addChildren([landingRoute]),
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
