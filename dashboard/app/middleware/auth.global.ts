export default defineNuxtRouteMiddleware((to) => {
  const { loggedIn } = useUserSession()

  if (to.path === '/login') return

  if (!loggedIn.value) {
    return navigateTo('/login')
  }
})
