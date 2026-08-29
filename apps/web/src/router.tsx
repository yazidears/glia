import { createRootRoute, createRoute, createRouter, Outlet } from '@tanstack/react-router'
import { LandingScreen } from '@/screens/landing-screen'

const rootRoute = createRootRoute({ component: Outlet })

const landingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: LandingScreen,
})

export const router = createRouter({
  routeTree: rootRoute.addChildren([landingRoute]),
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
