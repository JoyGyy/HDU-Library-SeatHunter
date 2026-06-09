import React, { useState, useEffect } from 'react'
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  FlatList,
  Alert,
  ActivityIndicator,
} from 'react-native'
import { getCurrentBookings, checkIn } from '../api/client'

interface Booking {
  booking_id: string
  room_name: string
  seat_num: string
  begin_time: string | null
  end_time: string | null
  status: string
}

const statusMap: Record<string, string> = {
  '0': '待签到',
  '1': '已签到',
  '2': '已结束',
}

export default function CheckInScreen() {
  const [bookings, setBookings] = useState<Booking[]>([])
  const [loading, setLoading] = useState(false)
  const [checkingId, setCheckingId] = useState<string | null>(null)

  useEffect(() => {
    loadBookings()
  }, [])

  const loadBookings = async () => {
    setLoading(true)
    try {
      const resp = await getCurrentBookings()
      setBookings(resp.data.bookings)
    } catch (e) {
      Alert.alert('错误', '获取预约失败')
    }
    setLoading(false)
  }

  const handleCheckIn = async (bookingId: string) => {
    setCheckingId(bookingId)
    try {
      const resp = await checkIn(bookingId)
      if (resp.data.success) {
        Alert.alert('成功', '签到成功！')
        loadBookings()
      } else {
        Alert.alert('失败', resp.data.message)
      }
    } catch (e) {
      Alert.alert('错误', '签到请求失败')
    }
    setCheckingId(null)
  }

  const renderItem = ({ item }: { item: Booking }) => (
    <View style={styles.card}>
      <View style={styles.cardHeader}>
        <Text style={styles.roomName}>{item.room_name}</Text>
        <Text
          style={[
            styles.status,
            item.status === '0' ? styles.statusPending : styles.statusDone,
          ]}
        >
          {statusMap[item.status] || item.status}
        </Text>
      </View>
      <Text style={styles.seatInfo}>座位: {item.seat_num}</Text>
      <Text style={styles.timeInfo}>
        时间: {item.begin_time || '—'} ~ {item.end_time || '—'}
      </Text>
      {item.status === '0' && (
        <TouchableOpacity
          style={styles.checkinBtn}
          onPress={() => handleCheckIn(item.booking_id)}
          disabled={checkingId === item.booking_id}
        >
          {checkingId === item.booking_id ? (
            <ActivityIndicator color="#1e1e2e" />
          ) : (
            <Text style={styles.checkinBtnText}>签到</Text>
          )}
        </TouchableOpacity>
      )}
    </View>
  )

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>当前预约</Text>
        <TouchableOpacity onPress={loadBookings}>
          <Text style={styles.refreshBtn}>刷新</Text>
        </TouchableOpacity>
      </View>
      {loading ? (
        <ActivityIndicator
          size="large"
          color="#89b4fa"
          style={{ marginTop: 40 }}
        />
      ) : (
        <FlatList
          data={bookings}
          renderItem={renderItem}
          keyExtractor={item => item.booking_id}
          ListEmptyComponent={
            <Text style={styles.empty}>暂无预约</Text>
          }
          contentContainerStyle={{ paddingBottom: 20 }}
        />
      )}
    </View>
  )
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#1e1e2e',
    padding: 16,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  title: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#cdd6f4',
  },
  refreshBtn: {
    color: '#89b4fa',
    fontSize: 16,
  },
  card: {
    backgroundColor: '#313244',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  roomName: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#cdd6f4',
  },
  status: {
    fontSize: 14,
    fontWeight: 'bold',
  },
  statusPending: {
    color: '#f9e2af',
  },
  statusDone: {
    color: '#a6e3a1',
  },
  seatInfo: {
    fontSize: 14,
    color: '#a6adc8',
    marginBottom: 4,
  },
  timeInfo: {
    fontSize: 14,
    color: '#a6adc8',
    marginBottom: 12,
  },
  checkinBtn: {
    backgroundColor: '#a6e3a1',
    borderRadius: 8,
    padding: 12,
    alignItems: 'center',
  },
  checkinBtnText: {
    color: '#1e1e2e',
    fontSize: 16,
    fontWeight: 'bold',
  },
  empty: {
    color: '#a6adc8',
    textAlign: 'center',
    marginTop: 40,
    fontSize: 16,
  },
})
