export default defineNuxtRouteMiddleware((to) => {
  const { loggedIn } = useUserSession()

  if (to.path === '/login' || to.path === '/demo' || to.path === '/auth/forbidden') return

  if (!loggedIn.value) {
    return navigateTo('/login')
  }

  const { canAccess, landingPage } = useUserRole()
  if (!canAccess(to.path)) {
    return navigateTo(landingPage.value)
  }
})
