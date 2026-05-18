/**
 * Chat global store — manages total unread count for sidebar badge & browser notification
 */
const useChatStore = defineStore('chat', {
  state: () => ({
    totalUnread: 0,
  }),
  actions: {
    setTotalUnread(count) {
      this.totalUnread = count
    },
    decrement(n) {
      this.totalUnread = Math.max(0, this.totalUnread - n)
    },
  },
})

export default useChatStore
