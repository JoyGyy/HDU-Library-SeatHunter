import axios from 'axios'

const BASE_URL = 'http://192.168.1.100:8000'

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

export const setBaseURL = (url: string) => {
  api.defaults.baseURL = url
}

export const login = (studentId: string, password: string) =>
  api.post('/api/auth/login', { student_id: studentId, password })

export const getAuthStatus = () => api.get('/api/auth/status')

export const checkIn = (bookingId: string) =>
  api.post(`/api/checkin/${bookingId}`)

export const getCurrentBookings = () => api.get('/api/checkin/bookings')

export const getFriends = () => api.get('/api/friends')

export const addFriend = (studentId: string, password: string) =>
  api.post('/api/friends', { student_id: studentId, password })

export const deleteFriend = (studentId: string) =>
  api.delete(`/api/friends/${studentId}`)

export const testFriendLogin = (studentId: string) =>
  api.post(`/api/friends/${studentId}/test`)

export const getBookings = () => api.get('/api/bookings')

export default api
